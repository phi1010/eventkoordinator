from django.db import models

from apiv1.models.sync.syncbasedata import SyncBaseItem, SyncBaseTarget, SyncDiffData


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

    def sync_diff(self, only_differences: bool = True) -> SyncDiffData | None:
        """iCal items are imported, not pushed; their existence means they are in sync."""
        from apiv1.models.sync.syncbasedata import PropertyDiff
        properties = []
        if not only_differences:
            properties.append(PropertyDiff(
                property_name="ical_definition",
                local_value=self.ical_definition,
                remote_value=self.ical_definition,
                file_type="text",
            ))
        return SyncDiffData(
            series_id=self.related_event.series_id,
            event_id=self.related_event.pk,
            target_id=self.sync_target.pk,
            properties=properties,
        )

