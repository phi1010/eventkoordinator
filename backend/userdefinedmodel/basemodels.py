import uuid

from django.db import models
from polymorphic.models import PolymorphicModel


class MetaBase(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PolymorphicMetaBase(PolymorphicModel, MetaBase):
    class Meta:
        abstract = True
