from django.contrib import admin
from polymorphic.admin import PolymorphicChildModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from sync_ical import models


@admin.register(models.IcalCalendarSyncTarget)
class IcalCalendarSyncTargetAdmin(PolymorphicChildModelAdmin, SimpleHistoryAdmin):
    list_display = ("name", "url", "created_at", "updated_at")
    search_fields = ("name", "url")
    ordering = ("-updated_at",)

@admin.register(models.IcalCalenderSyncItem)
class IcalCalenderSyncItemAdmin(SimpleHistoryAdmin):
    list_display = ("uid", "calendar", "related_event", "flag_push", "updated_at")
    list_filter = ("calendar", "flag_push")
    search_fields = ("uid", "calendar__name", "related_event__name")
    ordering = ("-updated_at",)
    raw_id_fields = ("related_event",)
