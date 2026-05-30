"""
Pydantic/Django-Ninja schemas for the userdefinedmodel API (/api/udm/).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Optional

from ninja import Schema
from pydantic import Field, field_validator, model_validator

# ─── Cardinality / length caps ────────────────────────────────────────────────

_MAX_SLUG_LEN = 80
_MAX_LABEL_LEN = 200
_MAX_HELP_TEXT_LEN = 2_000
_MAX_DESCRIPTION_LEN = 5_000
_MAX_NOTES_LEN = 2_000
_MAX_ADMIN_LABEL_LEN = 200
_MAX_LANG_CODE_LEN = 10
_MAX_STATE_NAME_LEN = 100
_MAX_TRANS_NAME_LEN = 100
_MAX_MIME_LEN = 100
_MAX_REGEX_LEN = 500
_MAX_FAIL_MSG_LEN = 200
_MAX_SORT_ORDER = 32_767

_MAX_FIELDS = 200
_MAX_LANGUAGES = 50
_MAX_CHOICES = 500
_MAX_CHOICE_LEN = 200
_MAX_STATES = 100
_MAX_TRANSITIONS = 200
_MAX_RULES = 50
_MAX_MULTI_RULES = 50
_MAX_MIME_ENTRIES = 50
_MAX_GROUP_IDS = 100
_MAX_CHANGED_FIELDS = 200
_MAX_MAPPING_ENTRIES = 300

_MAX_TEXT_LENGTH = 50_000
_MAX_FILE_BYTES = 500_000_000
_MAX_ITEMS_RULE = 10_000

# ─── Reusable annotated types ─────────────────────────────────────────────────

Slug = Annotated[str, Field(min_length=1, max_length=_MAX_SLUG_LEN, pattern=r"^[a-z][a-z0-9_-]*$")]
LangCode = Annotated[str, Field(min_length=2, max_length=_MAX_LANG_CODE_LEN, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]+)*$")]
Label = Annotated[str, Field(min_length=1, max_length=_MAX_LABEL_LEN)]
HelpText = Annotated[str, Field(max_length=_MAX_HELP_TEXT_LEN)]

LocalizedLabel = Annotated[dict[LangCode, Label], Field(min_length=1, max_length=_MAX_LANGUAGES)]
LocalizedHelpText = Annotated[dict[LangCode, HelpText], Field(max_length=_MAX_LANGUAGES)]

# ─── Enums ────────────────────────────────────────────────────────────────────

class DataType(str, Enum):
    TEXT_SHORT = "text_short"; TEXT_LONG = "text_long"
    TEXT_MARKDOWN = "text_markdown"; TEXT_RICHTEXT = "text_richtext"
    INTEGER = "integer"; FLOAT = "float"; BOOLEAN = "boolean"
    DATE = "date"; TIME = "time"; DATETIME = "datetime"
    SELECT_SINGLE = "select_single"; SELECT_MULTI = "select_multi"
    IMAGE = "image"; FILE = "file"
    USER_SELECT = "user_select"; USER_SELECT_MULTI = "user_select_multi"
    GROUP_SELECT = "group_select"; GROUP_SELECT_MULTI = "group_select_multi"
    SUBMODEL_SELECT = "submodel_select"; SUBMODEL_LIST = "submodel_list"
    ENTITY_SELECT = "entity_select"; ENTITY_SELECT_MULTI = "entity_select_multi"


class ConfigVersionStatus(str, Enum):
    DRAFT = "draft"; PUBLISHED = "published"; ARCHIVED = "archived"


class MigrationAction(str, Enum):
    MAP = "map"; DISCARD = "discard"; OVERFLOW = "overflow"


class BulkMigrationStatus(str, Enum):
    DRAFT = "draft"; RUNNING = "running"; DONE = "done"; PARTIAL = "partial"


# ─── TypeConfig models ────────────────────────────────────────────────────────

class TextTypeConfig(Schema):
    max_length: Optional[int] = Field(None, ge=1, le=_MAX_TEXT_LENGTH)
    renderer: Optional[Literal["markdown_wysiwyg", "markdown_preview", "plaintext"]] = None
    model_config = {"extra": "forbid"}


class NumberTypeConfig(Schema):
    min: Optional[Decimal] = Field(None, ge=Decimal("-1e15"), le=Decimal("1e15"))
    max: Optional[Decimal] = Field(None, ge=Decimal("-1e15"), le=Decimal("1e15"))
    decimal_places: Optional[int] = Field(None, ge=0, le=10)
    model_config = {"extra": "forbid"}


class SelectTypeConfig(Schema):
    choices: list[Annotated[str, Field(min_length=1, max_length=_MAX_CHOICE_LEN)]] = Field(
        ..., min_length=1, max_length=_MAX_CHOICES
    )
    model_config = {"extra": "forbid"}


class UserGroupTypeConfig(Schema):
    limit_to_group_ids: Optional[list[int]] = Field(None, max_length=_MAX_GROUP_IDS)
    model_config = {"extra": "forbid"}


class EntitySelectTypeConfig(Schema):
    limit_to_type_ids: Optional[list[int]] = Field(None, max_length=100)
    display_field_slug: Optional[Annotated[str, Field(max_length=_MAX_SLUG_LEN)]] = None
    model_config = {"extra": "forbid"}


class SubmodelTypeConfig(Schema):
    renderer: Optional[Literal["table", "list"]] = None
    model_config = {"extra": "forbid"}


_TYPE_CONFIG_CLS: dict[DataType, type[Schema] | None] = {
    DataType.TEXT_SHORT: TextTypeConfig, DataType.TEXT_LONG: TextTypeConfig,
    DataType.TEXT_MARKDOWN: TextTypeConfig, DataType.TEXT_RICHTEXT: TextTypeConfig,
    DataType.INTEGER: NumberTypeConfig, DataType.FLOAT: NumberTypeConfig,
    DataType.BOOLEAN: None, DataType.DATE: None,
    DataType.TIME: None, DataType.DATETIME: None,
    DataType.SELECT_SINGLE: SelectTypeConfig, DataType.SELECT_MULTI: SelectTypeConfig,
    DataType.IMAGE: None, DataType.FILE: None,
    DataType.USER_SELECT: UserGroupTypeConfig, DataType.USER_SELECT_MULTI: UserGroupTypeConfig,
    DataType.GROUP_SELECT: UserGroupTypeConfig, DataType.GROUP_SELECT_MULTI: UserGroupTypeConfig,
    DataType.SUBMODEL_SELECT: SubmodelTypeConfig, DataType.SUBMODEL_LIST: SubmodelTypeConfig,
    DataType.ENTITY_SELECT: EntitySelectTypeConfig, DataType.ENTITY_SELECT_MULTI: EntitySelectTypeConfig,
}

# ─── Single-field rule schemas ────────────────────────────────────────────────

class RequiredRuleIn(Schema):
    type: Literal["required"]
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class MinLengthRuleIn(Schema):
    type: Literal["min_length"]
    min_length: int = Field(..., ge=0, le=_MAX_TEXT_LENGTH)
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class MaxLengthRuleIn(Schema):
    type: Literal["max_length"]
    max_length: int = Field(..., ge=1, le=_MAX_TEXT_LENGTH)
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class RegexRuleIn(Schema):
    type: Literal["regex"]
    pattern: Annotated[str, Field(min_length=1, max_length=_MAX_REGEX_LEN)]
    failure_message: Annotated[str, Field(max_length=_MAX_FAIL_MSG_LEN)] = ""
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class MinValueRuleIn(Schema):
    type: Literal["min_value"]
    min_value: Decimal = Field(..., ge=Decimal("-1e15"), le=Decimal("1e15"))
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class MaxValueRuleIn(Schema):
    type: Literal["max_value"]
    max_value: Decimal = Field(..., ge=Decimal("-1e15"), le=Decimal("1e15"))
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class MinItemsRuleIn(Schema):
    type: Literal["min_items"]
    min_items: int = Field(..., ge=0, le=_MAX_ITEMS_RULE)
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class MaxItemsRuleIn(Schema):
    type: Literal["max_items"]
    max_items: int = Field(..., ge=0, le=_MAX_ITEMS_RULE)
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class MaxFileSizeRuleIn(Schema):
    type: Literal["max_file_size"]
    max_bytes: int = Field(..., ge=1, le=_MAX_FILE_BYTES)
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class AllowedMimeTypesRuleIn(Schema):
    type: Literal["allowed_mime_types"]
    mime_types: list[Annotated[str, Field(min_length=1, max_length=_MAX_MIME_LEN)]] = Field(
        ..., min_length=1, max_length=_MAX_MIME_ENTRIES
    )
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


class RequiredInLanguageRuleIn(Schema):
    type: Literal["required_in_language"]
    language: LangCode
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}


SingleFieldRuleIn = Annotated[
    RequiredRuleIn | MinLengthRuleIn | MaxLengthRuleIn | RegexRuleIn
    | MinValueRuleIn | MaxValueRuleIn | MinItemsRuleIn | MaxItemsRuleIn
    | MaxFileSizeRuleIn | AllowedMimeTypesRuleIn | RequiredInLanguageRuleIn,
    Field(discriminator="type"),
]

# ─── Multi-field rule schemas ─────────────────────────────────────────────────

class MultiFieldRuleKind(str, Enum):
    AT_LEAST_ONE = "at_least_one_required"
    EXACTLY_ONE = "exactly_one_required"
    MUTUAL_EXCL = "mutual_exclusion"


class MultiFieldRuleIn(Schema):
    kind: MultiFieldRuleKind
    field_slugs: list[Slug] = Field(..., min_length=2, max_length=_MAX_FIELDS)
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}

# ─── FieldDefinition schemas ──────────────────────────────────────────────────

class FieldDefinitionIn(Schema):
    slug: Slug
    data_type: DataType
    sort_order: int = Field(0, ge=0, le=_MAX_SORT_ORDER)
    is_localized: bool = False
    labels: LocalizedLabel
    help_texts: LocalizedHelpText = Field(default_factory=dict)
    type_config: dict[str, Any] = Field(default_factory=dict)
    submodel_config_version_id: Optional[uuid.UUID] = None
    rules: list[SingleFieldRuleIn] = Field(default_factory=list, max_length=_MAX_RULES)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_type_config(self) -> "FieldDefinitionIn":
        cls = _TYPE_CONFIG_CLS.get(self.data_type)
        if cls is None:
            if self.type_config:
                raise ValueError(f"{self.data_type} does not accept type_config")
        else:
            cls.model_validate(self.type_config)
        submodel_types = {DataType.SUBMODEL_SELECT, DataType.SUBMODEL_LIST}
        if self.data_type in submodel_types and self.submodel_config_version_id is None:
            raise ValueError("submodel_config_version_id required for submodel types")
        if self.data_type not in submodel_types and self.submodel_config_version_id is not None:
            raise ValueError("submodel_config_version_id must be null for non-submodel types")
        return self


class FieldDefinitionOut(Schema):
    id: uuid.UUID
    slug: str
    data_type: str
    sort_order: int
    is_localized: bool
    label: dict[str, str]
    help_text: dict[str, str]
    type_config: dict[str, Any]
    submodel_config: Optional["ConfigVersionOut"] = None
    default: Optional[Any] = None
    save_rules: dict[str, Any]

# ─── Languages and FieldConfig schemas ───────────────────────────────────────

class ConfigLanguageIn(Schema):
    code: LangCode
    label: Label
    is_default: bool = False
    sort_order: int = Field(0, ge=0, le=_MAX_SORT_ORDER)
    model_config = {"extra": "forbid"}


class ConfigLanguageOut(Schema):
    code: str; label: str; is_default: bool; sort_order: int


class FieldConfigCreateIn(Schema):
    name: Annotated[str, Field(min_length=1, max_length=_MAX_LABEL_LEN)]
    description: Annotated[str, Field(max_length=_MAX_DESCRIPTION_LEN)] = ""
    languages: list[ConfigLanguageIn] = Field(..., min_length=1, max_length=_MAX_LANGUAGES)
    model_config = {"extra": "forbid"}

    @field_validator("languages")
    @classmethod
    def exactly_one_default(cls, langs: list[ConfigLanguageIn]) -> list[ConfigLanguageIn]:
        if sum(1 for l in langs if l.is_default) != 1:
            raise ValueError("exactly one language must have is_default=True")
        return langs


class FieldConfigUpdateIn(Schema):
    name: Optional[Annotated[str, Field(min_length=1, max_length=_MAX_LABEL_LEN)]] = None
    description: Optional[Annotated[str, Field(max_length=_MAX_DESCRIPTION_LEN)]] = None
    model_config = {"extra": "forbid"}


class FieldConfigOut(Schema):
    id: uuid.UUID; name: str; description: str
    stale_entity_count: int
    type_ids: list[uuid.UUID]
    languages: list[ConfigLanguageOut]

# ─── Workflow schemas ─────────────────────────────────────────────────────────

class WorkflowStateIn(Schema):
    name: Annotated[str, Field(min_length=1, max_length=_MAX_STATE_NAME_LEN, pattern=r"^[a-z][a-z0-9_-]*$")]
    label: LocalizedLabel
    is_initial: bool = False
    allows_edit: bool = True
    model_config = {"extra": "forbid"}


class WorkflowTransitionIn(Schema):
    name: Annotated[str, Field(min_length=1, max_length=_MAX_TRANS_NAME_LEN, pattern=r"^[a-z][a-z0-9_-]*$")]
    label: LocalizedLabel
    from_state: Optional[Annotated[str, Field(max_length=_MAX_STATE_NAME_LEN)]] = None
    to_state: Annotated[str, Field(min_length=1, max_length=_MAX_STATE_NAME_LEN)]
    model_config = {"extra": "forbid"}


class WorkflowDefinitionIn(Schema):
    name: Annotated[str, Field(min_length=1, max_length=_MAX_LABEL_LEN)]
    description: Annotated[str, Field(max_length=_MAX_DESCRIPTION_LEN)] = ""
    states: list[WorkflowStateIn] = Field(..., min_length=1, max_length=_MAX_STATES)
    transitions: list[WorkflowTransitionIn] = Field(default_factory=list, max_length=_MAX_TRANSITIONS)
    model_config = {"extra": "forbid"}

    @field_validator("states")
    @classmethod
    def exactly_one_initial(cls, states: list[WorkflowStateIn]) -> list[WorkflowStateIn]:
        if sum(1 for s in states if s.is_initial) != 1:
            raise ValueError("exactly one state must have is_initial=True")
        return states


class WorkflowStateOut(Schema):
    name: str; label: dict[str, str]; is_initial: bool; allows_edit: bool


class WorkflowTransitionOut(Schema):
    name: str; label: dict[str, str]
    from_state: Optional[str]; to_state: str


class WorkflowOut(Schema):
    initial_state: str
    states: list[WorkflowStateOut]
    transitions: list[WorkflowTransitionOut]

# ─── ConfigVersion schemas ────────────────────────────────────────────────────

class ConfigDraftIn(Schema):
    notes: Annotated[str, Field(max_length=_MAX_NOTES_LEN)] = ""
    fields: list[FieldDefinitionIn] = Field(..., min_length=0, max_length=_MAX_FIELDS)
    multi_field_rules: list[MultiFieldRuleIn] = Field(default_factory=list, max_length=_MAX_MULTI_RULES)
    workflow: Optional[WorkflowDefinitionIn] = None
    model_config = {"extra": "forbid"}

    @field_validator("fields")
    @classmethod
    def unique_slugs(cls, fields: list[FieldDefinitionIn]) -> list[FieldDefinitionIn]:
        seen: set[str] = set()
        for f in fields:
            if f.slug in seen:
                raise ValueError(f"duplicate slug '{f.slug}'")
            seen.add(f.slug)
        return fields


class ConfigVersionOut(Schema):
    version_id: uuid.UUID
    status: str
    notes: str
    published_at: Optional[str]
    languages: list[ConfigLanguageOut]
    fields: list[FieldDefinitionOut]
    workflow: Optional[WorkflowOut] = None


FieldDefinitionOut.model_rebuild()

# ─── Entity schemas ───────────────────────────────────────────────────────────

class EntityCreateIn(Schema):
    user_defined_model_type_id: uuid.UUID
    model_config = {"extra": "forbid"}


class EntityPatchIn(Schema):
    changed_fields: dict[
        Annotated[str, Field(min_length=1, max_length=_MAX_SLUG_LEN)],
        Any,
    ] = Field(..., max_length=_MAX_CHANGED_FIELDS)
    model_config = {"extra": "forbid"}


class TransitionIn(Schema):
    transition: Annotated[str, Field(min_length=1, max_length=_MAX_TRANS_NAME_LEN)]
    model_config = {"extra": "forbid"}


class SubmodelOpKind(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class SubmodelOperationIn(Schema):
    op: SubmodelOpKind
    id: Optional[uuid.UUID] = None
    fields: dict[
        Annotated[str, Field(min_length=1, max_length=_MAX_SLUG_LEN)],
        Any,
    ] = Field(default_factory=dict, max_length=_MAX_CHANGED_FIELDS)
    sort_order: Optional[int] = Field(None, ge=0, le=_MAX_SORT_ORDER)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_op_constraints(self) -> "SubmodelOperationIn":
        if self.op in (SubmodelOpKind.UPDATE, SubmodelOpKind.DELETE) and self.id is None:
            raise ValueError(f"id is required for op='{self.op}'")
        if self.op == SubmodelOpKind.DELETE and self.fields:
            raise ValueError("fields must be absent for op='delete'")
        return self


SubmodelListPatch = Annotated[list[SubmodelOperationIn], Field(max_length=_MAX_FIELDS)]


class UserRefOut(Schema):
    id: uuid.UUID; display_name: str


class FieldValueOut(Schema):
    field_slug: str; data_type: str
    value: Any
    language: str = ""


class EntityOut(Schema):
    id: uuid.UUID
    config_version_id: uuid.UUID
    user_defined_model_type_id: Optional[uuid.UUID]
    current_state: Optional[str]
    owner: Optional[UserRefOut]
    editors: list[UserRefOut]
    field_values: list[FieldValueOut]
    children: dict[str, list[Any]]
    overflow_data: dict[str, Any]
    created_at: str; updated_at: str

# ─── Edit history schemas ─────────────────────────────────────────────────────

class FieldEditOut(Schema):
    change_kind: str
    field_slug: Optional[str] = None
    field_label: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    old_file_name: Optional[str] = None
    new_file_name: Optional[str] = None
    old_file_url: Optional[str] = None
    new_file_url: Optional[str] = None
    affected_node_id: Optional[uuid.UUID] = None


class EditGroupOut(Schema):
    id: uuid.UUID; saved_at: str
    saved_by: Optional[UserRefOut]
    node_id: uuid.UUID; node_type: str
    edits: list[FieldEditOut]


class EditHistoryOut(Schema):
    count: int; next: Optional[str]; results: list[EditGroupOut]

# ─── Migration schemas ────────────────────────────────────────────────────────

class MigrationFieldMappingIn(Schema):
    source_field_slug: Slug
    action: MigrationAction
    target_field_slug: Optional[Slug] = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def target_required_for_map(self) -> "MigrationFieldMappingIn":
        if self.action == MigrationAction.MAP and not self.target_field_slug:
            raise ValueError("target_field_slug required when action is 'map'")
        return self


class MigrationExecuteIn(Schema):
    migration_id: uuid.UUID
    confirmed: Literal[True]
    field_mappings: list[MigrationFieldMappingIn] = Field(..., max_length=_MAX_MAPPING_ENTRIES)
    model_config = {"extra": "forbid"}


class MigrationPreviewFieldOut(Schema):
    source_slug: str; source_data_type: str
    suggested_action: MigrationAction
    suggested_target_slug: Optional[str]
    conflict_reason: Optional[str]


class MigrationPreviewOut(Schema):
    migration_id: uuid.UUID
    source_version_id: uuid.UUID; target_version_id: uuid.UUID
    field_previews: list[MigrationPreviewFieldOut]


class BulkMigrationCreateIn(Schema):
    source_version_id: uuid.UUID; target_version_id: uuid.UUID
    user_defined_model_type_filter_id: Optional[uuid.UUID] = None
    field_mappings: list[MigrationFieldMappingIn] = Field(..., max_length=_MAX_MAPPING_ENTRIES)
    model_config = {"extra": "forbid"}


class BulkMigrationOut(Schema):
    id: uuid.UUID; status: BulkMigrationStatus
    source_version_id: uuid.UUID; target_version_id: uuid.UUID
    user_defined_model_type_filter_id: Optional[uuid.UUID]
    total_entities: int; done_entities: int; failed_entities: int
    executed_at: Optional[str]

# ─── Staging file and autocomplete schemas ────────────────────────────────────

class StagingFileOut(Schema):
    staging_id: uuid.UUID
    original_name: str; mime_type: str; size_bytes: int; expires_at: str


class UserAutocompleteItem(Schema):
    id: uuid.UUID; display_name: str


class GroupAutocompleteItem(Schema):
    id: int; name: str


class EntityAutocompleteItem(Schema):
    id: uuid.UUID
    display: str
    type_id: Optional[uuid.UUID]

# ─── Standard error schemas ───────────────────────────────────────────────────

class ConcurrentEditError(Schema):
    error: Literal["concurrent_edit"]
    retry_after_ms: int = 500


class FieldErrorsOut(Schema):
    errors: dict[str, list[str]]


class EditingNotAllowedError(Schema):
    error: Literal["editing_not_allowed_in_state"]
    current_state: str

# ─── Policy schemas ───────────────────────────────────────────────────────────

class PolicyAction(str, Enum):
    BROWSE = "browse"
    VIEW = "view"
    EDIT = "edit"
    CREATE = "create"
    SAVE = "save"
    DELETE = "delete"
    TRANSITION = "transition"


class MessageLevel(str, Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


LocalizedMessage = Annotated[
    dict[LangCode, Annotated[str, Field(max_length=2_000)]],
    Field(min_length=1, max_length=_MAX_LANGUAGES)
]


class PolicyMessage(Schema):
    level: MessageLevel
    message: LocalizedMessage
    field_slug: Optional[str] = None


class PolicyOutput(Schema):
    allow: bool
    messages: list[PolicyMessage] = []
    viewable_fields: list[str] = []
    editable_fields: list[str] = []


class PolicyCreateIn(Schema):
    slug: Slug
    source: Annotated[str, Field(min_length=1, max_length=500_000)]
    model_config = {"extra": "forbid"}


class PolicyUpdateIn(Schema):
    source: Annotated[str, Field(min_length=1, max_length=500_000)]
    model_config = {"extra": "forbid"}


class PolicyOut(Schema):
    slug: str
    source: str


class PolicyAssignIn(Schema):
    policy_slug: Slug
    sort_order: int = Field(0, ge=0, le=_MAX_SORT_ORDER)
    model_config = {"extra": "forbid"}


# ─── UDMType schemas ──────────────────────────────────────────────────────────

class UDMTypeOut(Schema):
    id: uuid.UUID
    name: str
    description: str
    field_config_id: Optional[uuid.UUID]


class UDMTypeCreateIn(Schema):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class PolicyEvalOut(Schema):
    input_document: dict[str, Any]
    policies: list[dict[str, str]]   # [{"slug": ..., "source": ...}]
    output: dict[str, Any]           # allow, messages, viewable_fields, editable_fields
    error: Optional[str] = None
