import graphene
import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

from ....attribute import AttributeInputType
from ....page.error_codes import PageErrorCode
from ....product.error_codes import ProductErrorCode
from ..utils import (
    AttributeAssignmentMixin,
    AttrValuesForSelectableFieldInput,
    AttrValuesInput,
    prepare_attribute_values,
    validate_attributes_input,
)


@pytest.mark.parametrize("creation", [True, False])
def test_validate_attributes_input_for_product(
    creation, weight_attribute, color_attribute, product_type
):
    # given
    color_attribute.value_required = True
    color_attribute.save(update_fields=["value_required"])

    weight_attribute.value_required = True
    weight_attribute.save(update_fields=["value_required"])

    input_data = [
        (
            weight_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", weight_attribute.pk),
                values=["a"],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
        (
            color_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", color_attribute.pk),
                values=["b"],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
    ]

    # when
    errors = validate_attributes_input(
        input_data,
        product_type.product_attributes.all(),
        is_page_attributes=False,
        creation=creation,
    )

    # then
    assert not errors


@pytest.mark.parametrize("creation", [True, False])
def test_validate_attributes_input_for_product_no_values_given(
    creation, weight_attribute, color_attribute, product_type
):
    # given
    color_attribute.value_required = True
    color_attribute.save(update_fields=["value_required"])

    weight_attribute.value_required = True
    weight_attribute.save(update_fields=["value_required"])

    input_data = [
        (
            weight_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", weight_attribute.pk),
                values=[],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
        (
            color_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", color_attribute.pk),
                values=[],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
    ]

    # when
    errors = validate_attributes_input(
        input_data,
        product_type.product_attributes.all(),
        is_page_attributes=False,
        creation=creation,
    )

    # then
    assert len(errors) == 1
    error = errors[0]
    assert error.code == ProductErrorCode.REQUIRED.value
    assert set(error.params["attributes"]) == {
        graphene.Node.to_global_id("Attribute", attr.pk)
        for attr in [weight_attribute, color_attribute]
    }


@pytest.mark.parametrize("creation", [True, False])
def test_validate_attributes_input_for_product_too_many_values_given(
    creation, weight_attribute, color_attribute, product_type
):
    # given
    color_attribute.input_type = AttributeInputType.DROPDOWN
    color_attribute.value_required = True
    color_attribute.save(update_fields=["value_required", "input_type"])

    weight_attribute.value_required = True
    weight_attribute.input_type = AttributeInputType.MULTISELECT
    weight_attribute.save(update_fields=["value_required", "input_type"])

    input_data = [
        (
            weight_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", weight_attribute.pk),
                values=["abc", "efg"],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
        (
            color_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", color_attribute.pk),
                values=["a", "b"],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
    ]

    # when
    errors = validate_attributes_input(
        input_data,
        product_type.product_attributes.all(),
        is_page_attributes=False,
        creation=creation,
    )

    # then
    assert len(errors) == 1
    error = errors[0]
    assert error.code == ProductErrorCode.INVALID.value
    assert error.params["attributes"] == [
        graphene.Node.to_global_id("Attribute", color_attribute.pk)
    ]


@pytest.mark.parametrize("creation", [True, False])
def test_validate_attributes_input_for_product_empty_values_given(
    creation, weight_attribute, color_attribute, product_type
):
    # given
    color_attribute.input_type = AttributeInputType.DROPDOWN
    color_attribute.value_required = True
    color_attribute.save(update_fields=["value_required", "input_type"])

    weight_attribute.value_required = True
    weight_attribute.input_type = AttributeInputType.MULTISELECT
    weight_attribute.save(update_fields=["value_required", "input_type"])

    input_data = [
        (
            weight_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", weight_attribute.pk),
                values=["a", None],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
        (
            color_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", color_attribute.pk),
                values=["  "],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
    ]

    # when
    errors = validate_attributes_input(
        input_data,
        product_type.product_attributes.all(),
        is_page_attributes=False,
        creation=creation,
    )

    # then
    assert len(errors) == 1
    error = errors[0]
    assert error.code == ProductErrorCode.REQUIRED.value
    assert set(error.params["attributes"]) == {
        graphene.Node.to_global_id("Attribute", attr.pk)
        for attr in [weight_attribute, color_attribute]
    }


def test_validate_attributes_input_for_product_lack_of_required_attribute(
    weight_attribute, color_attribute, product_type
):
    # given
    product_attributes = product_type.product_attributes.all()
    attr = product_attributes.first()
    attr.value_required = True
    attr.save(update_fields=["value_required"])

    weight_attribute.value_required = True
    weight_attribute.save(update_fields=["value_required"])

    input_data = [
        (
            weight_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", weight_attribute.pk),
                values=["a"],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
    ]

    # when
    errors = validate_attributes_input(
        input_data,
        product_attributes,
        is_page_attributes=False,
        creation=True,
    )

    # then
    assert len(errors) == 1
    error = errors[0]
    assert error.code == ProductErrorCode.REQUIRED.value
    assert set(error.params["attributes"]) == {
        graphene.Node.to_global_id("Attribute", attr.pk)
    }


@pytest.mark.parametrize("creation", [True, False])
def test_validate_attributes_input_for_product_creation_multiple_errors(
    creation, weight_attribute, color_attribute, product_type
):
    # given
    color_attribute.input_type = AttributeInputType.DROPDOWN
    color_attribute.value_required = True
    color_attribute.save(update_fields=["value_required", "input_type"])

    weight_attribute.value_required = True
    weight_attribute.input_type = AttributeInputType.MULTISELECT
    weight_attribute.save(update_fields=["value_required", "input_type"])

    input_data = [
        (
            weight_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", weight_attribute.pk),
                values=[None],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
        (
            color_attribute,
            AttrValuesInput(
                global_id=graphene.Node.to_global_id("Attribute", color_attribute.pk),
                values=["a", "b"],
                file_url=None,
                content_type=None,
                references=[],
            ),
        ),
    ]

    # when
    errors = validate_attributes_input(
        input_data,
        product_type.product_attributes.all()