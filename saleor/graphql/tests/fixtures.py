import json
import logging
from unittest import mock
from unittest.mock import Mock

import graphene
import pytest
from django.core.serializers.json import DjangoJSONEncoder
from django.test.client import MULTIPART_CONTENT, Client
from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from ...account.models import User
from ...core.jwt import create_access_token
from ...plugins.manager import get_plugins_manager
from ...tests.utils import flush_post_commit_hooks
from ..utils import handled_errors_logger, unhandled_errors_logger
from .utils import assert_no_permission

API_PATH = reverse("api")


class ApiClient(Client):
    """GraphQL API client."""

    def __init__(self, *args, **kwargs):
        user = kwargs.p