
# Generated by Django 3.0.6 on 2020-07-09 11:02

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("discount", "0019_auto_20200217_0350"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="vouchercustomer",
            options={"ordering": ("voucher", "customer_email", "pk")},
        ),
        migrations.AlterModelOptions(
            name="vouchertranslation",
            options={"ordering": ("language_code", "voucher", "pk")},
        ),
    ]