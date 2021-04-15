from django.db import migrations
from django.db.models import Q


BATCH_SIZE = 10000


def queryset_in_batches(queryset):
    """Slice a queryset into batches.

    Input queryset should be sorted by pk.
    """
    start_pk = 0

    while True:
        qs = queryset.filter(pk__gt=start_pk)[:BATCH_SIZE]
        pks = list(qs.values_list("pk", flat=True))

        if not pks