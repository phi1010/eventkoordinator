"""
Authentication router.

Handles user authentication, login, logout, and CSRF token management.
"""

import logging

import django.contrib.auth
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from ninja import Router

from apiv1.schemas import ErrorOut, UserIn, UserOut

logger = logging.getLogger(__name__)

router = Router()


@router.post("/authenticate", auth=None, response={200: UserOut, 401: ErrorOut})
def authenticate(request, user: UserIn):
    """Authenticate user with username and password"""
    usermodel = django.contrib.auth.authenticate(
        username=user.username, password=user.password
    )
    if usermodel is not None:
        django.contrib.auth.login(request, usermodel)
        return UserOut(username=usermodel.get_username(), user_id=str(usermodel.pk))
    else:
        logger.warning("Authentication failed")
        return 401, ErrorOut(code="auth.loginFailed")


@router.get("/me", response={200: UserOut, 401: ErrorOut})
def get_current_user(request):
    """Get current authenticated user information"""
    if request.user.is_authenticated:
        return UserOut(
            username=request.user.get_username(), user_id=str(request.user.pk)
        )
    else:
        return 401, ErrorOut(code="auth.notAuthenticated")


@router.post("/logout", response={200: dict, 401: ErrorOut})
def logout(request):
    """Logout the currently authenticated user"""
    if request.user.is_authenticated:
        django.contrib.auth.logout(request)
        return 200, {"status": "logged out"}
    else:
        return 401, ErrorOut(code="auth.notAuthenticated")


@router.get("/csrf", auth=None)
@ensure_csrf_cookie
def get_csrf_token(request):
    """Get CSRF token for the session"""
    return HttpResponse()
