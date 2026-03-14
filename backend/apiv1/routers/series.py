"""
Series and events router.

Handles endpoints for managing event series and individual events within them.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import django.utils.timezone
import pydot
from django.http import HttpResponse
from ninja import Router
from viewflow.fsm import chart

import apiv1
from apiv1.api_utils import (
    api_permission_mandatory,
    api_permission_required,
)
from apiv1.flows import EventFlow
from apiv1.helpers import (
    model_event_to_schema,
    model_series_list_item_to_schema,
    model_series_to_schema,
)
from apiv1.models import Event as EventModel
from apiv1.models import Series as SeriesModel
from apiv1.models import Proposal as ProposalModel
from apiv1.schemas import (
    CreateEventIn,
    CreateEventOut,
    CreateSeriesIn,
    ErrorOut,
    Event,
    EventTransitionOut,
    EventTransitions,
    Series,
    SeriesListItem,
    UpdateEventIn,
    UpdateSeriesIn,
)

router = Router()


@router.get("/event-flow-chart", response={200: bytes, 401: ErrorOut, 403: ErrorOut})
@api_permission_required((apiv1, "view", SeriesModel))
def event_flow_chart_image(request):
    """Return an SVG diagram of the event lifecycle state machine."""
    dot_graph = chart(EventFlow.status)
    graphs = pydot.graph_from_dot_data(dot_graph)
    graph = graphs[0]
    svg_data = graph.create(format="svg")
    return HttpResponse(svg_data, content_type="image/svg+xml")


@router.get("", response={200: list[SeriesListItem], 401: ErrorOut, 403: ErrorOut})
@api_permission_required((apiv1, "view", SeriesModel))
def get_series(request) -> list[SeriesListItem]:
    """Fetch and return all series without event payloads."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        series_list = SeriesModel.objects.all().order_by('name')
        return [model_series_list_item_to_schema(s) for s in series_list if s.id]
    except Exception as e:
        logger.error(f"Failed to fetch series: {str(e)}")
        return []


@router.post("/create", response={201: Series, 401: ErrorOut, 403: ErrorOut})
@api_permission_required((apiv1, "add", SeriesModel))
def create_series(request, payload: CreateSeriesIn) -> tuple[int, Series]:
    """Create a new series without creating an initial event."""
    series_id = uuid4()

    # Create series in database
    series_model = SeriesModel.objects.create(
        id=series_id,
        name=payload.name or "New Series",
        description=payload.description,
    )


    return 201, model_series_to_schema(series_model)


@router.post(
    "/{series_id}/events/create",
    response={201: CreateEventOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "change", SeriesModel))
@api_permission_required((apiv1, "add", EventModel))
def create_event(request, series_id: str, payload: CreateEventIn) -> tuple[int, CreateEventOut] | tuple[int, ErrorOut]:
    """Create a new event in a series"""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
    except SeriesModel.DoesNotExist:
        return 404, ErrorOut(error="Series not found")

    event_id = uuid4()
    now = django.utils.timezone.now().replace(second=0, microsecond=0)

    # Parse datetime strings
    if payload.startTime:
        try:
            start_dt = datetime.fromisoformat(payload.startTime)
        except ValueError:
            start_dt = now + timedelta(days=1)
    else:
        start_dt = now + timedelta(days=1)

    if payload.endTime:
        try:
            end_dt = datetime.fromisoformat(payload.endTime)
        except ValueError:
            end_dt = start_dt + timedelta(hours=1)
    else:
        end_dt = start_dt + timedelta(hours=1)

    # Create event in database
    event_model = EventModel.objects.create(
        id=event_id,
        series=series_model,
        name=payload.name or "New Event",
        start_time=start_dt,
        end_time=end_dt,
        tag=payload.tag,
        use_full_days=payload.useFullDays or False,
        proposal_id=payload.proposal_id,
    )

    return 201, CreateEventOut(series_id=series_model.id, event=model_event_to_schema(event_model))


@router.put(
    "/{series_id}", response={200: Series, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut}
)
@api_permission_required((apiv1, "change", SeriesModel))
def update_series(request, series_id: str, payload: UpdateSeriesIn) -> tuple[int, Series] | tuple[int, ErrorOut]:
    """Update a series"""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
    except SeriesModel.DoesNotExist:
        return 404, ErrorOut(error="Series not found")

    # Only update fields that were provided
    if payload.name is not None:
        series_model.name = payload.name
    if payload.description is not None:
        series_model.description = payload.description

    series_model.save()
    return 200, model_series_to_schema(series_model)


@router.delete(
    "/{series_id}", response={204: None, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut}
)
@api_permission_mandatory()
def delete_series(request, series_id: str) -> tuple[int, None] | tuple[int, ErrorOut]:
    """Delete a series and all of its events."""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
    except SeriesModel.DoesNotExist:
        return 404, ErrorOut(error="Series not found")

    if not request.user.has_perm(
        f"{apiv1.__name__}.delete_{SeriesModel.__name__.lower()}", series_model
    ):
        return 401, ErrorOut(error="Unauthorized to delete this series")

    series_model.delete()
    return 204, None


@router.put(
    "/{series_id}/events/{event_id}",
    response={200: Event, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_required((apiv1, "change", EventModel))
def update_event(request, series_id: str, event_id: str, payload: UpdateEventIn) -> tuple[int, Event] | tuple[int, ErrorOut]:
    """Update an event in a series"""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
        event_model = EventModel.objects.get(id=event_id, series=series_model)
    except (SeriesModel.DoesNotExist, EventModel.DoesNotExist):
        return 404, ErrorOut(error="Series or event not found")

    # Only update fields that were provided
    if payload.name is not None:
        event_model.name = payload.name
    if payload.startTime is not None:
        try:
            event_model.start_time = datetime.fromisoformat(payload.startTime)
        except ValueError:
            pass
    if payload.endTime is not None:
        try:
            event_model.end_time = datetime.fromisoformat(payload.endTime)
        except ValueError:
            pass
    if payload.tag is not None:
        event_model.tag = payload.tag
    if payload.useFullDays is not None:
        event_model.use_full_days = payload.useFullDays
    if payload.proposal_id is not None:
        try:
            proposal = ProposalModel.objects.get(id=payload.proposal_id)
            event_model.proposal = proposal
        except ProposalModel.DoesNotExist:
            return 404, ErrorOut(error="Proposal not found")
    if payload.series_id is not None:
        try:
            new_series = SeriesModel.objects.get(id=payload.series_id)
            event_model.series = new_series
        except SeriesModel.DoesNotExist:
            return 404, ErrorOut(error="Target series not found")

    event_model.save()
    return 200, model_event_to_schema(event_model)


@router.delete(
    "/{series_id}/events/{event_id}",
    response={204: None, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def delete_event(request, series_id: str, event_id: str) -> tuple[int, None] | tuple[int, ErrorOut]:
    """Delete an event from a series."""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
        event_model = EventModel.objects.get(id=event_id, series=series_model)
    except (SeriesModel.DoesNotExist, EventModel.DoesNotExist):
        return 404, ErrorOut(error="Series or event not found")

    if not request.user.has_perm(
        f"{apiv1.__name__}.delete_{EventModel.__name__.lower()}", event_model
    ):
        return 401, ErrorOut(error="Unauthorized to delete this event")

    event_model.delete()
    return 204, None



@router.get(
    "/{series_id}", response={200: Series, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut}
)
@api_permission_required((apiv1, "view", SeriesModel))
def get_one_series(request, series_id: str) -> tuple[int, Series] | tuple[int, ErrorOut]:
    """Fetch one series including its events."""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
    except SeriesModel.DoesNotExist:
        return 404, ErrorOut(error="Series not found")

    return 200, model_series_to_schema(series_model)


@router.get(
    "/{series_id}/events/{event_id}/transitions",
    response={200: EventTransitions, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def get_event_transitions(
    request, series_id: str, event_id: str
) -> tuple[int, EventTransitions | ErrorOut]:
    """Get the available FSM transitions for an event."""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
        event_model = EventModel.objects.get(id=event_id, series=series_model)
    except (SeriesModel.DoesNotExist, EventModel.DoesNotExist):
        return 404, ErrorOut(error="Series or event not found")

    if not request.user.has_perm(
        f"{apiv1.__name__}.view_{SeriesModel.__name__.lower()}", series_model
    ):
        return 401, ErrorOut(error="Unauthorized to view this series")

    flow = EventFlow(event_model)
    transitions = flow.get_available_transitions(request.user)

    return 200, EventTransitions(
        event_id=event_model.id,
        current_status=event_model.status,
        transitions=[
            EventTransitionOut(
                action=t.action,
                label=t.label,
                target_status=t.target_status,
                enabled=t.enabled,
                disable_reason=t.disable_reason,
            )
            for t in transitions
        ],
    )


@router.post(
    "/{series_id}/events/{event_id}/transitions/{action}",
    response={200: Event, 400: ErrorOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def execute_event_transition(
    request, series_id: str, event_id: str, action: str
) -> tuple[int, Event | ErrorOut]:
    """Execute an event lifecycle transition (submit, approve, reject, publish, confirm, cancel, complete, archive)."""
    try:
        series_model = SeriesModel.objects.get(id=series_id)
        event_model = EventModel.objects.get(id=event_id, series=series_model)
    except (SeriesModel.DoesNotExist, EventModel.DoesNotExist):
        return 404, ErrorOut(error="Series or event not found")

    if not request.user.has_perm(
        f"{apiv1.__name__}.view_{SeriesModel.__name__.lower()}", series_model
    ):
        return 401, ErrorOut(error="Unauthorized to view this series")

    flow = EventFlow(event_model)
    transitions = flow.get_available_transitions(request.user)

    matching = next((t for t in transitions if t.action == action), None)
    if matching is None:
        return 400, ErrorOut(error=f"Transition '{action}' is not available from state '{event_model.status}'")
    if not matching.enabled:
        return 400, ErrorOut(error=matching.disable_reason or "Transition not allowed")

    success = flow.execute_transition(action)
    if not success:
        return 400, ErrorOut(error="Failed to execute transition")

    event_model.refresh_from_db()
    return 200, model_event_to_schema(event_model)

