from django.db import models

from apiv1.models.sync.syncbasedata import SyncBaseItem, SyncBaseTarget


class IcalCalendarSyncTarget(SyncBaseTarget):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    url = models.URLField(max_length=2000, unique=True)

    def create_new_sync_item(self, event) -> SyncBaseItem:
        raise NotImplementedError(
            "IcalCalendarSyncTarget does not support creating sync items via the API. "
            "iCal items are created by the import_ical management command."
        )

class IcalCalenderSyncItem(SyncBaseItem):
    uid = models.CharField(max_length=255, unique=True)
    sync_target = models.ForeignKey(IcalCalendarSyncTarget, on_delete=models.CASCADE, related_name="items")
    ical_definition = models.TextField(max_length=10000)
