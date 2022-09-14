"""List of all languages supported in Saleor.

Generated with Babel:

from babel import Locale
from babel.localedata import locale_identifiers

EXCLUDE = [
    "ar_001",
    "en_US_POSIX",
    "en_001",
    "en_150",
    "eo_001",
    "es_419",
    "ia_001",
    "prg_001",
    "vo_001",
    "yi_001",
]

languages = []

for lid in sorted(locale_identifiers()):
    if lid not in EXCLUDE:
        languages.append((lid.replace("_", "-"), Locale.parse(lid).english_name))
"""


LANGUAGES = [
    ("af", "Afrikaans"),
    ("af-na", "Afrikaans (Namibia)"),
    ("af-za", "Afrikaans (South Africa)"),
    ("agq", "Aghem"),
    ("agq-cm", "Aghem (Cameroon)"),
    ("ak", "Akan"),
    ("ak-gh", "Akan (Ghana)"),
    ("am", "Amharic"),
    ("am-et", "Amharic (Ethiopia)"),
    ("ar", "Arabic"),
    ("ar-ae", "Arabic (United Arab Emirates)"),
    ("ar-bh", "Arabic (Bahrain)"),
    ("ar-dj", "Arabic (Djibouti)"),
    ("ar-dz", "Arabic (Algeria)"),
    ("ar-eg", "Arabic (Egypt)"),
    ("ar-eh", "Arabic (Western Sahara)"),
    ("ar-er", "Arabic (Eritrea)"),
    ("ar-il", "Arabic (Israel)"),
    ("ar-iq", "Arabic (Iraq)"),
    ("ar-jo", "Arabic (Jordan)"),
    ("ar-km", "Arabic (Comoros)"),
    ("ar-kw", "Arabic (Kuwait)"),
    ("ar-lb", "Arabic (Lebanon)"),
    ("ar-ly", "Arabic (Libya)"),
    ("ar-ma", "Arabic (Morocco)"),
    ("ar-mr", "Arabic (Mauritania)"),
    ("ar-om", "Arabic (Oman)"),
    ("ar-ps", "Arabic (Palestinian Territories)"),
    ("ar-qa", "Arabic (Qatar)"),
    (