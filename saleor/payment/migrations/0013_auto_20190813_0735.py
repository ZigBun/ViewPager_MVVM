
# Generated by Django 2.2.4 on 2019-08-13 12:35

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payment", "0012_transaction_customer_id")]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="kind",
            field=models.CharField(
                choices=[
                    ("auth", "Authorization"),
                    ("refund", "Refund"),
                    ("capture", "Capture"),
                    ("void", "Void"),
                    ("confirm", "Confirm"),
                ],
                max_length=10,
            ),
        )
    ]