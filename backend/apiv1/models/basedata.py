import logging
from typing import Any

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import AppRegistryNotReady
from django.core.validators import (
    MaxValueValidator,
    MinLengthValidator,
    MinValueValidator,
)
from django.db import models, OperationalError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_prometheus.models import ExportModelOperationsMixin
from prometheus_client import Gauge
from prometheus_client.metrics_core import GaugeMetricFamily
from prometheus_client.registry import Collector, REGISTRY
from solo.models import SingletonModel
from viewflow import fsm

from project.basemodels import HistoricalMetaBase, MetaBase

from openid_user_management.models import OpenIDUser

logger = logging.getLogger(__name__)


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

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Series"

    def __str__(self):
        return self.name


class Event(HistoricalMetaBase):
    """An event is an individual time-bound item within a series."""

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="events")
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

    class Meta:
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["series", "start_time"]),
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
    """Public speaker profile independent from Django auth users."""

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=120)
    biography = models.TextField(validators=[MinLengthValidator(50)], max_length=2000)
    profile_picture = models.ImageField(
        upload_to="speaker_profiles/", blank=True, null=True
    )
    use_gravatar = models.BooleanField(default=False)

    class Meta:
        ordering = ["display_name"]

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
    photo = models.ImageField(upload_to="proposal_photos/", blank=True, null=True)
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

    speakers = models.ManyToManyField(
        Speaker, through="ProposalSpeaker", related_name="proposals"
    )
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


class ProposalSpeaker(HistoricalMetaBase):
    """Role and display order of speakers attached to a proposal."""

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary speaker"
        CO_SPEAKER = "co_speaker", "Co-speaker"

    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="proposal_speakers"
    )
    speaker = models.ForeignKey(
        Speaker, on_delete=models.CASCADE, related_name="speaker_proposals"
    )
    role = models.CharField(max_length=20, choices=Role, default=Role.CO_SPEAKER)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["proposal", "speaker"], name="unique_proposal_speaker"
            ),
            models.UniqueConstraint(
                fields=["proposal"],
                condition=Q(role="primary"),
                name="unique_primary_speaker_per_proposal",
            ),
        ]

    def __str__(self):
        return f"{self.proposal.pk}:{self.speaker.pk}:{self.role}"


def check_proposal_required_fields(proposal: Proposal) -> dict[Any, Any]:
    checklist = {}

    # Title validation
    TITLE = "Title (max 30 characters)"
    if proposal.title and proposal.title.strip() and 0 < len(proposal.title) <= 30:
        checklist[TITLE] = {"status": "ok"}
    else:
        checklist[TITLE] = {"status": "error"}

    # Abstract validation (50-250 chars)
    abstract_len = len(proposal.abstract) if proposal.abstract else 0
    ABSTRACT = "Abstract (50-250 characters)"
    if proposal.abstract and 50 <= abstract_len <= 250:
        checklist[ABSTRACT] = {"status": "ok"}
    else:
        checklist[ABSTRACT] = {"status": "error"}

    # Description validation (50-1000 chars)
    desc_len = len(proposal.description) if proposal.description else 0
    DESCRIPTION = "Description (50-1000 characters)"
    if proposal.description and 50 <= desc_len <= 1000:
        checklist[DESCRIPTION] = {"status": "ok"}
    else:
        checklist[DESCRIPTION] = {"status": "error"}

    # Duration validation
    DURATIONSET = "Duration set"
    total_minutes = proposal.get_total_duration_minutes()
    if total_minutes >= 1:
        checklist[DURATIONSET] = {"status": "ok"}
    else:
        checklist[DURATIONSET] = {"status": "error"}

    # Max participants validation
    MAXPARTICIPANTS = "Max participants set"
    if proposal.max_participants and proposal.max_participants >= 1:
        checklist[MAXPARTICIPANTS] = {"status": "ok"}
    else:
        checklist[MAXPARTICIPANTS] = {"status": "error"}

    # Occurrence count validation
    OCCURENCECOUNT = "Occurrence count set"
    if proposal.occurrence_count and proposal.occurrence_count >= 1:
        checklist[OCCURENCECOUNT] = {"status": "ok"}
    else:
        checklist[OCCURENCECOUNT] = {"status": "error"}

    # Preferred dates validation
    PREFERREDDATES = "Preferred dates specified"
    if proposal.preferred_dates and proposal.preferred_dates.strip():
        checklist[PREFERREDDATES] = {"status": "ok"}
    else:
        checklist[PREFERREDDATES] = {"status": "error"}

    LANGUAGE = "Language selected"
    if proposal.language:
        checklist[LANGUAGE] = {"status": "ok"}
    else:
        checklist[LANGUAGE] = {"status": "error"}

    SUBMISSIONTYPE = "Submission type selected"
    if proposal.submission_type:
        checklist[SUBMISSIONTYPE] = {"status": "ok"}
    else:
        checklist[SUBMISSIONTYPE] = {"status": "error"}

    # Area validation
    WORKSHOPAREA = "Workshop area selected"
    if proposal.area:
        checklist[WORKSHOPAREA] = {"status": "ok"}
    else:
        checklist[WORKSHOPAREA] = {"status": "error"}

    # Speaker presence validation: require at least one speaker
    speaker_count = proposal.speakers.count()

    ATLEASTONESPEAKER = "At least one speaker added"
    if speaker_count >= 1:
        checklist[ATLEASTONESPEAKER] = {"status": "ok"}
    else:
        checklist[ATLEASTONESPEAKER] = {"status": "error"}

    empty_bio_present = proposal.speakers.filter(
        Q(biography__isnull=True) | Q(biography__exact="")
    ).exists()

    SPEAKERSHAVEBIO = "All speakers have biography"
    if empty_bio_present:
        checklist[SPEAKERSHAVEBIO] = {"status": "error"}
    else:
        checklist[SPEAKERSHAVEBIO] = {"status": "ok"}
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
