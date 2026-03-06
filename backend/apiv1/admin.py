from django.contrib import admin
from django.forms import ModelForm
from simple_history.admin import SimpleHistoryAdmin
from viewflow import fsm

from . import models
from .flows import ProposalFlow


class ProposalSpeakerInline(admin.TabularInline):
    model = models.ProposalSpeaker
    extra = 1
    raw_id_fields = ("speaker",)
    ordering = ("sort_order",)


@admin.register(models.Series)
class SeriesAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(models.Event)
class EventAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "series", "start_time", "end_time")
    list_filter = ("series", "tag")
    search_fields = ("name", "tag")
    ordering = ("start_time",)


@admin.register(models.SubmissionType)
class SubmissionTypeAdmin(SimpleHistoryAdmin):
    list_display = ("code", "label", "is_active", "sort_order")
    list_editable = ("label", "is_active", "sort_order")
    search_fields = ("code", "label")


@admin.register(models.ProposalLanguage)
class ProposalLanguageAdmin(SimpleHistoryAdmin):
    list_display = ("code", "label", "is_active", "sort_order")
    list_editable = ("label", "is_active", "sort_order")
    search_fields = ("code", "label")


@admin.register(models.ProposalArea)
class ProposalAreaAdmin(SimpleHistoryAdmin):
    list_display = ("code", "label", "is_active", "sort_order")
    list_editable = ("label", "is_active", "sort_order")
    search_fields = ("code", "label")


@admin.register(models.Speaker)
class SpeakerAdmin(SimpleHistoryAdmin):
    list_display = ("display_name", "email", "use_gravatar", "created_at")
    search_fields = ("display_name", "email")
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("use_gravatar",)
    raw_id_fields = ()


@admin.register(models.Proposal)
class ProposalAdmin(fsm.FlowAdminMixin, SimpleHistoryAdmin):
    flow_state = ProposalFlow.status

    def get_object_flow(self, request, obj):
        return ProposalFlow(obj)

    list_display = (
        "id",
        "title",
        "submission_type",
        "status",
        "owner",
        "is_basic_course",
        "max_participants",
        "created_at",
    )
    list_filter = ("submission_type", "status", "area", "language", "is_basic_course")
    search_fields = ("title", "abstract", "description")
    readonly_fields = ("created_at", "updated_at", "status")
    raw_id_fields = ("owner",)
    filter_horizontal = ("editors",)
    inlines = (ProposalSpeakerInline,)
    fieldsets = (
        (
            "General",
            {
                "fields": (
                    "title",
                    "submission_type",
                    "area",
                    "language",
                    "abstract",
                    "description",
                    "internal_notes",
                )
            },
        ),
        (
            "Details",
            {
                "fields": (
                    "duration_minutes",
                    "occurrence_count",
                    "is_basic_course",
                    "max_participants",
                    "material_cost_eur",
                    "preferred_dates",
                )
            },
        ),
        ("People", {"fields": ("owner", "editors")}),
        ("Status", {"fields": ("status",)}),
    )


@admin.register(models.ProposalSpeaker)
class ProposalSpeakerAdmin(SimpleHistoryAdmin):
    list_display = ("proposal", "speaker", "role", "sort_order")
    search_fields = ("proposal__title", "speaker__display_name", "speaker__email")
    raw_id_fields = ("proposal", "speaker")
    ordering = ("proposal", "sort_order")
