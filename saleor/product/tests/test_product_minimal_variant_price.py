from unittest.mock import patch

from django.core.management import call_command
from prices import Money

from ..tasks import (
    update_products_discounted_prices_of_catalogues,
    update_products_discounted_prices_task,
)
from ..utils.variant_prices import update_product_discounted_price


def test_update_product_discounted_price(product, channel_USD):
    variant = product.variants.first()
    variant_channel_listing = variant.channel_listings.get(channel_id=channel_USD.id)
    product_channel_listing = product.channel_listings.get(channel_id=channel_USD.id)
    variant_channel_listing.price = Money("4.99", "USD")
    variant_channel_listing.save()
    product_channel_listing.refresh_from_db()

    assert product_channel_listing.discounted_price == Money("10", "USD")

    update_product_discounted_price(product)

    product_channel_listing.refresh_from_db()
    assert product_channel_listing.discounted_price == variant_channel_listing.price


def test_update_product_discounted_price_without_price(
    product, channel_USD, channel_PLN
):
    variant = product.variants.first()
    variant_channel_listing = variant.channel_listings.get(channel_id=channel_USD.id)
    product_channel_listing = product.channel_listings.get(channel_id=channel_USD.id)
    second_product_channel_listing = product.channel_listings.create(
        channel=channel_PLN
    )

    assert product_channel_listing.discounted_price == Money("10", "USD")

    update_product_discounted_price(product)

    product_channel_listing.refresh_from_db()
    assert product_channel_listing.discounted_price == variant_channel_listing.price
    assert second_product_channel_listing.discounted_price is None


def test_update_products_discounted_prices_of_catalogues_for_product(
    product, channel_USD
):
    variant = product.variants.first()
    variant_channel_listing = variant.channel_listings.get(channel_id=channel_USD.id)
    product_channel_listing = product.channel_listings.get(channel_id=channel_USD.id)
    variant_channel_listing.price = Money("0.99", "USD")
    variant_channel_listing.save()
    product_channel_listing.refresh_from_db()

    assert product_channel_listing.discounted_price == Money("10", "USD")

    update_products_discounted_prices_of_catalogues(product_ids=[product.pk])

    product_channel_listing.refresh_from_db()
    assert product_channel_listing.discounted_price == variant_channel_listing.price


def test_update_products_discounted_prices_of_catalogues_for_category(
    category, product, channel_USD
):
    variant = product.variants.first()
    variant_channel_listing = variant.channel_listings.get(
        channel=channel_USD,
        variant=variant,
    )
    variant_channel_listing.price = Money("0.89", "USD")
    variant_channel_listing.save()
    product_channel_listing = product.channel_listings.get(
        channel_id=channel_USD.id, product_id=product.id
    )
    product_channel_listing.refresh_from_db()

    assert product_channel_listing.discounted_price == Money("10", "USD")
    update_products_discounted_prices_of_catalogues(category_ids=[product.category_id])
    product_channel_listing.refresh_from_db()
    assert product_channel_listing.discounted_price == variant_channel_listing.price


def test_update_products_discounted_prices_of_catalogues_for_collection(
    collection, product, channel_USD
):
    variant = product.variants.first()
    variant_channel_listing = variant.channel_listings.get