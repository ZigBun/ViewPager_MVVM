import json
from unittest.mock import ANY, Mock, patch

import graphene
import pytest
import requests
from django.core.exceptions import ValidationError
from freezegun import freeze_time

from ...core.utils.json_serializer import CustomJsonEncoder
from ...webhook.event_types import WebhookEventAsyncType
from ...webhook.payloads import generate_meta, generate_requestor
from ..installation_utils import (
    AppInstallationError,
    install_app,
    validate_app_install_response,
)
from ..models import App
from ..types import AppExtensionMount, AppExtensionTarget


def test_validate_app_install_response():
    error_message = "Test error msg"
    response = Mock(spec=requests.Response)
    response.raise_for_status.side_effect = requests.HTTPError
    response.json.return_value = {"error": {"message": error_message}}

    with pytest.raises(AppInstallationError) as error:
        validate_app_install_response(response)
    assert str(error.value) == error_message


@pytest.mark.parametrize("json_response", ({}, {"error": {}}, Exception))
def test_validate_app_install_response_when_wrong_error_message(json_response):
    response = Mock(spec=requests.Response)
    response.raise_for_status.side_effect = requests.HTTPError
    response.json.side_effect = json_response

    with pytest.raises(requests.HTTPError):
        validate_app_install_response(response)


def test_install_app_created_app(
    app_manifest, app_installation, monkeypatch, permission_manage_products
):
    # given
    app_manifest["permissions"] = ["MANAGE_PRODUCTS"]
    mocked_get_response = Mock()
    mocked_get_response.json.return_value = app_manifest

    monkeypatch.setattr(requests, "get", Mock(return_value=mocked_get_response))
    mocked_post = Mock()
    monkeypatch.setattr(requests, "post", mocked_post)

    app_installation.permissions.set([permission_manage_products])

    # when
    app, _ = install_app(app_installation, activate=True)

    # then
    mocked_post.assert_called_once_with(
        app_manifest["tokenTargetUrl"],
        headers={
            "Content-Type": "application/json",
            # X- headers will be deprecated in Saleor 4.0, proper headers are without X-
            "X-Saleor-Domain": "mirumee.com",
            "Saleor-Domain": "mirumee.com",
            "Saleor-Api-Url": "http://mirumee.com/graphql/",
        },
        json={"auth_token": ANY},
        timeout=ANY,
    )
    assert App.objects.get().id == app.id
    assert list(app.permissions.all()) == [permission_manage_products]


def test_install_app_created_app_with_audience(
    app_manifest, app_installation, monkeypatch, site_settings
):
    # given
    audience = f"https://{site_settings.site.domain}.com/app-123"
    app_manifest["audience"] = audience
    mocked_get_response = Mock()
    mocked_get_response.json.return_value = app_manifest

    monkeypatch.setattr(requests, "get", Mock(return_value=mocked_get_response))
    monkeypatch.setattr("saleor.app.installation_utils.send_app_token", Mock())

    # when
    app, _ = install_app(app_installation, activate=True)

    # then
    assert app.audience == audience


@freeze_time("2022-05-12 12:00:00")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_install_app_created_app_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    app_manifest,
    app_installation,
    monkeypatch,
    permission_manage_products,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webh