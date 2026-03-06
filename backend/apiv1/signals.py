"""
Signal handlers for apiv1 app.

Handles automatic group assignments and other post-save/post-create actions.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


@receiver(post_save, sender=User)
def add_user_to_authenticated_group(sender, instance, created, **kwargs):
    """
    Automatically add newly created users to the 'Authenticated Users' group.

    This ensures all users have basic permissions to create proposals and
    view lookup data.
    """
    if created:
        try:
            group = Group.objects.get(name='Authenticated Users')
            instance.groups.add(group)
        except Group.DoesNotExist:
            # Group doesn't exist yet, skip (will be created by migration)
            pass

