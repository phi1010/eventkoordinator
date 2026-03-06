from apiv1.api_utils import perm_object_to_name
from project.basemodels import MetaBase
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class PerObjectPermissionBackend(ModelBackend):
    """
    Custom authentication backend that checks for object-level permissions.
    """

    def has_perm(self, user_obj, perm, obj=None):
        # First check if the user has the global permission
        if obj is None:
            if super().has_perm(user_obj, perm):
                return True
            else:
                return False
        # If an object is provided, check for object-level permission
        else:
            return self.check_object_permission(user_obj, perm, obj)

    def check_object_permission(self, user_obj, perm, obj):
        if isinstance(obj, MetaBase):
            obj: MetaBase
            perm = perm_object_to_name(perm)
            return obj.has_object_permission(user_obj, perm)
        return False  # Default to no permission unless overridden
