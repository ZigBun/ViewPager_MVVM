from ...attribute import models as attribute_models
from ...discount import models as discount_models
from ...menu import models as menu_models
from ...page import models as page_models
from ...product import models as product_models
from ...shipping import interface as shipping_interface
from ...shipping import models as shipping_models
from ...site import models as site_models
from ..core import ResolveInfo
from . import dataloaders

TYPE_TO_TRANSLATION_LOADER_MAP = {
    attribute_models.Attribute: (
        dataloaders.AttributeTranslationByIdAndLanguageCodeLoader
    ),
    attribute_models.AttributeValue: (
        dataloaders.AttributeValueTranslationByIdAndLanguageCodeLoader
    ),
    product_models.Category: (dataloaders.CategoryTranslationByIdAndLanguageCodeLoader),
    product_models.Collection: (
        dataloaders.CollectionTranslationByIdAndLanguageCodeLoader
    ),
    menu_models.MenuItem: (dataloaders.MenuItemTranslationByIdAndLanguageCodeLoader),
    page_models.Page: dataloaders.PageTranslationByIdAndLanguageCodeLoader,
    product_models.Product: (dataloaders.ProductTranslationByIdAndLanguageCodeLoader),
    product_models.ProductVariant: (
        dataloaders.ProductVariantTranslationByIdAndLanguageCodeLoader
    ),
    discount_models.Sale: dataloaders.SaleTranslationByIdAndLanguageCodeLoader,
    shipping_models.ShippingMethod: (
        dataloaders.ShippingMethodTranslationByIdAndLanguageCodeLoader
    ),
    shipping_interface.ShippingMethodData: (
        dataloaders.ShippingMet