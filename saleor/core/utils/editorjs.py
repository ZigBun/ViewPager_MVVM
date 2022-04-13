import re
import warnings
from typing import Dict, List, Literal, Union, overload

from django.utils.html import strip_tags
from urllib3.util import parse_url

BLACKLISTED_URL_SCHEMES = ("javascript",)
HYPERLINK_TAG_WITH_URL_PATTERN = r"(.*?<a\s+href=\\?\")(\w+://\S+[^\\])(\\?\">)"

ITEM_TYPE_TO_CLEAN_FUNC_MAP = {
    "list": lambda *params: clean_list_item(*params),
    "image": lambda *params: clean_image_item(*params),
    "embed": lambda *params: clean_emb