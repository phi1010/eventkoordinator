"""
Sync router.

Handles endpoints for synchronization status, pushing to platforms, and diffing.
"""

import logging
from uuid import UUID

import django
import django.utils.timezone
from django.shortcuts import get_object_or_404
from ninja import Router

import apiv1
from apiv1.api_utils import api_permission_required
from apiv1.models import Event
from apiv1.models.sync.syncbasedata import SyncBaseTarget, SyncBaseItem, SyncDiffData, PropertyDiff
from apiv1.schemas import (
    EventSyncInfo,
    SyncStatus,
    SyncPushResult,
    ErrorOut,
    SyncTargetOut,
    CreateSyncItemIn,
    CreateSyncItemOut,
)

logger = logging.getLogger(__name__)

router = Router()


@router.get(
    "/targets",
    response={200: list[SyncTargetOut], 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required("apiv1.viewrestricted_syncbasetarget")
def list_sync_targets(request) -> list[SyncTargetOut]:
    """List all sync targets with their public (non-secret) properties."""
    targets = SyncBaseTarget.objects.all()
    return [
        SyncTargetOut(
            id=target.pk,
            type=target.type,
            public_properties=target.public_properties,
        )
        for target in targets
    ]


@router.post(
    "/items",
    response={200: CreateSyncItemOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_required((apiv1, "add", SyncBaseItem))
def create_sync_item(request, payload: CreateSyncItemIn):
    """Create a new sync item linking a sync target to an event."""
    target = get_object_or_404(SyncBaseTarget, pk=payload.sync_target_id)
    event = get_object_or_404(Event, pk=payload.event_id)

    # Check if a sync item already exists for this target + event
    existing = SyncBaseItem.objects.filter(
        sync_target=target,
        related_event=event,
    )
    if existing.exists():
        return 200, CreateSyncItemOut(
            id=existing.first().pk,
            sync_target_id=target.pk,
            event_id=event.pk,
        )

    item = SyncBaseItem.objects.create(
        sync_target=target,
        related_event=event,
    )
    return 200, CreateSyncItemOut(
        id=item.pk,
        sync_target_id=target.pk,
        event_id=event.pk,
    )


@router.get(
    "/status/{series_id}/{event_id}",
    response={200: EventSyncInfo, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_required((apiv1, "view", Event))
def get_sync_status(request, series_id: UUID, event_id: UUID) -> EventSyncInfo:
    """Get synchronization status for an event across all sync targets."""
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)

    targets = SyncBaseTarget.objects.all()
    statuses = []
    for target in targets:
        status = target.get_status(event)
        # Find the latest sync item for last_synced timestamp
        latest_item = (
            SyncBaseItem.objects.filter(sync_target=target, related_event=event)
            .order_by("-updated_at")
            .first()
        )
        statuses.append(
            SyncStatus(
                platform=target.type,
                status=status.value,
                last_synced=(
                    latest_item.updated_at.isoformat() if latest_item else None
                ),
                last_error=None,
            )
        )

    return EventSyncInfo(
        series_id=series_id,
        event_id=event_id,
        sync_statuses=statuses,
    )


@router.post(
    "/push/{series_id}/{event_id}/{platform}",
    response={200: SyncPushResult, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "change", Event))
def push_to_platform(
    request, series_id: UUID, event_id: UUID, platform: str
) -> SyncPushResult:
    """Push/update event data to a specific platform"""
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)

    # Find sync items for this event belonging to targets of the given type
    items = SyncBaseItem.objects.filter(
        related_event=event,
    ).select_related("sync_target")

    pushed = False
    for item in items:
        real_target = item.sync_target.get_real_instance()
        if real_target.__class__.__name__ == platform:
            real_item = item.get_real_instance()
            real_item.push_update()
            pushed = True

    return SyncPushResult(
        success=pushed,
        message=(
            f"Event data pushed to {platform}"
            if pushed
            else f"No sync items found for platform {platform}"
        ),
        timestamp=django.utils.timezone.now().isoformat(),
        platform=platform,
        series_id=series_id,
        event_id=event_id,
    )


@router.get(
    "/diff/{series_id}/{event_id}/{platform}",
    response={200: SyncDiffData, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_required((apiv1, "view", Event))
def get_sync_diff(
    request, series_id: UUID, event_id: UUID, platform: str
) -> SyncDiffData:
    """Get diff data comparing local database properties with remote sync source."""
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)

    items = SyncBaseItem.objects.filter(
        related_event=event,
    ).select_related("sync_target")

    all_properties: list[PropertyDiff] = []
    for item in items:
        real_target = item.sync_target.get_real_instance()
        if real_target.__class__.__name__ == platform:
            real_item = item.get_real_instance()
            diff = real_item.sync_diff()
            if diff is not None:
                all_properties.extend(diff.properties)

    return SyncDiffData(
        series_id=series_id,
        event_id=event_id,
        platform=platform,
        properties=all_properties,
    )
