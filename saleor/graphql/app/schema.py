import graphene

from ...core.exceptions import PermissionDenied
from ...permission.auth_filters import AuthorizationFilters
from ...permission.enums import AppPermission
from ..core import ResolveInfo
from ..core.connection import create_connection_slice, filter_connection_queryset
from ..core.descriptions import ADDED_IN_31, PREVIEW_FEATURE
from ..core.fields import FilterConnectionField, PermissionsField
from ..core.types import FilterInputObjectType, NonNullList
from ..core.utils import from_global_id_or_error
from .dataloaders import AppByIdLoader, AppExtensionByIdLoader, app_promise_callback
from .filters import AppExtensionFilter, AppFilter
from .mutations import (
    AppActivate,
    AppCreate,
    AppDeactivate,
    AppDelete,
    AppDeleteFailedInstallation,
    AppFetchManifest,
    AppInstall,
    AppRetryInstall,
    AppTokenCreate,
    AppTokenDelete,
    AppTokenVerify,
    AppUpdate,
)
from .resolvers import (
    resolve_app,
    resolve_app_extensions,
    resolve_apps,
    resolve_apps_installations,
)
from .sorters import AppSortingInput
from .types import (
    App,
    AppCountableConnection,
    AppExtension,
    AppExtensionCountableConnection,
    AppInstallation,
)


class AppFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = AppFilter


class AppExtensionFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = AppExtensionFilter


class AppQueries(graphene.ObjectType):
    apps_installations = PermissionsField(
        NonNullList(AppInstallation),
        description="List of all apps installations",
        required=True,
        permissions=[
            AppPermission.MANAGE_APPS,
        ],
    )
    apps = FilterConnectionField(
        AppCountableConnection,
        filter=AppFilterInput(description="Filtering options for apps."),
        sort_by=AppSortingInput(description="Sort apps."),
        description="List of the apps.",
        permissions=[
            AuthorizationFilters.AUTHENTICATED_STAFF_USER,
            AppPermission.MANAGE_APPS,
        ],
    )
    app = PermissionsField(
        App,
        id=graphene.Argument(graphene.ID, description="ID of the app.", required=False),
        description=(
            "Look up an app by ID. If ID is not provi