
# Generated by Django 3.2.6 on 2021-08-17 10:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discount", "0027_auto_20210719_2155"),
    ]

    operations = [
        migrations.AlterField(
            model_name="saletranslation",
            name="language_code",
            field=models.CharField(max_length=35),
        ),
        migrations.AlterField(
            model_name="vouchertranslation",
            name="language_code",
            field=models.CharField(max_length=35),
        ),
    ]