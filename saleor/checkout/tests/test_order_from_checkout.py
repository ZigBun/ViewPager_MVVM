from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings
from prices import TaxedMoney

from ...core.exceptions import InsufficientStock
from ...core.taxes import zero_money, zero_taxed_money
from ...giftcard import GiftCardEvents
from ...giftcard.models import GiftCard, GiftCardEvent
from ...plugins.manager import get_plugins_manager
from ...product.models import ProductTranslation, ProductVariantTranslation
from ...tests.utils import flush_post_commit_hooks
from .. import calculations
from ..complete_checkout import create_order_from_checkout
from ..fetch import fetch_checkout_info, fetch_checkout_lines
from ..utils import add_variant_to_checkout


def test_create_order_insufficient_stock(
    checkout, customer_user, product_without_shipping, app
):
    variant = product_without_shipping.variants.get()
    manager = get_plugins_manager()
    checkout_info = fetch_checkout_info(checkout, [], [], manager)

    add_variant_to_checkout(checkout_info, variant, 10, check_quantity=False)
    checkout.user = customer_user
    checkout.billing_address = customer_user.default_billing_address
    checkout.shipping_address = customer_user.default_billing_address
    checkout.tracking_code = "tracking_code"
    checkout.save()

    checkout_lines, unavailable_variant_pks = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, checkout_lines, [], manager)
    lines, _ = fetch_checkout_lines(checkout)
    with pytest.raises(InsufficientStock):
        