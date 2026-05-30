from django.db import models

from userdefinedmodel.basemodels import MetaBase


class UserDefinedModelEntityMigration(MetaBase):
    class Action(models.TextChoices):
        MAP = "map"
        DISCARD = "discard"
        OVERFLOW = "overflow"

    user_defined_model_entity = models.ForeignKey(
        "userdefinedmodel.UserDefinedModelEntity",
        on_delete=models.CASCADE,
        related_name="migrations",
    )
    source_version = models.ForeignKey(
        "userdefinedmodel.ConfigVersion",
        on_delete=models.PROTECT,
        related_name="+",
    )
    target_user_defined_model_type = models.ForeignKey(
        "userdefinedmodel.UserDefinedModelType",
        on_delete=models.PROTECT,
        related_name="received_entity_migrations",
    )
    target_version = models.ForeignKey(
        "userdefinedmodel.ConfigVersion",
        on_delete=models.PROTECT,
        related_name="+",
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.ForeignKey(
        "openid_user_management.OpenIDUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    bulk_plan = models.ForeignKey(
        "userdefinedmodel.BulkMigrationPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entity_migrations",
    )

    def __str__(self):
        return f"Migration {self.id}"


class MigrationFieldMapping(MetaBase):
    migration = models.ForeignKey(
        UserDefinedModelEntityMigration,
        on_delete=models.CASCADE,
        related_name="field_mappings",
    )
    source_field = models.ForeignKey(
        "userdefinedmodel.FieldDefinition",
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=10, choices=UserDefinedModelEntityMigration.Action)
    target_field = models.ForeignKey(
        "userdefinedmodel.FieldDefinition",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self):
        return f"Mapping {self.source_field} → {self.target_field or self.action}"


class BulkMigrationPlan(MetaBase):
    class Status(models.TextChoices):
        DRAFT = "draft"
        RUNNING = "running"
        DONE = "done"
        PARTIAL = "partial"

    source_version = models.ForeignKey(
        "userdefinedmodel.ConfigVersion",
        on_delete=models.PROTECT,
        related_name="+",
    )
    target_version = models.ForeignKey(
        "userdefinedmodel.ConfigVersion",
        on_delete=models.PROTECT,
        related_name="+",
    )
    user_defined_model_type_filter = models.ForeignKey(
        "userdefinedmodel.UserDefinedModelType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        "openid_user_management.OpenIDUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    total_entities = models.PositiveIntegerField(default=0)
    done_entities = models.PositiveIntegerField(default=0)
    failed_entities = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"BulkMigrationPlan {self.id} ({self.status})"


class BulkMigrationFieldMapping(MetaBase):
    plan = models.ForeignKey(BulkMigrationPlan, on_delete=models.CASCADE, related_name="field_mappings")
    source_field = models.ForeignKey(
        "userdefinedmodel.FieldDefinition",
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=10, choices=UserDefinedModelEntityMigration.Action)
    target_field = models.ForeignKey(
        "userdefinedmodel.FieldDefinition",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self):
        return f"BulkMapping {self.source_field} → {self.target_field or self.action}"
