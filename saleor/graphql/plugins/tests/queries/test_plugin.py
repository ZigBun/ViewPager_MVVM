import copy
from unittest import mock

import pytest

from .....plugins.manager import get_plugins_manager
from .....plugins.tests.sample_plugins import ChannelPluginSample, PluginSample
from ....tests.utils import assert_no_permission, get_graphql_content

PLUGIN_QUERY = """
    query plugin($id: ID!){
      plugin(id:$id){
        id
        name
        description
        globalConfiguration{
          active
          configuration{
            name
            value
            helpText
            type
            label
          }
          channel{
            id
            slug
          }
        }
        channelConfigurations{
          active
          channel{
            id
            slug
          }
          configuration{
            name
            value
            helpText
            type
            label
          }
        }
      }
    }
"""


@pytest.mark.parametrize(
    "password, expected_password, api_key, expected_api_key",
    [
        (None, None, None, None),
        ("ABCDEFGHIJ", "", "123456789", "6789"),
        ("", None, "", None),
        (None, None, "1234", "4"),
    ],
)
def test_query_plugin_hides_secret_fields(
    password,
    expected_password,
    api_key,
    expected_api_key,
    staff_api_client,
    permission_manage_plugins,
    settings,
):
    settings.PLUGINS = ["saleor.plugins.tests.sample_plugins.PluginSample"]
    manager = get_plugins_manager()
    plugin = manager.get_plugin(PluginSample.PLUGIN_ID)
    configuration = copy.deepcopy(plugin.configuration)
    for conf_field in configuration:
        if conf_field["name"] == "Password":
            conf_field["value"] = password
        if conf_field["name"] == "API private key":
            conf_field["value"] = api_key
    manager.save_plugin_configuration(
        PluginSample.PLUGIN_ID,
        None,
        {
            "active": True,
            "configuration": configuration,
            "name": PluginSample.PLUGIN_NAME,
        },
    )

    variables = {"id": plugin.PLUGIN_ID}
    staff_api_client.user.user_permissions.add(permission_manage_plugins)
    response = staff_api_client.post_graphql(PLUGIN_QUERY, variables)
    content = get_graphql_content(response)

    plugin = content["data"]["plugin"]

    for conf_field in plugin["globalConfiguration"]["configuration"]:
        if conf_field["name"] == "Password":
            assert conf_field["value"] == expected_password
        if conf_field["name"] == "API private key":
            assert conf_field["value"] == expected_api_key


@pytest.mark.parametrize(
    "password, expected_password, api_key, expected_api_key",
    [
        (None, None, None, None),
        ("ABCDEFGHIJ", "", "123456789", "6789"),
        ("", None, "", None),
        (None, None, "1234", "4"),
    ],
)
def test_query_plugin_hides_secret_fields_for_channel_configurations(
    password,
    expected_password,
    api_key,
    expected_api_key,
    staff_api_client,
    permission_manage_plugins,
    settings,
    channel_PLN,
):
    settings.PLUGINS = ["saleor.plugins.tests.sample_plugins.ChannelPluginSample"]
    manager = get_plugins_manager()

    plugin = manager.get_plugin(
        ChannelPluginSample.PLUGIN_ID, channel_slug=channel_PLN.slug
    )
    configuration = copy.deepcopy(plugin.configuration)
    for conf_field in configuration:
        if conf_field["name"] == "Password":
            conf_field["value"] = password
        if conf_field["name"] == "API private key":
            conf_field["value"] = api_key

    manager.save_plugin_configuration(
        PluginSample.PLUGIN_ID,
        channel_PLN.slug,
        {
            "active": True,
            "configuration": configuration,
            "name": PluginSample.PLUGIN_NAME,
        },
    )

    variables = {"id": plugin.PLUGIN_ID}
    staff_api_client.user.user_permissions.add(permission_manage_plugins)
    response = staff_api_client.post_graphql(PLUGIN_QUERY, variables)
    content = get_graphql_content(response)

    plugin = content["data"]["plugin"]

    assert not plugin["globalConfiguration"]
    assert len(plugin["channelConfigurations"]) == 1
    for conf_field in plugin["channelConfigurations"][0]["configuration"]:
        if conf_field["name"] == "Password":
            assert conf_field["value"] == expected_password
        if conf_field["name"] == "API private key":
            assert conf_field["value"] == expected_api_key


def test_query_plugin_configuration(
    staff_api_client, permission_manage_plugins, settings
):
    settings.PLUGINS = ["saleor.plugins.tests.sample_plugins.PluginSample"]
    manager = get_plugins_manager()
    sample_plugin = manager.get_plugin(PluginSample.PLUGIN_ID)

    variables = {"id": sample_plugin.PLUGIN_ID}
    staff_api_client.user.user_permissions.add(permission_manage_plugins)
    response = staff_api_client.post_graphql(PLUGIN_QUERY, variables)
    content = get_graphql_content(response)
    plugin = content["data"]["plugin"]
    assert plugin["name"] == sample_plugin.PLUGIN_NAME
    assert plugin["id"] == sample_plugin.PLUGIN_ID
    assert plugin["description"] == sample_plugin.PLUGIN_DESCRIPTION

    assert plugin["globalConfiguration"]["active"] == sample_plugin.active
    configuration_item = plugin["globalConfiguration"]["configuration"][0]
    assert configuration_item["name"] == sample_plugin.configuration[0]["name"]
    assert configuration_item["value"] == sample_plugin.configuration[0]["value"]


def test_query_plugin_configuration_for_channel_configurations(
    staff_api_client, permission_manage_plugins, settings, channel_PLN
):
    settings.PLUGINS = ["saleor.plugins.tests.sample_plugins.ChannelPluginSample"]
    manager = get_plugins_manager()
    sample_plugin = manager.get_plugin(
        ChannelPluginSample.PLUGIN_ID, channel_slug=channel_PLN.slug
    )

    variables = {"id": sample_plugin.PLUGIN_ID}
    staff_api_client.user.user_permissions.add(permission_manage_plugins)
    response = staff_api_client.post_graphql(PLUGIN_QUERY, variables)
    content = get_graphql_content(response)
    plugin = content["data"]["plugin"]
    assert plugin["name"] == sample_plugin.PLUGIN_NAME
    assert plugin["id"] == sample_plugin.PLUGIN_ID
    assert plugin["description"] == sample_plugin.PLUGIN_DESCRIPTION

    assert not plugin["globalConfiguration"]
    assert len(plugin["channelConfigurations"]) == 1
