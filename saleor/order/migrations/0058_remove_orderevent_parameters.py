
# Generated by Django 2.0.8 on 2018-09-13 13:37

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("order", "0057_orderevent_parameters_new")]

    operations = [migrations.RemoveField(model_name="orderevent", name="parameters")]