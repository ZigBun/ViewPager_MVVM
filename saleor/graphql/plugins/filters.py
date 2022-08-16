from typing import List, Optional

import graphene

from ..channel.types import Channel
from ..core.types import NonNullList
from ..utils import get_nodes
from .enums import PluginConfigurationType
from .types import Plugin


def filter_plugin_status_in_channels(
    plugins: List[Plugin], status_in_channels: dict
) -> List[Plugin]:
    is_active = status_in_channels["active"]
    channels