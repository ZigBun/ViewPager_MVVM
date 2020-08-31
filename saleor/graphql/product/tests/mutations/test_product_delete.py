from unittest.mock import patch

import graphene
import pytest
from django.utils.functional import SimpleLazyObject
from freezegun import freeze_time
from prices import Money, TaxedMoney

from .....attribute.models import AttributeValue
from .....attribute.utils import associate_attribute_values_to_instance
from .....graphql.tests.utils import get_graphql_content
from .....order import OrderEvents, OrderStatus
from .....order.models import OrderEvent, OrderLine
fr