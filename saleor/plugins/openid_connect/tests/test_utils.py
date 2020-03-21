import json
import time
import warnings
from datetime import datetime
from unittest import mock
from unittest.mock import MagicMock, Mock

import pytest
import pytz
import requests
from authlib.jose import JWTClaims
from d