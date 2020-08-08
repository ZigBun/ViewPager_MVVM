from datetime import datetime, timedelta
from decimal import Decimal

import graphene
import pytest
import pytz
from django.utils import timezone

from .....attribute import AttributeInputType, AttributeType
from .....attribute.models import Attribute, AttributeValue
from .....attribute.utils import associate_attribute_values_to_instance
from .....core.postgres import FlatConcatSearchVector
from .....core.units import MeasurementUnits
from .....product import ProductTypeKind
from ..