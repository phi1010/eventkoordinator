import os
import uuid
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint
from django.utils.deconstruct import deconstructible
from django.utils.timezone import now

from userdefinedmodel.basemodels import MetaBase
from userdefinedmodel.models.config import FieldDefinition, TypedValue


@deconstructible
class UUIDFilenameUploadTo:
    def __init__(self, folder: str):
        self.folder = folder.strip("/")

    def __call__(self, instance, filename: str) -> str:
        _base, ext = os.path.splitext(os.path.basename(filename or ""))
        return f"{self.folder}/{uuid.uuid4()}{ext.lower()}"


class FileAttachment(MetaBase):
    file = models.FileField(upload_to=UUIDFilenameUploadTo("proposal_files"))
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    image_width = models.PositiveSmallIntegerField(null=True, blank=True)
    image_height = models.PositiveSmallIntegerField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.original_name


class StagingFile(MetaBase):
    uploader = models.ForeignKey(
        "openid_user_management.OpenIDUser",
        on_delete=models.CASCADE,
        related_name="staging_files",
    )
    file = models.FileField(upload_to=UUIDFilenameUploadTo("staging"))
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    intended_field = models.ForeignKey(
        FieldDefinition, on_delete=models.SET_NULL, null=True, blank=True
    )
    intended_node = models.ForeignKey(
        "userdefinedmodel.UserDefinedModelEntityNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.original_name


class UserDefinedModelEntityNode(MetaBase):
    config_version = models.ForeignKey(
        "userdefinedmodel.ConfigVersion",
        on_delete=models.PROTECT,
        related_name="nodes",
    )
    parent_node = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    parent_field = models.ForeignKey(
        FieldDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_nodes",
    )
    overflow_data = models.JSONField(default=dict)
    current_state = models.ForeignKey(
        "userdefinedmodel.WorkflowState",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="nodes_in_state",
    )

    def get_root(self) -> "UserDefinedModelEntity":
        node = self
        while node.parent_node_id is not None:
            node = node.parent_node
        return node.userdefinedmodelentity

    def get_field_value(self, slug: str) -> "FieldValue | None":
        try:
            return self.field_values.select_related("field").get(field__slug=slug, language="")
        except FieldValue.DoesNotExist:
            return None

    def _evaluate_rules(self, single_rules, multi_rules) -> dict:
        errors = defaultdict(list)

        for rule in single_rules.select_related("field"):
            real = rule.get_real_instance()
            if rule.field.is_localized:
                for fv in self.field_values.filter(field=rule.field):
                    for msg in real.validate(fv.get_value()):
                        errors[f"{rule.field.slug}[{fv.language}]"].append(msg)
            else:
                fv = self.get_field_value(rule.field.slug)
                val = fv.get_value() if fv else None
                for msg in real.validate(val):
                    errors[rule.field.slug].append(msg)

        for rule in multi_rules.prefetch_related("associations__field"):
            real = rule.get_real_instance()
            field_values = {}
            for a in rule.associations.all():
                if a.field.is_localized:
                    field_values[a.field.slug] = {
                        fv.language: fv.get_value()
                        for fv in self.field_values.filter(field=a.field)
                    }
                else:
                    fv = self.get_field_value(a.field.slug)
                    field_values[a.field.slug] = fv.get_value() if fv else None
            msg = real.validate(field_values)
            if msg:
                for slug in field_values:
                    errors[slug].append(msg)

        return dict(errors)

    def validate_for_save(self):
        from userdefinedmodel.models.rules import SingleFieldValidationRule, MultiFieldValidationRule
        single = SingleFieldValidationRule.objects.filter(
            field__version=self.config_version, applies_to_save=True
        )
        multi = MultiFieldValidationRule.objects.filter(
            config_version=self.config_version, applies_to_save=True
        )
        errors = self._evaluate_rules(single, multi)
        if errors:
            raise ValidationError(errors)

    def to_policy_document(self) -> dict:
        fields_data = {}
        for fv in self.field_values.select_related("field").all():
            slug = fv.field.slug
            val = fv.get_value()
            if fv.language:
                if slug not in fields_data:
                    fields_data[slug] = {
                        "data_type": fv.field.data_type,
                        "localized": True,
                        "value": {},
                    }
                fields_data[slug]["value"][fv.language] = val
            else:
                fields_data[slug] = {
                    "data_type": fv.field.data_type,
                    "localized": False,
                    "value": val,
                }

        children_data = {}
        for child in self.children.all():
            slug = child.parent_field.slug if child.parent_field else "unknown"
            if slug not in children_data:
                children_data[slug] = []
            children_data[slug].append(child.to_policy_document())

        doc = {
            "id": str(self.id),
            "type": "entity",
            "config_version_id": str(self.config_version_id),
            "config_id": str(self.config_version.config_id),
            "type_id": None,
            "owner": None,
            "editors": [],
            "current_state": self.current_state.name if self.current_state else None,
            "fields": fields_data,
            "children": children_data,
            "overflow_data": self.overflow_data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        # Enrich with entity-specific fields if this is a root entity
        try:
            entity = self.userdefinedmodelentity
            doc["type_id"] = str(entity.user_defined_model_type_id) if entity.user_defined_model_type_id else None
            doc["owner"] = {
                "id": str(entity.owner_id),
                "username": entity.owner.username if entity.owner else "",
                "is_active": entity.owner.is_active if entity.owner else False,
            } if entity.owner_id else None
            doc["editors"] = [
                {"id": str(e.id), "username": e.username}
                for e in entity.editors.all()
            ]
        except UserDefinedModelEntity.DoesNotExist:
            # Submodel — label with parent field slug
            if self.parent_field:
                doc["type"] = f"submodel:{self.parent_field.slug}"

        return doc

    def materialize_defaults(self):
        from userdefinedmodel.models.config import FieldDefaultValue
        for default in FieldDefaultValue.objects.filter(field__version=self.config_version):
            field = default.field
            lang = default.language
            fv, created = FieldValue.objects.get_or_create(
                node=self, field=field, language=lang
            )
            if created:
                fv.set_value(default.get_value(field=field), field=field)
                fv.save()

    def __str__(self):
        return f"Node {self.id}"


class UserDefinedModelEntity(UserDefinedModelEntityNode):
    user_defined_model_type = models.ForeignKey(
        "userdefinedmodel.UserDefinedModelType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entities",
    )
    owner = models.ForeignKey(
        "openid_user_management.OpenIDUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_entities",
    )
    editors = models.ManyToManyField(
        "openid_user_management.OpenIDUser",
        blank=True,
        related_name="edited_entities",
    )

    def __str__(self):
        return f"Entity {self.id}"


class SubmodelInstance(UserDefinedModelEntityNode):
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Submodel {self.id}"


class FieldValue(TypedValue, MetaBase):
    node = models.ForeignKey(
        UserDefinedModelEntityNode, on_delete=models.CASCADE, related_name="field_values"
    )
    field = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT, related_name="values")
    language = models.CharField(max_length=10, default="")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["node", "field", "language"],
                name="unique_value_per_node_field_language",
            )
        ]

    def clean(self):
        self._clean_typed_value(self.field)

    def get_value(self, field=None):
        return super().get_value(field=field or self.field)

    def set_value(self, value, field=None):
        super().set_value(value, field=field or self.field)

    def __str__(self):
        return f"FieldValue({self.field.slug}, node={self.node_id})"
