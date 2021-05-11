import graphene
from django.core.exceptions import ValidationError

from ....permission.enums import CheckoutPermissions
from ....tax import error_codes, models
from ...account.enums import CountryCodeEnum
from ...core import ResolveInfo
from ...core.descriptions import ADDED_IN_39, PREVIEW_FEATURE
from ...core.mutations import ModelMutation
from ...core.types import Error, NonNullList
from ...core.utils import get_duplicates_items
from ..types import TaxClass

TaxClassUpdateErrorCode = graphene.Enum.from_enum(error_codes.TaxClassUpdateErrorCode)


class CountryRateUpdateInput(graphene.InputObjectType):
    country_code = CountryCodeEnum(
        description="Country in which this rate applies.", required=True
    )
    rate = graphene.Float(
        description=(
            "Tax rate value provided as percentage. Example: provide `23` to "
            "represent `23%` tax rate. Provide `null` to remove the particular rate."
        ),
        required=False,
    )


class TaxClassUpdateError(Error):
    code = TaxClassUpdateErrorCode(description="The error code.", required=True)
    country_codes = NonNullList(
        graphene.String,
        description="List of country codes for which the configuration is invalid.",
        required=True,
    )


class TaxClassUpdateInput(graphene.InputObjectType):
    name = graphene.String(description="Name of the tax class.")
    update_country_rates = NonNullList(
        CountryRateUpdateInput,
        description=(
            "List of country-specific tax rates to create or update for this tax class."
        ),
    )
    remove_country_rates = NonNullList(
        CountryCodeEnum,
        description=(
            "List of country codes for which to remove the tax class rates. Note: It "
            "removes all rates for given country code."
        ),
    )


class TaxClassUpdate(ModelMutation):
    class Arguments:
        id = graphene.ID(description="ID of the tax class.", required=True)
        input = TaxClassUpdateInput(
            description="Fields required to update a tax class.", required=True
        )

    class Meta:
        description = "Update a tax class." + ADDED_IN_39 + PREVIEW_FEATURE
        error_type_class = TaxClassUpdateError
        model = models.TaxClass
        object_type = TaxClass
        permissions = (CheckoutPermissions.MANAGE_TAXES,)

    @classmethod
    def clean_input(cls, info: ResolveInfo, instance, data, **kwargs):
        update_country_rates = data.get("update_country_rates", [])
        update_country_codes = [item["country_code"] for item in update_country_rates]
        remove_country_rates = data.get("remove_country_rates", [])

        if duplicated_country_codes := list(
            get_duplicates_items(update_country_codes, remove_country_rates)
        ):
            message = (
                "The same country code cannot be in both lists for updating and "
                "removing items: "
            ) + ", ".join(duplicated_country_codes)
            params = {"country_codes": duplicated_country_codes}
            code = error_codes.TaxClassUpdateErrorCode.DUPLICATED_INPUT_ITEM.value
            raise ValidationError(message=message, code=code, params=params)

        return super().clean_input(info, instance, data, **kwargs)

    @classmethod
    def update_country_rates(cls, instance, c