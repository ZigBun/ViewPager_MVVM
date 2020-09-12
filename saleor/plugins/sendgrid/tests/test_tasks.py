from dataclasses import asdict
from unittest.mock import Mock, patch

import pytest

from ....account import CustomerEvents
from ....account.models import CustomerEvent
from ....account.notifications import get_default_user_payload
from ....giftcard import GiftCardEvents
from ....giftcard.models import GiftCardEvent
from ....graphql.core.utils import to_global_id_or_none
from ....invoice import InvoiceEvents
from ....invoice.models import Invoice, InvoiceEvent
from ....order import OrderEvents, OrderEventsEmails
from ....order.models import OrderEvent
from ....order.notifications import (
    get_default_fulfillment_payload,
    get_default_order_payload,
)
from ..tasks import (
    send_account_confirmation_email_task,
    send_account_delete_confirmation_email_task,
    send_email,
    send_fulfillment_confirmation_email_task,
    send_fulfillment_update_email_task,
    send_gift_card_email_task,
    send_invoice_email_task,
    send_order_canceled_email_task,
    send_order_confirmation_email_task,
    send_order_confirmed_email_task,
    send_order_refund_email_task,
    send_password_reset_email_task,
    send_payment_confirmation_email_task,
    send_request_email_change_email_task,
    send_set_user_password_email_task,
    send_user_change_email_notification_task,
)


@pytest.fixture
def sample_payload(customer_user):
    token = "token123"
    return {
        "user": get_default_user_payload(customer_user),
        "recipient_email": "user@example.com",
        "token": token,
        "reset_url": f"http://localhost:8000/redirect{token}",
        "domain": "localhost:8000",
        "site_name": "Saleor",
    }


@patch("saleor.plugins.sendgrid.tasks.Mail")
@patch("saleor.plugins.sendgrid.tasks.SendGridAPIClient.send")
def test_send_email(
    mocked_api_client, mocked_mail, sendgrid_email_plugin, sample_payload
):
    plugin = sendgrid_email_plugin(
        sender_name="Sender Name",
        sender_address="sender@example.com",
        api_key="123",
    )
    template_id = "ABC"
    recipient_email = sample_payload["recipient_email"]

    config = plugin.config

    mock_message = Mock()
    mocked_mail.return_value = mock_message

    send_email(config, template_id=template_id, payload=sample_payload)

    mocked_mail.assert_called_with(
        from_email=(config.sender_address, config.sender_name),
        to_emails=recipient_email,
    )

    mock_message.dynamic_template_data = sample_payload
    mock_message.template_id = template_id

    mocked_api_client.assert_called_with(mock_message)


@patch("saleor.plugins.sendgrid.tasks.send_email")
def test_send_account_confirmation_email_task(
    mocked_send_email, customer_user, sendgrid_email_plugin
):
    template_id = "ABC1"
    recipient_email = "admin@example.com"
    token = "token123"
    payload = {
        "user": get_default_user_payload(customer_user),
        "recipient_email": recipient_email,
        "token": token,
        "reset_url": f"http://localhost:8000/redirect{token}",
        "domain": "localhost:8000",
        "site_name": "Saleor",
 