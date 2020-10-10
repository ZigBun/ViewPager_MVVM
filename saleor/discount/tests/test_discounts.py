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
    first_variant, *rest_variants = all_variants

    first_variant_channel_listing = first_variant.channel_listings.get(
        channel=channel_USD
    )
    sale = Sale.objects.create(type=DiscountValueType.FIXED)
    sale_channel_listing = SaleChannelListing.objects.create(
        sale=sale,
        discount_value=discount_value,
        currency=channel_USD.currency_code,
        channel=channel_USD,
    )

    old_price = first_variant.get_price(
        product, [], channel_USD, first_variant_channel_listing, discounts=[]
    )

    old_price_for_applied_variants = []

    for variant in rest_variants:
        variant_channel_listing = variant.channel_listings.get(channel=channel_USD)
        old_price_for_applied_variants.append(
            variant.get_price(
                product, [], channel_USD, variant_channel_listing, discounts=[]
            )
        )

    discount = DiscountInfo(
        sale=sale,
        channel_listings={channel_USD.slug: sale_channel_listing},
        product_ids=set(),
        category_ids=set(),
        collection_ids=set(),
        variants_ids={variant.id for variant in rest_variants},
    )

    new_price = first_variant.get_price(
        product, [], channel_USD, first_variant_channel_listing, discounts=[discount]
    )

    new_price_for_applied_variants = []
    for variant in rest_variants:
        variant_channel_listing = variant.channel_listings.get(channel=channel_USD)
        new_price_for_applied_variants.append(
            variant.get_price(
                product, [], channel_USD, variant_channel_listing, discounts=[discount]
            )
        )

    assert new_price == old_price
    for p1, p2 in zip(new_price_for_applied_variants, old_price_for_applied_variants):
        assert p1 == p2 - Money(discount_value, "USD")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_percentage_discounts(product, channel_USD):
    variant = product.variants.get()
    sale = Sale.objects.create(type=DiscountValueType.PERCENTAGE)
    sale_channel_listing = SaleChannelListing.objects.create(
        sale=sale,
        discount_value=50,
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
    variant_channel_listing = variant.channel_listings.get(channel=channel_USD)
    final_price = variant.get_price(
        product, [], channel_USD, variant_channel_listing, discounts=[discount]
    )
    assert final_price == Money(5, "USD")


def test_voucher_queryset_active(voucher, channel_USD):
    vouchers = Voucher.objects.all()
    assert vouchers.count() == 1
    active_vouchers = Voucher.objects.active_in_channel(
        date=timezone.now() - timedelta(days=1), channel_slug=channel_USD.slug
    )
    assert active_vouchers.count() == 0


def test_voucher_queryset_active_in_channel(voucher, channel_USD):
    vouchers = Voucher.objects.all()
    assert vouchers.count() == 1
    active_vouchers = Voucher.objects.active_in_channel(
        date=timezone.now(), channel_slug=channel_USD.slug
    )
    assert active_vouchers.count() == 1


def test_voucher_queryset_active_in_other_channel(voucher, channel_PLN):
    vouchers = Voucher.objects.all()
    assert vouchers.count() == 1
    active_vouchers = Voucher.objects.active_in_channel(
        date=timezone.now(), channel_slug=channel_PLN.slug
    )
    assert active_vouchers.count() == 0


def test_sale_applies_to_correct_products(product_type, category, channel_USD):
    product = Product.objects.create(
        name="Test Product",
        slug="test-product",
        description={},
        product_type=product_type,
        category=category,
    )
    variant = ProductVariant.objects.create(product=product, sku="firstvar")
    variant_channel_listing = ProductVariantChannelListing.objects.create(
        variant=variant,
        channel=channel_USD,
        price_amount=Decimal(10),
        currency=channel_USD.currency_code,
    )
    product2 = Product.objects.create(
        name="Second product",
        slug="second-product",
        description={},
        product_type=product_type,
        category=category,
    )
    sec_variant = ProductVariant.objects.create(product=product2, sku="secvar")
    ProductVariantChannelListing.objects.create(
        variant=sec_variant,
        channel=channel_USD,
        price_amount=Decimal(10),
        currency=channel_USD.currency_code,
    )
    sale = Sale.objects.create(name="Test sale", type=DiscountValueType.FIXED)
    sale_channel_listing = SaleChannelListing.objects.create(
        sale=sale,
        currency=channel_USD.currency_code,
        channel=channel_USD,
        discount_value=3,
    )
    discount = DiscountInfo(
        sale=sale,
        channel_listings={channel_USD.slug: sale_channel_listing},
        product_ids={product.id},
        category_ids=set(),
        collection_ids=set(),
        variants_ids=set(),
    )
    _, product_discount = get_product_discount_on_sale(
        variant.product, set(), discount, channel_USD
    )

    discounted_price = product_discount(variant_channel_listing.price)
    assert discounted_price == Money(7, "USD")
    with pytest.raises(NotApplicable):
        get_product_discount_on_sale(sec_variant.product, set(), discount, channel_USD)


def test_increase_voucher_usage(channel_USD):
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.ENTIRE_ORDER,
        discount_value_type=DiscountValueType.FIXED,
        usage_limit=100,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(10, channel_USD.currency_code),
    )
    increase_voucher_usage(voucher)
    voucher.refresh_from_db()
    assert voucher.used == 1


def test_decrease_voucher_usage(channel_USD):
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.ENTIRE_ORDER,
        discount_value_type=DiscountValueType.FIXED,
        usage_limit=100,
        used=10,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(10, channel_USD.currency_code),
    )
    decrease_voucher_usage(voucher)
    voucher.refresh_from_db()
    assert voucher.used == 9


def test_add_voucher_usage_by_customer(voucher, customer_user):
    voucher_customer_count = VoucherCustomer.objects.all().count()
    add_voucher_usage_by_customer(voucher, customer_user.email)
    assert VoucherCustomer.objects.all().count() == voucher_customer_count + 1
    voucherCustomer = VoucherCustomer.objects.first()
    assert voucherCustomer.voucher == voucher
    assert voucherCustomer.customer_email == customer_user.email


def test_add_voucher_usage_by_customer_raise_not_applicable(voucher_customer):
    voucher = voucher_customer.voucher
    customer_email = voucher_customer.customer_email
    with pytest.raises(NotApplicable):
        add_voucher_usage_by_customer(voucher, customer_email)


def test_remove_voucher_usage_by_customer(voucher_customer):
    voucher_customer_count = VoucherCustomer.objects.all().count()
    voucher = voucher_customer.voucher
    customer_email = voucher_customer.customer_email
    remove_voucher_usage_by_customer(voucher, customer_email)
    assert VoucherCustomer.objects.all().count() == voucher_customer_count - 1


def test_remove_voucher_usage_by_customer_not_exists(voucher):
    remove_voucher_usage_by_customer(voucher, "fake@exmaimpel.com")


@pytest.mark.parametrize(
    "total, min_spent_amount, total_quantity, 