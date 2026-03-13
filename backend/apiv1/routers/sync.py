"""
Sync router.

Handles endpoints for synchronization status, pushing to platforms, and diffing.
"""

from uuid import UUID

import django
import django.utils.timezone
from ninja import Router

import apiv1
from apiv1.api_utils import api_permission_required
from apiv1.models import Event
from apiv1.schemas import (
    EventSyncInfo,
    SyncStatus,
    SyncPushResult,
    SyncDiffData,
    PropertyDiff,
    ErrorOut,
)

# ---------------------------------------------------------------------------
# Static mock data
# ---------------------------------------------------------------------------

_PLATFORM_STATUS: dict[str, dict] = {
    "pretalx": {
        "status": "entry up-to-date",
        "last_synced": "2026-03-10T14:30:00+00:00",
        "last_error": None,
    },
    "pretix": {
        "status": "entry differs",
        "last_synced": "2026-03-08T09:15:00+00:00",
        "last_error": None,
    },
    "Stadt Erlangen Kalender": {
        "status": "no entry exists",
        "last_synced": None,
        "last_error": None,
    },
    "nextcloud calendar": {
        "status": "entry differs",
        "last_synced": "2026-03-05T16:45:00+00:00",
        "last_error": "Connection timeout",
    },
    "Wordpress calendar": {
        "status": "entry up-to-date",
        "last_synced": "2026-03-12T11:00:00+00:00",
        "last_error": None,
    },
}

_PROPERTY_EXAMPLES: dict[str, dict] = {
    "title": {
        "local": "Workshop: Web Development\nLocation: Room A\nDuration: 2 hours",
        "remote": "Workshop: Advanced Web Development\nLocation: Room B\nDuration: 3 hours",
        "type": "txt",
    },
    "description": {
        "local": """{
  "summary": "Learn the basics of web development",
  "topics": ["HTML", "CSS", "JavaScript"],
  "level": "beginner",
  "max_participants": 20
}""",
        "remote": """{
  "summary": "Learn advanced web development techniques",
  "topics": ["React", "TypeScript", "Node.js"],
  "level": "intermediate",
  "max_participants": 25,
  "prerequisites": ["Basic JavaScript knowledge"]
}""",
        "type": "json",
    },
    "schedule": {
        "local": "Monday: 10:00 - 12:00\nTuesday: 14:00 - 16:00\nWednesday: 10:00 - 12:00",
        "remote": "Monday: 10:00 - 13:00\nTuesday: 14:00 - 17:00\nThursday: 10:00 - 12:00",
        "type": "txt",
    },
    "metadata": {
        "local": """{
  "created_at": "2026-02-15T10:00:00Z",
  "updated_at": "2026-02-20T15:30:00Z",
  "status": "draft",
  "tags": ["workshop", "programming"]
}""",
        "remote": """{
  "created_at": "2026-02-15T10:00:00Z",
  "updated_at": "2026-03-01T09:15:00Z",
  "status": "published",
  "tags": ["workshop", "programming", "web-dev"],
  "visibility": "public"
}""",
        "type": "json",
    },
}

# Properties shown in the diff view for each platform.
_PLATFORM_DIFF_PROPERTIES: dict[str, list[str]] = {
    "pretalx":                  ["title", "description"],
    "pretix":                   ["title", "metadata"],
    "Stadt Erlangen Kalender":  ["title", "schedule"],
    "nextcloud calendar":       ["schedule", "metadata"],
    "Wordpress calendar":       ["title", "description", "schedule"],
}

router = Router()


@router.get("/status/{series_id}/{event_id}", response={200: EventSyncInfo, 401: ErrorOut, 403: ErrorOut})
@api_permission_required((apiv1, "view", Event))
def get_sync_status(request, series_id: UUID, event_id: UUID) -> EventSyncInfo:
    """Get synchronization status for an event across different platforms"""
    statuses = [
        SyncStatus(
            platform=platform,
            status=data["status"],
            last_synced=data["last_synced"],
            last_error=data["last_error"],
        )
        for platform, data in _PLATFORM_STATUS.items()
    ]

    return EventSyncInfo(
        series_id=series_id,
        event_id=event_id,
        sync_statuses=statuses,
    )


@router.post("/push/{series_id}/{event_id}/{platform}", response={200: SyncPushResult, 401: ErrorOut, 403: ErrorOut})
@api_permission_required((apiv1, "change", Event))
def push_to_platform(request, series_id: UUID, event_id: UUID, platform: str) -> SyncPushResult:
    """Push/update event data to a specific platform"""
    return SyncPushResult(
        success=True,
        message=f"Event data pushed to {platform}",
        timestamp=django.utils.timezone.now().isoformat(),
        platform=platform,
        series_id=series_id,
        event_id=event_id,
    )


@router.get("/diff/{series_id}/{event_id}/{platform}", response={200: SyncDiffData, 401: ErrorOut, 403: ErrorOut})
@api_permission_required((apiv1, "view", Event))
def get_sync_diff(request, series_id: UUID, event_id: UUID, platform: str) -> SyncDiffData:
    """Get diff data comparing local database properties with remote sync source"""
    property_names = _PLATFORM_DIFF_PROPERTIES.get(platform, list(_PROPERTY_EXAMPLES.keys()))

    properties = [
        PropertyDiff(
            property_name=name,
            local_value=_PROPERTY_EXAMPLES[name]["local"],
            remote_value=_PROPERTY_EXAMPLES[name]["remote"],
            file_type=_PROPERTY_EXAMPLES[name]["type"],
        )
        for name in property_names
    ]

    return SyncDiffData(
        series_id=series_id,
        event_id=event_id,
        platform=platform,
        properties=properties,
    )

