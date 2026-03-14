"""
Proposals router.

Handles endpoints for managing proposals, associations, and validation.
"""

import logging
import uuid
from datetime import timedelta
from typing import cast

import pydot
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpResponse
from django.utils import timezone
from ninja import File, Router, UploadedFile
from openid_user_management.models import OpenIDUser
from viewflow.fsm import chart

import apiv1
from apiv1.api_utils import (
    api_permission_mandatory,
    api_permission_required,
)
from apiv1.flows import ProposalFlow
from apiv1.helpers import model_proposal_to_schema
from apiv1.models import check_proposal_required_fields
from apiv1.models import Proposal as ProposalModel
from apiv1.models import Event as EventModel
from apiv1.models import ProposalArea, ProposalLanguage, SubmissionType
from apiv1.schemas import (
    ErrorOut,
    ProposalCreateIn,
    ProposalDetail,
    ProposalEventSummary,
    ProposalHistory,
    ProposalHistoryEntry,
    ProposalSummary,
    ProposalTransitionOut,
    ProposalTransitions,
    ProposalUpdateIn,
    UserBasic,
)


router = Router()
logger = logging.getLogger(__name__)


def _proposal_to_detail_schema(proposal: ProposalModel) -> ProposalDetail:
    submission_type_code = (
        proposal.submission_type.code if proposal.submission_type else ""
    )
    area_code = proposal.area.code if proposal.area else None
    language_code = proposal.language.code if proposal.language else None

    owner = None
    if proposal.owner:
        owner = UserBasic(id=proposal.owner.pk, username=proposal.owner.username)

    editors = [UserBasic(id=p.pk, username=p.username) for p in proposal.editors.all()]

    return ProposalDetail(
        id=proposal.id,
        title=proposal.title,
        submission_type=submission_type_code,
        area=area_code,
        language=language_code,
        abstract=proposal.abstract,
        description=proposal.description,
        internal_notes=proposal.internal_notes,
        occurrence_count=proposal.occurrence_count,
        duration_days=proposal.duration_days,
        duration_time_per_day=proposal.duration_time_per_day,
        is_basic_course=proposal.is_basic_course,
        max_participants=proposal.max_participants,
        material_cost_eur=str(proposal.material_cost_eur),
        preferred_dates=proposal.preferred_dates,
        is_regular_member=proposal.is_regular_member,
        has_building_access=proposal.has_building_access,
        photo=proposal.photo.url if proposal.photo else None,
        owner=owner,
        editors=editors,
    )


@router.get("/flow-chart", response={200: bytes, 401: ErrorOut, 403: ErrorOut})
def flow_chart_image(request):
    dot_graph = chart(ProposalFlow.status)

    graphs = pydot.graph_from_dot_data(dot_graph)
    graph = graphs[0]
    png_data = graph.create(format="svg")

    return HttpResponse(png_data, content_type="image/svg+xml")


@router.get(
    "/search", response={200: list[ProposalSummary], 401: ErrorOut, 403: ErrorOut}
)
@api_permission_required((apiv1, "browse", ProposalModel))
def search_proposals(request, q: str = ""):
    """Search proposals by title for autocomplete dropdowns."""
    proposals = (
        ProposalModel.objects.select_related("submission_type")
        .filter(title__icontains=q)
        .order_by("title")[:20]
    )
    return [
        model_proposal_to_schema(p)
        for p in proposals
        if request.user.has_perm((apiv1, "view", ProposalModel), p)
    ]


@router.post(
    "/create",
    response={201: ProposalSummary, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "add", ProposalModel))
def create_proposal(
    request, payload: ProposalCreateIn
) -> tuple[int, ProposalSummary] | tuple[int, ErrorOut]:
    """Create a new proposal with sensible defaults"""
    try:
        # Get submission type if provided, otherwise leave as None
        submission_type = None
        if payload.submission_type:
            try:
                submission_type = SubmissionType.objects.get(
                    code=payload.submission_type
                )
            except SubmissionType.DoesNotExist:
                return 400, ErrorOut(error="Invalid submission type")

        # Use defaults for all optional fields
        title = payload.title or ""
        # Keep text fields empty by default; frontend shows guidance instead
        abstract = payload.abstract or ""
        description = payload.description or ""
        duration_days = (
            payload.duration_days if payload.duration_days is not None else 1
        )
        duration_time_per_day = (
            payload.duration_time_per_day
            if payload.duration_time_per_day is not None
            else "00:00"
        )
        max_participants = (
            payload.max_participants if payload.max_participants is not None else 0
        )
        occurrence_count = (
            payload.occurrence_count if payload.occurrence_count is not None else 0
        )
        material_cost_eur = (
            payload.material_cost_eur
            if payload.material_cost_eur is not None
            else "0.00"
        )
        preferred_dates = payload.preferred_dates or ""
        is_basic_course = (
            payload.is_basic_course if payload.is_basic_course is not None else False
        )
        is_regular_member = (
            payload.is_regular_member
            if payload.is_regular_member is not None
            else False
        )
        has_building_access = (
            payload.has_building_access
            if payload.has_building_access is not None
            else False
        )

        # Create proposal with owner set to authenticated user
        proposal = ProposalModel.objects.create(
            title=title,
            submission_type=submission_type,
            area_id=payload.area,
            language_id=payload.language,
            abstract=abstract,
            description=description,
            internal_notes=payload.internal_notes or "",
            occurrence_count=occurrence_count,
            duration_days=duration_days,
            duration_time_per_day=duration_time_per_day,
            is_basic_course=is_basic_course,
            max_participants=max_participants,
            material_cost_eur=material_cost_eur,
            preferred_dates=preferred_dates,
            is_regular_member=is_regular_member,
            has_building_access=has_building_access,
            owner=request.user if request.user.is_authenticated else None,
        )

        try:
            proposal.clean()  # Validate duration
        except Exception as e:
            logger.error(f"Proposal validation failed: {str(e)}")
            return 400, ErrorOut(error="Proposal validation failed")

        return 201, model_proposal_to_schema(proposal)
    except Exception as e:
        logger.error(f"Failed to create proposal: {str(e)}")
        return 400, ErrorOut(error="Failed to create proposal")


@router.get(
    "/{proposal_id}",
    response={200: ProposalDetail, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def get_proposal(
    request, proposal_id: uuid.UUID
) -> tuple[int, ProposalDetail] | tuple[int, ErrorOut]:
    """Get full proposal details"""
    try:
        proposal = (
            ProposalModel.objects.select_related(
                "submission_type", "area", "language", "owner"
            )
            .prefetch_related("editors")
            .get(pk=proposal_id)
        )
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")

    if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to view this proposal")

    return 200, _proposal_to_detail_schema(proposal)


@router.post(
    "/{proposal_id}/photo",
    response={200: ProposalDetail, 400: ErrorOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def upload_proposal_photo(
    request, proposal_id: uuid.UUID, file: UploadedFile = File(...)
) -> tuple[int, ProposalDetail] | tuple[int, ErrorOut]:
    """Upload or replace a proposal image."""
    try:
        proposal = (
            ProposalModel.objects.select_related(
                "submission_type", "area", "language", "owner"
            )
            .prefetch_related("editors")
            .get(pk=proposal_id)
        )
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")

    if not request.user.has_perm((apiv1, "change", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to change this proposal")

    photo_field = cast(models.FileField, proposal._meta.get_field("photo"))
    try:
        photo_field.clean(file, proposal)
    except ValidationError as exc:
        return 400, ErrorOut(
            error="Invalid proposal image",
            detail=" ".join(exc.messages),
        )

    previous_photo_name = proposal.photo.name if proposal.photo else None
    proposal.photo = file
    proposal.save(update_fields=["photo"])

    if previous_photo_name and previous_photo_name != proposal.photo.name:
        photo_field.storage.delete(previous_photo_name)

    return 200, _proposal_to_detail_schema(proposal)


@router.put(
    "/{proposal_id}",
    response={
        200: ProposalDetail,
        400: ErrorOut,
        404: ErrorOut,
        401: ErrorOut,
        403: ErrorOut,
    },
)
@api_permission_mandatory()
def update_proposal(
    request, proposal_id: uuid.UUID, payload: ProposalUpdateIn
) -> tuple[int, ProposalDetail] | tuple[int, ErrorOut]:
    """Update a proposal"""
    try:
        proposal = ProposalModel.objects.select_related(
            "submission_type", "area", "language"
        ).get(pk=proposal_id)
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")
    if not request.user.has_perm((apiv1, "change", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to change this proposal")

    # Update fields that were provided
    if payload.title is not None:
        proposal.title = payload.title

    if payload.submission_type is not None:
        try:
            submission_type = SubmissionType.objects.get(code=payload.submission_type)
            proposal.submission_type = submission_type
        except SubmissionType.DoesNotExist:
            return 400, ErrorOut(error="Invalid submission type")

    if payload.area is not None:
        if payload.area:
            try:
                area = ProposalArea.objects.get(code=payload.area)
                proposal.area = area
            except ProposalArea.DoesNotExist:
                return 400, ErrorOut(error="Invalid area")
        else:
            proposal.area = None

    if payload.language is not None:
        if payload.language:
            try:
                language = ProposalLanguage.objects.get(code=payload.language)
                proposal.language = language
            except ProposalLanguage.DoesNotExist:
                return 400, ErrorOut(error="Invalid language")
        else:
            proposal.language = None

    if payload.abstract is not None:
        proposal.abstract = payload.abstract

    if payload.description is not None:
        proposal.description = payload.description

    if payload.internal_notes is not None:
        proposal.internal_notes = payload.internal_notes

    if payload.occurrence_count is not None:
        proposal.occurrence_count = payload.occurrence_count

    if payload.duration_days is not None:
        proposal.duration_days = payload.duration_days

    if payload.duration_time_per_day is not None:
        proposal.duration_time_per_day = payload.duration_time_per_day

    if payload.is_basic_course is not None:
        proposal.is_basic_course = payload.is_basic_course

    if payload.max_participants is not None:
        proposal.max_participants = payload.max_participants

    if payload.material_cost_eur is not None:
        proposal.material_cost_eur = payload.material_cost_eur

    if payload.preferred_dates is not None:
        proposal.preferred_dates = payload.preferred_dates

    if payload.is_regular_member is not None:
        proposal.is_regular_member = payload.is_regular_member

    if payload.has_building_access is not None:
        proposal.has_building_access = payload.has_building_access

    # Owner cannot be changed after proposal creation
    # It is automatically set to the creating user and remains immutable

    # Handle editors update
    if payload.editor_ids is not None:
        try:
            # UUIDs are already strings, no conversion needed
            user_ids = [uid for uid in payload.editor_ids if uid]
            editors = OpenIDUser.objects.filter(pk__in=user_ids)
            proposal.editors.set(editors)
        except (ValueError, Exception) as e:
            logger.error(f"Failed to update editors: {str(e)}")
            return 400, ErrorOut(error="Invalid editor ID format")

    try:
        proposal.clean()  # Validate duration
    except Exception as e:
        logger.error(f"Proposal validation failed: {str(e)}")
        return 400, ErrorOut(error="Proposal validation failed")

    proposal.save()

    return 200, _proposal_to_detail_schema(proposal)


@router.delete(
    "/{proposal_id}",
    response={204: None, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def delete_proposal(
    request, proposal_id: uuid.UUID
) -> tuple[int, None] | tuple[int, ErrorOut]:
    """Delete a proposal when the current user has object-level permission."""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")

    if not request.user.has_perm((apiv1, "delete", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to delete this proposal")

    proposal.delete()
    return 204, None


@router.get(
    "/{proposal_id}/checklist",
    response={200: dict, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def get_proposal_checklist(
    request, proposal_id: uuid.UUID
) -> tuple[int, dict] | tuple[int, ErrorOut]:
    """Get validation checklist for a proposal showing what information is complete"""
    try:
        proposal = ProposalModel.objects.select_related("submission_type").get(
            pk=proposal_id
        )
        if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
            return 401, ErrorOut(error="Permission denied")
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "view", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")

    checklist = check_proposal_required_fields(proposal)

    return 200, checklist


@router.get(
    "/{proposal_id}/history",
    response={200: ProposalHistory, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def get_proposal_history(
    request, proposal_id: uuid.UUID, days: int = 7
) -> tuple[int, ProposalHistory] | tuple[int, ErrorOut]:
    """Get proposal history changes for the last N days (default 7 days)."""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")

    if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to view this proposal")

    safe_days = max(1, min(30, days))  # Limit to 1-30 days for safety
    cutoff_date = timezone.now() - timedelta(days=safe_days)

    history_records = (
        proposal.history.filter(history_date__gte=cutoff_date)
        .select_related("history_user")
        .order_by("-history_date", "-history_id")
    )

    change_type_map = {"+": "create", "~": "change", "-": "delete"}
    entries: list[ProposalHistoryEntry] = []

    for record in history_records:
        change_type = change_type_map.get(record.history_type, "change")
        changed_by = record.history_user.username if record.history_user else "Unknown"

        if record.history_type == "~":
            prev_record = getattr(record, "prev_record", None)

            if prev_record is not None:
                diff = record.diff_against(prev_record)
                if diff.changes:
                    for change in diff.changes:
                        old_val = None if change.old is None else str(change.old)
                        new_val = None if change.new is None else str(change.new)
                        entries.append(
                            ProposalHistoryEntry(
                                timestamp=record.history_date.isoformat(),
                                changed_by=changed_by,
                                change_type=change_type,
                                field_name=change.field,
                                old_value=old_val,
                                new_value=new_val,
                                summary=f"Changed proposal field: {change.field}",
                            )
                        )
                    continue

            entries.append(
                ProposalHistoryEntry(
                    timestamp=record.history_date.isoformat(),
                    changed_by=changed_by,
                    change_type=change_type,
                    field_name=None,
                    old_value=None,
                    new_value=None,
                    summary="Proposal updated",
                )
            )
            continue

        summary = (
            "Proposal created" if record.history_type == "+" else "Proposal deleted"
        )
        entries.append(
            ProposalHistoryEntry(
                timestamp=record.history_date.isoformat(),
                changed_by=changed_by,
                change_type=change_type,
                field_name=None,
                old_value=None,
                new_value=None,
                summary=summary,
            )
        )

    return 200, ProposalHistory(proposal_id=proposal_id, entries=entries)


@router.get(
    "/{proposal_id}/transitions",
    response={200: ProposalTransitions, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def get_proposal_transitions(
    request, proposal_id: uuid.UUID
) -> tuple[int, ProposalTransitions | ErrorOut]:
    """Get available transitions for a proposal and the current user."""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")

    if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to view this proposal")

    # Get available transitions from ProposalFlow
    flow = ProposalFlow(proposal)
    transitions = flow.get_available_transitions(request.user)

    # Convert to response format with proper schema objects
    transitions_data = [
        ProposalTransitionOut(
            action=t.action,
            label=t.label,
            target_status=t.target_status,
            enabled=t.enabled,
            disable_reason=t.disable_reason,
        )
        for t in transitions
    ]

    return 200, ProposalTransitions(
        proposal_id=proposal_id,
        current_status=proposal.status,
        transitions=transitions_data,
    )


def _execute_proposal_transition(
    request, proposal_id: uuid.UUID, action: str
) -> tuple[int, ProposalDetail | ErrorOut]:
    """
    Common helper method for executing proposal transitions.
    """
    try:
        proposal = ProposalModel.objects.select_related(
            "submission_type", "area", "language"
        ).get(pk=proposal_id)
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")

    # Check if user can view the proposal
    if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to view this proposal")

    # Create flow and evaluate transition
    flow = ProposalFlow(proposal)
    transitions = flow.get_available_transitions(request.user)

    # Find the transition
    transition = next((t for t in transitions if t.action == action), None)
    if not transition:
        return 400, ErrorOut(error=f"Unknown transition action: {action}")

    # Check if transition is enabled
    if not transition.enabled:
        return 400, ErrorOut(
            error=f"Cannot perform this action: {transition.disable_reason}"
        )

    # Execute the transition
    try:
        success = flow.execute_transition(action)
        if not success:
            return 400, ErrorOut(error=f"Failed to execute {action} transition")
    except Exception as e:
        logger.error(f"Error executing transition {action}: {str(e)}")
        return 400, ErrorOut(error="Error executing transition")

    return 200, _proposal_to_detail_schema(proposal)


@router.post(
    "/{proposal_id}/submit",
    response={
        200: ProposalDetail,
        400: ErrorOut,
        404: ErrorOut,
        401: ErrorOut,
        403: ErrorOut,
    },
)
@api_permission_mandatory()
def submit_proposal(
    request, proposal_id: uuid.UUID
) -> tuple[int, ProposalDetail | ErrorOut]:
    """Submit a proposal (from DRAFT or REVISE status)."""
    return _execute_proposal_transition(request, proposal_id, "submit")


@router.post(
    "/{proposal_id}/accept",
    response={
        200: ProposalDetail,
        400: ErrorOut,
        404: ErrorOut,
        401: ErrorOut,
        403: ErrorOut,
    },
)
@api_permission_mandatory()
def accept_proposal(
    request, proposal_id: uuid.UUID
) -> tuple[int, ProposalDetail | ErrorOut]:
    """Accept a submitted proposal."""
    return _execute_proposal_transition(request, proposal_id, "accept")


@router.post(
    "/{proposal_id}/reject",
    response={
        200: ProposalDetail,
        400: ErrorOut,
        404: ErrorOut,
        401: ErrorOut,
        403: ErrorOut,
    },
)
@api_permission_mandatory()
def reject_proposal(
    request, proposal_id: uuid.UUID
) -> tuple[int, ProposalDetail | ErrorOut]:
    """Reject a submitted proposal."""
    return _execute_proposal_transition(request, proposal_id, "reject")


@router.post(
    "/{proposal_id}/revise",
    response={
        200: ProposalDetail,
        400: ErrorOut,
        404: ErrorOut,
        401: ErrorOut,
        403: ErrorOut,
    },
)
@api_permission_mandatory()
def revise_proposal(
    request, proposal_id: uuid.UUID
) -> tuple[int, ProposalDetail | ErrorOut]:
    """Request revision for a submitted or rejected proposal."""
    return _execute_proposal_transition(request, proposal_id, "revise")


@router.get(
    "/{proposal_id}/events",
    response={200: list[ProposalEventSummary], 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def get_proposal_events(
    request, proposal_id: uuid.UUID
) -> tuple[int, list[ProposalEventSummary]] | tuple[int, ErrorOut]:
    """List all events linked to a proposal."""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
    except ProposalModel.DoesNotExist:
        return 404, ErrorOut(error="Proposal not found")

    if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
        return 401, ErrorOut(error="Unauthorized to view this proposal")

    events = (
        EventModel.objects.filter(proposal=proposal)
        .select_related("series", "proposal")
        .order_by("start_time")
    )

    return 200, [
        ProposalEventSummary(
            id=event.id,
            name=event.name,
            startTime=event.start_time.isoformat(),
            endTime=event.end_time.isoformat(),
            status=event.status,
            series_id=event.series_id,
            series_name=event.series.name,
        )
        for event in events
        if request.user.has_perm((apiv1, "view", EventModel), event)
    ]

