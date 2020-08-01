import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, List, Optional

from ..account.models import User
from ..app.models import App
from ..core.prices import quantize_price
from ..core.tracing import traced_atomic_transaction
from ..order.events import (
    event_transaction_capture_requested,
    event_transaction_refund_requested,
    event_transaction_void_requested,
)
from ..payment.interface import (
    CustomerSource,
    PaymentGateway,
    RefundData,
    TransactionActionData,
)
from . import GatewayError, PaymentError, TransactionAction, TransactionKind
from .models import Payment, Transaction, TransactionItem
from .utils import (
    clean_authorize,
    clean_capture,
    create_payment_information,
    create_transaction,
    gateway_postprocess,
    get_already_processed_transaction_or_create_new_transaction,
    update_payment,
    validate_gateway_response,
)

if TYPE_CHECKING:
    from ..plugins.manager import PluginsManager

logger = logging.getLogger(__name__)
ERROR_MSG = "Oops! Something went wrong."
GENERIC_TRANSACTION_ERROR = "Transaction was unsuccessful."


def raise_payment_error(fn: Callable) -> Callable:
    def wrapped(*args, **kwargs):
        result = fn(*args, **kwargs)
        if not result.is_success:
            raise PaymentError(result.error or GENERIC_TRANSACTION_ERROR)
        return result

    return wrapped


def payment_postprocess(fn: Callable) -> Callable:
    def wrapped(*args, **kwargs):
        txn = fn(*args, **kwargs)
        gateway_postprocess(txn, txn.payment)
        return txn

    return wrapped


def require_active_payment(fn: Callable) -> Callable:
    def wrapped(payment: Payment, *args, **kwargs):
        if not payment.is_active:
            raise PaymentError("This payment is no longer active.")
        return fn(payment, *args, **kwargs)

    return wrapped


def with_locked_payment(fn: Callable) -> Callable:
    """Lock payment to protect from asynchronous modification."""

    def wrapped(payment: Payment, *args, **kwargs):
        with traced_atomic_transaction():
            payment = Payment.objects.select_for_update().get(id=payment.id)
            return fn(payment, *args, **kwargs)

    return wrapped


def request_charge_action(
    transaction: TransactionItem,
    manager: "PluginsManager",
    charge_value: Optional[Decimal],
    channel_slug: str,
    user: Optional[User],
    app: Optional[App],
):
    if charge_value is None:
        charge_value = transaction.authorized_value

    _request_payment_action(
        transaction=transaction,
        manager=manager,
        action_type=TransactionAction.CHARGE,
        action_value=charge_value,
        channel_slug=channel_slug,
    )
    if order_id := transaction.order_id:
        event_transaction_capture_requested(
            order_id=order_id,
            reference=transaction.reference,
            amount=quantize_price(charge_value, transaction.currency),
            user=user,
            app=app,
        )


def request_refund_action(
    transaction: TransactionItem,
    manager: "PluginsManager",
    refund_value: Optional[Decimal],
    channel_slug: str,
    user: Optional[User],
    app: Optional[App],
):
    if refund_value is None:
        refund_value = transaction.charged_value

    _request_payment_action(
        transaction=transaction,
        manager=manager,
        action_type=TransactionAction.REFUND,
        action_value=refund_value,
        channel_slug=channel_slug,
    )
    if order_id := transaction.order_id:
        event_transaction_refund_requested(
            order_id=order_id,
            reference=transaction.reference,
            amount=quantize_price(refund_value, transaction.currency),
            user=user,
            app=app,
        )


def request_void_action(
    transaction: TransactionItem,
    manager: "PluginsManager",
    channel_slug: str,
    user: Optional[User],
    app: Optional[App],
):
    _request_payment_action(
        transaction=transaction,
        manager=manager,
        action_type=TransactionAction.VOID,
        action_value=None,
        channel_slug=channel_slug,
    )
    if order_id := transaction.order_id:
        event_transaction_void_requested(
            order_id=order_id, reference=transaction.reference, user=user, app=app
        )


def _request_payment_action(
    transaction: TransactionItem,
    manager: "PluginsManager",
    action_type: str,
    action_value: Optional[Decimal],
    channel_slug: str,
):
    payment_data = TransactionActionData(
        transaction=tr