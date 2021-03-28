from functools import partial
from typing import Iterable, Union
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField, Q, Value
from django.db.models.expressions import Exists, OuterRef
from django.forms.models import model_to_dict
from django.utils import timezone
from django.utils.crypto 