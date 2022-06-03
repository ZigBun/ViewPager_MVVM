
# Generated by Django 3.0.5 on 2020-04-16 06:01

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("webhook", "0002_webhook_name"),
        ("account", "0043_rename_service_account_to_app"),
    ]

    state_operations = [
        migrations.RemoveField(
            model_name="webhook",
            name="app",
        ),
    ]

    operations = [
        migrations.RenameField(
            model_name="webhook", old_name="service_account", new_name="app"
        ),
        migrations.SeparateDatabaseAndState(state_operations=state_operations),
    ]