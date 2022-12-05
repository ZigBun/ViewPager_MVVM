import graphene

from .....permission.enums import ProductPermissions
from .....product import models
from .....product.utils import delete_categories
from ....core import ResolveInfo
from ....core.mutations import ModelDeleteMutation
from ....core.t