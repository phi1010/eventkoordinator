from django.apps import AppConfig


class ProjectConfig(AppConfig):
    name = "project"

    def ready(self):
        import project.checks  # noqa: F401
