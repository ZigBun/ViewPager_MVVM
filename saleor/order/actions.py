import logging
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple, TypedDict
from uuid import UUID

from django.contrib.sites.models import Site
from django.db import transaction

from ..account.models import User
from ..core import analytics
from ..core.exceptions import AllocationError, InsufficientStock, InsufficientStockData
from ..core.tracing import traced_atomic_transaction
from ..core.transactions import transaction_with_commit_on_errors
from ..core.utils.events import call_event
from ..giftcard import GiftCardLineData
from ..payment import (
    ChargeStatus,
    CustomPaymentChoices,
    PaymentError,
    TransactionKind,
    gateway,
)
from ..payment.gateway import request_refund_action
from ..payment.interface import RefundData
from ..payment.models import Payment, Transaction, TransactionItem
from ..payment.utils import create_payment
from ..warehouse.management import (
    deallocate_stock,
    deallocate_stock_for_order,
    decrease_stock,
    get_order_lines_with_track_inventory,
)
from ..warehouse.models import Stock
from . import (
    FulfillmentLineData,
    FulfillmentStatus,
    OrderOrigin,
    OrderStatus,
    events,
    utils,
)
from .events import (
    