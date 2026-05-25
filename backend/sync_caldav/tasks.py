import logging
from datetime import date, datetime, time, timedelta, timezone

import icalendar
import recurring_ical_events
from celery import shared_task
from django.db import transaction
from django.utils import timezone as django_timezone

logger = logging.getLogger(__name__)


def _default_sync_window() -> tuple[date, date]:
    today = django_timezone.now().date()
    return today - timedelta(days=365), today + timedelta(days=366)


def _as_utc_datetime(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _expand_calendar(raw_ical: str) -> list[dict]:
    """Expand a VCALENDAR string into individual occurrence dicts within the sync window."""
    window_start, window_end = _default_sync_window()
    cal = icalendar.Calendar.from_ical(raw_ical)
    occurrences = recurring_ical_events.of(cal).between(window_start, window_end)

    results = []
    seen: set[tuple] = set()
    for vevent in occurrences:
        uid = str(vevent.get("UID", "")).strip()
        summary = str(vevent.get("SUMMARY", "")).strip() or "(no title)"
        raw_start = vevent.get("DTSTART")
        if raw_start is None:
            continue
        dtstart = _as_utc_datetime(raw_start.dt)
        raw_end = vevent.get("DTEND")
        dtend = _as_utc_datetime(raw_end.dt) if raw_end else dtstart

        key = (uid, dtstart, dtend)
        if key in seen:
            continue
        seen.add(key)
        results.append({"uid": uid, "summary": summary, "dtstart": dtstart, "dtend": dtend})
    return results


@shared_task
def sync_caldav_target(sync_target_id):
    """Pull events from a CalDAV calendar and sync them to the local database."""
    from apiv1.models import Event
    from sync_caldav.models import CalDAVSyncTarget, CalDAVSyncItem

    try:
        sync_target = CalDAVSyncTarget.objects.get(pk=sync_target_id)
    except CalDAVSyncTarget.DoesNotExist:
        logger.error("CalDAVSyncTarget %s not found", sync_target_id)
        return

    logger.info("Fetching CalDAV calendar for sync target %r", sync_target.name)
    try:
        calendar = sync_target._get_calendar()
        remote_events = calendar.events()
    except Exception:
        logger.exception("Failed to fetch CalDAV calendar for sync target %s", sync_target_id)
        return

    # Build uid → raw_ical map from remote (one iCal document per unique UID).
    remote_ical_by_uid: dict[str, str] = {}
    for cal_event in remote_events:
        try:
            raw = cal_event.data if isinstance(cal_event.data, str) else cal_event.data.decode("utf-8")
            cal = icalendar.Calendar.from_ical(raw)
            uid = next(
                (str(c.get("UID", "")).strip()
                 for c in cal.subcomponents if c.name == "VEVENT" and c.get("UID")),
                None,
            )
            if uid:
                remote_ical_by_uid[uid] = raw
        except Exception:
            logger.exception("Failed to parse remote CalDAV event, skipping")

    logger.info("Found %d unique UIDs on remote for sync target %r", len(remote_ical_by_uid), sync_target.name)

    # Group existing sync items by uid.
    existing_by_uid: dict[str, list[CalDAVSyncItem]] = {}
    for item in CalDAVSyncItem.objects.filter(sync_target=sync_target).select_related("related_event"):
        if item.caldav_uid:
            existing_by_uid.setdefault(item.caldav_uid, []).append(item)

    created_count = 0
    updated_count = 0
    deleted_count = 0

    with transaction.atomic():
        for uid, raw_ical in remote_ical_by_uid.items():
            existing_items = existing_by_uid.get(uid, [])
            unclaimed = [i for i in existing_items if i.related_event.series_id is None and i.related_event.proposal_id is None]
            claimed = [i for i in existing_items if i not in unclaimed]

            # Always refresh the cached remote snapshot on claimed items.
            for item in claimed:
                if item.remote_ical_definition != raw_ical:
                    item.remote_ical_definition = raw_ical
                    item.save(update_fields=["remote_ical_definition"])

            # If all existing items are claimed, there is nothing to import — skip to
            # avoid creating duplicate pull-imported events alongside pushed ones.
            if existing_items and not unclaimed:
                continue

            # For unclaimed: check if the iCal changed (or if there are no items yet).
            ical_unchanged = (
                unclaimed
                and all(i.remote_ical_definition == raw_ical for i in unclaimed)
            )
            if ical_unchanged:
                continue

            # iCal is new or changed — delete all unclaimed occurrences and regenerate.
            for item in unclaimed:
                item.related_event.delete()  # cascades to CalDAVSyncItem
                deleted_count += 1

            try:
                occurrences = _expand_calendar(raw_ical)
            except Exception:
                logger.exception("Failed to expand iCal for uid=%s, skipping", uid)
                continue

            for occ in occurrences:
                event = Event.objects.create(
                    series=None,
                    proposal=None,
                    name=occ["summary"],
                    start_time=occ["dtstart"],
                    end_time=occ["dtend"],
                    use_full_days=True,
                )
                CalDAVSyncItem.objects.create(
                    sync_target=sync_target,
                    caldav_uid=uid,
                    related_event=event,
                    remote_ical_definition=raw_ical,
                    flag_push=False,
                )
                created_count += 1

        # Delete stale unclaimed items whose UID is no longer on the remote.
        for item in CalDAVSyncItem.objects.filter(sync_target=sync_target).select_related("related_event"):
            if item.caldav_uid not in remote_ical_by_uid:
                event = item.related_event
                if event.series_id is None and event.proposal_id is None:
                    event.delete()
                    deleted_count += 1

    logger.info(
        "Sync complete for %r: %d created, %d updated, %d deleted",
        sync_target.name,
        created_count,
        updated_count,
        deleted_count,
    )


@shared_task
def sync_all_caldav_targets():
    """Dispatch sync_caldav_target for every CalDAVSyncTarget in the database."""
    from sync_caldav.models import CalDAVSyncTarget

    target_ids = list(CalDAVSyncTarget.objects.values_list("pk", flat=True))
    logger.info("Dispatching sync for %d CalDAV sync target(s)", len(target_ids))
    for target_id in target_ids:
        sync_caldav_target.delay(target_id)
