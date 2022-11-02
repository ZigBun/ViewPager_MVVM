from ..anonymize.plugin import AnonymizePlugin
from ..base_plugin import ConfigurationTypeField
from ..manager import get_plugins_manager
from ..tests.sample_plugins import PluginSample
from ..tests.utils import get_config_value


def test_update_config_items_keeps_bool_value(plugin_configuration, settings):
    settings.PLUGINS = ["saleor.plugins.tests.sample_plugins.PluginSample"]
    data_to_update = [
        {"name": "Username", "value": "new_admin@example.com"},
        {"name": "Use sandbox", "value": False},
    ]
    manager = get_plugins_manager()
    plugin_sample = manager.get_plugin(PluginSample.PLUGIN_ID)
    plugin_sample._update_config_items(data_to_update, plugin_sample.configuration)

    assert get_config_value("Use sandbox", plugin_sample.configuration) is False


def test_update_config_items_convert_to_bool_value():
    data_to_update = [
        {"name": "Username", "value": "new_admin@example.com"},
        {"name": "Use sandbox", "value": "false"},
    ]
    plugin_sample = PluginSample(
        configuration=PluginSample.DEFAULT_CONFIGURATION,
        active=PluginSample.DEFAULT_ACTIVE,
    )
    plugin_sample._update_config_items(data_to_update, plugin_sample.configuration)

    assert get_config_value("Use sandbox", plugin_sample.configuration) is False


def test_update_config_items_skips_new_keys_when_doesnt_exsist_in_conf_structure():
    data_to_update = [
        {"name": "New-field", "value": "content"},
    ]
    plugin_sample = PluginSample(
        configuration=PluginSample.DEFAULT_CONFIGURATION,
        active=PluginSample.DEFAULT_ACTIVE,
    )
    current_config = PluginSample.DEFAULT_CONFIGURATION

    plugin_sample._update_config_items(data_to_update, current_config)
    assert not all(
        [config_field["name"] == "New-field" for config_field in current_config]
    )


def test_update_config_items_adds_new_keys(monkeypatch):
    # Add new definition of field to CONFIG_STRUCTURE
    monkeypatch.setattr(
        PluginSample,
        "CONFIG_STRUCTURE",
        {
            "New-field": {
                "type": ConfigurationTypeField.STRING,
                "help_text": "New input field",
                "label": "New field",
            },
            **PluginSample.CONFIG_STRUCTURE,
        },
    )

    data_to_update = [
        {"name": "New-field", "value": "content"},
    ]
    plugin_sample = PluginSample(
        configuration=PluginSample.DEFAULT_CONFIGURATION,
        active=PluginSample.DEFAULT_ACTIVE,
    )
    current_config = [
        {"name"