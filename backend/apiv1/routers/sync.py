"""
Sync router.

Handles endpoints for synchronization status, pushing to platforms, and diffing.
"""

import random
from datetime import datetime, timedelta
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

router = Router()


@router.get("/status/{series_id}/{event_id}", response={200: EventSyncInfo, 401: ErrorOut, 403: ErrorOut})
@api_permission_required((apiv1, "view", Event))
def get_sync_status(request, series_id: UUID, event_id: UUID) -> EventSyncInfo:
    """Get synchronization status for an event across different platforms"""
    platforms = [
        "pretalx",
        "pretix",
        "Stadt Erlangen Kalender",
        "nextcloud calendar",
        "Wordpress calendar",
    ]

    statuses = []
    for platform in platforms:
        # Generate random status for demo
        status_options = [
            "no entry exists",
            "entry up-to-date",
            "entry differs",
        ]
        random_status = random.choice(status_options)

        # Generate random last_synced date (within last 7 days or None)
        last_synced = None
        if random.random() > 0.3:  # 70% chance of having been synced
            days_ago = random.randint(0, 7)
            last_synced = (django.utils.timezone.now() - timedelta(days=days_ago)).isoformat()

        statuses.append(SyncStatus(
            platform=platform,
            status=random_status,
            last_synced=last_synced,
            last_error=None if random.random() > 0.1 else "Connection timeout",
        ))

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

    # Generate mock diff data for demonstration
    properties = []

    # Example property diffs with realistic data
    property_examples = [
        {
            "name": "title",
            "local": "Workshop: Web Development\nLocation: Room A\nDuration: 2 hours",
            "remote": "Workshop: Advanced Web Development\nLocation: Room B\nDuration: 3 hours",
            "type": "txt"
        },
        {
            "name": "description",
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
            "type": "json"
        },
        {
            "name": "schedule",
            "local": """Monday: 10:00 - 12:00
Tuesday: 14:00 - 16:00
Wednesday: 10:00 - 12:00""",
            "remote": """Monday: 10:00 - 13:00
Tuesday: 14:00 - 17:00
Thursday: 10:00 - 12:00""",
            "type": "txt"
        },
        {
            "name": "metadata",
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
            "type": "json"
        },
    ]

    # Randomly select 2-4 properties to show diffs
    num_diffs = random.randint(2, 4)
    selected = random.sample(property_examples, num_diffs)

    for prop in selected:
        properties.append(PropertyDiff(
            property_name=prop["name"],
            local_value=prop["local"],
            remote_value=prop["remote"],
            file_type=prop["type"]
        ))

    return SyncDiffData(
        series_id=series_id,
        event_id=event_id,
        platform=platform,
        properties=properties
    )

