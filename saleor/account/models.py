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
from django.utils.crypto import get_random_string
from django_countries.fields import Country, CountryField
from phonenumber_field.modelfields import PhoneNumber, PhoneNumberField

from ..app.models import App
from ..core.models import ModelWithExternalReference, ModelWithMetadata
from ..core.utils.json_serializer import CustomJsonEncoder
from ..order.models import Order
from ..permission.enums import AccountPermissions, BasePermissionEnum, get_permissions
from ..permission.models import Permission, PermissionsMixin, _user_has_perm
from . import CustomerEvents
from .validators import validate_possible_number


class PossiblePhoneNumberField(PhoneNumberField):
    """Less strict field for phone numbers written to database."""

    default_validators = [validate_possible_number]


class AddressQueryset(models.QuerySet["Address"]):
    def annotate_default(self, user):
        # Set default shipping/billing address pk to None
        # if default shipping/billing address doesn't exist
        default_shipping_address_pk, default_billing_address_pk = None, None
        if user.default_shipping_address:
            default_shipping_address_pk = user.default_shipping_address.pk
        if user.default_billing_address:
            default_billing_address_pk = user.default_billing_address.pk

        return user.addresses.annotate(
            user_default_shipping_address_pk=Value(
                default_shipping_address_pk, models.IntegerField()
            ),
            user_default_billing_address_pk=Value(
                default_billing_address_pk, models.IntegerField()
            ),
        )


AddressManager = models.Manager.from_queryset(AddressQueryset)


class Address(ModelWithMetadata):
    first_name = models.CharField(max_length=256, blank=True)
    last_name = models.CharField(max_length=256, blank=True)
    company_name = models.CharField(max_length=256, blank=True)
    street_address_1 = models.CharField(max_length=256, blank=True)
    street_address_2 = models.CharField(max_length=256, blank=True)
    city = models.CharField(max_length=256, blank=True)
    city_area = models.CharField(max_length=128, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = CountryField()
    country_area = models.CharField(max_length=128, blank=True)
    phone = PossiblePhoneNumberField(blank=True, default="", db_index=True)

    objects = AddressManager()

    class Meta:
        ordering = ("pk",)
        indexes = [
            *ModelWithMetadata.Meta.indexes,
            GinIndex(
                name="address_search_gin",
                # `opclasses` and `fields` should be the same length
                fields=["first_name", "last_name", "city", "country"],
                opclasses=["gin_trgm_ops"] * 4,
            ),
            GinIndex(
                name="warehouse_address_search_gin",
                # `opclasses` and `fields` should be the same length
                fields=[
                    "company_name",
                    "street_address_1",
                    "street_address_2",
                    "city",
                    "postal_code",
                    "phone",
                ],
                opclasses=["gin_trgm_ops"] * 6,
            ),
        ]

    def __eq__(self, other):
        if not isinstance(other, Address):
            return False
        return self.as_data() == other.as_data()

    __hash__ = models.Model.__hash__

    def as_data(self):
        """Return the address as a dict suitable for passing as kwargs.

        Result does not contain the primary key or an associated user.
        """
        data = model_to_dict(self, exclude=["id", "user"])
        if isinstance(data["country"], Country):
            data["country"] = data["country"].code
        if isinstance(data["phone"], PhoneNumber):
            data["phone"] = data["phone"].as_e164
        return data

    def get_copy(self):
        """Return a new instance of the same address."""
        return Address.objects.create(**self.as_data())


class UserManager(BaseUserManager["User"]):
    def create_user(
        self, email, password=None, is_staff=False, is_active=True, **extra_fields
    ):
        """Create a user instance with the given email and password."""
        email = UserManager.normalize_email(email)
        # Google OAuth2 backend send unnecessary username field
        extra_fields.pop("username", None)

        user = self.model(
            email=email, is_active=is_active, is_staff=is_staff, **extra_fields
        )
        if password:
            user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        user = self.create_user(
            email, password, is_staff=True, is_superuser=True, **extra_fields
        )
        group, created = Group.objects.get_or_create(name="Full Access")
        if created:
            group.permissions.add(*get_permissions())
        group.user_set.add(user)
        return user

    def customers(self):
        orders = Order.objects.values("user_id")
        return self.get_queryset().filter(
            Q(is_staff=False)
            | (Q(is_staff=True) & (Exists(orders.filter(user_id=OuterRef("pk")))))
        )

    def staff(self):
        return self.get_queryset().filter(is_staff=True)


class User(
    PermissionsMixin, ModelWithMetadata, AbstractBaseUser, ModelWithExternalReference
):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=256, blank=True)
    last_name = models.CharField(max_length=256, blank=True)
    addresses = models.ManyToManyField(
        Address, blank=True, related_name="user_addresses"
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    note = models.TextField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    default_shipping_address = models.ForeignKey(
        Address, related_name="+", null=True, blank=True, on_delete=models.SET_NULL
    )
    default_billing_address = models.ForeignKey(
        Address, related_name="+", null=True, blank=True, on_delete=models.SET_NULL
    )
    avatar = models.ImageField(upload_to="user-avatars", blank=True, null=True)
    jwt_token_key = models.CharField(
        max_length=12, default=partial(get_random_string, length=12)
    )
    language_code = models.CharField(
        max_length=35, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE
    )
    search_document = models.TextField(blank=True, default="")
    uuid = models.UUIDField(default=uuid4, unique=True)

    USERNAME_FIELD = "email"

    objects = UserManager()

    class Meta:
        ordering = ("email",)
        permissions = (
            (AccountPermissions.MANAGE_USERS.codename, "Manage customers."),
            (AccountPermissions.MANAGE_STAFF.codename, "Manage staff."),
            (AccountPermissions.IMPERSONATE_USER.codename, "Impersonate user."),
        )
        indexes = [
            *ModelWithMetadata.Meta.indexes,
            # Orders searching index
            GinIndex(
                name="order_user_search_gin",
                # `opclasses` and `fields` should be the same length
                fields=["email", "first_name", "last_name"],
                opclasses=["gin_trgm_ops"] * 3,
            ),
            # Account searching index
            GinIndex(
                name="user