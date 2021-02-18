
# Generated by Django 3.2.10 on 2022-01-04 12:39

from collections import defaultdict

from django.db import migrations

EMAIL_PLUGINS = [
    "mirumee.notifications.admin_email",
    "mirumee.notifications.user_email",
]

EMAIL_NAMES = [
    # user emails
    "account_confirmation",
    "account_set_customer_password",
    "account_delete",
    "account_change_email_confirm",
    "account_change_email_request",
    "account_password_reset",
    "invoice_ready",
    "order_confirmation",
    "order_confirmed",
    "order_fulfillment_confirmation",
    "order_fulfillment_update",
    "order_payment_confirmation",
    "order_canceled",
    "order_refund_confirmation",
    "send_gift_card",
    # admin emails
    "staff_order_confirmation_template",
    "set_staff_password_template",
    "csv_product_export_success_template",
    "csv_export_failed_template",
    "staff_password_reset_template",
]


def move_email_templates_to_separate_model(apps, schema):
    PluginConfiguration = apps.get_model("plugins", "PluginConfiguration")
    EmailTemplate = apps.get_model("plugins", "EmailTemplate")

    plugin_configs = PluginConfiguration.objects.filter(identifier__in=EMAIL_PLUGINS)

    for plugin_config_obj in plugin_configs.iterator():
        # Move email templates from PluginConfiguration.configuration JSON field to
        # EmailTemplate instances.
        email_templates = []
        for json_config in plugin_config_obj.configuration:
            config_key = json_config.get("name")
            if config_key in EMAIL_NAMES:
                config_value = json_config.get("value")
                email_template = EmailTemplate(
                    name=config_key,
                    value=config_value,
                    plugin_configuration=plugin_config_obj,
                )
                email_templates.append(email_template)

        EmailTemplate.objects.bulk_create(email_templates)

        # After saving new EmailTemplate instances to DB, recreate
        # PluginConfiguration.configuration list but with email templates omitted.
        new_configuration = []
        for json_config in plugin_config_obj.configuration:
            config_key = json_config.get("name")
            if config_key not in EMAIL_NAMES:
                new_configuration.append(json_config)

        plugin_config_obj.configuration = new_configuration
        plugin_config_obj.save(update_fields=["configuration"])


def revert_changes(apps, schema):
    EmailTemplate = apps.get_model("plugins", "EmailTemplate")
    PluginConfiguration = apps.get_model("plugins", "PluginConfiguration")

    templates_by_plugin_id = defaultdict(list)
    for et in EmailTemplate.objects.all():
        email_config = {"name": et.name, "value": et.value}
        templates_by_plugin_id[et.plugin_configuration_id].append(email_config)

    plugin_configs = PluginConfiguration.objects.filter(identifier__in=EMAIL_PLUGINS)
    for pc in plugin_configs:
        email_templates = templates_by_plugin_id.get(pc.id)
        if email_templates:
            pc.configuration.extend(email_templates)
        pc.save(update_fields=["configuration"])


class Migration(migrations.Migration):
    dependencies = [
        ("plugins", "0009_emailtemplate"),
    ]

    operations = [
        migrations.RunPython(
            move_email_templates_to_separate_model,
            reverse_code=revert_changes,
        ),
    ]