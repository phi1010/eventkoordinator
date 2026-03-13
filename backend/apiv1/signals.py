"""
Signal handlers for apiv1 app.

Handles automatic group assignments and other post-save/post-create actions.
"""

from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from apiv1.auth_groups import (
    assign_authenticated_group_to_all_users,
    ensure_authenticated_users_group,
)

User = get_user_model()


@receiver(post_save, sender=User)
def add_user_to_authenticated_group(sender, instance, created, **kwargs):
    """
    Automatically add newly created users to the 'Authenticated Users' group.

    This ensures all users have basic permissions to create proposals and
    view lookup data.
    """
    if created:
        group = ensure_authenticated_users_group()
        instance.groups.add(group)


@receiver(post_migrate)
def ensure_authenticated_group_on_migrate(sender, **kwargs):
    """Recreate default group data after migrate/flush based test DB setup."""
    if sender.name != "apiv1":
        return
    assign_authenticated_group_to_all_users()

