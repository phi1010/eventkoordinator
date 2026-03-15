import uuid
from typing import ClassVar

from django.db import models
from ninja import Schema

from apiv1.models import Event
from project.basemodels import PolymorphicMetaBase


class PropertyDiff(Schema):
    property_name: str
    local_value: str
    remote_value: str
    file_type: str


class SyncDiffData(Schema):
    series_id: uuid.UUID
    event_id: uuid.UUID
    platform: str
    properties: list[PropertyDiff]


class SyncBaseTarget(PolymorphicMetaBase):
    """Base class for all sync targets (e.g. Pretix, iCal calendars)."""

    # Fields whose values must never be exposed through the public API.
    # Subclasses should extend this list for their own secret fields.
    secret_field_names: ClassVar[list[str]] = []

    # Field names that belong to the base / polymorphic infrastructure and
    # should be excluded from public_properties.
    _INFRASTRUCTURE_FIELDS: ClassVar[set[str]] = {
        "id",
        "created_at",
        "updated_at",
        "polymorphic_ctype",
        "polymorphic_ctype_id",
        "syncbasetarget_ptr",
        "syncbasetarget_ptr_id",
    }

    class SyncTargetStatus(models.TextChoices):
        NO_ENTRY_EXISTS = "no entry exists", "No entry exists"
        ENTRY_UP_TO_DATE = "entry up-to-date", "Entry up-to-date"
        ENTRY_DIFFERS = "entry differs", "Entry differs"

    class Meta:
        permissions = [
            ("viewrestricted_syncbasetarget", "Can view restricted sync target information"),
        ]

    @property
    def type(self) -> str:
        return self.get_real_instance().__class__.__name__

    @property
    def public_properties(self) -> dict[str, str]:
        """Return a dict of non-secret, non-infrastructure field values."""
        real = self.get_real_instance()
        result: dict[str, str] = {}
        for field in real._meta.get_fields():
            if not hasattr(field, "column"):
                # Skip reverse relations and similar non-concrete fields
                continue
            name = field.name
            if name in self._INFRASTRUCTURE_FIELDS:
                continue
            if name in real.secret_field_names:
                continue
            result[name] = str(getattr(real, name, ""))
        return result

    def get_status(self, event: Event) -> "SyncBaseTarget.SyncTargetStatus":
        """Return the sync status for a given event against this target."""
        items = SyncBaseItem.objects.filter(
            sync_target=self,
            related_event=event,
        )
        if not items.exists():
            return self.SyncTargetStatus.NO_ENTRY_EXISTS

        for item in items:
            real_item = item.get_real_instance()
            diff = real_item.sync_diff()
            if diff is not None and len(diff.properties) > 0:
                return self.SyncTargetStatus.ENTRY_DIFFERS

        return self.SyncTargetStatus.ENTRY_UP_TO_DATE


class SyncBaseItem(PolymorphicMetaBase):
    flag_push = models.BooleanField(default=False)
    related_event = models.ForeignKey(Event, on_delete=models.CASCADE)
    sync_target = models.ForeignKey(
        SyncBaseTarget,
        on_delete=models.CASCADE,
        related_name="sync_items",
        null=True,
        blank=True,
    )

    def push_update(self):
        pass

    def pull_update(self):
        pass

    def sync_diff(self) -> SyncDiffData | None:
        return None
