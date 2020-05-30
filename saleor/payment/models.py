from decimal import Decimal
from operator import attrgetter

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import JSONField
from django_prices.models import MoneyField
from prices import Money

from ..checkout.models import Checkout
from ..core.models import ModelWithMetadata
from ..core.taxes import zero_money
from ..permission.enums import PaymentPermissions
from . import (
    ChargeStatus,
    CustomPaymentChoices,
    StorePaymentMethod,
    TransactionAction,
    TransactionKind,
    TransactionStatus,
)


class TransactionItem(ModelWithMetadata):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=512, blank=True, default="")
    type = models.CharField(max_length=512, blank=True, default="")
    reference = models.CharField(max_length=512, blank=True, default="")
    available_actions = ArrayField(
        models.CharField(max_length=128, choices=TransactionAction.CHOICES),
        default=list,
    )

    currency = models.CharField(max_length=settings.DEFAULT_CURRENCY_CODE_LENGTH)

    amount_charged = MoneyField(amount_field="charged_value", currency_field="currency")
    charged_value = models.DecimalField(
        max_digits=settings.DEFAULT_MAX_DIGITS,
        decimal_places=settings.DEFAULT_DECIMAL_PLACES,
        default=Decimal("0"),
    )
    amount_authorized = MoneyField(
        amount_field="authorized_value", currency_field="currency"
    )
    authorized_value = models.DecimalField(
        max_digits=settings.DEFAULT_MAX_DIGITS,
        decimal_places=settings.DEFAULT_DECIMAL_PLACES,
        default=Decimal("0"),
    )
    amount_refunded = MoneyField(
        amount_field="refunded_value", currency_field="currency"
    )
    refunded_value = models.DecimalField(
        max_digits=settings.DEFAULT_MAX_DIGITS,
        decimal_places=settings.DEFAULT_DECIMAL_PLACES,
        default=Decimal("0"),
    )
    amount_voided = MoneyField(amount_field="voided_value", currency_field="cu