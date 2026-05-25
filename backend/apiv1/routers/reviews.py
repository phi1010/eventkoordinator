"""
Proposal reviews router.

Endpoints for managing proposal peer-reviews and group-review requests.
"""

import logging
import uuid

from django.contrib.auth.models import Group
from django.utils import timezone
from ninja import Router

import apiv1
from apiv1.api_utils import api_permission_mandatory
from apiv1.models import Proposal as ProposalModel
from apiv1.models.basedata import ProposalReview
from apiv1.schemas import (
    ErrorOut,
    ProposalReviewCreateIn,
    ProposalReviewOut,
    ProposalReviewUpdateIn,
)

router = Router()
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _group_label(code: str) -> str:
    """Return the display name for a group identified by its pk (stored as string)."""
    try:
        return Group.objects.get(pk=int(code)).name
    except (Group.DoesNotExist, ValueError):
        return code


def _review_to_schema(r: ProposalReview) -> ProposalReviewOut:
    return ProposalReviewOut(
        id=r.id,
        kind=r.kind,
        reviewer_id=r.reviewer_id,
        reviewer_username=r.reviewer.username if r.reviewer else None,
        reviewer_is_system=r.reviewer_is_system,
        group_code=r.group_code,
        group_label=_group_label(r.group_code) if r.group_code else "",
        status=r.status,
        comment=r.comment,
        requested_by_id=r.requested_by_id,
        requested_by_username=r.requested_by.username if r.requested_by else None,
        requested_at=r.requested_at.isoformat() if r.requested_at else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        requested_directly=r.requested_directly,
        requested_via_groups=r.requested_via_groups or [],
        previous_status=r.previous_status or "",
        previous_comment=r.previous_comment or "",
        migrated=r.migrated,
        created_at=r.created_at.isoformat(),
    )


def _get_proposal_or_404(proposal_id: uuid.UUID, request) -> tuple[ProposalModel | None, tuple | None]:
    """Return (proposal, None) or (None, error_tuple)."""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "view", ProposalModel), None):
            return None, (401, ErrorOut(code="auth.permissionDenied"))
        return None, (404, ErrorOut(code="proposals.notFound"))

    if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
        return None, (403, ErrorOut(code="auth.permissionDenied"))

    return proposal, None


# ── List ──────────────────────────────────────────────────────────────────────

@router.get(
    "/{proposal_id}/reviews",
    response={200: list[ProposalReviewOut], 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def list_reviews(request, proposal_id: uuid.UUID):
    """Return all reviews and group-review requests for a proposal."""
    proposal, err = _get_proposal_or_404(proposal_id, request)
    if err:
        return err

    reviews = ProposalReview.objects.filter(proposal=proposal).select_related(
        "reviewer", "requested_by"
    )
    return 200, [_review_to_schema(r) for r in reviews]


# ── Create ─────────────────────────────────────────────────────────────────────

@router.post(
    "/{proposal_id}/reviews",
    response={201: ProposalReviewOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def create_review(request, proposal_id: uuid.UUID, payload: ProposalReviewCreateIn):
    """Create a new review (user or group) for a proposal.

    - Moderators can request reviews from any user or group.
    - Any authenticated user can add their own unsolicited review.
    """
    proposal, err = _get_proposal_or_404(proposal_id, request)
    if err:
        return err

    can_moderate = request.user.has_perm((apiv1, "moderate", ProposalModel), proposal)

    if payload.kind == "group":
        if not can_moderate:
            return 403, ErrorOut(code="auth.permissionDenied")
        if not payload.group_code:
            return 400, ErrorOut(code="reviews.missingGroupCode")
        # Validate that the group_code is a valid Django Group pk
        try:
            group_obj = Group.objects.prefetch_related("user_set").get(pk=int(payload.group_code))
        except (Group.DoesNotExist, ValueError):
            return 400, ErrorOut(code="reviews.groupNotFound")
        # Prevent duplicate group requests
        if ProposalReview.objects.filter(
            proposal=proposal, kind="group", group_code=payload.group_code
        ).exists():
            return 400, ErrorOut(code="reviews.duplicateGroupRequest")

        now = timezone.now()
        r = ProposalReview.objects.create(
            proposal=proposal,
            kind="group",
            group_code=payload.group_code,
            requested_by=request.user,
            requested_at=now,
        )

        # Create or update a pending user-review slot for every group member so
        # the group card can show member chips and derive its status.
        for member in group_obj.user_set.all():
            existing = ProposalReview.objects.filter(
                proposal=proposal, kind="user", reviewer=member
            ).first()
            if existing:
                via = existing.requested_via_groups or []
                if payload.group_code not in via:
                    existing.requested_via_groups = via + [payload.group_code]
                    existing.save(update_fields=["requested_via_groups"])
            else:
                ProposalReview.objects.create(
                    proposal=proposal,
                    kind="user",
                    reviewer=member,
                    status="pending",
                    comment="",
                    requested_by=request.user,
                    requested_at=now,
                    completed_at=None,
                    requested_directly=False,
                    requested_via_groups=[payload.group_code],
                )

        return 201, _review_to_schema(r)

    # kind == 'user'
    from openid_user_management.models import OpenIDUser

    if payload.reviewer_is_system:
        # Only moderators can create migrated system reviews
        if not can_moderate:
            return 403, ErrorOut(code="auth.permissionDenied")
        # Only one system review allowed per proposal
        if ProposalReview.objects.filter(proposal=proposal, reviewer_is_system=True).exists():
            return 400, ErrorOut(code="reviews.duplicateSystemReview")
        r = ProposalReview.objects.create(
            proposal=proposal,
            kind="user",
            reviewer=None,
            reviewer_is_system=True,
            status="note",
            comment=payload.comment,
            requested_at=timezone.now(),
            migrated=payload.migrated,
        )
        return 201, _review_to_schema(r)

    if payload.reviewer_id:
        # Requesting someone else's review — needs moderate permission
        if not can_moderate:
            return 403, ErrorOut(code="auth.permissionDenied")
        try:
            reviewer = OpenIDUser.objects.get(pk=payload.reviewer_id)
        except OpenIDUser.DoesNotExist:
            return 400, ErrorOut(code="reviews.reviewerNotFound")
    else:
        # Self-review — requires create_review permission (or moderate)
        reviewer = request.user
        has_create_review = request.user.has_perm((apiv1, "create_review", ProposalModel), None)
        if not has_create_review and not can_moderate:
            return 403, ErrorOut(code="auth.permissionDenied")

    # Prevent duplicate user reviews for the same reviewer on this proposal
    if ProposalReview.objects.filter(
        proposal=proposal, kind="user", reviewer=reviewer
    ).exists():
        return 400, ErrorOut(code="reviews.duplicateReview")

    r = ProposalReview.objects.create(
        proposal=proposal,
        kind="user",
        reviewer=reviewer,
        status=payload.status if payload.reviewer_id is None else "pending",
        comment=payload.comment if payload.reviewer_id is None else "",
        requested_by=request.user if payload.reviewer_id else None,
        requested_at=timezone.now(),
        completed_at=timezone.now() if payload.reviewer_id is None and payload.status != "pending" else None,
        requested_directly=payload.requested_directly,
        requested_via_groups=payload.requested_via_groups or [],
        migrated=payload.migrated,
    )
    return 201, _review_to_schema(r)


# ── Update ────────────────────────────────────────────────────────────────────

@router.put(
    "/{proposal_id}/reviews/{review_id}",
    response={200: ProposalReviewOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def update_review(
    request, proposal_id: uuid.UUID, review_id: uuid.UUID, payload: ProposalReviewUpdateIn
):
    """Submit or update a vote on an existing user review.

    Only the reviewer themselves can update their own review.
    Moderators can update any review.
    """
    proposal, err = _get_proposal_or_404(proposal_id, request)
    if err:
        return err

    try:
        review = ProposalReview.objects.select_related("reviewer", "requested_by").get(
            pk=review_id, proposal=proposal
        )
    except ProposalReview.DoesNotExist:
        return 404, ErrorOut(code="reviews.notFound")

    if review.kind == "group":
        return 400, ErrorOut(code="reviews.cannotUpdateGroupRequest")

    can_moderate = request.user.has_perm((apiv1, "moderate", ProposalModel), proposal)
    is_own = review.reviewer == request.user

    if not is_own and not can_moderate:
        return 403, ErrorOut(code="auth.permissionDenied")

    valid_statuses = {"approved", "rejected", "revise", "pending"}
    if payload.status not in valid_statuses:
        return 400, ErrorOut(code="reviews.invalidStatus")

    if payload.status == "pending":
        # Withdraw: only the reviewer can reset their own vote back to pending
        if not is_own:
            return 403, ErrorOut(code="auth.permissionDenied")
        review.status = "pending"
        review.completed_at = None
        review.save(update_fields=["status", "completed_at"])
    else:
        review.status = payload.status
        review.comment = payload.comment
        review.completed_at = timezone.now()
        review.save()
    return 200, _review_to_schema(review)


# ── Delete (withdraw) ─────────────────────────────────────────────────────────

@router.delete(
    "/{proposal_id}/reviews/{review_id}",
    response={204: None, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def delete_review(request, proposal_id: uuid.UUID, review_id: uuid.UUID):
    """Withdraw a review request or remove a review.

    Moderators can withdraw any review. Reviewers can withdraw their own.
    """
    proposal, err = _get_proposal_or_404(proposal_id, request)
    if err:
        return err

    try:
        review = ProposalReview.objects.select_related("reviewer").get(
            pk=review_id, proposal=proposal
        )
    except ProposalReview.DoesNotExist:
        return 404, ErrorOut(code="reviews.notFound")

    can_moderate = request.user.has_perm((apiv1, "moderate", ProposalModel), proposal)
    is_own = review.reviewer == request.user

    if not is_own and not can_moderate:
        return 403, ErrorOut(code="auth.permissionDenied")

    if review.kind == "group":
        # Remove this group code from every member's requested_via_groups.
        # Delete member slots that were created solely by this group request.
        group_code = review.group_code
        member_reviews = ProposalReview.objects.filter(
            proposal=proposal,
            kind="user",
            requested_via_groups__contains=group_code,
        )
        to_delete = []
        to_update = []
        for mr in member_reviews:
            via = [c for c in (mr.requested_via_groups or []) if c != group_code]
            if not via and not mr.requested_directly and mr.status == "pending":
                to_delete.append(mr.pk)
            else:
                mr.requested_via_groups = via
                to_update.append(mr)
        if to_delete:
            ProposalReview.objects.filter(pk__in=to_delete).delete()
        if to_update:
            ProposalReview.objects.bulk_update(to_update, ["requested_via_groups"])

    review.delete()
    return 204, None


# ── Reset on resubmission ─────────────────────────────────────────────────────

@router.post(
    "/{proposal_id}/reviews/reset",
    response={200: list[ProposalReviewOut], 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def reset_reviews(request, proposal_id: uuid.UUID):
    """Reset all completed reviews to pending (called after resubmission).

    Preserves previous_status and previous_comment for context.
    Group requests get their requested_at refreshed.
    System/note reviews are not reset.
    Only the proposal owner/editors or moderators may call this.
    """
    proposal, err = _get_proposal_or_404(proposal_id, request)
    if err:
        return err

    can_moderate = request.user.has_perm((apiv1, "moderate", ProposalModel), proposal)
    is_owner_or_editor = (
        request.user == proposal.owner
        or proposal.editors.filter(pk=request.user.pk).exists()
    )

    if not can_moderate and not is_owner_or_editor:
        return 403, ErrorOut(code="auth.permissionDenied")

    now = timezone.now()
    reviews = ProposalReview.objects.filter(proposal=proposal).select_related(
        "reviewer", "requested_by"
    )

    to_update = []
    for r in reviews:
        if r.reviewer_is_system or r.status == "note":
            continue
        if r.kind == "group":
            r.requested_at = now
            to_update.append(r)
        elif r.status != "pending":
            r.previous_status = r.status
            r.previous_comment = r.comment
            r.status = "pending"
            r.completed_at = None
            r.requested_at = now
            to_update.append(r)

    if to_update:
        ProposalReview.objects.bulk_update(
            to_update,
            ["status", "completed_at", "requested_at",
             "previous_status", "previous_comment"],
        )

    updated = ProposalReview.objects.filter(proposal=proposal).select_related(
        "reviewer", "requested_by"
    )
    return 200, [_review_to_schema(r) for r in updated]
