
# Generated by Django 3.2.13 on 2022-06-14 08:42

from django.db import migrations


def add_relations_between_existing_channels_and_warehouses(apps, schema_editor):
    Channel = apps.get_model("channel", "Channel")
    Warehouse = apps.get_model("warehouse", "Warehouse")
    warehouse_ids = Warehouse.objects.values_list("id", flat=True)
    for channel in Channel.objects.iterator():
        channel.warehouses.set(warehouse_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0029_warehouse_channels"),
    ]

    operations = [
        migrations.RunPython(
            add_relations_between_existing_channels_and_warehouses,
            migrations.RunPython.noop,
        ),
    ]