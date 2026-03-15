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
)

logger = logging.getLogger(__name__)

router = Router()


def _items_for_target_and_event(
    target: SyncBaseTarget, event: Event
) -> list[SyncBaseItem]:
    """Return all SyncBaseItem instances linking *target* to *event*.

    Because ``sync_target`` is a concrete FK only on each subclass (not on the
    polymorphic base table), we fetch all items for the event and filter in
    Python by the resolved ``sync_target`` property.
    """
    return [
        item
        for item in SyncBaseItem.objects.filter(related_event=event)
        if getattr(item.sync_target, "pk", None) == target.pk
    ]


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
        matching = _items_for_target_and_event(target, event)
        latest_item = max(matching, key=lambda i: i.updated_at) if matching else None
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

    items = SyncBaseItem.objects.filter(related_event=event)

    pushed = False
    for item in items:
        target = item.sync_target
        if target is not None and target.type == platform:
            item.push_update()
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

    items = SyncBaseItem.objects.filter(related_event=event)

    all_properties: list[PropertyDiff] = []
    for item in items:
        target = item.sync_target
        if target is not None and target.type == platform:
            diff = item.sync_diff()
            if diff is not None:
                all_properties.extend(diff.properties)

    return SyncDiffData(
        series_id=series_id,
        event_id=event_id,
        platform=platform,
        properties=all_properties,
    )
