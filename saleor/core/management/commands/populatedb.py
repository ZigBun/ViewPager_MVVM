from io import StringIO

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from ....account.utils import create_superuser
from ...utils.random_data import (
    add_address_to_admin,
    create_channels,
    create_checkout_with_custom_prices,
    create_checkout_with_preorders,
    create_checkout_with_same_variant_in_multiple_lines,
    create_gift_cards,
    create_menus,
    create_orders,
    create_page_type,
    create_pages,
    create_permission_groups,
    create_product_sales,
    create_products_by_schema,
    create_shipping_zones,
    create_staffs,
    create_tax_classes,
    create_users,
    create_vouchers,
    create_warehouses,
)


class Command(BaseCommand):
    help = "Populate database with test objects"
    placeholders_dir = "saleor/static/placeholders/"

    def add_arguments(self, parser):
        parser.add_argument(
            "--createsuperuser",
            action="store_true",
            dest="createsuperuser",
            default=False,
            help="Create admin account",
        )
        parser.add_argument("--user_password", type=str, default="password")
        parser.add_argument("--staff_password", type=str, default="password")
        parser.add_argument("--superuser_password", type=str, default="admin")
        parser.add_argument(
            "--withoutimages",
            action="store_true",
            dest="withoutimages",
            default=False,
            help="Don't create product images",
        )
        parser.add_argument(
            "--skipsequencereset",
            action="store_true",
            dest="skipsequencereset",
            default=False,
            help="Don't reset SQL sequences that are out of sync.",
        )

    def sequence_reset(self):
        """Run a SQL sequence reset on all saleor.* apps.

        When a value is manually assigned to an auto-incrementing field
        it doesn't update the field's sequence, which might cause a conflict
        later on.
        """
        commands = StringIO()
        for app in apps.get_app_configs():
            if "saleor" in app.name:
                call_command(
                    "sqlsequencereset", app.label, stdout=commands, no_color=True
                )
        with connection.cursor() as cursor:
            cursor.execute(commands.getvalue())

    def handle(self, *args, **options):
        # set only our custom plugin to not call external API when preparing
        # example database
        user_password = options["user_password"]
        staff_password = options["staff_password"]
        superuser_password = options["superuser_password"]
        settings.PLUGINS = [
            "saleor.payment.gateways.dummy.plugin.DummyGatewayPlugin",
            "saleor.payment.ga