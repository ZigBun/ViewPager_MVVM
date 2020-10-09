import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable, List, Optional, Tuple

import requests
from django.utils import timezone
from posuto import Posuto
from requests.auth import HTTPBasicAuth

from ....order.models import Order
from ... import PaymentError
from ...interface import AddressData, PaymentData, PaymentLineData, RefundData
from ...models import Payment
from ...utils import price_to_minor_unit
from .api_types import NPResponse, error_np_response
from .const import NP_ATOBARAI, REQUEST_TIMEOUT
from .errors import (
    BILLING_ADDRESS_INVALID,
    NO_BILLING_ADDRESS,
    NO_PSP_REFERENCE,
    NO_SHIPPING_ADDRESS,
    NO_TRACKING_NUMBER,
    NP_CONNECTION_ERROR,
    SHIPPING_ADDRESS_INVALID,
    SHIPPING_COMPANY_CODE_INVALID,
)
from .utils import (
    create_refunded_lines,
    notify_dashboard,
    np_atobarai_opentracing_trace,
)

if TYPE_CHECKING:
    from . import ApiConfig


logger = logging.getLogger(__name__)


def get_url(config: "ApiConfig", path: str = "") -> str:
    """Resolve test/production URLs based on the api config."""
    return f"{config.url}{path}"


def _request(
    config: "ApiConfig",
    method: str,
    path: str = "",
    json: Optional[dict] = None,
) -> requests.Response:
    trace_name = f"np-atobarai.request.{path.lstrip('/')}"
    with np_atobarai_opentracing_trace(trace_name):
        response = requests.request(
            method=method,
            url=get_url(config, path),
            timeout=REQUEST_TIMEOUT,
            json=json or {},
            auth=HTTPBasicAuth(config.merchant_code, config.sp_code),
            headers={"X-NP-Terminal-Id": config.terminal_id},
        )
        # NP Atobarai returns error codes with http status code 400
        # Because we want to pass those errors to the end user,
        # we treat 400 as valid response.
        if 400 < response.status_code <= 600:
            raise requests.HTTPError
        return response


def np_request(
    config: "ApiConfig", method: str, path: str = "", json: Optional[dict] = None
) -> NPResponse:
    try:
        response = _request(config, method, path, json)
        response_data = response.json()
        if "errors" in response_data:
            return NPResponse({}, response_data["errors"][0]["codes"])
        return NPResponse(response_data["results"][0], [])
    except requests.RequestException:
        logger.warning("Cannot connect to NP Atobarai.", exc_info=True)
        return NPResponse({}, [NP_CONNECTION_ERROR])


def handle_unrecoverable_state(
    order: Optional[Order],
    action: str,
    transaction_id: str,
    error_codes: Iterable[str],
) -> None:
    message = f"Payment #{transaction_id} {action.capitalize()} Unrecoverable Error"
    logger.error("%s: %s", message, ", ".join(error_codes))
    if order:
        notify_dashboard(order, message)


def health_check(config: "ApiConfig") -> bool:
    try:
        _request(config, "post", "/authorizations/find")
        return True
    except requests.RequestException:
        return False


def format_name(ad: AddressData) -> str:
    """Follow the Japanese name guidelines."""
    return f"{ad.last_name}　{ad.first_name}".strip()


def format_address(config: "ApiConfig", ad: AddressData) -> Optional[str]:
    """Follo