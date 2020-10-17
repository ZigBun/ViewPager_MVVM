import sys

from django.core.management.color import color_style
from django.db import IntegrityError, migrations, transaction
from django.db.models import Q

WARNING = """
    A problem arose migrating proxy model permissions for {old} to {new}.

      Permission(s) for {new} already existed.
      Codenames Q: {query}

    Ensure to audit ALL permissions for {old} and {new}.
"""


def update_proxy_model_permissions(
    apps, schema_editor, reverse=False
):  # noqa: D205, D212, D400, D415
    """
    Update the content_type of proxy model permissions to use the ContentType
    of the proxy model.
    """
    style = color_style()
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    alias = schema_editor.connection.alias
    for Model in apps.get_models():
        opts = Model._meta
        if not opts.proxy:
            continue
        proxy_default_permissions_codenames = [
            "%s_%s" % (action, opts.model_name) for action in o