import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import icalendar
import recurring_ical_events
import requests
from celery import shared_task
from django.db import transaction
from django.utils import timezone as django_timezone

logger = logging.getLogger(__name__)


def _default_import_window() -> tuple[date, date]:
    today = django_timezone.now().date()
    # recurring_ical_events.between() excludes the end boundary, so add one extra day
    # to include occurrences on the day exactly one year in the future.
    return today - timedelta(days=365), today + timedelta(days=366)


def _as_utc_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _read_text_field(component: icalendar.cal.Component, key: str) -> Optional[str]:
    value = component.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_categories(component: icalendar.cal.Component) -> Optional[str]:
    categories = component.get("CATEGORIES")
    if categories is None:
        return None

    values: list[str]
    if hasattr(categories, "cats"):
        values = [str(item).strip() for item in categories.cats]
    elif isinstance(categories, (list, tuple, set)):
        values = [str(item).strip() for item in categories]
    else:
        values = [str(categories).strip()]

    cleaned = [value for value in values if value]
    return ",".join(cleaned) if cleaned else None


def _read_event_datetimes(component: icalendar.cal.Component) -> tuple[datetime, datetime]:
    dtstart = _as_utc_datetime(component.decoded("DTSTART"))

    if component.get("DTEND") is not None:
        dtend = _as_utc_datetime(component.decoded("DTEND"))
    elif component.get("DURATION") is not None:
        dtend = dtstart + component.decoded("DURATION")
    else:
        dtend = dtstart

    return dtstart, dtend


def extract_tag(categories: Optional[str]) -> Optional[str]:
    """Extract the first tag from categories"""
    if not categories:
        return None
    tags = [tag.strip() for tag in categories.split(",")]
    return next((tag for tag in tags if tag), None)


def parse_calendar_data(
    ics_content: str,
    *,
    window_start: Optional[date] = None,
    window_end: Optional[date] = None,
) -> list[dict]:
    """Parse iCalendar content and expand recurring events within the import window."""
    if window_start is None or window_end is None:
        window_start, window_end = _default_import_window()

    calendar = icalendar.Calendar.from_ical(ics_content)
    expanded_events = recurring_ical_events.of(calendar).between(window_start, window_end)

    events: list[dict] = []
    seen_occurrences: set[tuple[str, datetime, datetime]] = set()

    for component in expanded_events:
        summary = _read_text_field(component, "SUMMARY")
        uid = _read_text_field(component, "UID")
        if not summary or not uid or component.get("DTSTART") is None:
            continue

        dtstart, dtend = _read_event_datetimes(component)
        occurrence_key = (uid, dtstart, dtend)
        if occurrence_key in seen_occurrences:
            continue
        seen_occurrences.add(occurrence_key)

        events.append(
            {
                "summary": summary,
                "dtstart": dtstart,
                "dtend": dtend,
                "uid": uid,
                "description": _read_text_field(component, "DESCRIPTION"),
                "categories": _read_categories(component),
                "ical_definition": component.to_ical().decode("utf-8"),
            }
        )

    return events


@shared_task
def sync_ical_target(sync_target_id):
    """Fetch and sync a single IcalCalendarSyncTarget by primary key."""
    from apiv1.models import Event
    from sync_ical.models import IcalCalendarSyncTarget, IcalCalenderSyncItem

    try:
        sync_target = IcalCalendarSyncTarget.objects.get(pk=sync_target_id)
    except IcalCalendarSyncTarget.DoesNotExist:
        logger.error("IcalCalendarSyncTarget %s not found", sync_target_id)
        return

    logger.info("Fetching iCal feed for sync target %r (%s)", sync_target.name, sync_target.url)
    try:
        response = requests.get(sync_target.url, timeout=30)
        response.raise_for_status()
        ics_content = response.text
    except Exception:
        logger.exception("Failed to fetch iCal feed for sync target %s", sync_target_id)
        return

    logger.info("Parsing calendar data for sync target %r", sync_target.name)
    try:
        raw_events = parse_calendar_data(ics_content)
    except Exception:
        logger.exception("Failed to parse calendar data for sync target %s", sync_target_id)
        return

    if not raw_events:
        logger.warning("No events found in iCal feed for sync target %r", sync_target.name)
        return

    logger.info("Found %d event occurrences for sync target %r", len(raw_events), sync_target.name)

    created_event_count = 0
    deleted_event_count = 0

    with transaction.atomic():
        seen_uids: set[str] = set()

        # Pre-fetch existing UIDs to avoid creating Events that won't be used.
        existing_uids: set[str] = set(
            IcalCalenderSyncItem.objects.filter(sync_target=sync_target)
            .values_list("uid", flat=True)
        )

        for raw_event in raw_events:
            tag = extract_tag(raw_event["categories"])
            occurrence_uid = f"{raw_event['uid']}_{raw_event['dtstart'].isoformat()}"
            seen_uids.add(occurrence_uid)

            if occurrence_uid not in existing_uids:
                event = Event.objects.create(
                    series=None,
                    name=raw_event["summary"],
                    start_time=raw_event["dtstart"],
                    end_time=raw_event["dtend"],
                    tag=tag,
                    use_full_days=True,
                )
                IcalCalenderSyncItem.objects.create(
                    uid=occurrence_uid,
                    sync_target=sync_target,
                    ical_definition=raw_event["ical_definition"],
                    related_event=event,
                )
                created_event_count += 1
            else:
                IcalCalenderSyncItem.objects.filter(uid=occurrence_uid).exclude(
                    ical_definition=raw_event["ical_definition"]
                ).update(ical_definition=raw_event["ical_definition"])

        stale_items = list(
            IcalCalenderSyncItem.objects.filter(sync_target=sync_target).exclude(uid__in=seen_uids)
        )
        if stale_items:
            stale_event_ids = [item.related_event_id for item in stale_items]
            deleted_event_count = len(stale_event_ids)
            # Deleting the Event cascades to the IcalCalenderSyncItem.
            Event.objects.filter(pk__in=stale_event_ids).delete()

    logger.info(
        "Sync complete for %r: %d new, %d deleted",
        sync_target.name,
        created_event_count,
        deleted_event_count,
    )


@shared_task
def sync_all_ical_targets():
    """Dispatch sync_ical_target for every IcalCalendarSyncTarget in the database."""
    from sync_ical.models import IcalCalendarSyncTarget

    target_ids = list(IcalCalendarSyncTarget.objects.values_list("pk", flat=True))
    logger.info("Dispatching sync for %d iCal sync target(s)", len(target_ids))
    for target_id in target_ids:
        sync_ical_target.delay(target_id)
