"""
Custom user model for OpenID Connect authentication.

Uses UUID as primary key instead of username or email, providing better
privacy and compatibility with OpenID Connect flows.
"""
import logging
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

logger = logging.getLogger(__name__)

class CustomUserManager(BaseUserManager):
    """
    Custom manager for the UUID-based user model.
    Handles user creation with username as the primary login field.
    """

    def create_user(self, username, email, password=None, **extra_fields):
        """
        Create and save a regular user with the given username, email and password.
        """
        if not username:
            raise ValueError("Username is required")
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        """
        Create and save a superuser with the given username, email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class OpenIDUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for OpenID Connect authentication.

    Uses UUID (uuid4) as the primary key instead of username or email,
    providing better privacy and alignment with OpenID Connect standards.
    Email is used as the unique login identifier.
    """

    # Primary key: UUID instead of username or email
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Authentication fields
    username = models.CharField(max_length=150, unique=True, db_index=True, default=uuid.uuid4)
    email = models.EmailField(unique=True, db_index=True)


    # Phone and address fields (optional, OpenID Connect standard claims)
    phone_number = models.CharField(max_length=20, blank=True)
    picture = models.URLField(blank=True, help_text="Profile picture URL")
    locale = models.CharField(max_length=10, blank=True, help_text="User's locale (e.g., 'en-US')")

    # Account status fields
    is_active = models.BooleanField(default=True, help_text="User account is active")
    is_staff = models.BooleanField(default=False, help_text="User can access admin site")

    # Timestamps
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    # OpenID Connect fields
    openid_subject = models.CharField(
        max_length=255,
        blank=True,
        unique=True,
        null=True,
        db_index=True,
        help_text="OpenID Connect Subject (sub) claim from identity provider"
    )
    openid_provider = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name of the OpenID Connect identity provider (e.g., 'google', 'keycloak')"
    )

    # Custom manager
    objects = CustomUserManager()

    # Set username as the field used for authentication
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = 'OpenID User'
        verbose_name_plural = 'OpenID Users'
        db_table = 'openid_user_management_openid_user'
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['openid_subject']),
            models.Index(fields=['openid_provider']),
            models.Index(fields=['is_active']),
            models.Index(fields=['date_joined']),
        ]

    def __str__(self):
        """Return a string representation of the user."""
        return f"{self.username} ({self.email})"

    def get_full_name(self):
        """
        Return the user's full name.
        Returns username as we don't have separate name fields.
        """
        return self.username

    def get_short_name(self):
        """Return the user's short name."""
        return self.username

    def get_email_display(self):
        """Return email for authentication contexts."""
        return self.email

    def has_perm(self, perm, obj = None):
        result = super().has_perm(perm, obj)
        logger.getChild("has_perm").debug(f"Got permission {result!r} for user {self.username!r} on permission {perm!r} with object: {obj!r}")
        return result