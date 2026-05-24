import logging
from uuid import uuid4

from caldav.davclient import DAVClient
from django.db import models

from apiv1.models.sync.syncbasedata import SyncBaseItem, SyncBaseTarget, SyncDiffData, PropertyDiff

logger = logging.getLogger(__name__)


class CalDAVSyncTarget(SyncBaseTarget):
    secret_field_names = ["password"]

    name = models.CharField(max_length=255)
    url = models.URLField(max_length=2000)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    calendar_display_name = models.CharField(max_length=255)
    instance_base_url = models.CharField(max_length=2000, blank=True, default="")

    def _get_calendar(self):
        logger.debug("Connecting to CalDAV server %s as %s", self.url, self.username)
        client = DAVClient(url=self.url, username=self.username, password=self.password)
        principal = client.principal()
        calendars = principal.get_calendars()
        logger.debug("Found %d calendars on server", len(calendars))
        for cal in calendars:
            display_name = cal.get_display_name()
            logger.debug("Checking calendar %r", display_name)
            if display_name == self.calendar_display_name:
                logger.debug("Matched calendar %r", display_name)
                return cal
        raise ValueError(
            f"Calendar {self.calendar_display_name!r} not found on CalDAV server at {self.url}"
        )

    def create_new_sync_item(self, event) -> "CalDAVSyncItem":
        logger.debug(
            "Creating CalDAV sync item for event %s on target %s",
            event.pk, self.pk,
        )
        item, created = CalDAVSyncItem.objects.get_or_create(
            sync_target=self,
            related_event=event,
            defaults={"caldav_uid": None, "flag_push": True},
        )
        if created:
            logger.debug("Created new CalDAVSyncItem %s (no uid yet)", item.pk)
        else:
            logger.debug("CalDAVSyncItem already exists: %s (uid=%s)", item.pk, item.caldav_uid)
        return item


class CalDAVSyncItem(SyncBaseItem):
    sync_target = models.ForeignKey(
        CalDAVSyncTarget, on_delete=models.CASCADE, related_name="items"
    )
    caldav_uid = models.CharField(max_length=255, unique=True, null=True, blank=True, default=None)

    def _get_calendar(self):
        return self.sync_target._get_calendar()

    def get_status(self):
        if self.flag_push:
            return SyncBaseTarget.SyncTargetStatus.CREATION_PENDING
        return super().get_status()

    def push_update(self):
        event = self.related_event
        target = self.sync_target
        logger.debug(
            "push_update: event=%s uid=%s target=%s (%s)",
            event.pk, self.caldav_uid, target.pk, target.name,
        )
        calendar = self._get_calendar()

        # Delete the existing remote event if we have a UID for it, then release
        # the UID so a fresh one is always assigned — this avoids conflicts with
        # CalDAV servers that keep deleted events in a trash bin under the same UID.
        if self.caldav_uid:
            try:
                calendar.get_event_by_uid(self.caldav_uid).delete()
                logger.debug("Deleted existing remote event uid=%s", self.caldav_uid)
            except Exception:
                logger.debug("Remote event uid=%s already absent", self.caldav_uid)
            self.caldav_uid = None
            self.save()

        # Assign a new UID and persist it as a checkpoint before touching the
        # remote — if the process dies here the item stays in CREATION_PENDING
        # (flag_push=True) with a known UID so recovery is possible.
        self.caldav_uid = str(uuid4())
        self.flag_push = True
        self.save()
        logger.debug("Assigned new uid=%s for event=%s", self.caldav_uid, event.pk)

        blocks = event.get_time_blocks()

        if event.use_full_days or len(blocks) <= 1:
            extra_props = {"x-eventkoordinator-event": str(event.pk)}
            if target.instance_base_url:
                extra_props["x-eventkoordinator-instance"] = target.instance_base_url
            dtstart = blocks[0].start if blocks else event.start_time
            dtend = blocks[0].end if blocks else event.end_time
            logger.debug(
                "Creating remote event uid=%s summary=%r start=%s end=%s",
                self.caldav_uid, event.name, dtstart, dtend,
            )
            calendar.add_event(
                dtstart=dtstart,
                dtend=dtend,
                uid=self.caldav_uid,
                summary=event.name,
                description="Created automatically. Do not edit, updates will be overwritten!",
                **extra_props,
            )
        else:
            ical_str = self._build_recurring_ical(event, blocks, target)
            logger.debug(
                "Creating remote recurring event uid=%s summary=%r blocks=%d",
                self.caldav_uid, event.name, len(blocks),
            )
            calendar.add_event(ical=ical_str)

        self.flag_push = False
        self.save()
        logger.debug("push_update complete for uid=%s", self.caldav_uid)

    def _build_recurring_ical(self, event, blocks, target) -> str:
        from icalendar import Calendar as ICalCalendar, Event as ICalEvent

        cal = ICalCalendar()
        cal.add("prodid", "-//EventKoordinator//EN")
        cal.add("version", "2.0")

        vevent = ICalEvent()
        vevent.add("uid", self.caldav_uid)
        vevent.add("summary", event.name)
        vevent.add("description", "Created automatically. Do not edit, updates will be overwritten!")
        vevent.add("dtstart", blocks[0].start)
        vevent.add("dtend", blocks[0].end)
        vevent.add("rrule", {"FREQ": "DAILY", "COUNT": len(blocks)})
        vevent["x-eventkoordinator-event"] = str(event.pk)
        if target.instance_base_url:
            vevent["x-eventkoordinator-instance"] = target.instance_base_url

        cal.add_component(vevent)
        return cal.to_ical().decode("utf-8")

    def delete_remote(self):
        from caldav import error as caldav_error
        logger.debug("delete_remote: uid=%s", self.caldav_uid)
        if not self.caldav_uid:
            logger.debug("delete_remote: no uid assigned, nothing to delete")
            return
        try:
            calendar = self._get_calendar()
            calendar.get_event_by_uid(self.caldav_uid).delete()
            logger.debug("Deleted remote event uid=%s", self.caldav_uid)
        except Exception as exc:
            if isinstance(exc, caldav_error.NotFoundError):
                logger.debug("Remote event uid=%s already absent, skipping", self.caldav_uid)
                return
            logger.error("Failed to delete CalDAV event %s: %s", self.caldav_uid, exc)
            raise

    def sync_diff(self, only_differences: bool = True) -> SyncDiffData | None:
        logger.debug("sync_diff: uid=%s only_differences=%s", self.caldav_uid, only_differences)
        if not self.caldav_uid:
            logger.debug("sync_diff: no uid assigned, returning None")
            return None
        try:
            calendar = self._get_calendar()
            remote_evt = calendar.get_event_by_uid(self.caldav_uid)
        except Exception as exc:
            logger.debug("Remote event uid=%s not found (%s), returning None", self.caldav_uid, exc)
            return None

        cal_instance = remote_evt.icalendar_instance
        vevent = next(
            (c for c in cal_instance.subcomponents if c.name == "VEVENT"),
            None,
        )
        if vevent is None:
            logger.debug("No VEVENT subcomponent found for uid=%s", self.caldav_uid)
            return None

        event = self.related_event
        properties: list[PropertyDiff] = []

        def _diff(name: str, local: str, remote: str) -> None:
            if only_differences and local == remote:
                return
            logger.debug("diff %s: local=%r remote=%r", name, local, remote)
            properties.append(
                PropertyDiff(property_name=name, local_value=local, remote_value=remote, file_type="text")
            )

        _diff("summary", event.name, str(vevent.get("SUMMARY", "")))

        blocks = event.get_time_blocks()
        local_start = blocks[0].start if blocks else event.start_time
        local_end = blocks[0].end if blocks else event.end_time

        remote_dtstart = vevent.get("DTSTART")
        _diff(
            "start_time",
            local_start.isoformat(),
            remote_dtstart.dt.isoformat() if remote_dtstart else "",
        )

        remote_dtend = vevent.get("DTEND")
        _diff(
            "end_time",
            local_end.isoformat(),
            remote_dtend.dt.isoformat() if remote_dtend else "",
        )

        if not event.use_full_days:
            remote_rrule = vevent.get("RRULE")
            remote_count = (
                remote_rrule.get("COUNT", [None])[0] if remote_rrule else None
            )
            local_count = len(blocks)
            _diff("days", str(local_count), str(remote_count) if remote_count is not None else "1")

        logger.debug("sync_diff complete: %d differing properties for uid=%s", len(properties), self.caldav_uid)
        return SyncDiffData(
            series_id=event.series_id,
            event_id=event.pk,
            target_id=self.sync_target.pk,
            properties=properties,
        )
