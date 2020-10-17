from typing import cast

import graphene
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import make_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from ....account import events as account_events
from ....account import models
from ....account.error_codes import AccountErrorCode
from ....account.notifications import (
    send_password_reset_notification,
    send_set_password_notification,
)
from ....account.search import prepare_user_search_document_value
from ....account.utils import retrieve_user_by_email
from ....checkout import AddressType
from ....core.exceptions import PermissionDenied
from ....core.tracing import traced_atomic_transaction
from ....core.utils.url import validate_storefront_url
from ....giftcard.utils import assign_user_gift_cards
from ....graphql.utils import get_user_or_app_from_context
from ....order.utils import match_orders_with_new_user
from ....permission.auth_filters import AuthorizationFilters
from ....permission.enums import AccountPermissions
from ...account.i18n import I18nMixin
from ...account.types import Address, AddressInput, User
from ...app.dataloaders import get_app_promise
from ...channel.utils import clean_channel, validate_channel
from ...core import ResolveInfo
from ...core.context import disallow_replica_in_context
from ...core.descriptions import ADDED_IN_310
from ...core.enums import LanguageCodeEnum
from ...core.mutations import (
    BaseMutation,
    ModelDeleteMutation,
    ModelMutation,
    validation_error_to_error_type,
)
from ...core.types import AccountError
from ...plugins.dataloaders import get_plugin_manager_promise
from .authentication import CreateToken

BILLING_ADDRESS_FIELD = "default_billing_address"
SHIPPING_ADDRESS_FIELD = "default_shipping_address"
INVALID_TOKEN = "Invalid or expired token."


def check_can_edit_address(context, address):
    """Determine whether the user or app can edit the given address.

    This method assumes that an address can be edited by:
    - apps with manage users permission
    - staff with manage users permission
    - customers associated to the given address.
    """
    requester = get_user_or_app_from_context(context)
    if requester and requester.has_perm(AccountPermissions.MANAGE_USERS):
        return True
    app = get_app_promise(context).get()
    if not app and context.user:
        is_owner = context.user.addresses.filter(pk=address.pk).exists()
        if is_owner:
            return True
    raise PermissionDenied(
        permissions=[AccountPermissions.MANAGE_USERS, AuthorizationFilters.OWNER]
    )


class SetPassword(CreateToken):
    class Arguments:
        token = graphene.String(
            description="A one-time token required to set the password.", required=True
        )
        email = graphene.String(required=True, description="Email of a user.")
        password = graphene.String(required=True, description="Password of a user.")

    class Meta:
        description = (
            "Sets the user's password from the token sent by email "
            "using the RequestPasswordReset mutation."
        )
        error_type_class = AccountError
        error_type_field = "account_errors"

    @classmethod
    def mutate(  # type: ignore[override]
        cls, root, info: ResolveInfo, /, *, email, password, token
    ):
        disallow_replica_in_context(info.context)
        manager = get_plugin_manager_promise(info.context).get()
        result = manager.perform_mutation(
            mutation_cls=cls,
            root=root,
            info=info,
            data={"email": email, "password": password, "token": token},
        )
        if result is not None:
            return result

        try:
            cls._set_password_for_user(email, password, token)
        except ValidationError as e:
            errors = validation_error_to_error_type(e, AccountError)
            return cls.handle_typed_errors(errors)
        return super().mutate(root, info, email=email, password=password)

    @classmethod
    def _set_password_for_user(cls, email, password, token):
        try:
            user = models.User.objects.get(email=email)
        except ObjectDoesNotExist:
            raise ValidationError(
                {
                    "email": ValidationError(
                        "User doesn't exist", code=AccountErrorCode.NOT_FOUND.value
                    )
                }
            )
        if not default_token_generator.check_token(user, token):
            raise ValidationError(
                {
                    "token": ValidationError(
                        INVALID_TOKEN, code=AccountErrorCode.INVALID.value
                    )
                }
            )
        try:
            password_validation.validate_password(password, user)
        except ValidationError as error:
            raise ValidationError({"password": error})
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        account_events.customer_password_reset_event(user=user)


class RequestPasswordReset(BaseMutation):
    class Arguments:
        email = graphene.String(
            required=True,
            description="Email of the user that will be used for password recovery.",
        )
        redirect_url = graphene.String(
            required=True,
            description=(
                "URL of a view where users should be redirected to "
                "reset the password. URL in RFC 1808 format."
  