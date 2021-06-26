from collections import defaultdict
from typing import Iterable, List, Tuple

from django.db.models import F
from promise import Promise

from ...checkout.fetch import (
    CheckoutInfo,
    CheckoutLineInfo,
    apply_voucher_to_checkout_line,
    get_delivery_method_info,
    update_delivery_method_lists_for_checkout_info,
)
from ...checkout.models import Checkout, CheckoutLine, CheckoutMetadata
from ...discount import VoucherType
from ...payment.models import TransactionItem
from ..account.dataloaders import AddressByIdLoader, UserByUserIdLoader
from ..core.dataloaders import DataLoader
from ..discount.dataloaders import (
    VoucherByCodeLoader,
    VoucherInfoByVoucherCodeLoader,
    load_discounts,
)
from ..plugins.dataloaders import get_plugin_manager_promise
from ..product.dataloaders import (
    CollectionsByVariantIdLoader,
    ProductByVariantIdLoader,
    ProductTypeByVariantIdLoader,
    ProductVariantByIdLoader,
    VariantChannelListingByVariantIdAndChannelIdLoader,
)
from ..shipping.dataloaders import (
    ShippingMethodByIdLoader,
    ShippingMethodChannelListingByChannelSlugLoader,
)
from ..tax.dataloaders import TaxClassByVariantIdLoader, TaxConfigurationByChannelId
from ..warehouse.dataloaders import WarehouseByIdLoader


class CheckoutByTokenLoader(DataLoader[str, Checkout]):
    context_key = "checkout_by_token"

    def batch_load(self, keys):
        checkouts = Checkout.objects.using(self.database_connection_name).in_bulk(keys)
        return [checkouts.get(token) for token in keys]


class CheckoutLinesInfoByCheckoutTokenLoader(DataLoader[str, List[CheckoutLineInfo]]):
    context_key = "checkoutlinesinfo_by_checkout"

    def batch_load(self, keys):
        def with_checkout_lines(results):
            checkouts, checkout_lines = results
            variants_pks = list(
                {line.variant_id for lines in checkout_lines for line in lines}
            )
            if not variants_pks:
                return [[] for _ in keys]

            channel_pks = [checkout.channel_id for checkout in checkouts]

            def with_variants_products_collections(results):
                (
                    variants,
                    products,
                    product_types,
                    collections,
                    tax_classes,
                    channel_listings,
                    voucher_infos,
                ) = results
                variants_map = dict(zip(variants_pks, variants))
                products_map = dict(zip(variants_pks, products))
                product_types_map = dict(zip(variants_pks, product_types))
                collections_map = dict(zip(variants_pks, collections))
                tax_class_map = dict(zip(variants_pks, tax_classes))
                channel_listings_map = dict(
                    zip(variant_ids_channel_ids, channel_listings)
                )

                lines_info_map = defaultdict(list)
                voucher_infos_map = {
                    voucher_info.voucher.code: voucher_info
                    for voucher_info in voucher_infos
                    if voucher_info
                }
                for checkout, lines in zip(checkouts, checkout_lines):
                    lines_info_map[checkout.pk].extend(
                        [
                            CheckoutLineInfo(
                                line=line,
                                variant=variants_map[line.variant_id],
                                channel_listing=channel_listings_map[
                                    (line.variant_id, checkout.channel_id)
                                ],
                                product=products_map[line.variant_id],
                                product_type=product_types_map[line.variant_id],
                                collections=collections_map[line.variant_id],
                                tax_class=tax_class_map[line.variant_id],
                            )
                            for line in lines
                        ]
                    )

                for checkout in checkouts:
                    if not checkout.voucher_code:
                        continue
                    voucher_info = voucher_infos_map.get(checkout.voucher_code)
                    if not voucher_info:
                        continue
                    voucher = voucher_info.voucher
                    if (
                        voucher.type == VoucherType.SPECIFIC_PRODUCT
                        or voucher.apply_once_per_order
                    ):
                        discounts = load_discounts(self.context)
                        apply_voucher_to_checkout_line(
                            voucher_info=voucher