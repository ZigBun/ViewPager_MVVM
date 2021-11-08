from django.conf import settings

from ....channel.models import Channel
from ....core.management.commands.populatedb import Command as PopulateDBCommand
from ....payment.gateways.braintree.plugin import BraintreeGatewayPlugin
from ....plugins.manager import get_plugins_manager


def configure_braintree():
    braintree_api_key = getattr(settings, "BRAINTREE_API_KEY", "")
    braintree_merchant_id = getattr(settings, "BRAINTREE_MERCHANT_ID", "")
    braintree_secret = getattr(settings, "BRAINTREE_SECRET_API_KEY", "")

    if not (braintree_api_key and braintree_merchant_id and braintree_secret):
        return False

    channels = Channel.objects.all()
    manager = get_plugins_manager()
    for channel in channels:
        manager.save_plugin_configuration(
            BraintreeGatewayPlugin.PLUGIN_ID,
            channel.slug,
            {
                "active": True,
   