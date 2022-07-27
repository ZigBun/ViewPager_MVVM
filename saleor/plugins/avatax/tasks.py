import opentracing
import opentracing.tags
from celery.utils.log import get_task_logger

from ...celeryconf import app
from ...core.taxes import TaxError
from ...order.ev