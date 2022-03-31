import os

import pytest

from ....account.models import Address
from ....checkout.fetch import CheckoutInfo, get_delivery_method_info
from ....shipping.models import ShippingMethodChannelListing
from ....shipping.utils import convert_to_shipping_method_data
from ...models import PluginConfiguration
from .. import AvataxConfiguration
from ..plugin import AvataxPlugin


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": [("Authorization", "Basic Og==")],
    }


@pytest.fixture
def plugin_configuration(db, channel_USD):
    default_username = os.environ.get("AVALARA_USERNAME", "test")
    default_password = os.environ.get("AVALARA_PASSWORD", "test")

    def set_configuration(
        username=default_username,
        password=default_password,
        sandbox=True,
        channel=None,
        active=True,
        from_street_address="Teczowa 7",
        from_city="Wroclaw",
        from_country="PL",
        from_country_area="",
        from_postal_code="53-601",
        shipping_tax_code="FR000000",
    ):
        channel = channel or channel_USD
        data = {
            "active": active,
            "name": AvataxPlugin.PLUGIN_NAME,
            "channel": channel,
            "configuration": [
                {"name": "Username or account", "value": username},
                {"name": "Password or license", "value": password},
                {"name": "Use sandbox", "value": sandbox},
                {"name": "Company name", "value": "DEFAULT"},
                {"name": "Autocommit", "value": False},
                {"name": "from_street_address", "value": from_street_address},
                {"name": "from_city", "value": from_city},
                {"name": "from_country", "value": from_country},
                {"name": "from_country_area", "value": from_country_area},
                {"name": "from_postal_code", "value": from_postal_code},
                {"name": "shipping_tax_code", "value": shipping_tax_code},
            ],
        }
        configuration = PluginConfiguration.objects.create(
            identifier=AvataxPlugin.PLUGIN_ID, **data
        )
        return configuration

    return set_configuration


@pytest.fixture
def avatax_config():
    return AvataxConfiguration(
        username_or_account=os.environ.get("AVALARA_USERNAME", "test"),
        password_or_license=os.environ.get("AVALARA_PASSWORD", "test"),
        use_sandbox=True,
        from_street_address="Tęczowa 7",
        from_city="WROCŁAW",
        from_country_area="",
        from_postal_code="53-601",
        from_country="PL",
    )


@pytest.fixture
def ship_to_pl_address(db):
    return Address.objects.create(
        first_name="Eleanor",
        last_name="Smith",
        street_address_1="Oławska 10",
        city="WROCŁAW",
        postal_code="53-105",
        country="PL",
        phone="+48713988155",
    )


@pytest.fixture
def checkout_with_items_and_shipping(checkout_with_items, address, shipping_method):
    checkout_with_items.shipping_address = address
    checkout_with_items.shipping_method = shipping_method
    checkout_with_items.billing_address = address
    checkout_with_items.save()
    return checkout_with_items


@pytest.fixture
def checkout_with_items_and_shipping_info(checkout_with_items_and_shipping):
    checkout = checkout_with_items_and_shipping
    channel = checkout.channel
    shipping_address = checkout.shipping_address
    shipping_method = checkout.shipping_method
    shipping_channel_listing = ShippingMethodChannelListing.objects.get(
        channel=channel,
        shipping_method=shipping_method,
    )
    checkout_info = CheckoutInfo(
        checkout=checkout,
        user=checkout.user,
        channel=channel,
        billing_address=checkout.billing_address,
        shipping_address=shipping_address,
        delivery_method_info=get_delivery_method_info(
            convert_to_shipping_method_data(shipping_method, shipping_channel_listing),
            shipping_address,
        ),
        tax_configuration=channel.tax_configuration,
        valid_pick_up_points=[],
        all_shipping_methods=[],
    )
    return checkout_info


@pytest.fixture
def avalara_response_for_checkout_with_items_and_shipping():
    return {
        "id": 0,
        "code": "8657e84b-c5ab-4c27-bcc2-c8d3ebbe771b",
        "companyId": 242975,
        "date": "2021-03-18",
        "paymentDate": "2021-03-18",
        "status": "Temporary",
        "type": "SalesOrder",
        "batchCode": "",
        "currencyCode": "USD",
        "exchangeRateCurrencyCode": "USD",
        "customerUsageType": "",
        "entityUseCode": "",
        "customerVendorC