import functools
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, List, Optional, Tuple

from asgiref.local import Local
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.utils import timezone
from graphql import GraphQLDocument
from pytimeparse import parse

from ..event_types import WebhookEventAsyncType
from ..utils import get_webhooks_for_event
from .buffers import get_buffer
from .exceptions import TruncationError
from .payloads import generate_api_call_payload, generate_event_delivery_attempt_payload
from .tracing import opentracing_trace

if TYPE_CHECKING:
    from celery.exceptions import Retry
    from django.http import HttpRequest, HttpResponse

    from ...core.models import EventDeliveryAttempt

logger = logging.getLogger(__name__)
CACHE_TIMEOUT = parse("2 minutes")
BUFFER_KEY = "observability_buffer"
WEBHOOKS_KEY = "observability_webhooks"
_active_webhooks_exists_cache: Dict[str, Tuple[bool, float]] = {}
_context = Local()


@dataclass
class WebhookData:
    id: int
    saleor_domain: str
    target_url: str
    secret_key: Optional[str] = None


def get_buffer_name() -> str:
    return cache.make_key(BUFFER_KEY)


_webhooks_mem_cache: Dict[str, Tuple[List[WebhookData], float]] = {}


def get_webhooks_clear_mem_cache():
    _webhooks_mem_cache.clear()


def get_webhooks(timeout=CACHE_TIMEOUT) -> List[WebhookData]:
    with opentracing_trace("get_observability_webhooks", "webhooks"):
        buffer_name = get_buffer_name()
        if cached := _webhooks_mem_cache.get(buffer_name, None):
            webhooks_data, check_time = cached
            if monotonic() - check_time <= timeout:
                return webhooks_data
        webhooks_data = cache.get(WEBHOOKS_KEY)
        if webhooks_data is None:
            webhooks_data = []
            if webhooks := get_webhooks_for_event(WebhookEventAsyncType.OBSERVABILITY):
                domain = Site.objects.get_current().domain
                for webhook in webhooks:
                    webhooks_data.append(
                        WebhookData(
                            id=webhook.id,
                            saleor_domain=domain,
                            target_url=webhook.target_url,
                            secret_key=webhook.secret_key,
                        )
                    )
            cache.set(WEBHOOKS_KEY, webhooks_data, timeout=CACHE_TIMEOUT)
        _webhooks_mem_cache[buffer_name] = (webhooks_data, monotonic())
        return webhooks_data


def task_next_retry_date(retry_error: "Retry") -> Optional[datetime]:
    if isinstance(retry_error.when, (int, float)):
        return timezone.now() + timedelta(seconds=retry_error.when)
    if isinstance(retry_error.when, datetime):
        return retry_error.when
    return None


def put_event(generate_payload: Callable[[], Any]):
    try:
        payload = generate_payload()
        with opentracing_trace("put_event", "buffer"):
            if get_buffer(get_buffer_name()).put_event(payload):
                logger.warning("Observability buffer full, event dropped.")
    except TruncationError as err:
        logger.warning("Observability event dropped. %s", err, extra=err.extra)
    except Exception:
        logger.error("Observability event dropped.", exc_info=True)


def pop_events_with_remaining_size() -> Tuple[List[Any], int]:
    with opentracing_trace("pop_events", "buffer"):
        try:
            buffer = get_buffer(get_buffer_name())
            events, remaining = buffer.pop_events_get_size()
            batch_count = buffer.in_batches(remaining)
        except Exception:
            logger.error("Could not p