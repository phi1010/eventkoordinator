from django.apps import AppConfig


class Apiv1Config(AppConfig):
    name = 'apiv1'

    def ready(self):
        """Import signal handlers when Django starts."""
        import apiv1.signals  # noqa: F401

