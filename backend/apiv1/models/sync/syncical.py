from django.db import models

from apiv1.models.sync.syncbasedata import SyncBaseItem

class SyncIcalCalendar(SyncBaseItem):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    url = models.URLField(max_length=2000, unique=True)

class SyncIcalItem(SyncBaseItem):
    uid = models.CharField(max_length=255, unique=True)
    calendar = models.ForeignKey(SyncIcalCalendar, on_delete=models.CASCADE, related_name="items")
    ical_definition = models.TextField(max_length=10000)
