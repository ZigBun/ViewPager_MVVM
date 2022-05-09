import re
from unittest.mock import ANY

import graphene
import pytest
from django_countries import countries

from .... import __version__
from ....account.models import Address
from ....core import TimePeriodType
from ....core.error_codes import ShopErrorCode
from ....permission.enums import get_permissions_codename
from ....shipping import PostalCodeRuleInclusionType
from ....shipping.models import ShippingMethod
from ....site import GiftCardSettingsExpiryType
from ....site.models import Site
from ...account.enums import CountryCodeEnum
from ...core.utils import str_to_enum
from ...tests.utils import assert_no_permission, get_graphql_content

COUNTRIES_QUERY = """
    query {
        shop {
            countries%(attributes)s {
                code
                country
            }
        }
    }
"""

LIMIT_INFO_QUERY = """
    {
      shop {
        limits {
          currentUsage {
            channels
          }
          allowedUsage {
            channels
          }
        }
      }
    }
"""


def test_query_countries(user_api_client):
    response = user_api_client.post_graphql(COUNTRIES_QUERY % {"attributes": ""})
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    assert len(data["countries"]) == len(countries)


@pytest.mark.parametrize(
    "language_code, expected_value",
    (
        ("", "Afghanistan"),
        ("(languageCode: EN)", "Afghanistan"),
        ("(languageCode: PL)", "Afganistan"),
        ("(languageCode: DE)", "Afghanistan"),
    ),
)
def test_query_countries_with_translation(
    language_code, expected_value, user_api_client
):
    response = user_api_client.post_graphql(
        COUNTRIES_QUERY % {"attributes": language_code}
    )
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    assert len(data["countries"]) == len(countries)
    assert data["countries"][0]["code"] == "AF"
    assert data["countries"][0]["country"] == expected_value


def test_query_name(user_api_client, site_settings):
    query = """
    query {
        shop {
            name
            description
        }
    }
    """
    response = user_api_client.post_graphql(query)
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    assert data["description"] == site_settings.description
    assert data["name"] == site_settings.site.name


def test_query_company_address(user_api_client, site_settings, address):
    query = """
    query {
        shop{
            companyAddress{
                city
                streetAddress1
                postalCode
            }
        }
    }
    """
    site_settings.company_address = address
    site_settings.save()
    response = user_api_client.post_graphql(query)
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    company_address = data["companyAddress"]
    assert company_address["city"] == address.city
    assert company_address["streetAddress1"] == address.street_address_1
    assert company_address["postalCode"] == address.postal_code


def test_query_domain(user_api_client, site_settings, settings):
    query = """
    query {
        shop {
            domain {
                host
                sslEnabled
                url
            }
        }
    }
    """
    response = user_api_client.post_graphql(query)
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    assert data["domain"]["host"] == site_settings.site.domain
    assert data["domain"]["sslEnabled"] == settings.ENABLE_SSL
    assert data["domain"]["url"]


def test_query_languages(settings, user_api_client):
    query = """
    query {
        shop {
            languages {
                code
                language
            }
        }
    }
    """
    response = user_api_client.post_graphql(query)
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    assert len(data["languages"]) == len(settings.LANGUAGES)


def test_query_permissions(staff_api_client):
    query = """
    query {
        shop {
            permissions {
                code
                name
            }
        }
    }
    """
    permissions_codenames = set(get_permissions_codename())
    response = staff_api_client.post_graphql(query)
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    permissions = data["permissions"]
    permissions_codes = {permission.get("code") for permission in permissions}
    assert len(permissions_codes) == len(permissions_codenames)
    for code in permissions_codes:
        assert code in [str_to_enum(code) for code in permissions_codenames]


def test_query_charge_taxes_on_shipping(api_client, site_settings):
    query = """
    query {
        shop {
            chargeTaxesOnShipping
        }
    }"""
    response = api_client.post_graphql(query)
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    charge_taxes_on_shipping = site_settings.charge_taxes_on_shipping
    assert data["chargeTaxesOnShipping"] == charge_taxes_on_shipping


def test_query_digital_content_settings(
    staff_api_client, site_settings, permission_manage_settings
):
    query = """
    query {
        shop {
            automaticFulfillmentDigitalProducts
            defaultDigitalMaxDownloads
            defaultDigitalUrlValidDays
        }
    }"""

    max_download = 2
    url_valid_days = 3
    site_settings.automatic_fulfillment_digital_products = True
    site_settings.default_digital_max_downloads = max_download
    site_settings.default_digital_url_valid_days = url_valid_days
    site_settings.save()

    response = staff_api_client.post_graphql(
        query, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    data = content["data"]["shop"]
    automatic_fulfillment = site_settings.automatic_fulfillment_digital_products
    assert data["automaticFulfillmentDigitalProducts"] == automatic_fulfillment
    assert data["defaultDigitalMaxDownloads"] == max_download
    assert data["defaultDigitalUrlValidDays"] == url_valid_days


QUERY_RETRIEVE_DEFAULT_MAIL_SENDER_SETTINGS = """
    {
      shop {
        defaultMailSenderName
        defaultMailSenderAddress
      }
    }
"""


def test_query_default_mail_sender_settings(
    staff_api_client, site_settings, permission_manage_settings
):
    site_settings.default_mail_sender_name = "Mirumee Labs Info"
    site_settings.default_mail_sender_address = "hello@example.com"
    site_settings.save(
        update_fields=["default_mail_sender_name", "default_mail_sender_address"]
    )

    query = QUERY_RETRIEVE_DEFAULT_MAIL_SENDER_SETTINGS

    response = staff_api_client.post_graphql(
        query, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)

    data = content["data"]["shop"]
    assert data["defaultMailSenderName"] == "Mirumee Labs Info"
    assert data["defaultMailSenderAddress"] == "hello@example.com"


def test_query_default_mail_sender_settings_not_set(
    staff_api_client, site_settings, permission_manage_settings, settings
):
    site_settings.default_mail_sender_name = ""
    site_settings.default_mail_sender_address = None
    site_settings.save(
        update_fields=["default_mail_sender_name", "default_mail_sender_address"]
    )

    settings.DEFAULT_FROM_EMAIL = "default@example.com"

    query = QUERY_RETRIEVE_DEFAULT_MAIL_SENDER_SETTINGS

    response = staff_api_client.post_graphql(
        query, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)

    data = content["data"]["shop"]
    assert data["defaultMailSenderName"] == ""
    assert data["defaultMailSenderAddress"] is None


def test_shop_digital_content_settings_mutation(
    staff_api_client, site_settings, permission_manage_settings
):
    query = """
        mutation updateSettings($input: ShopSettingsInput!) {
            shopSettingsUpdate(input: $input) {
                shop {
                    automaticFulfillmentDigitalProducts
                    defaultDigitalMaxDownloads
                    defaultDigitalUrlValidDays
                }
                errors {
                    field,
                    message
                }
            }
        }
    """

    max_downloads = 15
    url_valid_days = 30
    variables = {
        "input": {
            "automaticFulfillmentDigitalProducts": True,
            "defaultDigitalMaxDownloads": max_downloads,
            "defaultDigitalUrlValidDays": url_valid_days,
        }
    }

    assert not site_settings.automatic_fulfillment_digital_products
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)

    data = content["data"]["shopSettingsUpdate"]["shop"]
    assert data["automaticFulfillmentDigitalProducts"]
    assert data["defaultDigitalMaxDownloads"]
    assert data["defaultDigitalUrlValidDays"]
    site_settings.refresh_from_db()
    assert site_settings.automatic_fulfillment_digital_products
    assert site_settings.default_digital_max_downloads == max_downloads
    assert site_settings.default_digital_url_valid_days == url_valid_days


def test_shop_settings_mutation(
    staff_api_client, site_settings, permission_manage_settings
):
    query = """
        mutation updateSettings($input: ShopSettingsInput!) {
            shopSettingsUpdate(input: $input) {
                shop {
                    headerText,
                    includeTaxesInPrices,
                    chargeTaxesOnShipping,
                    fulfillmentAutoApprove,
                    fulfillmentAllowUnpaid
                }
                errors {
                    field,
                    message
                }
            }
        }
    """
    charge_taxes_on_shipping = site_settings.charge_taxes_on_shipping
    new_charge_taxes_on_shipping = not charge_taxes_on_shipping
    variables = {
        "input": {
            "includeTaxesInPrices": False,
            "headerText": "Lorem ipsum",
            "chargeTaxesOnShipping": new_charge_taxes_on_shipping,
            "fulfillmentAllowUnpaid": False,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    data = content["data"]["shopSettingsUpdate"]["shop"]
    assert data["headerText"] == "Lorem ipsum"
    assert data["includeTaxesInPrices"] is False
    assert data["chargeTaxesOnShipping"] == new_charge_taxes_on_shipping
    assert data["fulfillmentAutoApprove"] is True
    assert data["fulfillmentAllowUnpaid"] is False
    site_settings.refresh_from_db()
    assert not site_settings.include_taxes_in_prices
    assert site_settings.charge_taxes_on_shipping == new_charge_taxes_on_shipping


def test_shop_reservation_settings_mutation(
    staff_api_client, site_settings, permission_manage_settings
):
    query = """
        mutation updateSettings($input: ShopSettingsInput!) {
            shopSettingsUpdate(input: $input) {
                shop {
                    reserveStockDurationAnonymousUser
                    reserveStockDurationAuthenticatedUser
                }
                errors {
                    field,
                    message
                }
            }
        }
    """
    variables = {
        "input": {
            "reserveStockDurationAnonymousUser": 42,
            "reserveStockDurationAuthenticatedUser": 24,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    data = content["data"]["shopSettingsUpdate"]["shop"]
    assert data["reserveStockDurationAnonymousUser"] == 42
    assert data["reserveStockDurationAuthenticatedUser"] == 24
    site_settings.refresh_from_db()
    assert site_settings.reserve_stock_duration_anonymous_user == 42
    assert site_settings.reserve_stock_duration_authenticated_user == 24


def test_shop_reservation_disable_settings_mutation(
    staff_api_client, site_settings, permission_manage_settings
):
    query = """
        mutation updateSettings($input: ShopSettingsInput!) {
            shopSettingsUpdate(input: $input) {
                shop {
                    reserveStockDurationAnonymousUser
                    reserveStockDurationAuthenticatedUser
                }
                errors {
                    field,
                    message
                }
            }
        }
    """
    variables = {
        "input": {
            "reserveStockDurationAnonymousUser": None,
            "reserveStockDurationAuthenticatedUser": None,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    data = content["data"]["shopSettingsUpdate"]["shop"]
    assert data["reserveStockDurationAnonymousUser"] is None
    assert data["reserveStockDurationAuthenticatedUser"] is None
    site_settings.refresh_from_db()
    assert site_settings.reserve_stock_duration_anonymous_user is None
    assert site_settings.reserve_stock_duration_authenticated_user is None


def test_shop_reservation_set_negative_settings_mutation(
    staff_api_client, site_settings, permission_manage_settings
):
    query = """
        mutation updateSettings($input: ShopSettingsInput!) {
            shopSettingsUpdate(input: $input) {
                shop {
                    reserveStockDurationAnonymousUser
                    reserveStockDurationAuthenticatedUser
                }
                errors {
                    field,
                    message
                }
            }
        }
    """
    variables = {
        "input": {
            "reserveStockDurationAnonymousUser": -14,
            "reserveStockDurationAuthenticatedUser": -6,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    data = content["data"]["shopSettingsUpdate"]["shop"]
    assert data["reserveStockDurationAnonymousUser"] is None
    assert data["reserveStockDurationAuthenticatedUser"] is None
    site_settings.refresh_from_db()
    assert site_settings.reserve_stock_duration_anonymous_user is None
    assert site_settings.reserve_stock_duration_authenticated_user is None


@pytest.mark.parametrize("quantity_value", [25, 1, None])
def test_limit_quantity_per_checkout_mutation(
    staff_api_client, site_settings, permission_manage_settings, quantity_value
):
    query = """
        mutation updateSettings($input: ShopSettingsInput!) {
            shopSettingsUpdate(input: $input) {
                shop {
                    limitQuantityPerCheckout
                }
                errors {
                    field,
                    message
                }
            }
        }
    """
    variables = {"input": {"limitQuantityPerCheckout": quantity_value}}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    data = content["data"]["shopSettingsUpdate"]["shop"]
    site_settings.refresh_from_db()

    assert data["limitQuantityPerCheckout"] == quantity_value
    assert site_settings.limit_quantity_per_checkout == quantity_value


@pytest.mark.parametrize("quantity_value", [0, -25])
def test_limit_quantity_per_checkout_neg_or_zero_value(
    staff_api_client, site_settings, permission_manage_settings, quantity_value
):
    query = """
        mutation updateSettings($input: ShopSettingsInput!) {
            shopSettingsUpdate(input: $input) {
                shop {
                    limitQuantityPerCheckout
                }
                errors {
                    field,
                    message
                }
            }
        }
    """
    variables = {"input": {"limitQuantityPerCheckout": quantity_value}}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    errors = content["data"]["shopSettingsUpdate"]["errors"]
    site_settings.refresh_from_db()

    assert len(errors) == 1
    assert errors.pop() == {
        "field": "limitQuantityPerCheckout",
        "message": "Quantity limit cannot be lower than 1.",
    }

    assert site_settings.limit_quantity_per_checkout == 50  # default


MUTATION_UPDATE_DEFAULT_MAIL_SENDER_SETTINGS = """
    mutation updateDefaultSenderSettings($input: ShopSettingsInput!) {
      shopSettingsUpdate(input: $input) {
        shop {
          defaultMailSenderName
          defaultMailSenderAddress
        }
        errors {
          field
          message
        }
      }
    }
"""


def test_update_default_sender_settings(staff_api_client, permission_manage_settings):
    query = MUTATION_UPDATE_DEFAULT_MAIL_SENDER_SETTINGS

    variables = {
        "input": {
            "defaultMailSenderName": "Dummy Name",
            "defaultMailSenderAddress": "dummy@example.com",
        }
    }

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)

    data = content["data"]["shopSettingsUpdate"]["shop"]
    assert data["defaultMailSenderName"] == "Dummy Name"
    assert data["defaultMailSenderAddress"] == "dummy@example.com"


@pytest.mark.parametrize(
    "sender_name",
    (
        "\nDummy Name",
        "\rDummy Name",
        "Dummy Name\r",
        "Dummy Name\n",
        "Dummy\rName",
        "Dummy\nName",
    ),
)
def test_update_default_sender_settings_invalid_name(
    staff_api_client, permission_manage_settings, sender_name
):
    query = MUTATION_UPDATE_DEFAULT_MAIL_SENDER_SETTINGS

    variables = {"input": {"defaultMailSenderName": sender_name}}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)

    errors = content["data"]["shopSettingsUpdate"]["errors"]
    assert errors == [
        {"field": "defaultMailSenderName", "message": "New lines are not allowed."}
    ]


@pytest.mark.parametrize(
    "sender_email",
    (
        "\ndummy@example.com",
        "\rdummy@example.com",
        "dummy@example.com\r",
        "dummy@example.com\n",
        "dummy@example\r.com",
        "dummy@example\n.com",
    ),
)
def test_update_default_sender_settings_invalid_email(
    staff_api_client, permission_manage_settings, sender_email
):
    query = MUTATION_UPDATE_DEFAULT_MAIL_SENDER_SETTINGS

    variables = {"input": {"defaultMailSenderAddress": sender_email}}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)

    errors = content["data"]["shopSettingsUpdate"]["errors"]
    assert errors == [
        {"field": "defaultMailSenderAddress", "message": "Enter a valid email address."}
    ]


def test_shop_domain_update(staff_api_client, permission_manage_settings):
    query = """
        mutation updateSettings($input: SiteDomainInput!) {
            shopDomainUpdate(input: $input) {
                shop {
                    name
                    domain {
                        host,
                    }
                }
            }
        }
    """
    new_name = "saleor test store"
    variables = {"input": {"domain": "lorem-ipsum.com", "name": new_name}}
    site = Site.objects.get_current()
    assert site.domain != "lorem-ipsum.com"
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_settings]
    )
    content = get_graphql_content(response)
    data = content["data"]["shopDomainUpdate"]["shop"]
    assert data["domain"]["host"] == "lorem-ipsum.com"
    assert data["name"] == new_name
    site.refresh_from_db()
    assert site.domain == "lorem-ipsum.com"
    assert site.name == new_name


MUTATION_CUSTOMER_SET_PASSWORD_URL_UPDATE = """
    mutation updateSettings($customerSetPasswordUrl: String!) {
        shopSettingsUpdate(input: {customerSetPasswordUrl: $customerSetPasswordUrl}){
            shop {
                customerSetPasswordUrl
            }
            errors {
                message
                field
                code
            }
        }
    }
"""


def test_shop_customer_set_password_url_update(
    staff_api_client, site_settings, permission_manage_settings
):
    customer_set_password_url = "http://www.example.com/set_pass/"
    variables = {"customerSetPasswordUrl": customer_set_password_url}
    assert site_settings.customer_set_password_url != customer_set_password_url
    response = staff_api_client.post_graphql(
        MUTATION_CUSTOMER_SET_PASSWORD_URL_UPDATE,
        variables,
        permissions=[permission_manage_settings],
    )
    content = get_graphql_content(response)
    data = content["data"]["shopSettingsUpdate"]
    assert not data["errors"]
    Site.objects.clear_cache()
    site_settings = Site.objects.get_current().settings
    assert site_settings.customer_set_password_url == customer_set_password_url


@pytest.mark.parametrize(
    "customer_set_password_url",
    [
        ("http://not-allowed-storefron.com/pass"),
        ("http://[value-error-in-urlparse@test/pass"),
        ("without-protocole.com/pass"),
    ],
)
def test_shop_customer_set_password_url_update_invalid_url(
    staff_api_client,
    site_settings,
    permission_manage_settings,
    customer_set_password_url,
):
    variables = {"customerSetPasswordUrl": customer_set_password_url}
    assert not site_settings.customer_set_password_url
    response = staff_api_client.post_graphql(
        MUTATION_CUSTOMER_SET_PASSWORD_URL_UPDATE,
        variables,
        permissions=[permission_manage_settings],
    )
    content = get_graphql_content(response)
    data = content["data"]["shopSettingsUpdate"]
    assert data["errors"][0] == {
        "field": "customerSetPasswordUrl",
        "code": ShopErrorCode.INVALID.name,
        "message": ANY,
    }
 