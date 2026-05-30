from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint

from userdefinedmodel.basemodels import MetaBase, PolymorphicMetaBase
from userdefinedmodel.models.config import FieldDefinition


class SingleFieldValidationRule(PolymorphicMetaBase):
    field = models.ForeignKey(
        FieldDefinition, on_delete=models.CASCADE, related_name="single_field_rules"
    )
    applies_to_save = models.BooleanField(default=False)
    admin_label = models.CharField(max_length=200, blank=True)

    APPLICABLE_TYPES: frozenset | None = None

    def validate(self, value) -> list[str]:
        raise NotImplementedError

    def clean(self):
        applicable = getattr(self.__class__, "APPLICABLE_TYPES", None)
        if applicable and self.field_id and self.field.data_type not in applicable:
            raise ValidationError(
                f"{self.__class__.__name__} cannot be applied to a {self.field.data_type} field."
            )

    def clone_to(self, target_field: FieldDefinition) -> "SingleFieldValidationRule":
        obj = self.get_real_instance()
        obj.pk = None
        obj.id = None
        obj.field = target_field
        return obj

    def __str__(self):
        return f"{self.__class__.__name__} on {self.field}"


class RequiredRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = frozenset(FieldDefinition.DataType.values)

    def validate(self, value) -> list[str]:
        if value is None or value == "" or value == [] or value == {}:
            return ["This field is required."]
        return []


class MinLengthRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = frozenset([
        FieldDefinition.DataType.TEXT_SHORT,
        FieldDefinition.DataType.TEXT_LONG,
        FieldDefinition.DataType.TEXT_MARKDOWN,
        FieldDefinition.DataType.TEXT_RICHTEXT,
    ])
    min_length = models.PositiveIntegerField()

    def validate(self, value) -> list[str]:
        if value is not None and len(str(value)) < self.min_length:
            return [f"Must be at least {self.min_length} characters."]
        return []


class MaxLengthRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = frozenset([
        FieldDefinition.DataType.TEXT_SHORT,
        FieldDefinition.DataType.TEXT_LONG,
        FieldDefinition.DataType.TEXT_MARKDOWN,
        FieldDefinition.DataType.TEXT_RICHTEXT,
    ])
    max_length = models.PositiveIntegerField()

    def validate(self, value) -> list[str]:
        if value is not None and len(str(value)) > self.max_length:
            return [f"Must be at most {self.max_length} characters."]
        return []


class RegexRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = frozenset([
        FieldDefinition.DataType.TEXT_SHORT,
        FieldDefinition.DataType.TEXT_LONG,
        FieldDefinition.DataType.TEXT_MARKDOWN,
        FieldDefinition.DataType.TEXT_RICHTEXT,
    ])
    pattern = models.CharField(max_length=500)
    failure_message = models.CharField(max_length=200, blank=True)

    def validate(self, value) -> list[str]:
        import re
        if value is not None and not re.fullmatch(self.pattern, str(value)):
            return [self.failure_message or f"Value does not match required pattern."]
        return []


class MinValueRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = frozenset([FieldDefinition.DataType.INTEGER, FieldDefinition.DataType.FLOAT])
    min_value = models.DecimalField(max_digits=20, decimal_places=6)

    def validate(self, value) -> list[str]:
        from decimal import Decimal
        if value is not None and Decimal(str(value)) < self.min_value:
            return [f"Must be at least {self.min_value}."]
        return []


class MaxValueRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = frozenset([FieldDefinition.DataType.INTEGER, FieldDefinition.DataType.FLOAT])
    max_value = models.DecimalField(max_digits=20, decimal_places=6)

    def validate(self, value) -> list[str]:
        from decimal import Decimal
        if value is not None and Decimal(str(value)) > self.max_value:
            return [f"Must be at most {self.max_value}."]
        return []


_LIST_TYPES = frozenset([
    FieldDefinition.DataType.SUBMODEL_LIST,
    FieldDefinition.DataType.SELECT_MULTI,
    FieldDefinition.DataType.USER_SELECT_MULTI,
    FieldDefinition.DataType.GROUP_SELECT_MULTI,
    FieldDefinition.DataType.ENTITY_SELECT_MULTI,
])


class MinItemsRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = _LIST_TYPES
    min_items = models.PositiveSmallIntegerField()

    def validate(self, value) -> list[str]:
        count = len(value) if isinstance(value, (list, tuple)) else 0
        if count < self.min_items:
            return [f"Must have at least {self.min_items} item(s)."]
        return []


class MaxItemsRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = _LIST_TYPES
    max_items = models.PositiveSmallIntegerField()

    def validate(self, value) -> list[str]:
        count = len(value) if isinstance(value, (list, tuple)) else 0
        if count > self.max_items:
            return [f"Must have at most {self.max_items} item(s)."]
        return []


_FILE_TYPES = frozenset([FieldDefinition.DataType.IMAGE, FieldDefinition.DataType.FILE])


class MaxFileSizeRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = _FILE_TYPES
    max_bytes = models.PositiveIntegerField()

    def validate(self, value) -> list[str]:
        # value is a FileAttachment instance or None
        if value is not None and hasattr(value, "size_bytes") and value.size_bytes > self.max_bytes:
            return [f"File size must not exceed {self.max_bytes} bytes."]
        return []


class AllowedMimeTypesRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = _FILE_TYPES

    def validate(self, value) -> list[str]:
        if value is None:
            return []
        allowed = set(self.allowed_types.values_list("mime_type", flat=True))
        if allowed and hasattr(value, "mime_type") and value.mime_type not in allowed:
            return [f"File type '{value.mime_type}' is not allowed."]
        return []


class AllowedMimeTypeEntry(MetaBase):
    rule = models.ForeignKey(AllowedMimeTypesRule, on_delete=models.CASCADE, related_name="allowed_types")
    mime_type = models.CharField(max_length=100)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["rule", "mime_type"], name="unique_mime_per_rule")
        ]

    def __str__(self):
        return self.mime_type


class RequiredInLanguageRule(SingleFieldValidationRule):
    APPLICABLE_TYPES = frozenset(FieldDefinition.DataType.values) - frozenset([
        FieldDefinition.DataType.SUBMODEL_SELECT,
        FieldDefinition.DataType.SUBMODEL_LIST,
        FieldDefinition.DataType.ENTITY_SELECT,
        FieldDefinition.DataType.ENTITY_SELECT_MULTI,
    ])
    language = models.CharField(max_length=10)

    def validate(self, value) -> list[str]:
        if value is None or value == "" or value == [] or value == {}:
            return [f"This field is required in language '{self.language}'."]
        return []


# ─── Multi-field rules ────────────────────────────────────────────────────────

class MultiFieldValidationRule(PolymorphicMetaBase):
    config_version = models.ForeignKey(
        "userdefinedmodel.ConfigVersion",
        on_delete=models.CASCADE,
        related_name="multi_field_rules",
    )
    applies_to_save = models.BooleanField(default=False)
    admin_label = models.CharField(max_length=200, blank=True)
    fields = models.ManyToManyField(
        FieldDefinition,
        through="MultiFieldRuleAssociation",
        related_name="multi_field_rules",
    )

    def validate(self, field_values: dict) -> str | None:
        raise NotImplementedError

    def __str__(self):
        return f"{self.__class__.__name__} on {self.config_version}"


class MultiFieldRuleAssociation(MetaBase):
    rule = models.ForeignKey(MultiFieldValidationRule, on_delete=models.CASCADE, related_name="associations")
    field = models.ForeignKey(FieldDefinition, on_delete=models.CASCADE, related_name="multi_field_rule_associations")

    class Meta:
        constraints = [
            UniqueConstraint(fields=["rule", "field"], name="unique_field_per_multi_rule")
        ]


def _is_nonempty(val) -> bool:
    if val is None:
        return False
    if isinstance(val, (list, tuple, dict)):
        return len(val) > 0
    if isinstance(val, str):
        return val.strip() != ""
    return True


class AtLeastOneRequiredRule(MultiFieldValidationRule):
    def validate(self, field_values: dict) -> str | None:
        if not any(_is_nonempty(v) for v in field_values.values()):
            slugs = ", ".join(field_values.keys())
            return f"At least one of [{slugs}] must be filled."
        return None


class ExactlyOneRequiredRule(MultiFieldValidationRule):
    def validate(self, field_values: dict) -> str | None:
        filled = [s for s, v in field_values.items() if _is_nonempty(v)]
        if len(filled) != 1:
            slugs = ", ".join(field_values.keys())
            return f"Exactly one of [{slugs}] must be filled (found {len(filled)})."
        return None


class MutualExclusionRule(MultiFieldValidationRule):
    def validate(self, field_values: dict) -> str | None:
        filled = [s for s, v in field_values.items() if _is_nonempty(v)]
        if len(filled) > 1:
            return f"At most one of [{', '.join(field_values.keys())}] may be filled."
        return None
