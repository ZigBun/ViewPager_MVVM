
# Generated by Django 3.1.7 on 2021-03-26 08:37

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0023_auto_20201110_0834"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="error",
            field=models.CharField(max_length=256, null=True),
        ),
    ]