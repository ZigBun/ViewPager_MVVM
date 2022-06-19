from collections import defaultdict

from ...attribute import models as attribute_models
from ...discount import models as discount_models
from ...menu import models as menu_models
from ...page import models as page_models
from ...product import models as product_models
from ...shipping import models as shipping_models
from ...site import models as site_models
from ..core.dataloaders import DataLoader


class BaseTranslationByIdAndLanguageCodeLoader(DataLoader):
    model = None
    relation_name = None

    def batch_load(self, keys):
        if not self.model:
            raise ValueError("Provide a model for this dataloader.")
        if not self.relation_name:
            raise ValueError("Provide a relation_name for this dataloader.")

        ids = set([str(key[0]) for key in keys])
        language_codes = set([key[1] for key in keys])

        filters = {
            "language_code__in": language_codes,
            f"{self.relation_name}__in": ids,
        }

        translations = self.model.objects.using(self.database_connection_name).filter(
            **filters
        )
        translation_by_language_code_by_id = defaultdict(
            lambda: defaultdict(lambda: None)
        )
        for translation in translations:
            language_code = translation.language_code
            id = str(getattr(translation, self.relation_name))
            translation_by_language_code_by_id[language_code][id] = translation
        return [translation_by_language_code_by_id[key[1]][str(key[0])] for key in keys]


class AttributeTranslationByIdAndLanguageCodeLoader(
    BaseTranslationById