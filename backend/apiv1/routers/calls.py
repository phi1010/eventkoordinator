"""
Calls router.

Handles CRUD endpoints for Calls (Ausschreibungen).
"""

import logging
import uuid
from datetime import date, datetime

import apiv1
from apiv1.api_utils import api_permission_mandatory, api_permission_required
from apiv1.models import Call as CallModel
from apiv1.schemas import CallCreateIn, CallOut, CallUpdateIn, ErrorOut
from ninja import Router

router = Router()
logger = logging.getLogger(__name__)


def _call_to_schema(call: CallModel) -> CallOut:
    return CallOut(
        id=call.id,
        title=call.title,
        description=call.description,
        execution_period_start=call.execution_period_start.isoformat(),
        execution_period_end=call.execution_period_end.isoformat(),
        submission_deadline=call.submission_deadline.isoformat(),
        print_deadline=call.print_deadline.isoformat(),
        responsible_name=call.responsible_name,
        responsible_email=call.responsible_email,
        is_active=call.is_active,
    )


@router.get("/", response={200: list[CallOut], 401: ErrorOut, 403: ErrorOut})
@api_permission_mandatory()
def list_calls(request, active_only: bool = True):
    """List calls. Requires browse_proposal (submitters) or view_call (managers).
    Submitters always see active-only calls; managers respect the active_only param."""
    if not request.user.is_authenticated:
        return 401, ErrorOut(code="auth.notAuthenticated")

    can_browse = request.user.has_perm("apiv1.browse_proposal")
    can_manage = request.user.has_perm("apiv1.view_call")

    if not can_browse and not can_manage:
        return 403, ErrorOut(code="auth.permissionDenied")

    qs = CallModel.objects.all()
    if active_only or not can_manage:
        qs = qs.filter(is_active=True)

    return 200, [_call_to_schema(c) for c in qs]


@router.get("/{call_id}", response={200: CallOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut})
@api_permission_mandatory()
def get_call(request, call_id: uuid.UUID):
    """Get a single call by ID. Requires browse_proposal or view_call."""
    if not request.user.is_authenticated:
        return 401, ErrorOut(code="auth.notAuthenticated")

    can_browse = request.user.has_perm("apiv1.browse_proposal")
    can_manage = request.user.has_perm("apiv1.view_call")

    if not can_browse and not can_manage:
        return 403, ErrorOut(code="auth.permissionDenied")

    try:
        call = CallModel.objects.get(pk=call_id)
    except CallModel.DoesNotExist:
        return 404, ErrorOut(code="calls.notFound")

    # Submitters (browse_proposal only) may not see inactive calls
    if not can_manage and not call.is_active:
        return 404, ErrorOut(code="calls.notFound")

    return 200, _call_to_schema(call)


@router.post(
    "/create",
    response={201: CallOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "add", CallModel))
def create_call(request, payload: CallCreateIn):
    """Create a new call. Requires add_call permission."""
    try:
        call = CallModel.objects.create(
            title=payload.title,
            description=payload.description or "",
            execution_period_start=date.fromisoformat(payload.execution_period_start),
            execution_period_end=date.fromisoformat(payload.execution_period_end),
            submission_deadline=datetime.fromisoformat(payload.submission_deadline),
            print_deadline=date.fromisoformat(payload.print_deadline),
            responsible_name=payload.responsible_name,
            responsible_email=payload.responsible_email,
            is_active=payload.is_active if payload.is_active is not None else True,
        )
    except (ValueError, Exception) as e:
        logger.error(f"Failed to create call: {e}")
        return 400, ErrorOut(code="calls.createFailed")
    return 201, _call_to_schema(call)


@router.put(
    "/{call_id}",
    response={200: CallOut, 400: ErrorOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "change", CallModel))
def update_call(request, call_id: uuid.UUID, payload: CallUpdateIn):
    """Update an existing call. Requires change_call permission."""
    try:
        call = CallModel.objects.get(pk=call_id)
    except CallModel.DoesNotExist:
        return 404, ErrorOut(code="calls.notFound")

    try:
        if payload.title is not None:
            call.title = payload.title
        if payload.description is not None:
            call.description = payload.description
        if payload.execution_period_start is not None:
            call.execution_period_start = date.fromisoformat(payload.execution_period_start)
        if payload.execution_period_end is not None:
            call.execution_period_end = date.fromisoformat(payload.execution_period_end)
        if payload.submission_deadline is not None:
            call.submission_deadline = datetime.fromisoformat(payload.submission_deadline)
        if payload.print_deadline is not None:
            call.print_deadline = date.fromisoformat(payload.print_deadline)
        if payload.responsible_name is not None:
            call.responsible_name = payload.responsible_name
        if payload.responsible_email is not None:
            call.responsible_email = payload.responsible_email
        if payload.is_active is not None:
            call.is_active = payload.is_active
        call.save()
    except (ValueError, Exception) as e:
        logger.error(f"Failed to update call {call_id}: {e}")
        return 400, ErrorOut(code="calls.updateFailed")

    return 200, _call_to_schema(call)


@router.delete(
    "/{call_id}",
    response={204: None, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "delete", CallModel))
def delete_call(request, call_id: uuid.UUID):
    """Delete a call. Requires delete_call permission."""
    try:
        call = CallModel.objects.get(pk=call_id)
    except CallModel.DoesNotExist:
        return 404, ErrorOut(code="calls.notFound")
    call.delete()
    return 204, None
