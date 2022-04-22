import sys
from collections import defaultdict
from typing import (
    TYPE_CHECKING,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypedDict,
    Union,
)
from uuid import UUID

from django.contrib.sites.models import Site
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.db.models.aggregates import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_stubs_ext import WithAnnotations

from ...channel.models import Channel
from ...product.models import ProductVariantChannelListing
from ...warehouse import WarehouseClickAndCollectOption
from ...warehouse.models import (
    ChannelWarehouse,
    PreorderReservation,
    Reservation,
    ShippingZone,
    Stock,
    Warehouse,
)
from ...warehouse.reservations import is_reservation_enabled
from ..core.dataloaders import DataLoader
from ..site.dataloaders import get_site_promise

if TYPE_CHECKING:
    # https://github.com/typeddjango/django-stubs/issues/719

    class WithAvailableQuantity(TypedDict):
        available_quantity: int

    StockWithAvailableQuantity = WithAnnotations[Stock, WithAvailableQuantity]
else:
    StockWithAvailableQuantity = Stock


CountryCode = Optional[str]
VariantIdCountryCodeChannelSlug = Tuple[int, CountryCode, str]


class AvailableQuantityByProductVariantIdCountryCodeAndChannelSlugLoader(
    DataLoader[VariantIdCountryCodeChannelSlug, int]
):
    """Calculates available variant quantity based on variant ID and country code.

    For each country code, for each shipping zone supporting that country,
    calculate the maximum available quantity, then return either that number
    or the maximum allowed checkout quantity, whichever is lower.
    """

    context_key = "available_quantity_by_productvariant_and_country"

    def batch_load(self, keys: Iterable[VariantIdCountryCodeChannelSlug]) -> List[int]:
        # Split the list of keys by country first. A typical query will only touch
        # a handful of unique countries but may access thousands of product variants,
        # so it's cheaper to execute one query per country.
        variants_by_country_and_channel: DefaultDict[
            Tuple[CountryCode, str], List[int]
        ] = defaultdict(list)
        for variant_id, country_code, channel_slug in keys:
            variants_by_country_and_channel[(country_code, channel_slug)].append(
                variant_id
            )

        # For each country code execute a single query for all product variants.
        quantity_by_variant_and_country: DefaultDict[
            VariantIdCountryCodeChannelSlug, int
        ] = defaultdict(int)

        site = None
        if variants_by_country_and_channel:
            site = get_site_promise(self.context).get()
            for key, variant_ids in variants_by_country_and_channel.items():
                country_code, channel_slug = key
                quantities = self.batch_load_quantities_by_country(
                    country_code, channel_slug, variant_ids, site
                )
                for variant_id, quantity in quantities:
                    quantity_by_variant_and_country[
                        (variant_id, country_code, channel_slug)
                    ] = max(0, quantity)

        return [quantity_by_variant_and_country[key] for key in keys]

    def batch_load_quantities_by_country(
        self,
        country_code: Optional[CountryCode],
        channel_slug: Optional[str],
        variant_ids: Iterable[int],
        site: Site,
    ) -> Iterable[Tuple[int, int]]:
        # get stocks only for warehouses assigned to the shipping zones
        # that are available in the given channel
        stocks = (
            Stock.objects.all()
            .using(self.database_connection_name)
            .filter(product_variant_id__in=variant_ids)
        )

        warehouse_shipping_zones = self.get_warehouse_shipping_zones(
            country_code, channel_slug
        )
        cc_warehouses = self.get_click_and_collect_warehouses(
            channel_slug, country_code
        )

        warehouse_shipping_zones_map = defaultdict(list)
        for warehouse_shipping_zone in warehouse_shipping_zones:
            warehouse_shipping_zones_map[warehouse_shipping_zone.warehouse_id].append(
                warehouse_shipping_zone.shippingzone_id
            )

        stocks = stocks.filter(
            Q(warehouse_id__in=warehouse_shipping_zones_map.keys())
            | Q(warehouse_id__in=cc_warehouses.values("id"))
        )

        stocks = stocks.annotate_available_quantity()

        stocks_reservations = self.prepare_stocks_reservations_map(variant_ids)

        # A single country code (or a missing country code) can return results from
        # multiple shipping zones. We want to prepare warehouse by shipping zone map
        # and quantity by warehouse map. To be able to calculate max quantity available
        # in any shipping zones combination without duplicating warehouse quantity.
        (
            warehouse_ids_by_shipping_zone_by_variant,
            variants_with_global_cc_warehouses,
            available_quantity_by_warehouse_id_and_variant_id,
        ) = self.prepare_warehouse_ids_by_shipping_zone_and_variant_map(
            stocks, stocks_reservations, warehouse_shipping_zones_map, cc_warehouses
        )

        quantity_map = self.prepare_quantity_map(
            country_code,
            warehouse_ids_by_shipping_zone_by_variant,
            variants_with_global_cc_warehouses,
            available_quantity_by_warehouse_id_and_variant_id,
        )

        # Return the quantities after capping them at the maximum quantity allowed in
        # checkout. This prevent users from tracking the store's precise stock levels.
        global_quantity_limit = site.settings.limit_quantity_per_checkout
        return [
            (
                variant_id,
                min(quantity_map[variant_id], global_quantity_limit or sys.maxsize),
            )
            for variant_id in variant_ids
        ]

    def get_warehouse_shipping_zones(self, country_code, channel_slug):
        """Get the WarehouseShippingZone instances for a given channel and country."""
        WarehouseShippingZone = Warehouse.shipping_zones.through
        warehouse_shipping_zones = WarehouseShippingZone.objects.using(
            self.database_connection_name
        ).all()
        if country_code or channel_slug:
            if country_code:
                shipping_zones = (
                    ShippingZone.objects.using(self.database_connection_name)
                    .filter(countries__contains=country_code)
                    .values("pk")
                )
                warehouse_shipping_zones = warehouse_shipping_zones.filter(
                    Exists(shipping_zones.filter(pk=OuterRef("shippingzone_id")))
                )
            if channel_slug:
                ShippingZoneChannel = Channel.shipping_zones.through  # type: ignore[attr-defined] # raw access to the through model # noqa: E501
                WarehouseChannel = Channel.warehouses.through  # type: ignore[attr-defined] # raw access to the through model # noqa: E501
                channels = (
                    Channel.objects.using(self.database_connection_name)
                    .filter(slug=channel_slug)
                    .values("pk")
                )
                shipping_zone_channels = (
                    ShippingZoneChannel.objects.using(self.database_connection_name)
                    .filter(Exists(channels.filter(pk=OuterRef("channel_id"))))
                    .values("shippingzone_id")
                )
                warehouse_channels = (
                    WarehouseChannel.objects.using(self.database_connection_name)
                    .filter(
                        Exists(channels.filter(pk=OuterRef("channel_id"))),
                    )
                    .values("warehouse_id")
                )
                warehouse_shipping_zones = warehouse_shipping_zones.filter(
                    Exists(
                        shipping_zone_channels.filter(
                            shippingzone_id=OuterRef("shippingzone_id")
                        )
                    ),
                    Exists(
                        warehouse_channels.filter(warehouse_id=OuterRef("warehouse_id"))
                    ),
                )
        return warehouse_shipping_zones

    def get_click_and_collect_warehouses(self, channel_slug, country_code):
        """Get the collection point warehouses for a given channel and country code."""
        warehouses = Warehouse.objects.none()
        if not country_code and channel_slug:
            channels = (
                Channel.objects.using(self.database_connection_name)
                .filter(slug=channel_slug)
                .values("pk")
            )
            WarehouseChannel = Channel.warehouses.through  # type: ignore[attr-defined] # raw access to the through model # noqa: E501
            warehouse_channels = (
                WarehouseChannel.objects.using(self.database_connection_name)
                .filter(
                    Exists(channels.filter(pk=OuterRef("channel_id"))),
                )
                .values("warehouse_id")
            )
            warehouses = Warehouse.objects.filter(
                Exists(warehouse_channels.filter(warehouse_id=OuterRef("id"))),
                click_and_collect_option__in=[
                    WarehouseClickAndCollectOption.LOCAL_STOCK,
                    WarehouseClickAndCollectOption.ALL_WAREHOUSES,
                ],
            )
        return warehouses

    def prepare_stocks_reservations_map(self, variant_ids):
        """Prepare stock id to quantity reserved map for provided variant ids."""
        stocks_reservations = defaultdict(int)
        site = get_site_promise(self.context).get()
        if is_reservation_enabled(site.settings):
            # Can't do second annotation on same queryset because it made
            # available_quantity annotated value incorrect thanks to how
            # Django's ORM builds SQLs with annotations
            reservations_qs = (
                Stock.objects.using(self.database_connection_name)
                .filter(product_variant_id__in=variant_ids)
                .annotate_reserved_quantity()
                .values_list("id", "reserved_quantity")
            )
            for stock_id, quantity_reserved in reservations_qs:
                stocks_reservations[stock_id] = quantity_reserved
        return stocks_reservations

    def prepare_warehouse_ids_by_shipping_zone_and_variant_map(
        self,
        stocks: QuerySet[StockWithAvailableQuantity],
        stocks_reservations,
        warehouse_shipping_zones_map,
        cc_warehouses,
    ):
        """Combine all quantities within a single zone.

        Prepare `warehouse_ids_by_shipping_zone_by_variant` map in the following format:
            {
                variant_id: {
                    shipping_zone_id/warehouse_id: [
                        warehouse_id
                    ]
                }
            }

        In case of the collection point warehouses the warehouse_id is used instead of
        the shipping zone id. Every stock of the collection point warehouse is treated
        as a magic single-warehouse shipping zone.
        """
        cc_warehouses_in_bulk = cc_warehouses.in_bulk()
        warehouse_ids_by_shipping_zone_by_variant: DefaultDict[
            int, DefaultDict[Union[int, UUID], List[UUID]]
        ] = defaultdict(lambda: defaultdict(list))
        variants_with_global_cc_warehouses = []
        available_quantity_by_warehouse_id_and_variant_id: DefaultDict[
            UUID, Dict[int, int]
        ] = defaultdict(lambda: defaultdict(int))
        for stock in stocks:
            reserved_quantity = stocks_reservations[stock.id]
            quantity = stock.available_quantity - reserved_quantity
            # when the available_quantity was under 0 we do not want clipping to zero,
            # as it means that the stock might be exceeded
            if stock.available_quantity > 0:
                quantity = max(0, quantity)
            variant_id = stock.product_variant_id
            warehouse_id = stock.warehouse_id
            available_quantity_by_warehouse_id_and_variant_id[warehouse_id][
                variant_id
            ] += quantity
            if shipping_zone_ids := warehouse_shipping_zones_map[warehouse_id]:
                for shipping_zone_id in shipping_zone_ids:
                    warehouse_ids_by_shipping_zone_by_variant[variant_id][
                        shipping_zone_id
                    ].append(warehouse_id)
            else:
                cc_option = cc_warehouses_in_bulk[warehouse_id].click_and_collect_option
                # every stock of a collection point warehouse should treat as a magic
                # single-warehouse shipping zone
                warehouse_ids_by_shipping_zone_by_variant[variant_id][warehouse_id] = [
                    warehouse_id
                ]
                # in case of global warehouses the quantity available will be the sum
                # of the available quantity for that variant from all stocks,
                # so we need to keep information for which variant there is a warehouse
                # with the global stock
                if cc_option == WarehouseClickAndCollectOption.ALL_WAREHOUSES:
                    variants_with_global_cc_warehouses.append(variant_id)
        return (
            warehouse_ids_by_shipping_zone_by_variant,
            variants_with_global_cc_warehouses,
            available_quantity_by_warehouse_id_and_variant_id,
        )

    def prepare_quantity_map(
        self,
        country_code,
        warehouse_ids_by_shipping_zone_by_variant,
        variants_with_global_cc_warehouses,
        available_quantity_by_warehouse_id_and_variant_id,
    ):
        """Prepare the variant id to quantity map.

        When the country code is known, the available quantity is the sum of quantities
        from all shipping zones supporting given country. When the country is not known
        the highest known quantity is returned.

        The local warehouses are treated as a magic single-warehouse shipping zone.
        When the variant has any global collection point warehouse, the quantity is the
        sum of the quantities from all shipping zones.
        In case of global warehouses the available quantity of such collection point
        is the sum of the available quantities from all stocks that passed the country
        or channel conditions.
        """
        quantity_map: DefaultDict[int, int] = defaultdict(int)
        for (
            variant_id,
            warehouse_ids_shipping_zone,
        ) in warehouse_ids_by_shipping_zone_by_variant.items():
            if country_code or variant_id in variants_with_global_cc_warehouses:
                used_warehouse_ids = []
                for warehouse_ids in warehouse_ids_sh