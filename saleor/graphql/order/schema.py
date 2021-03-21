from typing import List, Optional

import graphene
from graphql import GraphQLError

from ...order import models
from ...permission.enums import OrderPermissions
from ..core import ResolveInfo
from ..core.connection import create_connection_slice, filter_connection_queryset
from ..core.descriptions import ADDED_IN_310, DEPRECATED_IN_3X_FIELD
from ..core.enums import ReportingPeriod
from ..core.fields import ConnectionField, FilterConnectionField, PermissionsField
from ..core.sc