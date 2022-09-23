from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List

import graphene
from django.core.exceptions import ValidationError

from ....core.tracing import traced_atomic_transaction
from ....disc