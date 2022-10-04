from ...app.types import AppExtensionMount, AppExtensionTarget, AppType
from ..core.enums import to_enum


def description(enum):
    if enum is None:
        return "Enum dete