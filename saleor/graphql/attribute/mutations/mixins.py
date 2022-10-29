from django.core.exceptions import ValidationError
from django.utils.text import slugify
from text_unidecode import unidecode

from ....attribute import ATTRIBUTE_PROPERTIES_CONFIGURATION, AttributeInputType
from ....attribute import models as models
from ....attribute.error_codes import AttributeErrorCode
from ...core import ResolveInfo
from ...core.validators import validate_slug_and_generate_if_needed


class AttributeMixin:
    # must be redefined by inheriting classes
    ATTRIBUTE_VALUES_FIELD: str
    ONLY_SWATCH_FIELDS = ["file_url", "content_type", "value"]

    @classmethod
    def clean_values(cls, cleaned_input, attribute):
        """Clean attribute values.

        Transforms AttributeValueCreateInput into AttributeValue instances.
        Slugs are created from given names and checked for uniqueness within
        an attribute.
        """
        values_input = cleaned_input.get(cls.ATTRIBUTE_VALUES_FIELD)
        attribute_input_type = cleaned_input.get("input_type") or attribute.input_type

        if values_input is None:
            return

        if (
            values_input
            and attribute_input_type not in AttributeInputType.TYPES_WITH_CHOICES
        ):
            raise ValidationError(
                {
                    cls.ATTRIBUTE_VALUES_FIELD: ValidationError(
                        "Values cannot be used with "
                        f"input type {attribute_input_type}.",
                        code=AttributeErrorCode.INVALID.value,
                    )
                }
            )

        is_swatch_attr = attribute_input_type == AttributeInputType.SWATCH
        for value_data in values_input:
            cls._validate_value(attribute, value_data, is_swatch_attr)

        cls.check_values_are_unique(values_input, attribute)

    @classmethod
    def _validate_value(
        cls,
        attribute: models.Attribute,
        value_data: dict,
        is_swatch_attr: bool,
    ):
        """Validate the new attribute value."""
        value = value_data.get("name")
        if value is None:
            raise ValidationError(
                {
                    cls.ATTRIBUTE_VALUES_FIELD: ValidationError(
                        "The name field is required.",
                        code=AttributeErrorCode.REQUIRED.value,
                    )
                }
            )

        if i