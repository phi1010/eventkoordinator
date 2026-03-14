"""
Lookup and search router.

Handles endpoints for searching and retrieving lookup table data,
user searches, and global search functionality.
"""

from typing import Optional

import openid_user_management
from django.http import HttpRequest
from ninja import Router
from openid_user_management.models import OpenIDUser

import apiv1
from apiv1.api_utils import (
    api_permission_mandatory,
    api_permission_required,
)
from apiv1.helpers import (
    model_event_to_schema,
    model_series_to_schema,
)
from apiv1.models import (
    Event as EventModel,
    ProposalArea,
    ProposalLanguage,
    SubmissionType,
    Series as SeriesModel,
)
from apiv1.schemas import ErrorOut, Event, LookupOut, Series, UserBasic

router = Router()


@router.get(
    "/submission_types",
    response={200: list[LookupOut], 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "view", SubmissionType))
def get_submission_types(request):
    """Return all active submission types"""

    items = (
        SubmissionType.objects.filter(is_active=True)
        .order_by("sort_order", "label")
        .only("code", "label", "description", "is_active", "sort_order")
    )
    return [
        LookupOut(
            code=i.code,
            label=i.label,
            description=i.description or "",
            is_active=i.is_active,
            sort_order=i.sort_order,
        )
        for i in items
    ]


@router.get(
    "/proposal_languages",
    response={200: list[LookupOut], 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "view", ProposalLanguage))
def get_proposal_languages(request):
    """Return all active proposal languages"""

    items = (
        ProposalLanguage.objects.filter(is_active=True)
        .order_by("sort_order", "label")
        .only("code", "label", "description", "is_active", "sort_order")
    )
    return [
        LookupOut(
            code=i.code,
            label=i.label,
            description=i.description or "",
            is_active=i.is_active,
            sort_order=i.sort_order,
        )
        for i in items
    ]


@router.get(
    "/proposal_areas",
    response={200: list[LookupOut], 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "view", ProposalArea))
def get_proposal_areas(request):
    """Return all active proposal areas"""

    items = (
        ProposalArea.objects.filter(is_active=True)
        .order_by("sort_order", "label")
        .only("code", "label", "description", "is_active", "sort_order")
    )
    return [
        LookupOut(
            code=i.code,
            label=i.label,
            description=i.description or "",
            is_active=i.is_active,
            sort_order=i.sort_order,
        )
        for i in items
    ]


@router.get(
    "/users/search",
    response={200: list[UserBasic], 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def search_users(request: HttpRequest, q: str = ""):
    """Search users by username for autocomplete"""
    if request.user.has_perm((openid_user_management, "view", OpenIDUser)):
        users = OpenIDUser.objects.filter(username__icontains=q).order_by("username")[
            :20
        ]
    else:
        users = OpenIDUser.objects.filter(username__exact=q)[:1]
    return [UserBasic(id=u.pk, username=u.username) for u in users]


@router.get(
    "/series/search", response={200: list[Series], 401: ErrorOut, 403: ErrorOut}
)
@api_permission_required((apiv1, "view", SeriesModel))
def search_series(request, q: str = ""):
    """Search series by name for autocomplete dropdowns."""
    series_list = SeriesModel.objects.filter(name__icontains=q).order_by("name")[:20]
    return [model_series_to_schema(s) for s in series_list]


@router.get(
    "/events/search", response={200: list[Event], 401: ErrorOut, 403: ErrorOut}
)
@api_permission_required((apiv1, "browse", EventModel))
@api_permission_required((apiv1, "view", EventModel))
def search_events(request, q: str = "", series_id: Optional[str] = None):
    """Search events by name, optionally constrained to one series."""
    events = EventModel.objects.select_related("series").all()
    if series_id:
        events = events.filter(series_id=series_id)
    if q:
        events = events.filter(name__icontains=q)
    events = events.order_by("start_time")[:20]
    return [model_event_to_schema(e) for e in events]
