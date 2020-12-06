from typing import Generic, Iterable, List, TypeVar, Union

import opentracing
import opentracing.tags
from promise import Promise
from promise.dataloader import DataLoader as BaseLoader

from . import SaleorContext
from .context import get_database_conn