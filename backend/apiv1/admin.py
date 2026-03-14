from django.contrib import admin
from django.contrib.admin import ModelAdmin
from simple_history.admin import SimpleHistoryAdmin
from viewflow import fsm

from . import models
from .flows import ProposalFlow
from sync_pretix.models import PretixSyncTargetAreaAssociation
from .models import SyncBaseTarget, SyncBaseItem


class SpeakerInline(admin.TabularInline):
    model = models.Speaker
    extra = 1
    ordering = ("sort_order",)
    fields = ("display_name", "email", "role", "sort_order", "use_gravatar")


class PretixSyncTargetAreaAssociationInline(admin.TabularInline):
    model = PretixSyncTargetAreaAssociation
    extra = 0
    fields = (
        "event_slug",
        "ticket_product_member_regular_id",
        "ticket_product_member_discounted_id",
        "ticket_product_guest_regular_id",
        "ticket_product_guest_discounted_id",
        "ticket_product_business_id",
    )


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
    inlines = (PretixSyncTargetAreaAssociationInline,)


@admin.register(models.Speaker)
class SpeakerAdmin(SimpleHistoryAdmin):
    list_display = ("display_name", "email", "proposal", "role", "use_gravatar", "created_at")
    search_fields = ("display_name", "email", "proposal__title")
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("use_gravatar", "role")
    raw_id_fields = ("proposal",)


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
    inlines = (SpeakerInline,)
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


@admin.register(SyncBaseTarget)
class SyncBaseTargetAdmin(SimpleHistoryAdmin):

    list_display = (
        "id",
        "type",
        "created_at",
    )
    list_filter = ("type")
    readonly_fields = ("id","type", "created_at")
    fields = ("id","type", "created_at")
