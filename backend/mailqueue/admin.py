from django.contrib import admin


from mailqueue.models import MailQueueEntry, MailQueueDeliveryAttempt


class MailDeliveryAttemptsInline(admin.StackedInline):
    model = MailQueueDeliveryAttempt
    extra = 0
    # raw_id_fields = ("",)
    ordering = ("created_at",)
    fields = ("success", "error_message", "created_at", "updated_at")
    readonly_fields = ("success", "error_message", "created_at", "updated_at")

def custom_title_filter_factory(filter_cls, title):
    class Wrapper(filter_cls):
        def __new__(cls, *args, **kwargs):
            instance = filter_cls(*args, **kwargs)
            instance.title = title
            return instance

    return Wrapper


@admin.action(description="Resend 10 mails (only with no successful attempts)")
def resend_mails(modeladmin, request, queryset):
    for mail in queryset.all()[:10]:
        mail : MailQueueEntry
        if not mail.successful_attempt:
            try:
                mail.send_mail()
            except Exception as e:
                modeladmin.message_user(request, f"Failed to resend mail {mail.created_at} to {mail.recipient}: {e}", level="error")
            else:
                modeladmin.message_user(request, f"Successfully resent mail {mail.created_at} to {mail.recipient}", level="success")

@admin.register(MailQueueEntry)
class MailQueueEntryAdmin(admin.ModelAdmin):
    list_display = (
        "recipient",
        "subject",
        "created_at",
        "last_attempt_date",
        "number_of_attempts",
        "successful_attempt",
    )
    actions = [resend_mails]
    search_fields = (
        "recipient",
        "subject",
        "created_at",
    )
    list_filter = ("recipient", "created_at", "delivery_attempts__success", ("delivery_attempts__created_at", custom_title_filter_factory(admin.DateFieldListFilter, "Last Attempt Date")))
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "recipient",
                    "subject",
                    "body",
                    "body_html",
                    "last_attempt_date",
                    "number_of_attempts",
                    "successful_attempt",
                )
            },
        ),
    )
    readonly_fields = (
        "last_attempt_date",
        "number_of_attempts",
        "successful_attempt",
    )
    inlines = (MailDeliveryAttemptsInline,)


@admin.register(MailQueueDeliveryAttempt)
class MailQueueDeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("mail_entry", "success", "created_at")
    list_filter = ("success", "created_at")
    search_fields = ("mail_entry__recipient", "mail_entry__subject", "error_message")
    fieldsets = (
        (None, {"fields": ("mail_entry", "success", "error_message")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")
