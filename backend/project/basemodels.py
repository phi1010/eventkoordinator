import uuid

from django.db import models
from polymorphic.models import PolymorphicModel
from simple_history.models import HistoricalRecords


class MetaBase(models.Model):
    """Base model with common fields for all models."""

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def has_object_permission(self, user, perm):
        """Check if the user has the given permission for this object."""
        # Default implementation: none object-level permissions
        return user.has_perm(perm, None)

    class Meta:
        abstract = True

class HistoricalMetaBase(MetaBase):

    history = HistoricalRecords(inherit=True)

    class Meta:
        abstract = True

class PolymorphicMetaBase(PolymorphicModel, MetaBase):

    history = HistoricalRecords(inherit=True)

    class Meta:
        abstract = True