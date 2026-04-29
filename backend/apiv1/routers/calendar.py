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
        return 400, ErrorOut(code="calendar.invalidDatetimeFormat")

    if end_dt <= start_dt:
        return 400, ErrorOut(code="calendar.endBeforeStart")

    results: list[ExternalCalendarEvent] = []


    db_events = (
        EventModel.objects.select_related("series")
        .filter(start_time__lt=end_dt, end_time__gt=start_dt)
        .order_by("start_time")
    )

    for event in db_events:
        for i, block in enumerate(event.get_time_blocks()):
            block_id = f"db-{event.id}" if i == 0 else f"db-{event.id}-block{i}"

            # Only include blocks that overlap the requested range
            if block.start >= end_dt or block.end <= start_dt:
                continue

            results.append(
                ExternalCalendarEvent(
                    id=block_id,
                    title=event.name,
                    startUtc=to_utc_iso(block.start),
                    endUtc=to_utc_iso(block.end),
                    source="internal-calendar",
                )
            )

    return 200, sorted(results, key=lambda e: e.startUtc)
