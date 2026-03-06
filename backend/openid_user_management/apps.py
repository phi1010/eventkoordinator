"""
Application configuration for openid_user_management.

This app provides a custom Django user model using UUID as the primary key,
designed for OpenID Connect authentication flows.
"""

from django.apps import AppConfig


class OpenidUserManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'openid_user_management'
    verbose_name = 'OpenID User Management'

