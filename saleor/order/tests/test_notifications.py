from decimal import Decimal
from functools import partial
from unittest import mock

import graphene
from django.core.files import File
from measurement.measures import Weight
from prices import Money, fixed_discount

from ...core.notify_events import NotifyEventType
from ...core.prices import quantize_price
from ...core.tests.utils import get_site_context_payload
from ...discount import DiscountValueType
from ...graphql.core.utils import to_global_id_or_none
from ...graphql.order.utils import OrderLineData
from ...order import notifications
from ...order.fetch import fetch_order_info
from ...plugins.manager import get_plugins_manager
from ...product.models import DigitalContentUrl
from ...thumbnail import THUMBNAIL_SIZES
from ...thumbnail.models import Thumbnail
from ..notifications import (
    get_address_payload,
    get_custom_order_payload,
    get_default_fulfillment_line_payload,
    get_default_fulfillment_payload,
    get_default_images_payload,
    get_default_order_payload,
    get_order_line_payload,
)
from ..utils import add_variant_to_order


def test_get_custom_order_payload(order, site_settings):
    expected_payload = get_custom_order_payload(order)
    assert expected_payload == {
        "order": {
            "id": to_global_id_or_none(order),
            "number": order.number,
            "private_metadata": {},
            "metadata": order.metadata,
            "status": "unfulfilled",
            "language_code": "en",
            "currency": "USD",
            "token": expected_payload["order"]["token"],
            "total_net_amount": 0,
            "undiscounted_total_net_amount": 0,
            "total_gross_amount": 0,
            "undiscounted_total_gross_amount": 0,
            "display_gross_prices": True,
            "channel_slug": "main",
            "created": expected_payload["order"]["created"],
            "shipping_price_net_amount": 0,
            "shipping_price_gross_amount": 0,
            "order_details_url": "",
            "email": "test@example.com",
            "subtotal_gross_amount": expected_payload["order"]["subtotal_gross_amount"],
            "subtotal_net_amount": expected_payload["order"]["subtotal_net_amount"],
            "tax_amount": 0,
            "lines": [],
            "billing_address": {
                "first_name": "John",
                "last_name": "Doe",
                "company_name": "Mirumee Software",
                "street_address_1": "Tęczowa 7",
                "street_address_2": "",
                "city": "WROCŁAW",
                "city_area": "",
                "postal_code": "53-601",
                "country": "PL",
                "country_area": "",
                "phone": "+48713988102",
            },
            "shipping_address": {
                "first_name": "John",
                "last_name": "Doe",
                "company_name": "Mirumee Software",
                "street_address_1": "Tęczowa 7",
                "street_address_2": "",
                "city": "WROCŁAW",
                "city_area": "",
                "postal_code": "53-601",
                "country": "PL",
                "country_area": "",
                "phone": "+48713988102",
            },
            "shipping_method_name": None,
            "collection_point_name": None,
            "voucher_discount": None,
            "discounts": [],
            "discount_amount": 0,
        },
        "recipient_email": "test@example.com",
        **get_site_context_payload(site_settings.site),
    }


def test_get_order_line_payload(order_line):
    order_line.variant.product.weight = Weight(kg=5)
    order_line.variant.product.save()

    payload = get_order_line_payload(order_line)

    attributes = order_line.variant.product.attributes.all()
    expected_attributes_payload = []
    for attr in attributes:
        expected_attributes_payload.append(
            {
                "assignment": {
                    "attribute": {
                        "slug": attr.assignment.attribute.slug,
                        "name": attr.assignment.attribute.name,
                    }
                },
                "values": [
                    {
                        "name": value.name,
                        "value": value.value,
                        "slug": value.slug,
                        "file_url": value.file_url,
                    }
                    for value in attr.values.all()
                ],
            }
        )
    unit_tax_amount = (
        order_line.unit_price_gross_amount - order_line.unit_price_net_amount
    )
    total_gross = order_line.unit_price_gross * order_line.quantity
    total_net = order_line.unit_price_net * order_line.quantity
    total_tax = total_gross - total_net
    currency = order_line.currency
    assert payload == {
        "variant": {
            "id": to_global_id_or_none(order_line.variant),
            "first_image": None,
            "images": None,
            "weight": "",
            "is_preorder": False,
            "preorder_global_threshold": None,
            "preorder_end_date": None,
        },
        "product": {
            "attributes": expected_attributes_payload,
            "first_image": None,
            "images": None,
            "weight": "5.0 kg",
            "id": to_global_id_or_none(order_line.variant.product),
        },
        "translated_product_name": order_line.translated_product_name
        or order_line.product_name,
        "translated_variant_name": order_line.translated_variant_name
        or order_line.variant_name,
        "id": to_global_id_or_none(order_line),
        "product_name": order_line.product_name,
        "variant_name": order_line.variant_name,
     