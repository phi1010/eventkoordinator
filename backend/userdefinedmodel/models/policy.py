from django.db import models
from django.db.models import UniqueConstraint

from userdefinedmodel.basemodels import MetaBase


class Policy(MetaBase):
    slug = models.SlugField(max_length=80, unique=True)
    source = models.TextField()

    def __str__(self):
        return self.slug

    class Meta:
        verbose_name_plural = "policies"


class UserDefinedModelTypePolicy(MetaBase):
    user_defined_model_type = models.ForeignKey(
        "userdefinedmodel.UserDefinedModelType",
        on_delete=models.CASCADE,
        related_name="type_policies",
    )
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="type_assignments")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            UniqueConstraint(
                fields=["user_defined_model_type", "policy"],
                name="unique_policy_per_type",
            )
        ]

    def __str__(self):
        return f"{self.user_defined_model_type} → {self.policy}"
