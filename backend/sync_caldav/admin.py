from django.contrib import admin
from polymorphic.admin import PolymorphicChildModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from sync_caldav import models


@admin.register(models.CalDAVSyncTarget)
class CalDAVSyncTargetAdmin(PolymorphicChildModelAdmin, SimpleHistoryAdmin):
    list_display = ("name", "url", "calendar_display_name", "username", "created_at", "updated_at")
    search_fields = ("name", "url", "calendar_display_name", "username")
    ordering = ("-updated_at",)


@admin.register(models.CalDAVSyncItem)
class CalDAVSyncItemAdmin(SimpleHistoryAdmin):
    list_display = ("caldav_uid", "sync_target", "related_event", "flag_push", "updated_at")
    list_filter = ("sync_target", "flag_push")
    search_fields = ("caldav_uid", "sync_target__name", "related_event__name")
    ordering = ("-updated_at",)
    raw_id_fields = ("related_event",)
