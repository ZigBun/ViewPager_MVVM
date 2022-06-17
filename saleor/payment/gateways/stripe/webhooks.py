import logging
from typing import List, Optional

from django.core.exceptions import ValidationError
from django.core.handlers.wsgi import WSGIRequest
from django.db.models import Prefetch
from django.http import HttpResponse
from stripe.error import SignatureVerificationError
from stripe.stripe_object import StripeObject

from ....checkout.calculations import calculate_checkout_total_with_gift_cards
from ....checkout.complete_checkout import complete_checkout
from ....checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from ....checkout.models import Checkout
from ....core.transactions import transaction_with_commit_on_errors
from ....discount.utils import fetch_active_discounts
from ....order.actions import order_captured, order_refunded, order_voided
from ....order.fetch import fetch_order_info
from ....order.models import Order
from ....plugins.manager import get_plugins_manager
from ... import ChargeStatus, TransactionKind
from ...gateway import payment_refund_or_void
from ...interface import GatewayConfig, GatewayResponse
from ...models import Payment
from ...utils import (
    create_transaction,
    gateway_postprocess,
    price_from_minor_unit,
    try_void_or_refund_inactive_payment,
    update_payment_charge_status,
    update_payment_method_details,
)
from .consts import (
    WEBHOOK_AUTHORIZED_EVENT,
    WEBHOOK_CANCELED_EVENT,
    WEBHOOK_FAILED_EVENT,
    WEBHOOK_PROCESSING_EVENT,
    WEBHOOK_REFUND_EVENT,
    WEBHOOK_SUCCESS_EVENT,
)
from .stripe_api import (
    construct_stripe_event,
    get_payment_method_details,
    update_payment_method,
)

logger = logging.getLogger(__name__)


@transaction_with_commit_on_errors()
def handle_webhook(
    request: WSGIRequest, gateway_config: "GatewayConfig", channel_slug: str
):
    payload = request.body
    sig_header = request.META["HTTP_STRIPE_SIGNATURE"]
    api_key = gateway_config.connection_params["secret_api_key"]
    endpoint_secret = gateway_config.connection_params.get("webhook_secret")

    if not endpoint_secret:
        logger.warning("Missing webhook secret on Saleor side.")
        response = HttpResponse(status=500)
        response.content = "Missing webhook secret on Saleor side."
        return response

    try:
        event = construct_stripe_event(
            api_key=api_key,
            payload=payload,
            sig_header=sig_header,
            endpoint_secret=endpoint_secret,
        )
    except ValueError as e:
        # Invalid payload
        logger.warning(
            "Received invalid payload for Stripe webhook", extra={"error": e}
        )
        return HttpResponse(status=400)
    except SignatureVerificationError as e:
        # Invalid signature
        logger.warning("Invalid signature for Stripe webhook", extra={"error": e})
        return HttpResponse(status=400)

    webhook_handlers = {
        WEBHOOK_SUCCESS_EVENT: handle_successful_payment_intent,
        WEBHOOK_AUTHORIZED_EVENT: handle_authorized_payment_intent,
        WEBHOOK_PROCESSING_EVENT: handle_processing_payment_intent,
        WEBHOOK_FAILED_EVENT: handle_failed_paym