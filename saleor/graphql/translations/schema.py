import graphene

from ...attribute.models import Attribute, AttributeValue
from ...discount.models import Sale, Voucher
from ...menu.models import MenuItem
from ...page.models import Page
from ...permission.enums import SitePermissions
from ...product.models import Category, Collection, Product, ProductVariant
from ...shipping.models import ShippingMethod
from ..attribute.resolvers import resolve_attributes
from ..core import ResolveInfo
from ..core.connection import CountableConnection, create_connection_slice
from ..core.fields import ConnectionField, PermissionsField
from ..core.utils import from_global_id_or_error
from ..menu.resolvers import resolve_menu_items
from ..page.resolvers import resolve_pages
from ..product.resolvers import resolve_categories
from ..translations import types as translation_types
from .resolvers import (
    resolve_attribute_values,
    resolve_collections,
    resolve_product_variants,
    resolve_products,
    resolve_sales,
    resolve_shipping_methods,
    resolve_vouchers,
)

TYPES_TRANSLATIONS_MAP = {
    Product: translation_types.ProductTranslatableContent,
    Collection: translation_types.CollectionTranslatableContent,
    Category: translation_types.CategoryTranslatableContent,
    Attribute: translation_types.AttributeTranslatableContent,
    AttributeValue: translation_types.AttributeValueTranslatableContent,
    ProductVariant: translation_types.ProductVariantTranslatableContent,
    Page: translation_types.PageTranslatableContent,
    ShippingMethod: translation_types.ShippingMethodTranslatableContent,
    Sale: translation_types.SaleTranslatableContent,
    Voucher: translation_types.VoucherTranslatableContent,
    MenuItem: translation_types.MenuItemTranslatableContent,
}


class TranslatableItem(graphene.Union):
