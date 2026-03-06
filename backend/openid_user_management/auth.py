"""
Custom OIDC Authentication Backend for OpenIDUser model.

Integrates mozilla-django-oidc with our custom UUID-based user model.
"""

import logging

from django.conf import settings
from django.http import HttpRequest
from django.template.defaultfilters import urlencode
from mozilla_django_oidc.auth import OIDCAuthenticationBackend as BaseOIDCAuthenticationBackend
from openid_user_management.models import OpenIDUser

logger = logging.getLogger(__name__)


class OIDCAuthenticationBackend(BaseOIDCAuthenticationBackend):
    """
    Custom OIDC authentication backend for OpenIDUser model.

    Handles user creation and updates based on OIDC claims.
    """

    def create_user(self, claims):
        """
        Create a new OpenIDUser from OIDC claims.

        Args:
            claims (dict): OIDC claims from the identity provider

        Returns:
            OpenIDUser: The created user instance
        """
        email = claims.get('email', '')
        username = claims.get('preferred_username', email.split('@')[0] if email else '')

        # Generate unique username if it already exists
        base_username = username
        counter = 1
        while OpenIDUser.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = OpenIDUser.objects.create_user(
            username=username,
            email=email,
            password=None,  # No password for OIDC users
        )

        # Store OIDC provider information
        user.openid_subject = claims.get('sub', '')
        user.openid_provider = self.get_provider_name(claims)

        # Store optional profile information
        user.phone_number = claims.get('phone_number', '')
        user.picture = claims.get('picture', '')
        user.locale = claims.get('locale', '')

        user.save()

        logger.info(f"Created new OIDC user: {user.username} (UUID: {user.id})")
        return user

    def update_user(self, user, claims):
        """
        Update existing user with latest OIDC claims.

        Args:
            user (OpenIDUser): The user to update
            claims (dict): OIDC claims from the identity provider

        Returns:
            OpenIDUser: The updated user instance
        """
        # Update email if changed
        email = claims.get('email', '')
        if email and email != user.email:
            user.email = email

        # Update OIDC subject if not set
        if not user.openid_subject:
            user.openid_subject = claims.get('sub', '')

        # Update provider if not set
        if not user.openid_provider:
            user.openid_provider = self.get_provider_name(claims)

        # Update optional profile information
        if 'phone_number' in claims:
            user.phone_number = claims.get('phone_number', '')
        if 'picture' in claims:
            user.picture = claims.get('picture', '')
        if 'locale' in claims:
            user.locale = claims.get('locale', '')

        user.save()

        logger.debug(f"Updated OIDC user: {user.username}")
        return user

    def filter_users_by_claims(self, claims):
        """
        Find users matching the OIDC claims.

        First tries to match by openid_subject (sub claim),
        then falls back to email if subject is not found.

        Args:
            claims (dict): OIDC claims from the identity provider

        Returns:
            QuerySet: Users matching the claims
        """
        sub = claims.get('sub')
        email = claims.get('email')

        # Try to find user by OpenID subject first
        if sub:
            users = OpenIDUser.objects.filter(openid_subject=sub)
            if users.exists():
                return users

        # Fall back to email
        if email:
            return OpenIDUser.objects.filter(email=email)

        return OpenIDUser.objects.none()

    def get_provider_name(self, claims):
        """
        Extract provider name from claims.

        Args:
            claims (dict): OIDC claims

        Returns:
            str: Provider name
        """
        # Try to get issuer
        issuer = claims.get('iss', '')

        # Extract provider name from issuer URL
        if 'google' in issuer.lower():
            return 'google'
        elif 'github' in issuer.lower():
            return 'github'
        elif 'keycloak' in issuer.lower():
            return 'keycloak'
        elif 'auth0' in issuer.lower():
            return 'auth0'
        else:
            return issuer.split('//')[1].split('/')[0] if '//' in issuer else issuer

    def verify_claims(self, claims):
        """
        Verify that required claims are present.

        Args:
            claims (dict): OIDC claims

        Returns:
            bool: True if claims are valid
        """
        # Require either sub or email
        return bool(claims.get('sub') or claims.get('email'))


def generate_username(email):
    """
    Generate a username from email address.

    This function is referenced in settings.OIDC_USERNAME_ALGO.

    Args:
        email (str): Email address

    Returns:
        str: Generated username
    """
    if not email:
        return f"user_{OpenIDUser.objects.count() + 1}"

    # Use email local part as username
    username = email.split('@')[0]

    # Make it unique if necessary
    base_username = username
    counter = 1
    while OpenIDUser.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    return username



def provider_logout(request: HttpRequest):
    keycloak_logout_url = settings.OIDC_OP_LOGOUT_URL
    client_id = settings.OIDC_RP_CLIENT_ID
    redirect_url = request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL)
    return_url = keycloak_logout_url.format(urlencode(redirect_url), urlencode(client_id))
    return return_url