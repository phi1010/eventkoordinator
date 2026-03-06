from django.db import models

from apiv1.models import Event
from project.basemodels import HistoricalMetaBase


class SyncBaseItem(HistoricalMetaBase):
    flag_push = models.BooleanField(default=False)
    related_event = models.ForeignKey(Event, on_delete=models.CASCADE)
    def push_update(self):
        pass
    def pull_update(self):
        pass