"""
Calendar router.

Handles endpoints for external calendar event retrieval.
"""

import logging
from datetime import datetime, timedelta, timezone
from ninja import Router

import apiv1
from apiv1.api_utils import api_permission_required
from apiv1.models import Event as EventModel
from apiv1.schemas import ExternalCalendarEvent, ErrorOut

router = Router()

logger = logging.getLogger(__name__)


@router.get(
    "/events",
    response={200: list[ExternalCalendarEvent], 400: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "view", EventModel))
def get_external_calendar_events(
    request,
    start_utc: str,
    end_utc: str,
) -> tuple[int, list[ExternalCalendarEvent]] | tuple[int, ErrorOut]:
    """Return external calendar events overlapping the requested UTC timespan."""

    def parse_utc(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def to_utc_iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat().replace("+00:00", "Z")

    try:
        start_dt = parse_utc(start_utc)
        end_dt = parse_utc(end_utc)
    except ValueError:
        return 400, ErrorOut(
            error="Invalid ISO datetime format for start_utc or end_utc"
        )

    if end_dt <= start_dt:
        return 400, ErrorOut(error="end_utc must be greater than start_utc")

    results: list[ExternalCalendarEvent] = []

    if False:  # Mockdata
        # Use the request range's first UTC midnight as a stable anchor for deterministic mock data.
        anchor_day = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        templates = [
            ("City Council Session", "city-calendar", 0, 9, 0, 120),
            ("School Theater Rehearsal", "school-calendar", 1, 14, 30, 90),
            ("Community Meetup", "community-calendar", 2, 18, 0, 120),
            ("Sports Club Training", "sports-calendar", 3, 17, 0, 90),
            ("Public Library Workshop", "library-calendar", 4, 10, 0, 120),
            ("Open Museum Evening", "museum-calendar", 5, 16, 0, 180),
        ]
        day_window_count = max(
            7, int((end_dt - start_dt).total_seconds() // 86_400) + 2
        )

        for day_offset in range(day_window_count):
            day_start = anchor_day + timedelta(days=day_offset)
            for (
                title,
                source,
                template_offset,
                hour,
                minute,
                duration_minutes,
            ) in templates:
                if day_offset % 7 != template_offset:
                    continue
                event_start = day_start.replace(hour=hour, minute=minute)
                event_end = event_start + timedelta(minutes=duration_minutes)

                if event_start < end_dt and event_end > start_dt:
                    event_id = f"ext-{source}-{event_start.strftime('%Y%m%d%H%M')}"
                    results.append(
                        ExternalCalendarEvent(
                            id=event_id,
                            title=title,
                            startUtc=event_start.isoformat().replace("+00:00", "Z"),
                            endUtc=event_end.isoformat().replace("+00:00", "Z"),
                            source=source,
                        )
                    )

    db_events = (
        EventModel.objects.select_related("series")
        .filter(start_time__lt=end_dt, end_time__gt=start_dt)
        .order_by("start_time")
    )

    for event in db_events:
        ev_start = (
            event.start_time
            if event.start_time.tzinfo
            else event.start_time.replace(tzinfo=timezone.utc)
        )
        ev_end = (
            event.end_time
            if event.end_time.tzinfo
            else event.end_time.replace(tzinfo=timezone.utc)
        )

        if event.use_full_days:
            # Single continuous event spanning over midnight
            results.append(
                ExternalCalendarEvent(
                    id=f"db-{event.id}",
                    title=event.name,
                    startUtc=to_utc_iso(ev_start),
                    endUtc=to_utc_iso(ev_end),
                    source="internal-calendar",
                )
            )
        else:
            # Split into per-day blocks using the same daily start/end hours
            start_date = ev_start.date()
            end_date = ev_end.date()
            day_count = (end_date - start_date).days + 1

            if day_count <= 1:
                # Single-day event, no splitting needed
                results.append(
                    ExternalCalendarEvent(
                        id=f"db-{event.id}",
                        title=event.name,
                        startUtc=to_utc_iso(ev_start),
                        endUtc=to_utc_iso(ev_end),
                        source="internal-calendar",
                    )
                )
            else:
                # Multi-day: each day gets start hours → end hours
                start_time_of_day = ev_start.timetz()
                end_time_of_day = ev_end.timetz()

                for i in range(day_count):
                    day = start_date + timedelta(days=i)
                    day_start = datetime.combine(day, start_time_of_day)
                    day_end = datetime.combine(day, end_time_of_day)

                    # Correct days where end <= start (edge-case times)
                    if day_end <= day_start:
                        day_end = day_end + timedelta(days=1)
                        if day_end > ev_end:
                            continue

                    # Only include day blocks that overlap the requested range
                    if day_start >= end_dt or day_end <= start_dt:
                        continue

                    results.append(
                        ExternalCalendarEvent(
                            id=f"db-{event.id}-day{i}",
                            title=event.name,
                            startUtc=to_utc_iso(day_start),
                            endUtc=to_utc_iso(day_end),
                            source="internal-calendar",
                        )
                    )

    return 200, sorted(results, key=lambda e: e.startUtc)
