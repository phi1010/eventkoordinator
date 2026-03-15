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
    target_id: uuid.UUID
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
        matching_items = [
            item for item in SyncBaseItem.objects.filter(related_event=event)
            if getattr(item.sync_target, "pk", None) == self.pk
        ]
        if not matching_items:
            return self.SyncTargetStatus.NO_ENTRY_EXISTS

        for item in matching_items:
            diff = item.sync_diff()
            if diff is not None and len(diff.properties) > 0:
                return self.SyncTargetStatus.ENTRY_DIFFERS

        return self.SyncTargetStatus.ENTRY_UP_TO_DATE
    def create_new_sync_item(self, event: Event) -> "SyncBaseItem":
        """Create a new SyncBaseItem for the given event and this target.

        Subclasses must override this to return an instance of their specific
        SyncBaseItem subclass, with the appropriate sync_target FK set.
        """
        raise NotImplementedError("Subclasses must implement create_new_sync_item()")

class SyncBaseItem(PolymorphicMetaBase):
    flag_push = models.BooleanField(default=False)
    related_event = models.ForeignKey(Event, on_delete=models.CASCADE)

    @property
    def sync_target(self) -> SyncBaseTarget | None:
        """Return the sync target for this item.

        Subclasses must override this by declaring a ``sync_target``
        ``ForeignKey`` that shadows this property.
        """
        return None

    def push_update(self):
        pass

    def pull_update(self):
        pass

    def delete_remote(self):
        """Delete the remote resource linked to this sync item.

        Subclasses override this to implement platform-specific deletion.
        After deleting, implementations should reset any stored remote IDs.
        """
        pass

    def sync_diff(self) -> SyncDiffData | None:
        return None
