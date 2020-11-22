import logging
from tempfile import NamedTemporaryFile
from typing import Optional
from urllib.parse import urlsplit

import requests

from .... import PaymentError

# https://developer.apple.com/documentation/apple_pay_on_the_web/
# setting_up_your_server#3172427

APPLE_DOMAINS = [
    "apple-pay-gateway.apple.com",
    "cn-apple-pay-gateway.apple.com",
    "apple-pay-gateway-nc-pod1.apple.com",
    "apple-pay-gateway-nc-pod2.apple.com",
    "apple-pay-gateway-nc-pod3.apple.com",
    "apple-pay-gateway-nc-pod4.apple.com",
    "apple-pay-gateway-nc-pod5.apple.com",
    "apple-pay-gateway-pr-pod1.apple.com",
    "apple-pay-gateway-pr-pod2.apple.com",
    "apple-pay-gateway-pr-pod3.apple.com",
    "apple-pay-gateway-pr-pod4.apple.c