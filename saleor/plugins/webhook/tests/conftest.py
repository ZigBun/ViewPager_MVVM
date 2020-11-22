import uuid
from decimal import Decimal
from typing import List

import pytest
from measurement.measures import Weight
from prices import Money

from ....app.models import App
from ....plugins.manager import get_plugins_manager
from ....plugins.webhook.plugin import WebhookPlugin
from ....shipping.interface import ShippingMethodData
from ....webhook.event_types import WebhookEventSyn