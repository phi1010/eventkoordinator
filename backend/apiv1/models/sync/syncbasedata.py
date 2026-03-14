from django.db import models

from apiv1.models import Event
from project.basemodels import HistoricalMetaBase, PolymorphicMetaBase


class SyncBaseTarget(PolymorphicMetaBase):

    @property
    def type(self):
        return self.get_real_instance().__class__.__name__

class SyncBaseItem(PolymorphicMetaBase):
    flag_push = models.BooleanField(default=False)
    related_event = models.ForeignKey(Event, on_delete=models.CASCADE)
    def push_update(self):
        pass
    def pull_update(self):
        pass