from typing import TYPE_CHECKING

import graphene

from saleor.tax.models import TaxClassCountryRate

from ....tests.utils import assert_no_permission, get_graphql_content
from ..fragments import TAX_COUNTRY_CONFIGURATION_FRAGMENT

if TYPE_CHECKING:
    from django.db.models import QuerySet


QUERY = (
    """
    query TaxCountryConfiguration($countryCode: CountryCode!) {
        taxCountryConfiguration(countryCode: $countryCode) {
            ...TaxCountryConfiguration
        }
    }
    """
    + TAX_COUNTRY_CONFIGURATION_FRAGMENT
)


def _test_field_resolvers(
    country_code, country_rates: "QuerySet[TaxClassCountryRate]", data: dict
):
    assert data["country"]["code"] == country_code
    assert data["taxClassCountryRates"]
    assert len(data["taxClassCountryRates"]) == len(country_rates)

    for country_rate in country_rates:
        expected_rate_data = {
            "rate": country_rate.rate,
            "taxClass": {
                "id": graphene.Node.to_global_id("TaxClass", country_rate.tax_class.pk),
                "name": country_rate.tax_class.name,
            },
        }
        assert expecte