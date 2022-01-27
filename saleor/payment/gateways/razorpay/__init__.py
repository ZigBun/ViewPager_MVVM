import logging
import uuid
from decimal import Decimal
from typing import Dict

import opentracing
import opentracing.tags
import razorpay
import razorpay.errors

from ... import TransactionKind
from ...interface import GatewayConfig, GatewayResponse, PaymentData
from . import errors
from .utils import get_amount_for_razorpay, get_error_response

# The list of currencies supported by razorpay
SUPPORTED_CURRENCIES = ("INR",)

# Define what are the razorpay exceptions,
# as the razorpay provider doesn't define a base exception as of now.
RAZORPAY_EXCEPTIONS = (
    razorpay.errors.BadRequestError,
    razorpay.errors.GatewayError,
    razorpay.errors.ServerError,
)

# Get the logger for this file, it will allow us to log
# error responses from razorpay.
logger = logging.getLogger(__name__)


def _generate_response(
    payment_information: PaymentData, kind: str, data: Dict
) -> GatewayResponse:
    """Generate Saleor transaction information from the payload or from passed data."""
    return GatewayRespon