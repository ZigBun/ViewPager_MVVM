import json
from datetime import datetime
from unittest.mock import patch
from uuid import UUID

import graphene
import pytest
from django.http import JsonResponse
from django.utils import timezone

from ....core import EventDeliveryStatus
from ....webhook.event_types import WebhookEventAsyncType
from ..exceptions import TruncationError
from ..obfuscation import MASK
from ..payload_schema import (
    ApiCallPayload,
    ApiCallRequest,
    ApiCallResponse,
    App,
    EventDelivery,
    EventDeliveryAttemptPayload,
    EventDeliveryAttemptRequest,
    EventDeliveryAttemptResponse,
    EventDeliveryPayload,
    GraphQLOperation,
    ObservabilityEventTypes,
    Webhook,
)
from ..payloads import (
    GQL_OPERATION_PLACEHOLDER_SIZE,
    JsonTruncText,
    dump_payload,
    generate_api_call_payload,
    generate_event_delivery_attempt_payload,
    pretty_json,
    serialize_gql_operation_result,
    serialize_gql_operation_results,
    serialize_headers,
    to_camel_case,
)
from ..utils import GraphQLOperationResponse


@pytest.mark.parametrize(
    "snake_payload,expected_camel",
    [
        (
            ApiCallRequest(
                id="id",
                method="GET",
                url="http://example.com",
                time=123456.2,
                headers=[("snake_header_1", "val"), ("snake_header_2", "val")],
                content_length=1024,
            ),
            {
                "id": "id",
                "method": "GET",
                "url": "http://example.com",
                "time": 123456.2,
                "headers": [("snake_header_1", "val"), ("snake_header_2", "val")],
                "contentLength": 1024,
            },
        ),
        (
            {
                "key_a": {"sub_key_a": "val", "sub_key_b": "val"},
                "key_b": [{"list_key_a": "val"}, {"list_key_b": "val"}],
            },
            {
                "keyA": {"subKeyA": "val", "subKeyB": "val"},
                "keyB": [{"listKeyA": "val"}, {"listKeyB": "val"}],
            },
        ),
    ],
)
def test_to_camel_case(snake_payload, expected_camel):
    assert to_camel_case(snake_payload) == expected_camel


def test_serialize_gql_operation_result(gql_operation_factory):
    bytes_limit = 1024
    query = "query FirstQuery { shop { name } }"
    result = {"data": "result"}
    operation_result = gql_operation_factory(query, "FirstQuery", None, result)
    payload, _ = serialize_gql_operation_result(operation_result, bytes_limit)
    assert payload == GraphQLOperation(
        name=JsonTruncText("FirstQuery", False),
        operation_type="query",
        query=JsonTruncText(query, False),
        result=JsonTruncText(pretty_json(result), False),
        result_invalid=False,
    )
    assert len(dump_payload(payload)) <= bytes_limit


def test_serialize_gql_operation_result_when_no_operation_data():
    bytes_limit = 1024
    result = GraphQLOperationResponse()
    payload, _ = serialize_gql_operation_result(result, bytes_limit)
    assert payload == GraphQLOperation(
        name=None, operation_type=None, query=None, result=None, result_invalid=False
    )
    assert len(dump_payload(payload)) <= bytes_limit


def test_serialize_gql_operation_result_when_too_low_bytes_limit():
    result = GraphQLOperationResponse()
    with pytest.raises(TruncationError):
        serialize_gql_operation_result(result, GQL_OPERATION_PLACEHOLDER_SIZE - 1)


def test_serialize_gql_operation_result_when_minimal_bytes_limit(gql_operation_factory):
    query = "query FirstQuery { shop { name } }"
    operation_result = gql_operation_factory(
        query, "FirstQuery", None, {"data": "result"}
    )
    payload, left_bytes = serialize_gql_operation_result(
        operation_result, GQL_OPERATION_PLACEHOLDER_SIZE
    )
    assert payload == GraphQLOperation(
        name=JsonTruncText("", True),
        operation_type="query",
        query=JsonTruncText("", True),
        result=JsonTruncText("", True),
        result_invalid=False,
    )
    assert left_bytes == 0
    assert len(dump_payload(payload)) <= GQL_OPERATION_PLACEHOLDER_SIZE


def test_serialize_gql_operation_result_when_truncated(gql_operation_factory):
    query = "query FirstQuery { shop { name } }"
    operation_result = gql_operation_factory(
        query, "FirstQuery", None, {"data": "result"}
    )
    bytes_limit = 225
    payload, left_bytes = serialize_gql_operation_result(operation_result, bytes_limit)
    assert payload == GraphQLOperation(
        name=JsonTruncText("FirstQuery", False),
        operation_type="query",
        query=JsonTruncText("query FirstQue", True),
        result=JsonTruncText('{\n  "data": ', True),
        result_invalid=False,
    )
    assert left_bytes == 0
    assert len(dump_payload(payload)) <= bytes_limit


def test_serialize_gql_operation_results(gql_operation_factory):
    query = "query FirstQuery { shop { name } } query SecondQuery { shop { name } }"
    result = {"data": "result"}
    first_result = gql_operation_factory(query, "FirstQuery", None, result)
    second_result = gql_operation_factory(query, "SecondQuery", None, result)
    payloads = serialize_gql_operation_results([first_result, second_result], 1024)
    assert payloads == [
        G