from django.apps import AppConfig


class MailqueueConfig(AppConfig):
    name = 'mailqueue'

    def ready(self):
        """Import signal handlers when Django starts."""
        import mailqueue.signals  # noqa: F401

