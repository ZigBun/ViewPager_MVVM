
from collections import defaultdict
from typing import List, Tuple

import i18naddress
from django import forms
from django.core.exceptions import ValidationError
from django.forms import BoundField
from django.forms.models import ModelFormMetaclass
from django_countries import countries

from .models import Address
from .validators import validate_possible_number
from .widgets import DatalistTextWidget

COUNTRY_FORMS = {}
UNKNOWN_COUNTRIES = set()

AREA_TYPE = {
    "area": "Area",
    "county": "County",
    "department": "Department",
    "district": "District",
    "do_si": "Do/si",
    "eircode": "Eircode",
    "emirate": "Emirate",
    "island": "Island",
    "neighborhood": "Neighborhood",
    "oblast": "Oblast",
    "parish": "Parish",
    "pin": "PIN",
    "postal": "Postal code",
    "prefecture": "Prefecture",
    "province": "Province",
    "state": "State",
    "suburb": "Suburb",
    "townland": "Townland",
    "village_township": "Village/township",
    "zip": "ZIP code",
}


class PossiblePhoneNumberFormField(forms.CharField):
    """A phone input field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget.input_type = "tel"


class CountryAreaChoiceField(forms.ChoiceField):
    widget = DatalistTextWidget