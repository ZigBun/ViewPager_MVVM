from decimal import Decimal
from unittest.mock import ANY, Mock, patch

from django.test import override_settings
from prices import Money, TaxedMoney

from ....checkout.fetch import fetch_checkout_lines
from ...manager import get_plugins_manager
from .. im