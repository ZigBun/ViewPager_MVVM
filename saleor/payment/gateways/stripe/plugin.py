import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound
from django.http.request import split_domain_port

from ....graphql.core.enums import PluginErrorCode
from ....plugins.base_plugin import BasePlugin, ConfigurationTypeField
from ... import TransactionKind
from ...interface import (
    CustomerSource,
    GatewayConfig,
    GatewayResponse,
    PaymentData,
    PaymentMethodInfo,
    StorePaymentMethodEnum,
)
from ...models import Transaction
from ...utils import price_from_minor_unit, price_to_minor_unit
from ..utils import get_supported_currencies
from .stripe_api import (
    cancel_payment_intent,
    capture_payment_intent,
    create_payment_intent,
    delete_webhook,
    get_or_create_customer,
    get_payment_method_details,
    is_secret_api_key_valid,
    list_customer_payment_methods,
    refund_payment_intent,
    retrieve_payment_intent,
    subscribe_webhook,
)
from .webhooks import handle_webhook

if TYPE_CHECKING:
    from ....plugins.models import PluginConfiguration

from .consts import (
    ACTION_REQUIRED_STATUSES,
    AUTHORIZED_STATUS,
    PLUGIN_ID,
    PLUGIN_NAME,
    PROCESSING_STATUS,
    SUCCESS_STATUS,
    WEBHOOK_PATH,
)

logger = logging.getLogger(__name__)


class StripeGatewayPlugin(BasePlugin):
    PLUGIN_NAME = PLUGIN_NAME
    PLUGIN_ID = PLUGIN_ID
    DEFAULT_CONFIGURATION = [
        {"name": "public_api_key", "value": None},
        {"name": "secret_api_key", "value": None},
        {"name": "automatic_payment_capture", "value": True},
        {"name": "supported_currencies", "value": ""},
        {"name": "webhook_endpoint_id", "value": None},
        {"name": "webhook_secret_key", "value": None},
    ]

    CONFIG_STRUCTURE = {
        "public_api_key": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide Stripe public API key.",
            "label": "Public API key",
        },
        "secret_api_key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide Stripe secret API key.",
            "label": "Secret API key",
        },
        "automatic_payment_capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Determines if Saleor should automatically capture payments.",
            "label": "Automatic payment capture",
        },
        "supported_currencies": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines currencies supported by gateway."
            " Please enter currency codes separated by a comma.",
            "label": "Supported currencies",
        },
        "webhook_endpoint_id": {
            "type": ConfigurationTypeField.OUTPUT,
            "help_text": "Unique identifier for the webhook endpoint object.",
            "label": "Webhook endpoint",
        },
    }

    def __init__(self, *, configuration, **kwargs):
        # Webhook details are not listed in CONFIG_STRUCTURE as user input is not
        # required here
        raw_configuration = {item["name"]: item["value"] for item in configuration}
        webhook_secret = raw_configuration.get("webhook_secret_key")

        super().__init__(configuration=configuration, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=PLUGIN_NAME,
            auto_capture=configuration["automatic_payment_capture"],
            supported_currencies=configuration["supported_currencies"],
            connection_params={
                "public_api_key": configuration["public_api_key"],
                "secret_api_key": configuration["secret_api_key"],
                "webhook_id": configuration["webhook_endpoint_id"],
                "webhook_secret": webhook_secret,
            },
            store_customer=True,
        )

    def webhook(self, request: WSGIRequest, path: str, previous_value) -> HttpResponse:
        config = self.config
        if not self.channel:
            return HttpResponseNotFound()
        if path.startswith(WEBHOOK_PATH, 1):  # 1 as we don't check the '/'
            return handle_webhook(request, config, self.channel.slug)
        logger.warning(
            "Received request to incorrect stripe path", extra={"path": path}
        )
        return HttpResponseNotFound()

    def token_is_required_as_payment_input(self, previous_value):
        if not self.active:
            return previous_value
        return False

    def get_supported_currencies(self, previous_value):
        if not self.active:
            return previous_value
        return get_supported_currencies(self.config, PLUGIN_NAME)

    @property
    def order_auto_confirmation(self):
        if not self.channel:
            return False
        return self.channel.automatically_confirm_all_new_orders

    def _get_transaction_details_for_stripe_status(
        self, status: str
    ) -> Tuple[str, bool]:
        kind = TransactionKind.AUTH
        action_required = True

        # payment still requires an action
        if status in ACTION_REQUIRED_STATUSES:
            kind = TransactionKind.ACTION_TO_CO