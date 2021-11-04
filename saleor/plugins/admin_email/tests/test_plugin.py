from dataclasses import asdict
from smtplib import SMTPNotSupportedError
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.core.exceptions import ValidationError
from django.core.mail.backends.smtp import EmailBackend

from ....core.notify_events import NotifyEventType
from ....graphql.tests.utils import get_graphql_content
from ...email_common import DEFAULT_EMAIL_VALUE, get_email_template
from ...manager import get_plugins_manager
from ...models import PluginConfiguration
from ..constants import (
    CSV_EXPORT_FAILED_TEMPLATE_FIELD,
    CSV_EXPORT_SUCCESS_TEMPLATE_FIELD,
    SET_STAFF_PASSWORD_TEMPLATE_FIELD,
    STAFF_ORDER_CONFIRMATION_TEMPLATE_FIELD,
)
from ..notify_events import (
    send_csv_export_failed,
    send_csv_export_success,
    send_set_staff_password_email,
    send_staff_order_confirmation,
    send_staff_reset_password,
)
from ..plugin import get_admin_event_map


def test_event_map():
    assert get_admin_event_map() == {
        NotifyEventType.STAFF_ORDER_CONFIRMATION: send_staff_order_confirmation,
        NotifyEventType.ACCOUNT_SET_STAFF_PASSWORD: send_set_staff_password_email,
        NotifyEventType.CSV_EXPORT_SUCCESS: send_csv_export_success,
        NotifyEventType.CSV_EXPORT_FAILED: send_csv_export_failed,
        NotifyEventType.ACCOUNT_STAFF_RESET_PASSWORD: send_staff_reset_password,
    }


@pytest.mark.parametrize(
    "event_type",
    [
        NotifyEventType.STAFF_ORDER_CONFIRMATION,
        NotifyEventType.ACCOUNT_SET_STAFF_PASSWORD,
        NotifyEventType.CSV_EXPORT_SUCCESS,
        NotifyEventType.CSV_EXPORT_FAILED,
        NotifyEventType.ACCOUNT_STAFF_RESET_PASSWORD,
    ],
)
@patch("saleor.plugins.admin_email.plugin.get_admin_event_map")
def test_notify(mocked_get_event_map, event_type, admin_email_plugin):
    payload = {
        "field1": 1,
        "field2": 2,
    }
    mocked_event = Mock()
    mocked_get_event_map.return_value = {event_type: mocked_event}

    plugin = admin_email_plugin()
    plugin.notify(event_type, payload, previous_value=None)

    mocked_event.assert_called_with(payload, asdict(plugin.config), plugin)


@patch("saleor.plugins.admin_email.plugin.get_admin_event_map")
def test_notify_event_not_related(mocked_get_event_map, admin_email_plugin):
    event_type = NotifyEventType.ACCOUNT_SET_CUSTOMER_PASSWORD
    payload = {
        "field1": 1,
        "field2": 2,
    }

    mocked_event = Mock()
    mocked_get_event_map.return_value = {event_type: mocked_event}

    plugin = admin_email_plugin()
    plugin.notify(event_type, payload, previous_value=None)

    assert not mocked_event.called


@patch("saleor.plugins.admin_email.plugin.get_admin_event_map")
def test_notify_event_missing_handler(mocked_get_event_map, admin_email_plugin):
    event_type = NotifyEventType.CSV_EXPORT_FAILED
    payload = {
        "field1": 1,
        "field2": 2,
    }

    mocked_event_map = MagicMock()
    mocked_get_event_map.return_value = mocked_event_map

    plugin = admin_email_plugin()
    plugin.notify(event_type, payload, previous_value=None)

    assert not mocked_event_map.__getitem__.called


@patch("saleor.plugins.admin_email.plugin.get_admin_event_map")
def test_notify_event_plugin_is_not_active(mocked_get_event_map, admin_email_plugin):
    event_type = NotifyEventType.CSV_EXPORT_FAILED
    payload = {
        "field1": 1,
        "field2": 2,
    }

    plugin = admin_email_plugin(active=False)
    plugin.notify(event_type, payload, previous_value=None)

    assert not mocked_get_event_map.called


def test_save_plugin_configuration_tls_and_ssl_are_mutually_exclusive(
    admin_email_plugin,
):
    plugin = admin_email_plugin()
    configur