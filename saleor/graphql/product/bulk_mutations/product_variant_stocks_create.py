from collections import defaultdict
from typing import List

import graphene
from django.core.exceptions import ValidationError
from django.db import transaction

from ....core.tracing import traced_atomic_transaction
from ....permission.enums import ProductPermissions
from ....warehouse.error_codes import StockErrorCode
from ...channel 