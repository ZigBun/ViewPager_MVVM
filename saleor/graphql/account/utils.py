from collections import defaultdict
from typing import TYPE_CHECKING, List, Optional, Set, Union

import graphene
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ValidationError
from django.db.models import Q, Value
from django.db.models.functions import Concat
from graphene.utils.str_converters import to_camel_case

from ...account import events as account_events
from ...account.error_codes import AccountErrorCode
from ...account.models import Group, User
from ...core.exceptions import PermissionDenied
from ...permission.auth_filters import AuthorizationFilters
from ...permission.enums import AccountPermissions
from ...permission.utils import has_one_of_permissions
from ..app.dataloaders import get_app_promise
from ..core import ResolveInfo, SaleorContext

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ...app.models import App


class UserDeleteMixin:
    class Meta:
        abstract = True

    @classmethod
    def clean_instance(cls, info: ResolveInfo, instance) -> None:
        user = info.context.user
        if instance == user:
            raise ValidationError(
                {
                    "id": ValidationError(
                        "You cannot delete your own account.",
                        code=AccountErrorCode.DELETE_OWN_ACCOUNT.value,
                    )
                }
            )
        elif instance.is_superuser:
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Cannot delete this account.",
                        code=AccountErrorCode.DELETE_SUPERUSER_ACCOUNT.value,
                    )
                }
            )


class CustomerDeleteMixin(UserDeleteMixin):
    class Meta:
        abstract = True

    @classmethod
    def clean_instance(cls, info: ResolveInfo, instance) -> None:
        super().clean_instance(info, instance)
        if instance.is_staff:
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Cannot delete a staff account.",
                        code=AccountErrorCode.DELETE_STAFF_ACCOUNT.value,
                    )
                }
            )

    @classmethod
    def post_process(cls, info: ResolveInfo, deleted_count=1):
        app = get_app_promise(info.context).get()
        account_events.customer_deleted_event(
            staff_user=info.context.user,
            app=app,
            deleted_count=deleted_count,
        )


class StaffDeleteMixin(UserDeleteMixin):
    class Meta:
        abstract = True

    @classmethod
    def check_permissions(cls, context: SaleorContext, permissions=None, **data):
        if get_app_promise(context).get():
            raise PermissionDenied(
                message="Apps are not allowed to perform this mutation."
            )
        return super().check_permissions(context, permissions)  # type: ignore[misc] # mixin # noqa: E501

    @classmethod
    def clean_instance(cls, info: ResolveInfo, instance):
        errors: defaultdict[str, List[ValidationError]] = defaultdict(list)

        requestor = info.context.user

        cls.check_if_users_can_be_deleted(info, [instance], "id", errors)
        cls.check_if_requestor_can_manage_users(requestor, [instance], "id", errors)
        cls.check_if_removing_left_not_manageable_permissions(
            requestor, [instance], "id", errors
        )
        if errors:
            raise ValidationError(errors)

    @classmethod
    def check_if_users_can_be_deleted(cls, info: ResolveInfo, instances, field, errors):
        """Check if only staff users will be deleted. Cannot delete non-staff users."""
        not_staff_users = set()
        for user in instances:
            if not user.is_staff:
                not_staff_users.add(user)
            try:
                super().clean_instance(info, user)
            except ValidationError as error:
                errors["ids"].append(error)

        if not_staff_users:
            user_pks = [
                graphene.Node.to_global_id("User", user.pk) for user in not_staff_users
            ]
            msg = "Cannot delete a non-staff users."
            code = AccountErrorCode.DELETE_NON_STAFF_USER.value
            params = {"users": user_pks}
            errors[field].append(ValidationError(msg, code=code, params=params))

    @classmethod
    def check_if_requestor_can_manage_users(cls, requestor, instances, field, errors):
        """Requestor can't manage users with wider scope of permissions."""
        if requestor.is_superuser:
            return
        out_of_scope_users = get_out_of_scope_users(requestor, instances)
        if out_of_scope_users:
            user_pks = [
                graphene.Node.to_global_id("User", user.pk)
                for user in out_of_scope_users
            ]
            msg = "You can't manage this users."
            code = AccountErrorCode.OUT_OF_SCOPE_USER.value
            params = {"users": user_pks}
            error = ValidationError(msg, code=code, params=params)
            errors[field] = error

    @classmethod
    def check_if_removing_left_not_manageable_permissions(
        cls, requestor, users, field, errors: defaultdict[str, List[ValidationError]]
    ):
        """Check if after removing users all permissions will be manageable.

        After removing users, for each permission, there should be at least one
        active staff member who can manage it (has both “manage staff” and
        this permission).
        """
        if requestor.is_superuser:
            return
        permissions = get_not_manageable_permissions_when_deactivate_or_remove_users(
            users
        )
        if permissions:
            # add error
            msg = "Users cannot be removed, some of permissions will not be manageable."
            code = AccountErrorCode.LEFT_NOT_MANAGEABLE_PERMISSION.value
            params = {"permissions": permissions}
            error = ValidationError(msg, code=code, params=params)
            errors[field] = [error]


def get