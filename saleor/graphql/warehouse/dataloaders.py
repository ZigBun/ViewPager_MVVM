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
                shipping_zone_channels =