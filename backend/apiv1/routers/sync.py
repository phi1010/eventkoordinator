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
from apiv1.api_utils import api_permission_required, api_permission_mandatory
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
    """Return all SyncBaseItem instances linking *target* to *event*."""
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
    """Create a sync item for an event on a specific target."""
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
    """Get synchronization status for an event across all sync targets.
    Each status entry also reports ``can_push`` and ``can_delete`` by querying
    the permissions of the real sync item instances for the requesting user.
    """
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)
    targets = SyncBaseTarget.objects.all()
    statuses = []
    for target in targets:
        status = target.get_status(event)
        matching = _items_for_target_and_event(target, event)
        latest_item = max(matching, key=lambda i: i.updated_at) if matching else None
        # Determine push/delete capability by querying real instance permissions.
        if matching:
            can_push = any(
                request.user.has_perm(
                    "apiv1.push_syncbaseitem", item.get_real_instance()
                )
                for item in matching
            )
            can_delete = any(
                request.user.has_perm(
                    "apiv1.delete_syncbaseitem", item.get_real_instance()
                )
                for item in matching
            )
        else:
            # No items yet – push == "create", gated by the global add permission.
            can_push = request.user.has_perm("apiv1.add_syncbaseitem")
            can_delete = False
        statuses.append(
            SyncStatus(
                target_id=target.pk,
                platform=target.type,
                status=status.value,
                last_synced=(
                    latest_item.updated_at.isoformat() if latest_item else None
                ),
                last_error=None,
                can_push=can_push,
                can_delete=can_delete,
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
@api_permission_mandatory()
def delete_remote_sync_item(
    request, series_id: UUID, event_id: UUID, target_id: UUID
) -> SyncDeleteResult:
    """Delete the remote resource for all sync items linking this event to the target.

    Requires at minimum ``view_event`` permission. Additionally checks
    ``delete_syncbaseitem`` on each real instance before deletion.
    """
    if not request.user.has_perm("apiv1.view_event"):
        return 403, ErrorOut(error="Permission denied")

    event = get_object_or_404(Event, pk=event_id, series_id=series_id)
    target = get_object_or_404(SyncBaseTarget, pk=target_id)
    matching = _items_for_target_and_event(target, event)
    # Check permission on each real instance before mutating anything.
    for item in matching:
        real = item.get_real_instance()
        if not request.user.has_perm("apiv1.delete_syncbaseitem", real):
            return 403, ErrorOut(error="Permission denied")
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
@api_permission_mandatory()
def push_to_platform(
    request, series_id: UUID, event_id: UUID, target_id: UUID
) -> SyncPushResult:
    """Push/update event data to a specific sync target.

    Requires at minimum ``view_event`` permission. Additionally checks
    ``push_syncbaseitem`` on each real instance before pushing.
    """
    if not request.user.has_perm("apiv1.view_event"):
        return 403, ErrorOut(error="Permission denied")
    event = get_object_or_404(Event, pk=event_id, series_id=series_id)
    target = get_object_or_404(SyncBaseTarget, pk=target_id)
    matching = _items_for_target_and_event(target, event)
    # Check permission on each real instance before pushing.
    for item in matching:
        real = item.get_real_instance()
        if not request.user.has_perm("apiv1.push_syncbaseitem", real):
            return 403, ErrorOut(error="Permission denied")
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
