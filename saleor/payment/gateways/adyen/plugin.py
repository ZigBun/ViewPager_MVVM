import json
from typing import List, Optional
from urllib.parse import urlencode, urljoin

import opentracing
import opentracing.tags
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound
from django.urls import reverse
from requests.exceptions import SSLError

from ....checkout.models import Checkout
from ....core.utils import build_absolute_uri
from ....core.utils.url import prepare_url
from ....order.events import external_notification_event
from ....plugins.base_plugin import BasePlugin, ConfigurationTypeField
from ....plugins.error_codes import PluginErrorCode
from ....plugins.models import PluginConfiguration
from ... import PaymentError, TransactionKind
from ...interface import (
    GatewayConfig,
    GatewayResponse,
    InitializedPaymentResponse,
    PaymentData,
    PaymentGateway,
)
from ...models import Payment, Transaction
from ..utils import get_supported_currencies
from .utils.apple_pay import initialize_apple_pay, make_request_to_initialize_apple_pay
from .utils.common import (
    AUTH_STATUS,
    FAILED_STATUSES,
    PENDING_STATUSES,
    api_call,
    call_capture,
    call_refund,
    get_payment_method_info,
    get_request_data_for_check_payment,
    initialize_adyen_client,
    request_data_for_gateway_config,
    request_data_for_payment,
    request_for_payment_cancel,
    update_payment_with_action_required_data,
)
from .webhooks import handle_additional_actions, handle_webhook

GATEWAY_NAME = "Adyen"
WEBHOOK_PATH = "/webhooks"
ADDITIONAL_ACTION_PATH = "/additional-actions"


class AdyenGatewayPlugin(BasePlugin):
    PLUGIN_ID = "mirumee.payments.adyen"
    PLUGIN_NAME = GATEWAY_NAME
    CONFIGURATION_PER_CHANNEL = True
    DEFAULT_CONFIGURATION = [
        {"name": "merchant-account", "value": None},
        {"name": "api-key", "value": None},
        {"name": "supported-currencies", "value": ""},
        {"name": "client-key", "value": ""},
        {"name": "live", "value": ""},
        {"name": "adyen-auto-capture", "value": True},
        {"name": "auto-capture", "value": False},
        {"name": "hmac-secret-key", "value": ""},
        {"name": "notification-user", "value": ""},
        {"name": "notification-password", "value": ""},
        {"name": "enable-native-3d-secure", "value": False},
        {"name": "apple-pay-cert", "value": None},
    ]

    CONFIG_STRUCTURE = {
        "api-key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": (
                "To submit payments to Adyen, you'll be making API requests that are "
                "authenticated with an API key. You can generate API keys on your "
                "Customer Area."
            ),
            "label": "API key",
        },
        "merchant-account": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Your merchant account name.",
            "label": "Merchant Account",
        },
        "supported-currencies": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines currencies supported by gateway."
            " Please enter currency codes separated by a comma.",
            "label": "Supported currencies",
        },
        "client-key": {
            "type": ConfigurationTypeField.STRING,
            "help_text": (
                "The client key is a public key that uniquely identifies a web service "
                "user. Each web service user has a list of allowed origins, or domains "
                "from which we expect to get your requests. We make sure data cannot "
                "be accessed by unknown parties by using Cross-Origin Resource Sharing."
                "Not required for Android or iOS app."
            ),
            "label": "Client Key",
        },
        "live": {
            "type": ConfigurationTypeField.STRING,
            "help_text": (
                "Leave it blank when you want to use test env. To communicate with the"
                " Adyen API you should submit HTTP POST requests to corresponding "
                "endpoints. These endpoints differ for test and live accounts, and also"
                " depend on the data format (SOAP, JSON, or FORM) you use to submit "
                "data to the Adyen payments platform. "
                "https://docs.adyen.com/development-resources/live-endpoints"
            ),
            "label": "Live",
        },
        "adyen-auto-capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": (
                "All authorized payments will be marked as captured. This should only"
                " be enabled if Adyen is configured to auto-capture payments."
                " Saleor doesn't support the delayed capture Adyen feature."
            ),
            "label": "Assume all authorizations are automatically captured by Adyen",
        },
        "auto-capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": (
                "If enabled, Saleor will automatically capture funds. If, disabled, the"
                " funds are blocked but need to be captured manually."
            ),
            "label": "Automatically capture funds when a payment is made",
        },
        "hmac-secret-key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": (
                "Provide secret key generated on Adyen side."
                "https://docs.adyen.com/development-resources/webhooks#set-up-notificat"
                "ions-in-your-customer-area."
            ),
            "label": "HMAC secret key",
        },
        "notification-user": {
            "type": ConfigurationTypeField.STRING,
            "help_text": (
                "Base User provided on the Adyen side to authenticate incoming "
                "notifications. https://docs.adyen.com/development-resources/webhooks#"
                "set-up-notifications-in-your-customer-area "
            ),
            "label": "Notification user",
        },
        "notification-password": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": (
                "User password provided on the Adyen side for authenticate incoming "
                "notifications. https://docs.adyen.com/development-resources/webhooks#"
                "set-up-notifications-in-your-customer-area "
            ),
            "label": "Notification password",
        },
        "enable-native-3d-secure": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": (
                "Saleor uses 3D Secure redirect authentication by default. If you want"
                " to use native 3D Secure authentication, enable this option. For more"
                " details see Adyen documentation: native - "
                "https://docs.adyen.com/checkout/3d-secure/native-3ds2, redirect"
                " - https://docs.adyen.com/checkout/3d-secure/redirect-3ds2-3ds1"
            ),
            "label": "Enable native 3D Secure",
        },
        "apple-pay-cert": {
            "type": ConfigurationTypeField.SECRET_MULTILINE,
            "help_text": (
                "Follow the Adyen docs related to activating the Apple Pay for the "
                "web - https://docs.adyen.com/payment-methods/apple-pay/"
                "enable-apple-pay. This certificate is only required when you offer "
                "the Apple Pay as a web payment method.  Leave it blank if you don't "
                "offer Apple Pay or offer it only as a payment method in your iOS app."
            ),
            "label": "Apple Pay certificate",
        },
        "webhook-endpoint": {
            "type": ConfigurationTypeField.OUTPUT,
            "help_text": (
                "Endpoint which should be used to activate Adyen's webhooks. "
                "More details can be find here: "
                "https://docs.adyen.com/development-resources/webhooks"
            ),
            "label": "Webhook endpoint",
        },
    }

    def __init__(self, *args, **kwargs):
        channel = kwargs["channel"]
        raw_configuration = kwargs["configuration"].copy()
        self._insert_webhook_endpoint_to_configuration(raw_configuration, channel)
        kwargs["configuration"] = raw_configuration

        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=configuration["auto-capture"],
            supported_currencies=configuration["supported-currencies"],
            connection_params={
                "api_key": configuration["api-key"],
                "merchant_account": configuration["merchant-account"],
                "client_key": configuration["client-key"],
                "live": configuration["live"],
                "webhook_hmac": configuration["hmac-secret-key"],
                "webhook_user": configuration["notification-user"],
                "webhook_user_password": configuration["notification-password"],
                "adyen_auto_capture": configuration["adyen-auto-capture"],
                "enable_native_3d_secure": configuration["enable-native-3d-secure"],
                "apple_pay_cert": configuration["apple-pay-cert"],
            },
        )
        self.adyen = initialize_adyen_client(self.config)

    def _insert_webhook_endpoint_to_configuration(self, raw_configuration, channel):
        updated = False
        for config in raw_configuration:
            if config["name"] == "webhook-endpoint":
                updated = True
                config["value"] = self._generate_webhook_url(channel)
        if not updated:
            raw_configuration.append(
                {
                    "name": "webhook-endpoint",
                    "value": self._generate_webhook_url(channel),
                }
            )

    def _generate_webhook_url(self, channel) -> str:
        api_path = reverse(
            "plugins-per-channel",
            kwargs={"plugin_id": self.PLUGIN_ID, "channel_slug": channel.slug},
        )
        base_url = build_absolute_uri(api_path)
      