import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import icalendar
import recurring_ical_events
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone as django_timezone

from apiv1.models import Event, Series
from sync_ical.models import IcalCalendarSyncTarget, IcalCalenderSyncItem

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


class Command(BaseCommand):
    help = "Import calendar events from iCalendar format"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            default="https://www.zam.haus/?mec-ical-feed=1",
            help="URL of the iCalendar feed – used as the canonical identifier for the sync target",
        )
        parser.add_argument(
            "--file",
            type=str,
            help="Path to a local iCalendar file (content source; --url still identifies the sync target)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing series and events before importing",
        )
        parser.add_argument(
            "--calendar-name",
            type=str,
            default="",
            help="Human-readable name for the sync target calendar",
        )

    def handle(self, *args, **options):
        # Clear existing data if requested
        if options["clear"]:
            self.stdout.write(
                self.style.WARNING("Clearing existing series and events...")
            )
            IcalCalenderSyncItem.objects.all().delete()
            IcalCalendarSyncTarget.objects.all().delete()
            Event.objects.all().delete()
            Series.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Cleared."))

        source_url = options["url"]

        # Fetch or load iCalendar data
        if options["file"]:
            self.stdout.write(
                f"Loading iCalendar from file: {options['file']} "
                f"(sync target URL: {source_url})"
            )
            try:
                with open(options["file"], "r", encoding="utf-8") as f:
                    ics_content = f.read()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to read file: {e}"))
                return
        else:
            self.stdout.write(f"Fetching iCalendar from URL: {source_url}")
            try:
                response = requests.get(source_url)
                response.raise_for_status()
                ics_content = response.text
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to fetch calendar: {e}"))
                return

        # Create or update the sync target
        calendar_name = options.get("calendar_name") or source_url
        sync_target, target_created = IcalCalendarSyncTarget.objects.get_or_create(
            url=source_url,
            defaults={"name": calendar_name},
        )
        if not target_created and options.get("calendar_name"):
            sync_target.name = calendar_name
            sync_target.save()

        self.stdout.write(
            f"{'Created' if target_created else 'Using existing'} sync target: {sync_target.name}"
        )

        # Parse calendar data
        self.stdout.write("Parsing calendar data...")
        try:
            raw_events = parse_calendar_data(ics_content)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to parse calendar: {e}"))
            return

        if not raw_events:
            self.stdout.write(self.style.WARNING("No events found in calendar"))
            return

        self.stdout.write(f"Found {len(raw_events)} events")

        # Group events by series (by title)
        series_map: dict[str, dict] = {}
        for raw_event in raw_events:
            title = raw_event["summary"]

            if title not in series_map:
                series_map[title] = {
                    "name": title,
                    "description": raw_event["description"],
                    "events": [],
                }

            tag = extract_tag(raw_event["categories"])
            series_map[title]["events"].append(
                {
                    "name": title,
                    "start_time": raw_event["dtstart"],
                    "end_time": raw_event["dtend"],
                    "tag": tag,
                    # Unique occurrence key: uid + dtstart handles recurring events
                    "occurrence_uid": f"{raw_event['uid']}_{raw_event['dtstart'].isoformat()}",
                    "ical_definition": raw_event["ical_definition"],
                }
            )

        # Create series and events in database
        created_count = 0
        for series_name, series_data in series_map.items():
            try:
                series = Series.objects.create(
                    name=series_data["name"],
                    description=series_data["description"],
                )
                created_count += 1

                for event_data in series_data["events"]:
                    event = Event.objects.create(
                        series=series,
                        name=event_data["name"],
                        start_time=event_data["start_time"],
                        end_time=event_data["end_time"],
                        tag=event_data["tag"],
                        use_full_days=True,
                    )
                    IcalCalenderSyncItem.objects.get_or_create(
                        uid=event_data["occurrence_uid"],
                        defaults={
                            "sync_target": sync_target,
                            "related_event": event,
                            "ical_definition": event_data["ical_definition"],
                        },
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created series: {series.name} "
                        f"with {len(series_data['events'])} events"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Failed to create series "{series_name}": {e}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nImport complete! Created {created_count} new series."
            )
        )

