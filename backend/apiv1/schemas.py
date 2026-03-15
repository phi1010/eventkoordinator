"""
Centralized schema definitions for the API.

This module contains all Pydantic schema definitions used across the API
to avoid circular imports and serve as a single source of truth for API contracts.
"""

import uuid

from ninja import Schema
from typing import Optional, Literal
from pydantic import Field


class UserIn(Schema):
    username: str
    password: str


class UserBasic(Schema):
    id: uuid.UUID
    username: str


class UserOut(Schema):
    username: str
    user_id: str


class ErrorOut(Schema):
    error: str
    detail: Optional[str] = None


class Event(Schema):
    id: uuid.UUID
    name: str
    startTime: str  # ISO format string
    endTime: str  # ISO format string
    tag: Optional[str] = None
    useFullDays: bool = False
    proposal_id: Optional[uuid.UUID] = None
    series_id: Optional[uuid.UUID] = None
    series_name: Optional[str] = None
    status: str = "draft"


class Series(Schema):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    events: list[Event]


class SeriesListItem(Schema):
    id: uuid.UUID
    name: str
    description: Optional[str] = None


class CreateSeriesIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None


class CreateEventIn(Schema):
    name: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    tag: Optional[str] = None
    useFullDays: Optional[bool] = None
    proposal_id: Optional[uuid.UUID] = None


class CreateEventOut(Schema):
    series_id: uuid.UUID
    event: Event


class SyncStatus(Schema):
    target_id: uuid.UUID
    platform: str
    status: Literal["no entry exists", "entry up-to-date", "entry differs"]
    last_synced: Optional[str] = None
    last_error: Optional[str] = None


class EventSyncInfo(Schema):
    series_id: uuid.UUID
    event_id: uuid.UUID
    sync_statuses: list[SyncStatus]


class SyncPushResult(Schema):
    success: bool
    message: str
    timestamp: str
    target_id: uuid.UUID
    series_id: uuid.UUID
    event_id: uuid.UUID


class EventWithID(Schema):
    id: uuid.UUID
    name: str
    startTime: str
    endTime: str
    tag: Optional[str] = None


class UpdateSeriesIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None


class UpdateEventIn(Schema):
    name: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    tag: Optional[str] = None
    useFullDays: Optional[bool] = None
    proposal_id: Optional[uuid.UUID] = None
    series_id: Optional[uuid.UUID] = None


class ProposalSummary(Schema):
    id: uuid.UUID
    title: str
    submission_type: str


class ProposalChecklistItem(Schema):
    status: Literal["ok", "error"]


class ProposalChecklist(Schema):
    items: dict[str, ProposalChecklistItem]


class ProposalCreateIn(Schema):
    title: Optional[str] = Field(default=None, max_length=30)
    submission_type: Optional[str] = None
    area: Optional[str] = None
    language: Optional[str] = None
    abstract: Optional[str] = None
    description: Optional[str] = None
    internal_notes: Optional[str] = None
    occurrence_count: Optional[int] = None
    duration_days: Optional[int] = None
    duration_time_per_day: Optional[str] = None
    is_basic_course: Optional[bool] = None
    max_participants: Optional[int] = None
    material_cost_eur: Optional[str] = None
    preferred_dates: Optional[str] = None
    is_regular_member: Optional[bool] = None
    has_building_access: Optional[bool] = None


class ProposalUpdateIn(Schema):
    title: Optional[str] = Field(default=None, max_length=30)
    submission_type: Optional[str] = None
    area: Optional[str] = None
    language: Optional[str] = None
    abstract: Optional[str] = None
    description: Optional[str] = None
    internal_notes: Optional[str] = None
    occurrence_count: Optional[int] = None
    duration_days: Optional[int] = None
    duration_time_per_day: Optional[str] = None
    is_basic_course: Optional[bool] = None
    max_participants: Optional[int] = None
    material_cost_eur: Optional[str] = None
    preferred_dates: Optional[str] = None
    is_regular_member: Optional[bool] = None
    has_building_access: Optional[bool] = None
    # owner_id removed - owner is set on creation and cannot be changed
    editor_ids: Optional[list[str]] = None


class ProposalDetail(Schema):
    id: uuid.UUID
    title: str
    submission_type: str
    area: Optional[str] = None
    language: Optional[str] = None
    abstract: str
    description: str
    internal_notes: str
    occurrence_count: int
    duration_days: int
    duration_time_per_day: str
    is_basic_course: bool
    max_participants: int
    material_cost_eur: str
    preferred_dates: str
    is_regular_member: bool
    has_building_access: bool
    photo: Optional[str] = None
    owner: Optional[UserBasic] = None
    editors: list[UserBasic] = []


class SpeakerOut(Schema):
    id: uuid.UUID
    email: str = ""
    display_name: str
    biography: str
    profile_picture: Optional[str] = None
    use_gravatar: bool


class SpeakerCreateIn(Schema):
    email: str
    display_name: str
    biography: str
    use_gravatar: bool = False


class SpeakerUpdateIn(Schema):
    email: Optional[str] = None
    display_name: Optional[str] = None
    biography: Optional[str] = None
    use_gravatar: Optional[bool] = None


class ProposalSpeakerOut(Schema):
    id: uuid.UUID
    speaker: SpeakerOut
    role: str
    sort_order: int


# Unified schemas with all optional fields
class ProposalIn(Schema):
    title: Optional[str] = Field(default=None, max_length=30)
    submission_type: Optional[str] = None
    area: Optional[str] = None
    language: Optional[str] = None
    abstract: Optional[str] = None
    description: Optional[str] = None
    internal_notes: Optional[str] = None
    occurrence_count: Optional[int] = None
    duration_days: Optional[int] = None
    duration_time_per_day: Optional[str] = None
    is_basic_course: Optional[bool] = None
    max_participants: Optional[int] = None
    material_cost_eur: Optional[str] = None
    preferred_dates: Optional[str] = None
    is_regular_member: Optional[bool] = None
    has_building_access: Optional[bool] = None


class SpeakerIn(Schema):
    email: Optional[str] = None
    display_name: Optional[str] = None
    biography: Optional[str] = None
    use_gravatar: Optional[bool] = None


# Lookup table schema
class LookupOut(Schema):
    code: str
    label: str
    description: str = ""
    is_active: bool = True
    sort_order: int = 0


class ExternalCalendarEvent(Schema):
    id: str
    title: str
    startUtc: str
    endUtc: str
    source: str


class ProposalHistoryEntry(Schema):
    """Represents a single change in the proposal's history."""

    timestamp: str  # ISO format datetime
    changed_by: str  # username of user who made the change
    change_type: str  # 'create', 'change', 'delete'
    field_name: Optional[str] = None  # which field was changed
    old_value: Optional[str] = None  # previous value
    new_value: Optional[str] = None  # new value
    summary: str  # human-readable summary of the change


class ProposalHistory(Schema):
    """List of historical changes for a proposal."""

    proposal_id: uuid.UUID
    entries: list[ProposalHistoryEntry]


class ProposalTransitionOut(Schema):
    """Information about a single available or unavailable transition."""

    action: str  # 'submit', 'accept', 'reject', 'revise'
    label: str  # human-readable label
    target_status: str  # target status
    enabled: bool  # whether the transition is currently allowed
    disable_reason: Optional[str] = None  # reason if disabled


class ProposalTransitions(Schema):
    """List of available transitions for a proposal."""

    proposal_id: uuid.UUID
    current_status: str
    transitions: list[ProposalTransitionOut]


class ProposalEventSummary(Schema):
    """Summary of an event linked to a proposal."""

    id: uuid.UUID
    name: str
    startTime: str
    endTime: str
    status: str
    series_id: uuid.UUID
    series_name: str


class EventTransitionOut(Schema):
    """Information about a single available or unavailable event transition."""

    action: str
    label: str
    target_status: str
    enabled: bool
    disable_reason: Optional[str] = None


class EventTransitions(Schema):
    """List of available transitions for an event."""

    event_id: uuid.UUID
    current_status: str
    transitions: list[EventTransitionOut]


class CreateCalculatedPricesIn(Schema):
    """Creation mode for calculated prices: default configuration or manual empty values."""

    use_default_pricing_configuration: bool = True

    model_config = {"extra": "forbid"}


class UpdateCalculatedPricesIn(Schema):
    pricing_configuration_id: Optional[uuid.UUID] = None
    member_regular_gross_eur: Optional[str] = None
    member_discounted_gross_eur: Optional[str] = None
    guest_regular_gross_eur: Optional[str] = None
    guest_discounted_gross_eur: Optional[str] = None
    business_net_eur: Optional[str] = None


class CalculatedPricesOut(Schema):
    id: uuid.UUID
    event_id: uuid.UUID
    pricing_configuration_id: Optional[uuid.UUID] = None
    member_regular_gross_eur: Optional[str] = None
    member_discounted_gross_eur: Optional[str] = None
    guest_regular_gross_eur: Optional[str] = None
    guest_discounted_gross_eur: Optional[str] = None
    business_net_eur: Optional[str] = None


class SyncTargetOut(Schema):
    id: uuid.UUID
    type: str
    public_properties: dict[str, str]


