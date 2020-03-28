from collections import defaultdict

from promise import Promise

from ....attribute.models import (
    AssignedProductAttribute,
    AssignedProductAttributeValue,
    AssignedVariantAttribute,
    AssignedVariantAttributeValue,
    AttributeProduct,
    AttributeVariant,
)
from ....permission.enums import ProductPermissions
from ...attribute.dataloaders import AttributesByAttributeId, AttributeValueByIdLoader
from ...core.dataloaders import DataLoader
from ...utils import get_user_or_app_from_context
from .products import ProductByIdLoader, ProductVariantByIdLoader


class BaseProductAttributesByProductTypeIdLoader(DataLoader):
    """Loads product attributes by product type ID."""

    model_name = None
    extra_fields = None

    def batch_load(self, keys):
        if not self.model_name:
            raise ValueError("Provide a model_name for this dataloader.")
        if not self.extra_fields:
            self.extra_fields = []

        requestor = get_user_or_app_from_context(self.context)
        if (
            requestor
            and requestor.is_active
            and requestor.has_perm(ProductPermissions.MANAGE_PRODUCTS)
        ):
            qs = self.model_name.objects.using(self.database_connection_name).all()
        else:
            qs = self.model_name.objects.using(self.database_connection_name).filter(
                attribute__visible_in_storefront=True
            )

        product_type_attribute_pairs = qs.filter(product_type_id__in=keys).values_list(
            "product_type_id", "attribute_id", *self.extra_fields
        )

        product_type_to_attributes_map = defaultdict(list)
        for product_type_id, attr_id, *extra_fields in product_type_attribute_pairs:
            product_type_to_attributes_map[product_type_id].append(
                (attr_id, *extra_fields)
            )

        def map_attributes(attributes):
            attributes_map = {attr.id: attr for attr in attributes}
            return [
                [
                    (attributes_map[attr_id], *extra_fields)
                    for attr_id, *extra_fields in product_type_to_attributes_map[
                        product_type_id
                    ]
                ]
                for product_type_id in keys
            ]

        return (
            AttributesByAttributeId(self.context)
            .load_many(set(attr_id for _, attr_id, *_ in product_type_attribute_pairs))
            .then(map_attributes)
        )


class ProductAttributesByProductTypeIdLoader(
    BaseProductAttributesByProductTypeIdLoader
):
    """Loads product attributes by product type ID."""

    context_key = "product_attributes_by_producttype"
    model_name = AttributeProduct


class VariantAttributesByProductTypeIdLoader(
    BaseProductAttributesByProductTypeIdLoader
):
    """Loads variant attributes by product type ID."""

    context_key = "variant_attributes_by_producttype"
    model_name = AttributeVariant
    extra_fields = ["variant_selection"]


class AttributeProductsByProductTypeIdLoader(DataLoader):
    """Loads AttributeProduct objects by product type ID."""

    context_key = "attributeproducts_by_producttype"

    def batch_load(self, keys):
        requestor = get_user_or_app_from_context(self.context)
        if (
            requestor
            and requestor.is_active
            and requestor.has_perm(ProductPermissions.MANAGE_PRODUCTS)
        ):
            qs = AttributeProduct.objects.using(self.database_connection_name).all()
        else:
            qs = AttributeProduct.objects.using(self.database_connection_name).filter(
                attribute__visible_in_storefront=True
            )
        attribute_products = qs.filter(product_type_id__in=keys)
        producttype_to_attributeproducts = defaultdict(list)
        for attribute_product in attribute_products:
            producttype_to_attributeproducts[attribute_product.product_type_id].append(
                attribute_product
            )
        return [producttype_to_attributeproducts[key] for key in keys]


class AttributeVariantsByProductTypeIdLoader(DataLoader):
    context_key = "attributevariants_by_producttype"

    def batch_load(self, keys):
        requestor = get_user_or_app_from_context(self.context)
        if (
            requestor
            and requestor.is_active
            and requestor.has_perm(ProductPermissions.MANAGE_PRODUCTS)
        ):
            qs = AttributeVariant.objects.using(self.database_connection_name).all()
        else:
            qs = AttributeVariant.objects.using(self.database_connection_name).filter(
                attribute__visible_in_storefront=True
            )
        attribute_variants = qs.filter(product_type_id__in=keys)
        producttype_to_attributevariants = defaultdict(list)
        for attribute_variant in attribute_variants.iterator():
            producttype_to_attributevariants[attribute_variant.product_type_id].append(
                attribute_variant
            )
        return [producttype_to_attributevariants[key] for key in keys]


class AssignedProductAttributesByProductIdLoader(DataLoader):
    context_key = "assignedproductattributes_by_product"

    def batch_load(self, keys):
        requestor = get_user_or_app_from_context(self.context)
        if (
            requestor
            and requestor.is_active
            and requestor.has_perm(ProductPermissions.MANAGE_PRODUCTS)
        ):
            qs = AssignedProductAttribute.objects.using(
                self.database_connection_name
            ).all()
        else:
            qs = AssignedProductAttribute.objects.using(
                self.database_connection_name
            ).filter(assignment__attribute__visible_in_storefront=True)
        assigned_product_attributes = qs.filter(product_id__in=keys)
        product_to_assignedproductattributes = defaultdict(list)
        for assigned_product_attribute in assigned_product_attributes.iterator():
            product_to_assignedproductattributes[
                assigned_product_attribute.product_id
            ].append(assigned_product_attribute)
        return [product_to_assignedproductattributes[product_id] for product_id in keys]


class AssignedVariantAttributesByProductVariantId(DataLoader):
    context_key = "assignedvariantattributes_by_productvariant"

    def batch_load(self, keys):
        requestor = get_user_or_app_from_context(self.context)
        if (
            requestor
            and requestor.is_active
            and requestor.has_perm(ProductPermissions.MANAGE_PRODUCTS)
        ):
            qs = AssignedVariantAttribute.objects.using(
                self.database_connection_name
            ).all()
        else:
            qs = AssignedVariantAttribute.objects.using(
                self.database_connection_name
            ).filter(assignment__attribute__visible_in_storefront=True)
        assigned_variant_attributes = qs.filter(variant_id__in=keys).select_related(
            "assignment__attribute"
        )
        variant_attributes = defaultdict(list)
        for assigned_variant_attribute in assigned_variant_attributes.iterator():
            variant_attributes[assigned_variant_attribute.variant_id].append(
                assigned_variant_attribute
  