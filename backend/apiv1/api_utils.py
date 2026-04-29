import logging
from functools import wraps
from types import ModuleType
from typing import Any, Callable

from django.conf import settings
from django.db.models import Model
from django.http import HttpRequest
from openid_user_management.schemas import ErrorOut

logger = logging.getLogger(__name__)


def api_permission_required(
    *perms: str | tuple[ModuleType, str, type[Model]] | tuple[ModuleType, str],
):
    """Custom permission decorator to check user permissions on ninja apis."""
    perms = [
        perm_object_to_name(perm)
        for perm in perms
    ]
    if not perms:
        raise ValueError("At least one permission must be specified")

    def decorator(func):
        @wraps(func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                logging.warning(
                    f"Unauthorized access attempt to {request.path} by anonymous user"
                )
                return 401, ErrorOut(code="auth.notAuthenticated")

            for perm in perms:
                if not request.user.has_perm(perm):
                    logging.warning(
                        f"Unauthorized access attempt to {request.path} by unprivileged user"
                    )
                    return 403, ErrorOut(code="auth.permissionDenied")

            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def perm_object_to_name(perm: str | tuple[ModuleType, str, type[Model]] | tuple[ModuleType, str]) -> str | tuple[
    ModuleType, str, type[Model]] | tuple[ModuleType, str]:
    return (f"{perm[0].__name__}.{perm[1].__name__.lower()}"
            if (isinstance(perm, tuple) and len(perm) == 2)
            else f"{perm[0].__name__}.{perm[1]}_{perm[2].__name__.lower()}"
    if (isinstance(perm, tuple) and len(perm) == 3)
    else perm)


def api_permission_optional():
    """
    Custom permission decorator to indicate not checking user permissions on ninja apis on purpose.
    It logs a warning if no permission check is detected, which should be used for endpoints that may contain authorization but it's not mandatory, e.g. when checking items of a list that may be empty.
    """

    decorator = create_permission_check_detection_generator(
        lambda request: logger.getChild("authorization_checks").warning(
            "No permission has been checked on API endpoint %s which should in some cases contain authorization",
            request.path,
        )
    )

    return decorator


def api_permission_mandatory():
    """
    Custom permission decorator to indicate not checking user permissions on ninja apis on purpose.
    It logs a fatal error if no permission check is detected, which should be used for endpoints that must contain authorization.
    """

    decorator = create_permission_check_detection_generator(
        lambda request: logger.getChild("authorization_checks").fatal(
            "No permission has been checked on API endpoint %s which must contain authorization",
            request.path,
        )
    )

    return decorator


def create_permission_check_detection_generator(
    error_action: Callable,
) -> Callable[[Callable], Callable]:
    def decorator(func):
        @wraps(func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            checked_permissions = set()

            has_perm = request.user.has_perm

            @wraps(has_perm)
            def wrapper_has_perm(perm, *args, **kwargs):
                checked_permissions.add(perm)
                return has_perm(perm, *args, **kwargs)

            request.user.has_perm = wrapper_has_perm

            value = func(request, *args, **kwargs)

            if not checked_permissions:
                error_action(request)
            return value

        return wrapper

    return decorator


def api_permission_todo():
    """Custom permission decorator to indicate not checking user permissions on ninja apis *not* on purpose."""

    def decorator(func):
        @wraps(func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            if settings.DEBUG:
                logger.getChild("authorization_checks").warning(f"TODO: Implement permission checks for {request.path}")
                return func(request, *args, **kwargs)
            else:
                logger.getChild("authorization_checks").error(
                    f"TODO: Implement permission checks for {request.path} - Access denied in production"
                )
                return 403, ErrorOut(code="auth.permissionDenied")

        return wrapper

    return decorator
