from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from prices import Money, TaxedMoney

from ...product.models import Product, ProductVariant, ProductVariantChannelListing
from .. import DiscountInfo, DiscountValueType, VoucherType
from ..models import (
    NotApplicable,
    Sale,
    SaleChannelListing,
    Voucher,
    VoucherChannelListing,
    VoucherCustomer,
)
from ..utils import (
    add_voucher_usage_by_customer,
    decrease_voucher_usage,
    fetch_catalogue_info,
    get_product_discount_on_sale,
    increase_voucher_usage,
    remove_voucher_usage_by_customer,
    validate_voucher,
)


def test_valid_voucher_min_spent_amount(channel_USD):
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SHIPPING,
        discount_value_type=DiscountValueType.FIXED,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(10, "USD"),
        min_spent=Money(7, "USD"),
    )
    value = Money(7, "USD")

    voucher.validate_min_spent(value, channel_USD)


def test_valid_voucher_min_spent_amount_not_reached(channel_USD):
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SHIPPING,
        discount_value_type=DiscountValueType.FIXED,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(10, "USD"),
        min_spent=Money(7, "USD"),
    )
    value = Money(5, "USD")

    with pytest.raises(NotApplicable):
        voucher.validate_min_spent(value, channel_USD)


def test_valid_voucher_min_spent_amount_voucher_not_assigned_to_channel(
    channel_USD, channel_PLN
):
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SHIPPING,
        discount_value_type=DiscountValueType.FIXED,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(10, channel_USD.currency_code),
        min_spent=(Money(5, channel_USD.currency_code)),
    )
    price = Money(10, channel_PLN.currency_code)
    total_price = TaxedMoney(net=price, gross=price)
    with pytest.raises(NotApplicable):
        voucher.validate_min_spent(total_price, channel_PLN)


def test_valid_voucher_min_checkout_items_quantity(voucher):
    voucher.min_checkout_items_quantity = 3
    voucher.save()

    with pytest.raises(NotApplicable) as e:
        voucher.validate_min_checkout_items_quantity(2)

    assert (
        str(e.value)
        == "This offer is only valid for orders with a minimum of 3 quantity."
    )


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_discount_for_variants_is_applied_to_single_variant(product, channel_USD):
    discount_value = 5
    variant = product.variants.get()
    variant_channel_listing = variant.channel_listings.get(channel=channel_USD)
    sale = Sale.objects.create(type=DiscountValueType.FIXED)
    sale_channel_listing = SaleChannelListing.objects.create(
        sale=sale,
        discount_value=discount_value,
        currency=channel_USD.currency_code,
        channel=channel_USD,
    )
    old_price = variant.get_price(
        product, [], channel_USD, variant_channel_listing, discounts=[]
    )

    discount_info = DiscountInfo(
        sale=sale,
        channel_listings={channel_USD.slug: sale_channel_listing},
        product_ids=set(),
        category_ids=set(),
        collection_ids=set(),
        variants_ids={variant.id},
    )

    new_price = variant.get_price(
        product, [], channel_USD, variant_channel_listing, discounts=[discount_info]
    )

    assert new_price == old_price - Money(discount_value, "USD")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_discount_for_variants_are_not_applied_twice_for_variant_assigned_to_product(
    product, channel_USD
):
    discount_value = 5
    variant = product.variants.get()
    variant_channel_listing = variant.channel_listings.get(channel=channel_USD)
    sale = Sale.objects.create(type=DiscountValueType.FIXED)
    sale_channel_listing = SaleChannelListing.objects.create(
        sale=sale,
        discount_value=discount_value,
        currency=channel_USD.currency_code,
        channel=channel_USD,
    )
    old_price = variant.get_price(
        product, [], channel_USD, variant_channel_listing, discounts=[]
    )

    discount_info = DiscountInfo(
        sale=sale,
        channel_listings={channel_USD.slug: sale_channel_listing},
        product_ids={product.id},
        category_ids=set(),
        collection_ids=set(),
        variants_ids={variant.id},
    )

    new_price = variant.get_price(
        product, [], channel_USD, variant_channel_listing, discounts=[discount_info]
    )

    assert new_price == old_price - Money(discount_value, "USD")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_variant_discounts(product, channel_USD):
    variant = product.variants.get()
    low_sale = Sale.objects.create(type=DiscountValueType.FIXED)
    low_sale_channel_listing = SaleChannelListing.objects.create(
        sale=low_sale,
        discount_value=5,
        currency=channel_USD.currency_code,
        channel=channel_USD,
    )
    low_discount = DiscountInfo(
        sale=low_sale,
        channel_listings={channel_USD.slug: low_sale_channel_listing},
        product_ids={product.id},
        category_ids=set(),
        collection_ids=set(),
        variants_ids=set(),
    )
    sale = Sale.objects.create(type=DiscountValueType.FIXED)
    sale_channel_listing = SaleChannelListing.objects.create(
        sale=sale,
        discount_value=8,
        currency=channel_USD.currency_code,
        channel=channel_USD,
    )
    discount = DiscountInfo(
        sale=sale,
        channel_listings={channel_USD.slug: sale_channel_listing},
        product_ids={product.id},
        category_ids=set(),
        collection_ids=set(),
        variants_ids=set(),
    )
    high_sale = Sale.objects.create(type=DiscountValueType.FIXED)
    high_sale_channel_listing = SaleChannelListing.objects.create(
        sale=high_sale,
        discount_value=50,
        currency=channel_USD.currency_code,
        channel=channel_USD,
    )
    high_discount = DiscountInfo(
        sale=high_sale,
        channel_listings={channel_USD.slug: high_sale_channel_listing},
        product_ids={product.id},
        category_ids=set(),
        collection_ids=set(),
        variants_ids=set(),
    )
    variant_channel_listing = variant.channel_listings.get(channel=channel_USD)
    final_price = variant.get_price(
        product,
        [],
        channel_USD,
        variant_channel_listing,
        discounts=[low_discount, discount, high_discount],
    )
    assert final_price == Money(0, "USD")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_discount_for_variants_when_sale_for_specific_variants_only(
    product, channel_USD
):
    discount_value = 5
    variant = ProductVariant.objects.create(product=product, sku="456")
    ProductVariantChannelListing.objects.create(
        variant=variant,
        channel=channel_USD,
        price_amount=Decimal(20),
        cost_price_amount=Decimal(1),
        currency=channel_USD.currency_code,
    )
    variant = ProductVariant.objects.create(product=product, sku="789")
    ProductVariantChannelListing.objects.create(
        variant=variant,
        channel=channel_USD,
        price_amount=Decimal(20),
        cost_price_amount=Decimal(1),
        currency=channel_USD.currency_code,
    )
    product.refresh_from_db()

    all_variants = product.variants.all()
    first_variant, *rest_varian