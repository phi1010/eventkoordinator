from django.contrib import admin
from django.contrib.admin import ModelAdmin
from polymorphic.admin import PolymorphicInlineSupportMixin, PolymorphicParentModelAdmin, StackedPolymorphicInline
from simple_history.admin import SimpleHistoryAdmin
from viewflow import fsm

from sync_ical.models import IcalCalendarSyncTarget, IcalCalenderSyncItem
from . import models
from .flows import ProposalFlow
from sync_pretix.models import PretixSyncTargetAreaAssociation, PretixSyncTarget, PretixSyncItem
from .models import SyncBaseTarget, SyncBaseItem


class LinkedEventsInline(admin.TabularInline):
    model = models.Event
    extra = 0
    ordering = ("start_time",)
    fields = ("name", "series", "start_time", "end_time", "status")
    readonly_fields = ("name", "series", "start_time", "end_time", "status")
    show_change_link = True
    verbose_name = "Linked Event"
    verbose_name_plural = "Linked Events"

    def has_add_permission(self, request, obj=None):
        return False


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


class LinkedSyncItemsInline(StackedPolymorphicInline):
    model = SyncBaseItem

    class PretixSyncItemInline(StackedPolymorphicInline.Child):
        model = PretixSyncItem
        readonly_fields = ("sync_target", "area_association", "subevent_slug", "flag_push")

        def has_add_permission(self, request, obj=None):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    class IcalCalenderSyncItemInline(StackedPolymorphicInline.Child):
        model = IcalCalenderSyncItem
        readonly_fields = ("uid", "sync_target", "ical_definition", "flag_push")

        def has_add_permission(self, request, obj=None):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    child_inlines = (PretixSyncItemInline, IcalCalenderSyncItemInline)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Event)
class EventAdmin(PolymorphicInlineSupportMixin, SimpleHistoryAdmin):
    list_display = ("id", "name", "series", "start_time", "end_time")
    list_filter = ("series", "tag")
    search_fields = ("name", "tag")
    ordering = ("start_time",)
    inlines = (LinkedSyncItemsInline,)


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
    list_display = (
        "display_name",
        "email",
        "proposal",
        "role",
        "use_gravatar",
        "created_at",
    )
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
    inlines = (SpeakerInline, LinkedEventsInline)
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
class SyncBaseTargetAdmin(PolymorphicParentModelAdmin, SimpleHistoryAdmin):
    list_display = (
        "id",
        "type",
        "created_at",
    )
    child_models = (
        PretixSyncTarget,
        IcalCalendarSyncTarget,
    )
    readonly_fields = ("id", "type", "created_at")
    fields = ("id", "type", "created_at")
