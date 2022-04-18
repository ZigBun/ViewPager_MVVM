from collections import defaultdict
from typing import List

import graphene
from django.core.exceptions import ValidationError

from ...account import models
from ...account.error_codes import AccountErrorCode
from ...permission.enums import AccountPermissions
from ..core import ResolveInfo
from ..core.mutations import BaseBulkMutation, ModelBulkDeleteMutation
from ..core.types import AccountError, NonNullList, StaffError
from ..plugins.dataloaders import get_plugin_manager_promise
from .types import User
from .utils import CustomerDeleteMixin, StaffDeleteMixin


class UserBulkDelete(ModelBulkDeleteMutation):
    class Arguments:
        ids = NonNullList(
            graphene.ID, required=True, description="List of user IDs to delete."
        )

    class Meta:
        abstract = True


class CustomerBulkDelete(CustomerDeleteMixin, UserBulkDelete):
    class Meta:
        description = "Deletes customers."
        model = models.User
        object_type = User
        permissions = (AccountPermissions.MANAGE_USERS,)
        error_type_class = AccountError
        error_type_field = "account_errors"

    @classmethod
    def perform_mutation(cls, root, info: ResolveInfo, /, **data):
        count, errors = super().perform_mutation(root, info, **data)
        cls.post_process(info, count)
        return count, errors

    @classmethod
    def bulk_action(cls, info: ResolveInfo, queryset, /):
        instances = list(queryset)
        queryset.delete()
        manager = get_plugin_manager_promise(info.context).get()
        for instance in instances:
            manager.customer_deleted(instance)


class StaffBulkDelete(StaffDeleteMixin, UserBulkDelete):
    class Meta:
        description = (
            "Deletes staff users. Apps are not allowed to perform this mutation."
        )
        model = models.User
        object_type = User
        permissions = (AccountPermissions.MANAGE_STAFF,)
        error_type_class = StaffError
        error_type_field = "staff_errors"

    @classmethod
    def perform_mutation(  # type: ignore[override]
      