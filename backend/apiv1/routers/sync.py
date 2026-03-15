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
    SyncDeleteResult,
    ErrorOut,
    SyncTargetOut,
    SyncItemOut,
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


@router.post(
    "/create/{series_id}/{event_id}/{target_id}",
    response={200: SyncItemOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_required((apiv1, "add", SyncBaseItem))
def create_sync_item(request, series_id: UUID, event_id: UUID, target_id: UUID):
    """Create a sync item for an event on a specific target.

    Delegates to the target's ``create_new_sync_item`` method, which knows
    how to build the correct subclass instance.  The call is idempotent: if an
    item already exists it is returned without modification.

    Returns 400 if the target does not support API-driven creation (e.g. iCal)
    or if the event cannot be mapped to a target-specific configuration (e.g.
    missing proposal area).
    """
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)
    target = get_object_or_404(SyncBaseTarget, pk=target_id)

    try:
        item = target.get_real_instance().create_new_sync_item(event)
    except NotImplementedError as exc:
        logger.warning(f"Failed to create sync item: {exc}")
        return 400, ErrorOut(error="Not implemented")
    except ValueError as exc:
        logger.warning(f"Failed to create sync item: {exc}")
        return 400, ErrorOut(error="Value error")

    return 200, SyncItemOut(
        id=item.pk,
        target_id=target.pk,
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
        matching = _items_for_target_and_event(target, event)
        latest_item = max(matching, key=lambda i: i.updated_at) if matching else None
        statuses.append(
            SyncStatus(
                target_id=target.pk,
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


@router.delete(
    "/delete/{series_id}/{event_id}/{target_id}",
    response={200: SyncDeleteResult, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_required((apiv1, "change", Event))
def delete_remote_sync_item(
    request, series_id: UUID, event_id: UUID, target_id: UUID
) -> SyncDeleteResult:
    """Delete the remote resource for all sync items linking this event to the target.

    Calls ``delete_remote()`` on each matching sync item, which removes the
    remote object (e.g. a Pretix subevent) and resets any stored remote IDs.
    """
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)
    target = get_object_or_404(SyncBaseTarget, pk=target_id)

    matching = _items_for_target_and_event(target, event)
    for item in matching:
        item.get_real_instance().delete_remote()
        item.get_real_instance().delete()

    deleted = len(matching) > 0
    return SyncDeleteResult(
        success=deleted,
        message=(
            f"Remote resource deleted for {target.type}"
            if deleted
            else f"No sync items found for target {target_id}"
        ),
        timestamp=django.utils.timezone.now().isoformat(),
        target_id=target_id,
        series_id=series_id,
        event_id=event_id,
    )


@router.post(
    "/push/{series_id}/{event_id}/{target_id}",
    response={200: SyncPushResult, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_required((apiv1, "change", Event))
def push_to_platform(
    request, series_id: UUID, event_id: UUID, target_id: UUID
) -> SyncPushResult:
    """Push/update event data to a specific sync target."""
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)
    target = get_object_or_404(SyncBaseTarget, pk=target_id)

    matching = _items_for_target_and_event(target, event)
    for item in matching:
        item.push_update()

    pushed = len(matching) > 0
    return SyncPushResult(
        success=pushed,
        message=(
            f"Event data pushed to {target.type}"
            if pushed
            else f"No sync items found for target {target_id}"
        ),
        timestamp=django.utils.timezone.now().isoformat(),
        target_id=target_id,
        series_id=series_id,
        event_id=event_id,
    )


@router.get(
    "/diff/{series_id}/{event_id}/{target_id}",
    response={200: SyncDiffData, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_required((apiv1, "view", Event))
def get_sync_diff(
    request, series_id: UUID, event_id: UUID, target_id: UUID
) -> SyncDiffData:
    """Get diff data comparing local database properties with remote sync source."""
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)
    target = get_object_or_404(SyncBaseTarget, pk=target_id)

    matching = _items_for_target_and_event(target, event)

    all_properties: list[PropertyDiff] = []
    for item in matching:
        diff = item.sync_diff()
        if diff is not None:
            all_properties.extend(diff.properties)

    return SyncDiffData(
        series_id=series_id,
        event_id=event_id,
        target_id=target_id,
        properties=all_properties,
    )
