import uuid
from datetime import date, datetime
from tempfile import NamedTemporaryFile
from typing import IO, TYPE_CHECKING, Any, Dict, List, Set, Union

import petl as etl
from django.utils import timezone

from ...giftcard.models import GiftCard
from ...product.models import Product
from .. import FileTypes
from ..notifications import send_export_download_link_notification
from .product_headers import get_product_export_fields_and_headers_info
from .products_data import get_products_data

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ..models import ExportFile


BATCH_SIZE = 10000


def export_products(
    export_file: "ExportFile",
    scope: Dict[str, Union[str, dict]],
    export_info: Dict[str, list],
    file_type: str,
    delimiter: str = ",",
):
    from ...graphql.product.filters import ProductFilter

    file_name = get_filename("product", file_type)
    queryset = get_queryset(Product, ProductFilter, scope)

    (
        export_fields,
        file_headers,
        data_headers,
    ) = get_product_export_fields_and_headers_info(export_info)

    temporary_file = create_file_with_headers(file_headers, delimiter, file_type)

    export_products_in_batches(
        queryset,
        export_info,
        set(export_fields),
        data_headers,
        delimiter,
        temporary_file,
        file_type,
    )

    save_csv_file_in_export_file(export_file, temporary_file, file_name)
    temporary_file.close()

    send_export_download_link_notification(export_file, "products")


def export_gift_cards(
    export_file: "ExportFile",
    scope: Dict[str, Union[str, dict]],
    file_type: str,
    delimiter: str = ",",
):
    from ...graphql.giftcard.filters import GiftCardFilter

    file_name = get_filename("gift_card", file_type)

    queryset = get_queryset(GiftCard, GiftCardFilter, scope)
    # only unused gift cards codes can be exported
    queryset = queryset.filter(used_by_email__isnull=True)

    export_fields = ["code"]
    temporary_file = create_file_with_headers(export_fields, delimiter, file_type)

    export_gift_cards_in_batches(
        queryset,
        export_fields,
        delimiter,
        temporary_file,
        file_type,
    )

    save_csv_file_in_export_file(export_file, temporary_file, file_name)
    temporary_file.close()

    send_export_download_link_notification(export_file, "gift cards")


def get_filename(model_name: str, file_type: str) -> str:
    hash = uuid.uuid4()
    return "{}_data_{}_{}.{}".format(
        model_name, timezone.now().strftime("%d_%m_%Y_%H_%M_%S"), hash, file_type
    )


def get_queryset(model, filter, scope: Dict[str, Union[str, dict]]) -> "QuerySet":
    queryset = model.objects.all()
    if "ids" in scope:
        queryset = model.objects.filter(pk__in=scope["ids"])
    elif "filter" in scope:
        queryset = filter(data=parse_input(scope["filter"]), queryset=queryset).qs

    queryset = queryset.order_by("pk")

    return queryset


def parse_input(data: Any) -> Dict[str, Union[str, dict]]:
    """Parse input into correct data types.

    Scope coming from Celery will be passed as strings.
    """
    if "attributes" in data:
        serialized_attributes = []

        for attr in data.get("attributes") or []:
            if "date_time" in attr:
                if gte := attr["date_time"].get("gte"):
                    attr["date_time"]["gte"] = datetime.fromisoformat(gte)
                if lte := attr["date_time"].get("lte"):
                    attr["date_time"]["lte"] = datetime.fromisoformat(lte)

            if "date" in attr:
                if gte := attr["date"].get("gte"):
                    attr["date"]["gte"] = date.fromisoformat(gte)
                if lte := attr["date"].get("lte"):
                    attr["date"]["lte"] = date.fromisoformat(lte)

            serialized_attributes.append(attr)

        if serialized_attributes:
            data["attributes"] = serialized_attributes

    return data


def create_file_with_headers(file_headers: List[str], delimiter: str, file_type: str):
    table = etl.wrap([file_headers])

    if file_type == FileTypes.CSV:
        temp_file = Nam