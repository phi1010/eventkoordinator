from django.core import checks


@checks.register(checks.Tags.security)
def check_secret_key(app_configs, **kwargs):
    from django.conf import settings

    errors = []

    if not settings.SECRET_KEY:
        errors.append(
            checks.Error(
                "SECRET_KEY is not set.",
                hint="Set SECRET_KEY in your environment or settings file.",
                id="project.E001",
            )
        )
    elif settings.SECRET_KEY.startswith("insecure-default"):
        errors.append(
            checks.Warning(
                "SECRET_KEY is set to the insecure default value.",
                hint="Set a strong, unique SECRET_KEY in production.",
                id="project.W001",
            )
        )

    return errors
