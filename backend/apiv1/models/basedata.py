import logging
import os
import uuid
from typing import Any

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import AppRegistryNotReady
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinLengthValidator,
    MinValueValidator,
)
from django.db import models, OperationalError
from django.db.models import Q
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from django_prometheus.models import ExportModelOperationsMixin
from prometheus_client import Gauge
from prometheus_client.metrics_core import GaugeMetricFamily
from prometheus_client.registry import Collector, REGISTRY
from solo.models import SingletonModel
from viewflow import fsm

import apiv1
from project.basemodels import HistoricalMetaBase, MetaBase

from openid_user_management.models import OpenIDUser

logger = logging.getLogger(__name__)

IMAGE_FILE_VALIDATORS = [
    FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"])
]


@deconstructible
class UUIDFilenameUploadTo:
    """Store uploads under a fixed folder using a random UUID filename."""

    def __init__(self, folder: str):
        self.folder = folder.strip("/")

    def __call__(self, instance: models.Model, filename: str) -> str:
        _base_name, ext = os.path.splitext(os.path.basename(filename or ""))
        safe_ext = ext.lower()
        return f"{self.folder}/{uuid.uuid4()}{safe_ext}"


def time_string_to_minutes(time_str: str) -> int:
    """Convert HH:MM format string to total minutes. Returns 0 for invalid input."""
    try:
        if not time_str:
            return 0
        if ":" not in time_str:
            return int(time_str)
        else:
            hours, minutes = time_str.split(":")
        return int(hours) * 60 + int(minutes)
    except (ValueError, IndexError):
        return 0


def minutes_to_time_string(minutes: int) -> str:
    """Convert total minutes to HH:MM format string."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


class Series(HistoricalMetaBase):
    """A series is a collection of related events."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True, max_length=500)

    def has_object_permission(self, user, perm):
        logger.getChild("has_object_permission").debug(
            f"Checking permission {perm!r} for user {user.username!r} on series {self.pk}"
        )
        if perm.endswith(f".view_{Series.__name__.lower()}"):
            # Global view permission always grants object permission.
            if user.has_perm(perm, None):
                return True
            # Also when the user has view permission to any associated event
            if any((user.has_perm((apiv1, "view", Event), event) for event in self.events.all())):
                return True
            return False
        # For all other permissions the global permission is sufficient as
        # object permission (no per-object restrictions beyond global rights).
        return user.has_perm(perm, None)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Series"

    def __str__(self):
        return self.name


class Event(HistoricalMetaBase):
    """An event is an individual time-bound item within a series."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PROPOSED = "proposed", _("Proposed")
        PLANNED = "planned", _("Planned")
        PUBLISHED = "published", _("Published")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELED = "canceled", _("Canceled")
        COMPLETED = "completed", _("Completed")
        ARCHIVED = "archived", _("Archived")
        REJECTED = "rejected", _("Rejected")

    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="events")
    proposal = models.ForeignKey(
        "Proposal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    name = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    tag = models.CharField(max_length=100, blank=True, null=True)
    use_full_days = models.BooleanField(
        default=False,
        help_text="When checked, the event spans continuously over midnight. "
        "When unchecked, multi-day events are split into separate daily blocks "
        "using the start/end times of the first/last day.",
    )

    def has_object_permission(self, user, perm):
        logger.getChild("has_object_permission").debug(
            f"Checking permission {perm!r} for user {user.username!r} on event {self.pk}"
        )
        # Object-level view permission: granted when the event is not in draft
        # state and is linked to a proposal that the user has view permission on.
        if perm.endswith(f".view_{Event.__name__.lower()}"):
            if user.has_perm(perm, None):
                return True
            if self.status == Event.Status.DRAFT:
                return False
            if self.proposal_id is None:
                return False
            app_label = perm.split(".")[0]
            return user.has_perm(f"{app_label}.view_proposal", self.proposal)

        if perm.endswith(f".change_{Event.__name__.lower()}"):
            if user.has_perm(perm, None):
                return True
            return user.has_perm((apiv1, "change", Series), self.series)

        if perm.endswith(f".delete_{Event.__name__.lower()}"):
            return user.has_perm(perm, None)

        # All event workflow transitions require the corresponding global permission
        for action in (
            "submit",
            "approve",
            "reject",
            "publish",
            "confirm",
            "cancel",
            "complete",
            "archive",
        ):
            if perm.endswith(f".{action}_{Event.__name__.lower()}"):
                has_global_permission = user.has_perm(perm, None)

                # For linked proposals, approving/rejecting additionally requires
                # proposal ownership/editor rights.
                if action in ("approve", "reject") and self.proposal_id is not None:

                    if user == self.proposal.owner:
                        return True

                    user_id = getattr(user, "pk", None)
                    if user_id is None:
                        return False

                    return self.proposal.editors.filter(pk=user_id).exists()

                return has_global_permission
        return False

    class Meta:
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["series", "start_time"]),
        ]
        permissions = [
            ("submit_event", "Can submit events (Draft → Proposed)"),
            ("approve_event", "Can approve events (Proposed → Planned)"),
            ("reject_event", "Can reject events (Proposed → Rejected)"),
            ("publish_event", "Can publish events (Planned → Published)"),
            ("confirm_event", "Can confirm events (Published → Confirmed)"),
            ("cancel_event", "Can cancel events (Published → Canceled)"),
            ("complete_event", "Can complete events (Confirmed → Completed)"),
            ("archive_event", "Can archive events (Completed/Canceled/Rejected → Archived)"),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"


class LookupBase(HistoricalMetaBase):
    """Editable lookup table base used for select options in proposal forms."""

    code = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=500)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(9999)]
    )

    class Meta:
        abstract = True
        ordering = ["sort_order", "label"]

    def __str__(self):
        return self.label


class SubmissionType(LookupBase):
    class Meta(LookupBase.Meta):
        verbose_name = "Submission type"
        verbose_name_plural = "Submission types"


class ProposalLanguage(LookupBase):
    class Meta(LookupBase.Meta):
        verbose_name = "Proposal language"
        verbose_name_plural = "Proposal languages"


class ProposalArea(LookupBase):
    class Meta(LookupBase.Meta):
        verbose_name = "Proposal area"
        verbose_name_plural = "Proposal areas"


class Speaker(HistoricalMetaBase):
    """Public speaker profile belonging to exactly one proposal."""

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary speaker"
        CO_SPEAKER = "co_speaker", "Co-speaker"

    proposal = models.ForeignKey(
        "Proposal", on_delete=models.CASCADE, related_name="speakers"
    )
    email = models.EmailField(blank=True)
    display_name = models.CharField(max_length=120)
    biography = models.TextField(validators=[MinLengthValidator(50)], max_length=2000)
    profile_picture = models.ImageField(
        upload_to=UUIDFilenameUploadTo("speaker_profiles"),
        validators=IMAGE_FILE_VALIDATORS,
        blank=True,
        null=True,
    )
    use_gravatar = models.BooleanField(default=False)
    role = models.CharField(max_length=20, choices=Role, default=Role.CO_SPEAKER)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.display_name


class Proposal(ExportModelOperationsMixin("proposal"), HistoricalMetaBase):
    """Submission form content for workshops and open activities."""

    def has_object_permission(self, user, perm):
        logger.getChild("has_object_permission").debug(
            f"Checking permission {perm!r} for user {user.username!r} on proposal {self.pk}"
        )
        if perm.endswith(f".change_{Proposal.__name__.lower()}"):
            return (user == self.owner or user in self.editors.all()) and (
                self.status in [self.Status.DRAFT, self.Status.REVISE]
            )
        if perm.endswith(f".view_{Proposal.__name__.lower()}"):
            return user == self.owner or user in self.editors.all()
        if perm.endswith(f".delete_{Proposal.__name__.lower()}"):
            return user == self.owner and self.status in [self.Status.DRAFT]
        if perm.endswith(f".accept_{Proposal.__name__.lower()}"):
            return user.has_perm(perm, None)
        if perm.endswith(f".revise_{Proposal.__name__.lower()}"):
            return user.has_perm(perm, None)
        if perm.endswith(f".reject_{Proposal.__name__.lower()}"):
            return user.has_perm(perm, None)
        if perm.endswith(f".submit_{Proposal.__name__.lower()}"):
            return user == self.owner or user in self.editors.all()
        return False

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SUBMITTED = "submitted", _("Submitted")
        REVISE = "revise", _("Revise")
        ACCEPTED = "accepted", _("Accepted")
        REJECTED = "rejected", _("Rejected")

    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)

    title = models.CharField(max_length=30)
    submission_type = models.ForeignKey(
        SubmissionType,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    area = models.ForeignKey(
        ProposalArea,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="proposals",
    )
    language = models.ForeignKey(
        ProposalLanguage,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="proposals",
    )
    abstract = models.TextField(validators=[MinLengthValidator(50)], max_length=250)
    description = models.TextField(validators=[MinLengthValidator(50)], max_length=1000)
    internal_notes = models.TextField(blank=True, max_length=2000)
    occurrence_count = models.PositiveSmallIntegerField(default=0)
    photo = models.ImageField(
        upload_to=UUIDFilenameUploadTo("proposal_photos"),
        validators=IMAGE_FILE_VALIDATORS,
        blank=True,
        null=True,
    )
    duration_days = models.PositiveSmallIntegerField(default=1)
    duration_time_per_day = models.CharField(
        max_length=5, default="00:00"
    )  # HH:MM format

    is_basic_course = models.BooleanField(default=False)
    max_participants = models.PositiveIntegerField(default=0)
    material_cost_eur = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    preferred_dates = models.TextField(max_length=1000)

    is_regular_member = models.BooleanField(default=False)
    has_building_access = models.BooleanField(default=False)

    owner = models.ForeignKey(
        OpenIDUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_proposals",
    )
    editors = models.ManyToManyField(
        OpenIDUser, blank=True, related_name="edited_proposals"
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("browse_proposal", "Can browse proposal list"),
            ("accept_proposal", "Can accept proposals (when the workflow allows it)"),
            ("reject_proposal", "Can reject proposals (when the workflow allows it)"),
            ("submit_proposal", "Can submit proposals (when the workflow allows it)"),
            (
                "revise_proposal",
                "Can request for revision of proposals (when the workflow allows it)",
            ),
        ]

    def get_total_duration_minutes(self) -> int:
        """Calculate total duration in minutes."""
        time_minutes = time_string_to_minutes(self.duration_time_per_day)
        return self.duration_days * time_minutes

    def __str__(self):
        return self.title




def check_proposal_required_fields(proposal: Proposal) -> dict[Any, Any]:
    checklist = {}

    # Title validation
    title = "Title (max 30 characters)"
    if proposal.title and proposal.title.strip() and 0 < len(proposal.title) <= 30:
        checklist[title] = {"status": "ok"}
    else:
        checklist[title] = {"status": "error"}

    # Abstract validation (50-250 chars)
    abstract_len = len(proposal.abstract) if proposal.abstract else 0
    abstract = "Abstract (50-250 characters)"
    if proposal.abstract and 50 <= abstract_len <= 250:
        checklist[abstract] = {"status": "ok"}
    else:
        checklist[abstract] = {"status": "error"}

    # Description validation (50-1000 chars)
    desc_len = len(proposal.description) if proposal.description else 0
    description = "Description (50-1000 characters)"
    if proposal.description and 50 <= desc_len <= 1000:
        checklist[description] = {"status": "ok"}
    else:
        checklist[description] = {"status": "error"}

    # Duration validation
    durationset = "Duration set"
    total_minutes = proposal.get_total_duration_minutes()
    if total_minutes >= 1:
        checklist[durationset] = {"status": "ok"}
    else:
        checklist[durationset] = {"status": "error"}

    # Max participants validation
    maxparticipants = "Max participants set"
    if proposal.max_participants and proposal.max_participants >= 1:
        checklist[maxparticipants] = {"status": "ok"}
    else:
        checklist[maxparticipants] = {"status": "error"}

    # Occurrence count validation
    occurencecount = "Occurrence count set"
    if proposal.occurrence_count and proposal.occurrence_count >= 1:
        checklist[occurencecount] = {"status": "ok"}
    else:
        checklist[occurencecount] = {"status": "error"}

    # Preferred dates validation
    preferreddates = "Preferred dates specified"
    if proposal.preferred_dates and proposal.preferred_dates.strip():
        checklist[preferreddates] = {"status": "ok"}
    else:
        checklist[preferreddates] = {"status": "error"}

    language = "Language selected"
    if proposal.language:
        checklist[language] = {"status": "ok"}
    else:
        checklist[language] = {"status": "error"}

    submissiontype = "Submission type selected"
    if proposal.submission_type:
        checklist[submissiontype] = {"status": "ok"}
    else:
        checklist[submissiontype] = {"status": "error"}

    # Area validation
    workshoparea = "Workshop area selected"
    if proposal.area:
        checklist[workshoparea] = {"status": "ok"}
    else:
        checklist[workshoparea] = {"status": "error"}

    # Speaker presence validation: require at least one speaker
    speaker_count = proposal.speakers.count()

    atleastonespeaker = "At least one speaker added"
    if speaker_count >= 1:
        checklist[atleastonespeaker] = {"status": "ok"}
    else:
        checklist[atleastonespeaker] = {"status": "error"}

    empty_bio_present = proposal.speakers.filter(
        Q(biography__isnull=True) | Q(biography__exact="")
    ).exists()

    speakershavebio = "All speakers have biography"
    if empty_bio_present:
        checklist[speakershavebio] = {"status": "error"}
    else:
        checklist[speakershavebio] = {"status": "ok"}
    return checklist


if False: # Doesn't show up even when enabled.
    class CustomModeCollector(Collector):
        def describe(self):
            # Explicit metric descriptors help registries that rely on describe().
            yield GaugeMetricFamily(
                "django_model_proposal_count", "Number of Proposal objects"
            )
            yield GaugeMetricFamily("django_model_event_count", "Number of Event objects")
            yield GaugeMetricFamily("django_model_series_count", "Number of Series objects")

        def collect(self):
            if not apps.ready:
                return

            try:
                yield GaugeMetricFamily(
                    "django_model_proposal_count",
                    "Number of Proposal objects",
                    value=Proposal.objects.count(),
                )
                yield GaugeMetricFamily(
                    "django_model_event_count",
                    "Number of Event objects",
                    value=Event.objects.count(),
                )
                yield GaugeMetricFamily(
                    "django_model_series_count",
                    "Number of Series objects",
                    value=Series.objects.count(),
                )
            except (AppRegistryNotReady, OperationalError) as e:
                logger.error(f"Database/app registry error in CustomModeCollector: {str(e)}")


    REGISTRY.register(CustomModeCollector())
