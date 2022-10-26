from unittest import mock

from ....account.notifications import get_default_user_payload
from ....order.notifications import get_default_order_payload
from ..notify_events import (
    send_csv_export_failed,
    send_csv_export_success,
    send_set_staff_password_email,
    send_staff_order_confirmation,
    send_staff_reset_password,
)


@mock.patch(
    "saleor.plugins.admin_email.notify_events.send_staff_password_reset_email_task."
    "delay"
)
def test_send_account_password_reset_event(
    mocked_email_task, customer_user, admin_email_plugin
):
    token = "token123"
    payload = {
        "user": get_default_user_payload(customer_user),
        "recipient_email": "user@example.com",
        "token": token,
        "reset_url": f"http://localhost:8000/redirect{token}",
        "domain": "localhost:8000",
        "site_name": "Saleor",
    }
    config = {"host": "localhost", "port": "1025"}
    send_staff_reset_password(
        payload=payload, config=config, plugin=admin_email_plugin()
    )
    mocked_email_task.assert_called_with(
        payload["recipient_email"], payload, config, mock.ANY, mock.ANY
    )


@mock.patch(
    "saleor.plugins.admin_email.notify_events.send_staff_password_reset_email_task."
    "delay"
)
def test_send_account_password_reset_event_empty_template(
    mocked_email_task, customer_user, admin_email_plugin
):
    token = "token123"
    payload = {
        "user": get_default_user_payload