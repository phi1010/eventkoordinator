"""
Series and events router.

Handles endpoints for managing event series and individual events within them.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import django.utils.timezone
from ninja import Router

import apiv1
from apiv1.api_utils import (
    api_permission_required,
)
from apiv1.helpers import (
    model_event_to_schema,
    model_series_list_item_to_schema,
    model_series_to_schema,
)
from apiv1.models import Event as EventModel
from apiv1.models import Series as SeriesModel
from apiv1.schemas import (
    CreateEventIn,
    CreateEventOut,
    CreateSeriesIn,
    ErrorOut,
    Event,
    Series,
    SeriesListItem,
    UpdateEventIn,
    UpdateSeriesIn,
)

router = Router()


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
    """Create a new series with an initial event"""
    series_id = uuid4()
    event_id = uuid4()
    now = django.utils.timezone.now().replace(second=0, microsecond=0)

    # Create series in database
    series_model = SeriesModel.objects.create(
        id=series_id,
        name=payload.name or "New Series",
        description=payload.description,
    )

    # Create initial event
    EventModel.objects.create(
        id=event_id,
        series=series_model,
        name=(payload.name or "New Series") + " Session",
        start_time=now,
        end_time=now + timedelta(hours=1),
        tag="draft",
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

    event_model.save()
    return 200, model_event_to_schema(event_model)



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
