from typing import Dict, Union

import celery
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.db.models.expressions import Exists, OuterRef
from django.utils import timezone

from ..celeryconf import app
from ..core import JobStatus
from . import events
from .models import ExportEvent, ExportFile
from .notifications import send_export_failed_info
from .utils