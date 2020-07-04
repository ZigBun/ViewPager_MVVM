from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple

from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..core.exceptions import InsufficientStock, InsufficientStockData
from ..core.tracing import traced_atomic_transaction
from ..product.models import ProductVariant, ProductVariantChannelListing
from .manage