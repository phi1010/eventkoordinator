# Configurable UserDefinedModelEntity Form — Implementation Plan

## Requirements

### Field configuration
- Per-user_defined_model_type, configurable user_defined_model_entity form with a defined set of field types → §2.1, §8
- Supported types: `text_short`, `text_long`, `text_markdown`, `text_richtext`, `integer`, `float`, `boolean`, `date`, `time`, `datetime`, `select_single`, `select_multi`, `image`, `file`, `user_select`, `user_select_multi`, `group_select`, `group_select_multi`, `submodel_select`, `submodel_list` → §2.1
- Multiple user_defined_model_types may share the same field configuration → §2.1, §3
- A user_defined_model_type's configuration can be switched to a different one → §5.5, §6
- `TEXT_RICHTEXT` content is sanitised with **`nh3`** on write → §2.1
- Each field may carry an admin-chosen default value (per-language for localized fields); new user_defined_model_entities start pre-filled from these defaults, and publish is blocked unless the default combination passes save-time validation → §2.8

### Config versioning
- Field configuration is versioned with an explicit DRAFT → PUBLISHED → ARCHIVED lifecycle → §3
- Published versions are immutable; editing creates a new draft automatically → §3
- A user_defined_model_type's user_defined_model_entities remain bound to the version they were created under until migrated → §3, §5
- Orphaned archived `FieldConfig` versions (no living user_defined_model_entities) may only be deleted by explicit staff action → §6

### Submodels
- Submodel instances (e.g. Speakers) are stored as separate Django model rows → §2.2
- Submodels share a common base (`UserDefinedModelEntityNode`) with user_defined_model_entities for reuse of validation and migration logic → §2.2
- Submodels may be nested to any depth; the UI warns beyond 2 levels, with no hard model limit → §2.2

### File and image attachments
- File and image fields are supported on user_defined_model_entities and submodels at any nesting level → §2.3
- Files are only permanently stored when the user explicitly saves; selections are held in a temporary staging area until then → §2.3, §11
- Staged files use the same storage backend as committed files (staging/ prefix), configurable via django-storages → §2.3
- When a file/image field is overwritten the previous `FileAttachment` row is **soft-deleted** (not physically removed), so the edit history can show the prior version → §2.3, §13

### Configurable workflow
- Every `UserDefinedModelEntityNode` (both `UserDefinedModelEntity` and `SubmodelInstance`) can have a configurable workflow with named states and transitions; the hardcoded `UserDefinedModelEntity.Status` choices are replaced by `WorkflowState` instances → §2.2, §2.6, §15
- A `WorkflowDefinition` is assigned per `ConfigVersion`; different config versions (and therefore different submodel types) may have different workflows → §2.6
- Each transition carries: permission checks, additional validators, mandatory field updates (fields that must be filled on transition), pre-actions (before validation + save), and post-actions (after save) → §2.6, §15

### Validation rules
- Validation rules are stored as model instances in a polymorphic hierarchy, not as JSON → §2.5
- Single-field rules are attached to exactly one field via FK; reuse on another field requires an explicit copy → §2.5
- Incompatible (rule type, field type) pairs are rejected in `SingleFieldValidationRule.clean()` via an `APPLICABLE_TYPES` class variable → §2.5
- Multi-field rules are associated with multiple fields via a join table; cross-version integrity (all fields must belong to the same `ConfigVersion`) is enforced at the application level → §2.5
- A rule's `applies_to_save` flag controls whether it runs on every save (PATCH); save-time validation is permissive (allows partial/incomplete data) → §2.5, §4
- Stricter "submit-time" validation is not a rule flag: submission is a workflow transition, and the strict rules are attached to that transition as validators (`TransitionValidatorAssignment`) / mandatory fields (`TransitionMandatoryField`) → §2.6, §4, §15

### Migration
- UserDefinedModelEntities can be migrated to a different user_defined_model_type or re-bound to a newer config version → §5.1–§5.4
- Migration is user-confirmed per field: each orphaned source field can be mapped, discarded, or kept in an overflow store → §5.3
- Config republish and user_defined_model_type config-switch both trigger a bulk migration flow: one field mapping is defined once and applied to all affected user_defined_model_entities → §5.5
- Bulk migration always executes asynchronously via a **Celery task** → §5.5
- A config-switch always rolls back entirely if any user_defined_model_entity migration fails; no partial switch → §5.5
- Orphaned field values from any migration are preserved in `UserDefinedModelEntityNode.overflow_data` for staff review → §5.3

### Partial saves and per-field undo
- PATCH requests send only the fields the user changed; other fields are never overwritten → §12
- The frontend tracks saved vs. editing state per field; a reset button reverts a single field to its last saved value without a server user_defined_model_type → §12
- Unchanged fields retain their stored value even if another user modified them in the meantime → §12

### Edit history
- All field changes within a single save are grouped together as one `EditGroup`; workflow state transitions are also recorded → §2.4, §13
- History is scoped to the root user_defined_model_entity and includes edits from nested submodel instances → §2.4, §13
- File/image edits carry FK references to the soft-deleted old and active new `FileAttachment` rows, enabling the history UI to show the previous version inline → §2.3, §13
- Rich-text/markdown edits store the full old and new strings for client-side diff rendering → §13
- Edit history is retained indefinitely → §13

### Localisation
- Every `FieldDefinition` has a single language-independent `slug` key; its human-readable `label` and `help_text` are stored exclusively in `FieldDefinitionTranslation` rows — there are no direct `label`/`help_text` columns on `FieldDefinition` → §2.7
- `WorkflowState` and `WorkflowTransition` labels follow the same translation pattern → §2.7
- Supported languages are defined per `FieldConfig` as `ConfigLanguage` rows; one language is marked as the default fallback → §2.7
- Any field type (including file and image) can be made localized by setting `is_localized = True` on its `FieldDefinition`; a localized field stores one `FieldValue` per language using the same field definition and the same validators → §2.1, §2.3, §2.7
- Validators apply independently to each language's value; per-language required-ness is expressed with a `RequiredInLanguageRule` → §2.5, §2.7, §4
- The PATCH payload uses a `{language_code: value}` dict for localized fields; omitting a language leaves that language's stored value untouched → §6, §12

### Concurrent write safety
- The root `UserDefinedModelEntity` row is locked (`SELECT FOR UPDATE NOWAIT`) before any validation runs and held through the write; it is the single mutex for the whole user_defined_model_entity tree → §14, §14.2
- Validation results are never cached across a transaction boundary → §14.1
- Only one row is ever write-locked, so there is no lock-ordering or deadlock concern between user_defined_model_entity writes → §14.2
- Status transitions hold the root lock so no concurrent field edit can race against the status change → §14.3
- Lock contention returns HTTP 409 immediately; the frontend retries → §14.5
- The test suite uses **PostgreSQL exclusively** (SQLite dropped); no conditional locking guards needed → §14

---

## Overview

Replace the current hardcoded `UserDefinedModelEntity` / `Speaker` fields with a versioned,
**shareable** field configuration system. A `FieldConfig` is an independent entity;
multiple user_defined_model_types can reference the same one. The same validation and migration logic
applies to user_defined_model_entities and all submodel instances through a shared base model.

**Django app:** all models, views, serializers, Celery tasks, Rego policies, and
management commands described in this plan live in a new Django app **`userdefinedmodel`**
(`backend/userdefinedmodel/`). The app's API is mounted at `/api/udm/`.

---

## 1. Core Concepts

| Term | Meaning |
|---|---|
| **FieldConfig** | Independent, named configuration entity; may be shared by multiple user_defined_model_types |
| **SingleFieldValidationRule** | Polymorphic rule attached to exactly one `FieldDefinition` via FK; must be copied to reuse on a different field |
| **MultiFieldValidationRule** | Polymorphic rule associated with multiple `FieldDefinition`s via a join table; expresses cross-field constraints |
| **ConfigVersion** | One immutable snapshot of field definitions (DRAFT → PUBLISHED → ARCHIVED) |
| **FieldDefinition** | A single configured field within a version |
| **UserDefinedModelEntityNode** | Concrete base model shared by `UserDefinedModelEntity` and all submodel instances |
| **FieldValue** | Stores the actual value of one field on one UserDefinedModelEntityNode |
| **FileAttachment** | File or image permanently bound to a FieldValue (created only at save time) |
| **StagingFile** | Temporary file upload held server-side until the user saves; promoted or discarded |
| **EditGroup** | Records all field changes made in a single save operation |
| **FieldEdit** | One changed field within an EditGroup (old value → new value) |
| **UserDefinedModelEntityMigration** | A recorded move of one UserDefinedModelEntity to a different user_defined_model_type / config version |
| **BulkMigrationPlan** | A staff-configured mapping applied to many user_defined_model_entities at once (config switch or republish) |
| **ConfigLanguage** | A supported BCP-47 language code registered on a `FieldConfig`; one is marked as default fallback |
| **FieldDefinitionTranslation** | A translated `label` / `help_text` for one `FieldDefinition` in one language |

---

## 2. Django Models

### 2.1 Config versioning

```
FieldConfig  ──1:N──  ConfigVersion
    │                      │
    │ (referenced by)  FieldDefinition (N per version)
    │                      │
  N:1                 SubmodelConfigVersion (optional FK)
    │                      │
   UserDefinedModelType            FieldDefinition (recursive, for sub-fields)
```

A `FieldConfig` is an independent entity — not owned by any single user_defined_model_type. Many
user_defined_model_types may share one `FieldConfig`. Each `UserDefinedModelType` holds a nullable FK to the
`FieldConfig` it currently uses.

**`FieldConfig`**
```python
class FieldConfig(HistoricalMetaBase):
    name        = models.CharField(max_length=200)  # e.g. "Standard Workshop Form"
    description = models.TextField(blank=True)
```

**On `UserDefinedModelType`** (new field, added alongside existing UserDefinedModelType fields):
```python
field_config = models.ForeignKey(
    FieldConfig,
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name="user_defined_model_types",
)
```

Changing `UserDefinedModelType.field_config` triggers the **config-switch migration flow** (see §5.5).

**`ConfigVersion`**
```python
class ConfigVersion(HistoricalMetaBase):
    class Status(models.TextChoices):
        DRAFT     = "draft"
        PUBLISHED = "published"
        ARCHIVED  = "archived"

    config       = models.ForeignKey(FieldConfig, on_delete=models.CASCADE,
                                     related_name="versions")
    status       = models.CharField(max_length=10, choices=Status,
                                    default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    notes        = models.TextField(blank=True)  # human change-log entry
    # Workflow governing nodes created under this version. Null = no workflow,
    # all field edits are always permitted regardless of state.
    workflow     = models.ForeignKey(
        "WorkflowDefinition", on_delete=models.PROTECT,
        null=True, blank=True, related_name="config_versions",
    )

    class Meta:
        # At most one DRAFT and one PUBLISHED per FieldConfig at any time.
        constraints = [
            UniqueConstraint(
                fields=["config"],
                condition=Q(status="draft"),
                name="unique_draft_per_config",
            ),
            UniqueConstraint(
                fields=["config"],
                condition=Q(status="published"),
                name="unique_published_per_config",
            ),
        ]

    def publish(self):
        """Atomically archive the current published version and publish this one."""
        with transaction.atomic():
            ConfigVersion.objects.filter(
                config=self.config, status=self.Status.PUBLISHED
            ).update(status=self.Status.ARCHIVED)
            self.status = self.Status.PUBLISHED
            self.published_at = now()
            self.save()
```

**`FieldDefinition`**

```python
class FieldDefinition(HistoricalMetaBase):
    class DataType(models.TextChoices):
        TEXT_SHORT      = "text_short"       # CharField, max_length config
        TEXT_LONG       = "text_long"        # TextField, no rich text
        TEXT_MARKDOWN   = "text_markdown"    # Stored as Markdown string
        TEXT_RICHTEXT   = "text_richtext"    # Stored as HTML (sanitised on write)
        INTEGER         = "integer"
        FLOAT           = "float"
        BOOLEAN         = "boolean"
        DATE            = "date"
        TIME            = "time"
        DATETIME        = "datetime"
        SELECT_SINGLE        = "select_single"        # choices list in type_config
        SELECT_MULTI         = "select_multi"         # choices list in type_config
        IMAGE                = "image"
        FILE                 = "file"
        USER_SELECT          = "user_select"          # single OpenIDUser PK
        USER_SELECT_MULTI    = "user_select_multi"    # list of OpenIDUser PKs
        GROUP_SELECT         = "group_select"         # single auth.Group PK
        GROUP_SELECT_MULTI   = "group_select_multi"   # list of auth.Group PKs
        SUBMODEL_SELECT      = "submodel_select"      # FK reference to existing SubmodelInstance
        SUBMODEL_LIST        = "submodel_list"        # inline children (1:N)

    version         = models.ForeignKey(ConfigVersion, on_delete=models.CASCADE,
                                        related_name="field_definitions")
    # slug is the language-independent machine key; never translated.
    slug            = models.SlugField(max_length=80)
    # label / help_text live exclusively in FieldDefinitionTranslation rows (see §2.7).
    data_type       = models.CharField(max_length=30, choices=DataType)
    sort_order      = models.PositiveSmallIntegerField(default=0)
    # When True, one FieldValue row is stored per language (see §2.7).
    is_localized    = models.BooleanField(default=False)

    # For SUBMODEL_LIST / SUBMODEL_SELECT: the config version that defines sub-fields.
    # Null for all other types.
    submodel_config = models.ForeignKey(
        "ConfigVersion", on_delete=models.PROTECT,
        null=True, blank=True, related_name="used_as_submodel"
    )

    # Type-specific config: choices for select, min/max for numbers, etc.
    type_config     = models.JSONField(default=dict)
    # Examples:
    # select:             {"choices": ["option_a", "option_b"]}
    # text:               {"max_length": 1000}
    # number:             {"min": 0, "max": 100, "decimal_places": 2}
    # user_select*:       {"limit_to_group_ids": [3, 7]}   # optional; omit = all active users
    # group_select*:      {"limit_to_group_ids": [3, 7]}   # optional; omit = all groups

    # Validation rules are stored as model instances — see §2.5 and §4.
    # Single-field rules carry a FK back to this FieldDefinition.
    # Multi-field rules reference this field through MultiFieldRuleAssociation.

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            UniqueConstraint(fields=["version", "slug"], name="unique_slug_in_version"),
        ]
```

**Datatype immutability rule** — when a `FieldDefinition` already has `FieldValue`
rows pointing to it, its `data_type` may only be changed if every existing value can
be losslessly converted. Permitted automatic conversions:

| From | To | Conversion |
|---|---|---|
| `integer` | `float` | cast |
| `text_short` | `text_long` | no-op |
| `text_long` | `text_markdown` | no-op (plain text is valid markdown) |
| `select_single` | `select_multi` | wrap scalar in list |
| `user_select` | `user_select_multi` | wrap scalar in list |
| `group_select` | `group_select_multi` | wrap scalar in list |

All other changes are blocked. The admin/API must expose a dry-run endpoint that
returns the count of unconvertible values before allowing the change.

**User and group field validation** — `FieldValue.clean()` for `USER_SELECT*` and
`GROUP_SELECT*` types verifies that every stored PK refers to an existing,
active record (`is_active=True` for users). If `type_config` contains
`limit_to_group_ids`, the stored user PKs must also belong to one of those groups.
Deleted users/groups cause existing values to fail `clean()`; the API exposes this
as a field error so staff can correct the value before the next submit.

**API serialisation** — UserDefinedModelEntity GET responses resolve user/group PKs to display
objects so the frontend never needs a separate lookup per stored ID:

```jsonc
// field with data_type "user_select_multi"
{
  "field_slug": "reviewers",
  "value": [
    { "id": 5,  "display_name": "Alice" },
    { "id": 12, "display_name": "Bob"   }
  ]
}
// field with data_type "group_select"
{
  "field_slug": "responsible_team",
  "value": { "id": 3, "name": "Workshop Committee" }
}
```

PATCH input still uses raw PKs (or a list of PKs for multi variants).

---

### 2.2 Shared user_defined_model_entity node

```
UserDefinedModelEntityNode  ──1:N──  FieldValue  ──0:1──  FileAttachment
     │
     ├── UserDefinedModelEntity  (root nodes; one per submission)
     └── SubmodelInstance  (child nodes)
```

**`UserDefinedModelEntityNode`** (concrete, not abstract — enables self-referential FK for nesting)

```python
class UserDefinedModelEntityNode(HistoricalMetaBase):
    config_version = models.ForeignKey(
        ConfigVersion, on_delete=models.PROTECT, related_name="nodes"
    )
    # Non-null for submodel instances; null for root UserDefinedModelEntity nodes.
    parent_node    = models.ForeignKey(
        "self", on_delete=models.CASCADE,
        null=True, blank=True, related_name="children"
    )
    # Which field in the parent defines this child's type.
    parent_field   = models.ForeignKey(
        FieldDefinition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="child_nodes"
    )
    # Orphaned field values from a migration land here for staff review.
    overflow_data  = models.JSONField(default=dict)
    # Current position in the node's workflow. Null until the workflow's
    # initial state is assigned on first save (see §2.6).
    current_state  = models.ForeignKey(
        "WorkflowState", on_delete=models.PROTECT,
        null=True, blank=True, related_name="nodes_in_state",
    )

    def get_field_value(self, slug: str) -> "FieldValue | None": ...
    def validate_for_save(self): ...
    def to_policy_document(self) -> dict: ...   # canonical JSON for Rego authz, see §16
    # No validate_for_submit(): strict submit validation is performed by the
    # workflow transition engine (§15), which recursively re-runs each node's
    # save rules plus its submit-transition validators across the subtree.
```

**`UserDefinedModelEntity`** extends `UserDefinedModelEntityNode` via multi-table inheritance.
The hardcoded `Status` choices are removed — states are now `WorkflowState`
instances (see §2.6):

```python
class UserDefinedModelEntity(UserDefinedModelEntityNode):
    user_defined_model_type    = models.ForeignKey(UserDefinedModelType, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="user_defined_model_entities")
    owner   = models.ForeignKey(OpenIDUser, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="owned_user_defined_model_entities")
    editors = models.ManyToManyField(OpenIDUser, blank=True,
                                     related_name="edited_user_defined_model_entities")
    # ... existing permission logic migrated here; permission checks now
    # consult current_state and its outgoing WorkflowTransitions
```

**`SubmodelInstance`** extends `UserDefinedModelEntityNode`:

```python
class SubmodelInstance(UserDefinedModelEntityNode):
    sort_order = models.PositiveSmallIntegerField(default=0)
    # The type of submodel is inferred from parent_field.submodel_config.

    class Meta:
        ordering = ["sort_order", "id"]
```

---

### 2.3 Field values

**`FieldValue`**

The typed value columns and their accessors are shared with the default-value
model (§2.8), so they live on an abstract base:

```python
class TypedValue(models.Model):
    """Abstract holder of one typed value, selected by an associated
    FieldDefinition's data_type. Reused by FieldValue and FieldDefaultValue."""

    # The value is stored in exactly one typed column selected by
    # field.data_type (see the mapping table below). A single untyped
    # JSONField is deliberately NOT used: it stores Decimals via float
    # (precision loss on money like material_cost_eur), can't sort/filter
    # dates or numbers at the SQL level (needed for the staff review /
    # export views), and gives no referential integrity for user/group/
    # submodel references. Typed columns fix all three; the unused columns
    # are NULL and cost ~nothing (Postgres stores trailing NULLs as a bitmap).
    value_text     = models.TextField(null=True, blank=True)        # text_*, select_single (choice key)
    value_decimal  = models.DecimalField(max_digits=30, decimal_places=10,
                                          null=True, blank=True)     # integer + float, exact
    value_bool     = models.BooleanField(null=True)
    value_date     = models.DateField(null=True, blank=True)
    value_time     = models.TimeField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_json     = models.JSONField(null=True, blank=True)        # select_multi, *_multi PK lists
    # Real FKs for single references → DB-level integrity + correct on_delete,
    # which makes the USER_SELECT/GROUP_SELECT existence check in §2.1 redundant.
    value_user     = models.ForeignKey(OpenIDUser, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name="+")  # user_select
    value_group    = models.ForeignKey("auth.Group", on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name="+")  # group_select
    value_node     = models.ForeignKey(UserDefinedModelEntityNode, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name="+")  # submodel_select
    # SUBMODEL_LIST has no value column — children are UserDefinedModelEntityNode rows via parent_node.

    class Meta:
        abstract = True

    # Logical accessor: read/write the correct typed column for the field's
    # data_type. The validation engine (§4), history diffing (§13) and the
    # API serialiser all go through these instead of touching columns directly.
    def get_value(self): ...
    def set_value(self, value): ...

    def _clean_typed_value(self, field: "FieldDefinition"):
        """Validate the value matches field.data_type and type_config, and that
        exactly the one column for this data_type is populated. The 'exactly one
        column' rule is enforced here, NOT as a CheckConstraint: a DB constraint
        interacts badly with clearing-to-null and per-language rows."""
        ...


class FieldValue(TypedValue, MetaBase):
    node       = models.ForeignKey(UserDefinedModelEntityNode, on_delete=models.CASCADE,
                                   related_name="field_values")
    field      = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                   related_name="values")
    # BCP-47 language code for localized fields (field.is_localized=True).
    # Empty string for non-localized fields — this lets a single unique
    # constraint cover both cases without a nullable column.
    language   = models.CharField(max_length=10, default="")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["node", "field", "language"],
                name="unique_value_per_node_field_language",
            )
        ]

    def clean(self):
        self._clean_typed_value(self.field)
```

**Value column by `data_type`:**

| `data_type` | Column |
|---|---|
| `text_short`, `text_long`, `text_markdown`, `text_richtext` | `value_text` |
| `select_single` | `value_text` (stores the choice key) |
| `integer`, `float` | `value_decimal` (exact NUMERIC; no float round-trip) |
| `boolean` | `value_bool` |
| `date` / `time` / `datetime` | `value_date` / `value_time` / `value_datetime` |
| `select_multi`, `user_select_multi`, `group_select_multi` | `value_json` (list of keys / PKs) |
| `user_select` / `group_select` / `submodel_select` | `value_user` / `value_group` / `value_node` |
| `image`, `file` | *(no column — the `FileAttachment` FK points at this `FieldValue`)* |
| `submodel_list` | *(no `FieldValue` row — children are `UserDefinedModelEntityNode`s via `parent_node`)* |

Localisation is unaffected: there is still one `FieldValue` row per language
(`language` column), and the typed-column choice is the same for every language.

Typed columns make per-field SQL filtering and sorting possible for the staff
review/export views, e.g.
`FieldValue.objects.filter(field__slug="duration_days", value_decimal__gt=3)`,
with a real index — something a single JSON column cannot do.

**`FileAttachment`** — created only when a save is committed, never on file selection.
When a file/image field is overwritten the old `FileAttachment` row is **soft-deleted**
(its `field_value` FK is set to null and `deleted_at` is stamped) so the previous
version remains accessible from the edit history timeline. Physical file deletion
happens via a separate `cleanup_deleted_attachments` management command.

```python
class FileAttachment(MetaBase):
    # Null when this attachment has been replaced and is kept only for history.
    field_value   = models.ForeignKey(FieldValue, on_delete=models.SET_NULL,
                                      null=True, blank=True,
                                      related_name="attachments")
    file          = models.FileField(upload_to=UUIDFilenameUploadTo("proposal_files"))
    original_name = models.CharField(max_length=255)
    mime_type     = models.CharField(max_length=100)
    size_bytes    = models.PositiveIntegerField()
    # For IMAGE types, also store dimensions:
    image_width   = models.PositiveSmallIntegerField(null=True, blank=True)
    image_height  = models.PositiveSmallIntegerField(null=True, blank=True)
    # Soft-delete: set when this attachment is superseded by a newer upload.
    deleted_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        # Exactly one active (non-deleted) attachment per FieldValue at any time.
        constraints = [
            UniqueConstraint(
                fields=["field_value"],
                condition=Q(deleted_at__isnull=True),
                name="unique_active_attachment_per_field_value",
            )
        ]
```

`FieldEdit.old_file_attachment` and `new_file_attachment` (replacing the plain name
strings) now carry FKs to `FileAttachment` so the history UI can render the previous
image inline. See §13.

**`StagingFile`** — temporary holding area for uploaded files before save.

```python
class StagingFile(MetaBase):
    uploader       = models.ForeignKey(OpenIDUser, on_delete=models.CASCADE,
                                       related_name="staging_files")
    file           = models.FileField(upload_to=UUIDFilenameUploadTo("staging"))
    original_name  = models.CharField(max_length=255)
    mime_type      = models.CharField(max_length=100)
    size_bytes     = models.PositiveIntegerField()
    expires_at     = models.DateTimeField()  # default: upload time + 24 h

    # Optional scope hint — used for permission checks and pre-validation only.
    intended_field = models.ForeignKey(FieldDefinition, on_delete=models.SET_NULL,
                                       null=True, blank=True)
    intended_node  = models.ForeignKey(UserDefinedModelEntityNode, on_delete=models.SET_NULL,
                                       null=True, blank=True)
```

- A management command `cleanup_staging_files` deletes rows and physical files where
  `expires_at < now()`. Run via cron or Celery beat.
- `StagingFile` rows that are promoted to `FileAttachment` are deleted immediately
  after promotion (within the same transaction as the save).
- The file is moved from `staging/` to `proposal_files/` on promotion; no copy is made.

File storage backend is configured via `settings.PROPOSAL_FILE_STORAGE`
(defaults to `django.core.files.storage.FileSystemStorage`); swap to
`storages.backends.s3boto3.S3Boto3Storage` (django-storages) without model changes.
Both `StagingFile.file` and `FileAttachment.file` use the same storage backend.

---

### 2.4 Edit history

All field changes produced by a single PATCH (or structural node operation) are
grouped under one `EditGroup`. This gives a human-readable timeline where
"saved abstract + photo at 14:32" appears as one entry rather than two.

```python
class EditGroup(MetaBase):
    """All FieldEdits produced by a single save user_defined_model_type."""
    node          = models.ForeignKey(UserDefinedModelEntityNode, on_delete=models.CASCADE,
                                      related_name="edit_groups")
    # Denormalised shortcut to the root user_defined_model_entity so the history page can
    # show changes from nested submodel edits without a recursive query.
    root_proposal = models.ForeignKey(
        "UserDefinedModelEntity", on_delete=models.CASCADE,
        null=True, blank=True, related_name="all_edit_groups"
    )
    saved_by      = models.ForeignKey(OpenIDUser, on_delete=models.SET_NULL,
                                      null=True, blank=True)
    saved_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-saved_at"]


class FieldEdit(MetaBase):
    """One atomic change within an EditGroup."""

    class ChangeKind(models.TextChoices):
        FIELD_VALUE    = "field_value"     # a scalar or file field changed
        NODE_ADDED     = "node_added"      # a SubmodelInstance was created
        NODE_REMOVED   = "node_removed"    # a SubmodelInstance was deleted
        NODE_REORDERED = "node_reordered"  # sort_order on a SubmodelInstance changed

    group         = models.ForeignKey(EditGroup, on_delete=models.CASCADE,
                                      related_name="field_edits")
    change_kind   = models.CharField(max_length=20, choices=ChangeKind,
                                     default=ChangeKind.FIELD_VALUE)

    # For FIELD_VALUE changes:
    field         = models.ForeignKey(FieldDefinition, on_delete=models.SET_NULL,
                                      null=True, blank=True)
    old_value     = models.JSONField(null=True, blank=True)  # null = field did not exist before
    new_value     = models.JSONField(null=True, blank=True)  # null = field was cleared

    # File/image fields: FK to soft-deleted (old) and active (new) FileAttachment rows.
    # Null when the field is not a file/image type or the attachment did not exist.
    old_attachment = models.ForeignKey(
        "FileAttachment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="as_old_in_edits",
    )
    new_attachment = models.ForeignKey(
        "FileAttachment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="as_new_in_edits",
    )

    # For NODE_ADDED / NODE_REMOVED / NODE_REORDERED:
    affected_node = models.ForeignKey(UserDefinedModelEntityNode, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name="+")
```

**Creation rule:** One `EditGroup` is created per PATCH call inside the same
`transaction.atomic()` block. It covers all changes in that call — root-entity
scalar writes, and any submodel creates/updates/deletes triggered by inline
`submodel_list` operations (§6, §12). `FieldEdit`s for submodel field changes
carry `affected_node` pointing to the relevant `SubmodelInstance` so the history
UI can label them. If nothing actually changed the `EditGroup` is not persisted.

**Immutability:** `EditGroup` and `FieldEdit` rows are never updated after creation.
They are deleted only if the parent `UserDefinedModelEntityNode` is deleted.

---

### 2.5 Validation rule model hierarchy

Validation rules are stored as model instances using `django-polymorphic`,
following the same pattern as `SyncBaseTarget`. There are two **separate**
polymorphic roots — one for single-field rules and one for multi-field rules —
because the relationship to `FieldDefinition` differs structurally.

#### Ownership and immutability

Rules are owned by a `ConfigVersion` through their field(s):

- A **`SingleFieldValidationRule`** owns a FK to a `FieldDefinition`, which belongs
  to a `ConfigVersion`. When the version is PUBLISHED or ARCHIVED the rule is
  effectively frozen — the API rejects any mutation and instructs staff to create a
  new DRAFT first.
- A **`MultiFieldValidationRule`** holds a direct FK to `ConfigVersion` (because its
  associated fields are all in the same version, and the version FK is needed for
  cascade-delete and the frozen check without traversing the join table).

**Copy-on-write on publish:** `ConfigVersion.publish()` deep-copies all
`FieldDefinition` rows, all attached rules, and all `FieldDefaultValue` rows (§2.8)
into the new DRAFT. Single-field rule copies get new PKs and point to the new field
copies. Multi-field rule copies get new PKs, a new `config_version` FK, and new
`MultiFieldRuleAssociation` rows pointing to the new field copies. Default copies get
new PKs pointing to the new field copies.

Copying a single-field rule to attach it to a *different* field in the same version
is also supported (the admin provides a "copy to field…" action) — this is the
intended mechanism for reuse.

#### Single-field rule root

```python
class SingleFieldValidationRule(PolymorphicMetaBase):
    """Polymorphic root for all single-field validation rules."""

    field             = models.ForeignKey(
        FieldDefinition, on_delete=models.CASCADE,
        related_name="single_field_rules",
    )
    # Runs on every save (PATCH) when True. When False the rule only runs where
    # it is explicitly referenced by a WorkflowTransition (§2.6) — this is how a
    # submit-only rule avoids firing on every keystroke-level save.
    applies_to_save   = models.BooleanField(default=False)
    # Human-readable label shown in the admin rule list.
    admin_label       = models.CharField(max_length=200, blank=True)

    def validate(self, value) -> list[str]:
        """Return a (possibly empty) list of error strings for *value*."""
        raise NotImplementedError

    def clean(self):
        """Reject incompatible (rule subclass, field data_type) combinations."""
        # Each concrete subclass declares APPLICABLE_TYPES: frozenset[str].
        # Base implementation checks membership and raises ValidationError if violated.
        applicable = getattr(self.__class__, "APPLICABLE_TYPES", None)
        if applicable and self.field_id and self.field.data_type not in applicable:
            raise ValidationError(
                f"{self.__class__.__name__} cannot be applied to a "
                f"{self.field.data_type} field."
            )

    def clone_to(self, target_field: FieldDefinition) -> "SingleFieldValidationRule":
        """Return a new, unsaved copy of this rule bound to *target_field*."""
        obj = self.get_real_instance()
        obj.pk = None
        obj.field = target_field
        return obj
```

#### Single-field concrete subclasses

| Class | Extra fields | Applicable `data_type`s |
|---|---|---|
| `RequiredRule` | *(none)* | all |
| `MinLengthRule` | `min_length: PositiveIntegerField` | `text_*` |
| `MaxLengthRule` | `max_length: PositiveIntegerField` | `text_*` |
| `RegexRule` | `pattern: CharField(500)`, `failure_message: CharField(200)` | `text_*` |
| `MinValueRule` | `min_value: DecimalField(max_digits=20, decimal_places=6)` | `integer`, `float` |
| `MaxValueRule` | `max_value: DecimalField(max_digits=20, decimal_places=6)` | `integer`, `float` |
| `MinItemsRule` | `min_items: PositiveSmallIntegerField` | `submodel_list`, `select_multi`, `user_select_multi`, `group_select_multi` |
| `MaxItemsRule` | `max_items: PositiveSmallIntegerField` | same as above |
| `MaxFileSizeRule` | `max_bytes: PositiveIntegerField` | `file`, `image` |
| `AllowedMimeTypesRule` | *(see below)* | `file`, `image` |

`AllowedMimeTypesRule` stores its list of permitted MIME types as child rows rather
than a JSON field:

```python
class AllowedMimeTypesRule(SingleFieldValidationRule):
    pass  # MIME type list stored in AllowedMimeTypeEntry rows

class AllowedMimeTypeEntry(MetaBase):
    rule      = models.ForeignKey(AllowedMimeTypesRule, on_delete=models.CASCADE,
                                  related_name="allowed_types")
    mime_type = models.CharField(max_length=100)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["rule", "mime_type"],
                             name="unique_mime_per_rule")
        ]
```

#### Multi-field rule root

```python
class MultiFieldValidationRule(PolymorphicMetaBase):
    """Polymorphic root for cross-field validation rules."""

    # Owned by a ConfigVersion — needed for cascade-delete and frozen check.
    config_version    = models.ForeignKey(
        ConfigVersion, on_delete=models.CASCADE,
        related_name="multi_field_rules",
    )
    # See SingleFieldValidationRule.applies_to_save above for semantics.
    applies_to_save   = models.BooleanField(default=False)
    admin_label       = models.CharField(max_length=200, blank=True)

    # All fields must belong to config_version — enforced at the application level.
    fields            = models.ManyToManyField(
        FieldDefinition,
        through="MultiFieldRuleAssociation",
        related_name="multi_field_rules",
    )

    def validate(self, field_values: dict[str, object]) -> str | None:
        """Return an error string if the cross-field constraint is violated,
        or None if it passes. *field_values* maps slug → current value."""
        raise NotImplementedError
```

```python
class MultiFieldRuleAssociation(MetaBase):
    rule  = models.ForeignKey(MultiFieldValidationRule, on_delete=models.CASCADE,
                               related_name="associations")
    field = models.ForeignKey(FieldDefinition, on_delete=models.CASCADE,
                               related_name="multi_field_rule_associations")

    class Meta:
        constraints = [
            UniqueConstraint(fields=["rule", "field"],
                             name="unique_field_per_multi_rule")
        ]
```

#### Multi-field concrete subclasses

| Class | Semantics |
|---|---|
| `AtLeastOneRequiredRule` | At least one of the associated fields must be non-null / non-empty |
| `ExactlyOneRequiredRule` | Exactly one of the associated fields must be non-empty |
| `MutualExclusionRule` | At most one of the associated fields may be non-empty |

Multi-field errors are reported on all associated fields so the frontend can
highlight each relevant input.

#### Rule hierarchy diagram

```
SingleFieldValidationRule (PolymorphicMetaBase)
   field ──FK──► FieldDefinition
   │
   ├── RequiredRule
   ├── MinLengthRule          (min_length)
   ├── MaxLengthRule          (max_length)
   ├── RegexRule              (pattern, failure_message)
   ├── MinValueRule           (min_value)
   ├── MaxValueRule           (max_value)
   ├── MinItemsRule           (min_items)
   ├── MaxItemsRule           (max_items)
   ├── MaxFileSizeRule        (max_bytes)
   └── AllowedMimeTypesRule   ──1:N──► AllowedMimeTypeEntry

MultiFieldValidationRule (PolymorphicMetaBase)
   config_version ──FK──► ConfigVersion
   fields ──M2M (through MultiFieldRuleAssociation)──► FieldDefinition
   │
   ├── AtLeastOneRequiredRule
   ├── ExactlyOneRequiredRule
   └── MutualExclusionRule
```

---

### 2.6 Configurable workflow

Every `UserDefinedModelEntityNode` participates in a workflow defined by the `ConfigVersion` it
belongs to. A workflow governs which states a node can be in, which transitions are
allowed, and what must happen at each transition. Submodels and user_defined_model_entities may have
entirely different workflows because they have separate `ConfigVersion`s (via
`submodel_config`).

#### Model hierarchy

```
WorkflowDefinition  ──1:N──  WorkflowState
                    ──1:N──  WorkflowTransition
```

```python
class WorkflowDefinition(HistoricalMetaBase):
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # Assigned to a ConfigVersion (one version → one workflow, or null = no workflow).
    # Set as FK on ConfigVersion: config_version.workflow = FK(WorkflowDefinition)
```

```python
class WorkflowState(HistoricalMetaBase):
    workflow    = models.ForeignKey(WorkflowDefinition, on_delete=models.CASCADE,
                                    related_name="states")
    name        = models.CharField(max_length=100)   # e.g. "draft", "submitted"
    # label lives exclusively in WorkflowStateTranslation rows (see §2.7).
    is_initial  = models.BooleanField(default=False)  # assigned to new nodes on creation
    # Nodes in this state can have their field values edited (if False, PATCH is blocked).
    allows_edit = models.BooleanField(default=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["workflow"], condition=Q(is_initial=True),
                             name="one_initial_state_per_workflow"),
            UniqueConstraint(fields=["workflow", "name"],
                             name="unique_state_name_per_workflow"),
        ]
```

```python
class WorkflowTransition(HistoricalMetaBase):
    workflow        = models.ForeignKey(WorkflowDefinition, on_delete=models.CASCADE,
                                        related_name="transitions")
    name            = models.CharField(max_length=100)   # e.g. "submit", "accept"
    # label lives exclusively in WorkflowTransitionTranslation rows (see §2.7).
    # Null from_state = transition is valid from any state.
    from_state      = models.ForeignKey(WorkflowState, on_delete=models.CASCADE,
                                        null=True, blank=True,
                                        related_name="outgoing_transitions")
    to_state        = models.ForeignKey(WorkflowState, on_delete=models.CASCADE,
                                        related_name="incoming_transitions")
    # Django permission codename that the triggering user must hold.
    # Null = any authenticated user with user_defined_model_entity access may trigger it.
    permission_codename = models.CharField(max_length=200, blank=True)
    # Optional Rego rule-path override for authorising this transition (§16).
    # When blank, §15.1 step 4 evaluates the default `data.user_defined_model_entities.allow` rule
    # (action="transition", transition=<name>), which can branch on the name. Set
    # this only to point a specific transition at a different rule.
    policy_rule         = models.CharField(max_length=300, blank=True)
```

#### Transition validators

**This is where strict "submit-time" validation lives.** There is no separate
submit-rule flag on the rule models; instead the strict checks that must hold before
a user_defined_model_entity can be submitted (or accepted, etc.) are attached to the relevant
`WorkflowTransition` — typically the `submit` transition. A rule used only at submit
sets `applies_to_save=False` so it does not fire on every PATCH, and is referenced
from the transition via a `TransitionValidatorAssignment`.

Transition validators reuse the same `SingleFieldValidationRule` /
`MultiFieldValidationRule` polymorphic hierarchy and the same evaluation engine as
`validate_for_save()` (§4). A `TransitionValidatorAssignment` attaches a rule to a
transition; the rule is evaluated as part of the transition execution (§15):

```python
class TransitionValidatorAssignment(MetaBase):
    transition = models.ForeignKey(WorkflowTransition, on_delete=models.CASCADE,
                                   related_name="validator_assignments")
    # Exactly one of these two FKs is non-null:
    single_field_rule = models.ForeignKey(
        SingleFieldValidationRule, on_delete=models.CASCADE,
        null=True, blank=True, related_name="+",
    )
    multi_field_rule  = models.ForeignKey(
        MultiFieldValidationRule, on_delete=models.CASCADE,
        null=True, blank=True, related_name="+",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
```

#### Mandatory field updates

Fields that must be non-empty (or set to a specific value) for the transition to
be accepted:

```python
class TransitionMandatoryField(MetaBase):
    transition      = models.ForeignKey(WorkflowTransition, on_delete=models.CASCADE,
                                        related_name="mandatory_fields")
    field           = models.ForeignKey(FieldDefinition, on_delete=models.CASCADE,
                                        related_name="+")
    # Null = field must merely be non-empty. Non-null = field must equal this value.
    required_value  = models.JSONField(null=True, blank=True)
    sort_order      = models.PositiveSmallIntegerField(default=0)
```

**Canonical way to express "required at submit"** — to avoid two overlapping
mechanisms, use `TransitionMandatoryField` for plain required-ness (and fixed-value
requirements), and `TransitionValidatorAssignment` for everything else
(`MinLengthRule`, `RegexRule`, multi-field rules, …). The config UI should present
required-ness only through `TransitionMandatoryField`.

#### Transition actions (pre and post)

Actions are a polymorphic hierarchy of things to execute before or after a
transition. Pre-actions run before validation; post-actions run after the state
change is saved.

```python
class TransitionAction(PolymorphicMetaBase):
    class Phase(models.TextChoices):
        PRE  = "pre"   # before field validation and saving
        POST = "post"  # after state change is saved

    transition = models.ForeignKey(WorkflowTransition, on_delete=models.CASCADE,
                                   related_name="actions")
    phase      = models.CharField(max_length=4, choices=Phase)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def execute(self, node: "UserDefinedModelEntityNode", triggered_by) -> None:
        raise NotImplementedError
```

Initial concrete action subclasses:

| Class | Phase | Description |
|---|---|---|
| `SendNotificationAction` | `post` | Send an email/notification to configured recipients |
| `SetFieldValueAction` | `pre` | Forcibly set a field to a fixed value before the transition saves (e.g. clear `internal_notes` on submission) |
| `TriggerChildTransitionAction` | `post` | Fire a named transition on all child `SubmodelInstance` nodes |

#### Diagram

```
WorkflowDefinition ──1:N── WorkflowState
                   ──1:N── WorkflowTransition
                                │
                    ┌───────────┼────────────────┐
                    │           │                │
          TransitionValidatorAssignment  TransitionMandatoryField
                    │
          TransitionAction (PolymorphicMetaBase)
                    │
          ├── SendNotificationAction
          ├── SetFieldValueAction
          └── TriggerChildTransitionAction
```

---

### 2.7 Localisation

#### Supported languages per FieldConfig

Languages are defined once at the `FieldConfig` level and inherited by all its
`ConfigVersion`s. They determine which language tabs the frontend shows on
localized fields.

```python
class ConfigLanguage(MetaBase):
    config      = models.ForeignKey(FieldConfig, on_delete=models.CASCADE,
                                    related_name="languages")
    code        = models.CharField(max_length=10)   # BCP-47, e.g. "en", "de"
    label       = models.CharField(max_length=100)  # display name, e.g. "Deutsch"
    is_default  = models.BooleanField(default=False)
    sort_order  = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["config", "code"],
                             name="unique_language_per_config"),
            UniqueConstraint(fields=["config"],
                             condition=Q(is_default=True),
                             name="one_default_language_per_config"),
        ]
```

The default language is used as the fallback when no translation exists for a
requested language, and as the display language in contexts that show only one value.

#### Translatable labels

`FieldDefinition` has no direct `label` or `help_text` columns. Labels and help text
live exclusively in `FieldDefinitionTranslation` rows. The translation for the config's
default language acts as the fallback when no translation exists for the requested language:

```python
class FieldDefinitionTranslation(MetaBase):
    field     = models.ForeignKey(FieldDefinition, on_delete=models.CASCADE,
                                  related_name="translations")
    language  = models.CharField(max_length=10)   # must be in config.languages
    label     = models.CharField(max_length=200)
    help_text = models.TextField(blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["field", "language"],
                             name="unique_label_translation_per_field_language")
        ]
```

The same pattern applies to `WorkflowState` and `WorkflowTransition`. Neither
model carries a direct `label` column; labels live exclusively in translation rows:

```python
class WorkflowStateTranslation(MetaBase):
    state     = models.ForeignKey(WorkflowState, on_delete=models.CASCADE,
                                  related_name="translations")
    language  = models.CharField(max_length=10)   # must be in config.languages
    label     = models.CharField(max_length=200)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["state", "language"],
                             name="unique_state_translation_per_language")
        ]


class WorkflowTransitionTranslation(MetaBase):
    transition = models.ForeignKey(WorkflowTransition, on_delete=models.CASCADE,
                                   related_name="translations")
    language   = models.CharField(max_length=10)
    label      = models.CharField(max_length=200)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["transition", "language"],
                             name="unique_transition_translation_per_language")
        ]
```

The translation for the `FieldConfig`'s default language serves as the fallback
when no translation exists for the requested language.

#### Localized field values

When `FieldDefinition.is_localized = True`, the field stores one `FieldValue` row
per language using the `language` column added in §2.3. For non-localized fields
`language = ""`. All field types — including `image` and `file` — support
`is_localized`; a localized image field stores a separate `FileAttachment` chain
per language.

The same `FieldDefinition` and all its attached `SingleFieldValidationRule` /
`MultiFieldValidationRule` instances apply to **every language's value
independently**. There are no separate rule sets per language.

#### Per-language required-ness

A new single-field rule subclass expresses "this field must be non-empty in a
specific language":

```python
class RequiredInLanguageRule(SingleFieldValidationRule):
    """Field must be non-empty for `language`; other languages are not checked."""
    APPLICABLE_TYPES = frozenset(DataType) - {
        DataType.SUBMODEL_SELECT, DataType.SUBMODEL_LIST
    }
    language = models.CharField(max_length=10)
```

This is the recommended way to require English and German independently while
leaving other languages optional. The base `RequiredRule` on a localized field
means "every configured language must have a non-empty value" — it runs once per
language row found.

#### PATCH payload for localized fields

For localized fields the value in `changed_fields` is a `{language_code: value}`
dict. Languages absent from the dict are left untouched. To clear one language's
value pass `null` for that key; to clear all languages at once pass `null` as the
top-level value.

```jsonc
{
  "changed_fields": {
    // non-localized field — same format as always
    "duration_days": 3,

    // localized text field — supply only the changed languages
    "abstract": {
      "en": "English abstract text",
      "de": "Deutsches Abstract"
    },

    // clear one language value
    "abstract": { "fr": null },

    // clear all language values at once
    "abstract": null
  }
}
```

#### Localized fields and locking

No special handling is needed. The root-user_defined_model_entity lock (§14.2) serialises the whole
tree, so a PATCH that touches only some languages of a localized field still sees a
consistent snapshot of **all** that field's language rows during validation — which
is what `RequiredInLanguageRule` relies on.

#### Config schema representation

The config JSON schema (§6) includes localized labels and the list of supported
languages:

```jsonc
{
  "version_id": 42,
  "languages": [
    { "code": "en", "label": "English", "is_default": true },
    { "code": "de", "label": "Deutsch",  "is_default": false }
  ],
  "fields": [
    {
      "id": 7,
      "slug": "abstract",
      "is_localized": true,
      "label": { "en": "Abstract", "de": "Zusammenfassung" },
      "help_text": { "en": "...", "de": "..." },
      "data_type": "text_markdown",
      ...
    }
  ]
}
```

---

### 2.8 Default values

A `FieldDefinition` may carry an admin-chosen default. When a new `UserDefinedModelEntityNode`
is created the defaults are materialised into real `FieldValue` rows, so every
user_defined_model_entity starts from a complete, admin-approved combination of values rather than
an empty form.

Defaults are part of the config and are therefore **versioned** with it: a default
belongs to a `FieldDefinition` in a specific `ConfigVersion`, is deep-copied on
publish (§3), and converts under the §2.1 datatype-change rules like any stored
value. A default is stored in a `FieldDefaultValue` row that reuses the same typed
columns as `FieldValue` via the shared `TypedValue` base (§2.3), so defaults are
type-correct and per-language out of the box.

```python
class FieldDefaultValue(TypedValue, MetaBase):
    field    = models.ForeignKey(FieldDefinition, on_delete=models.CASCADE,
                                 related_name="defaults")
    # Per-language defaults for localized fields; "" for non-localized (mirrors
    # FieldValue.language). A localized field may define a default per language.
    language = models.CharField(max_length=10, default="")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["field", "language"],
                name="unique_default_per_field_language",
            )
        ]

    def clean(self):
        self._clean_typed_value(self.field)
```

**Which types support a default**

- All scalar types (`text_*`, `integer`, `float`, `boolean`, `date`, `time`,
  `datetime`), the select types, and the user/group reference types support a
  default.
- `image` / `file`: **no default** — there is no sensible config-owned file to
  pre-fill. A `FieldDefaultValue` for these types is rejected in `clean()`.
- `submodel_select`: not supported — a default would have to point at a concrete
  instance that does not exist until a user_defined_model_entity is created.
- `submodel_list`: a field with no default starts with zero children. Optional
  default children are out of scope for the first cut (a `min_items` rule plus a
  publish-time check is the simpler way to guarantee at least one child); revisit
  only if a concrete need appears.

**Materialisation on create**

`POST /api/udm/entities/` (root creation) and `op:"create"` submodel operations in a PATCH build the new node's
`FieldValue` rows by copying every `FieldDefaultValue` of the node's
`ConfigVersion` (one row per language for localized fields). Fields without a
default are simply left unset. Materialisation runs inside the create transaction;
the resulting node is then saved through the normal write path so `FieldValue.clean()`
runs on each materialised value.

**Guaranteeing a valid starting combination**

So an admin cannot publish defaults that contradict the field rules, `ConfigVersion.publish()`
(§3) builds a transient in-memory node from the defaults and runs **save-context**
validation on it (`validate_for_save`, i.e. all `applies_to_save` rules, including
multi-field rules such as `MutualExclusionRule` / `ExactlyOneRequiredRule`).
Publishing is blocked with field-keyed errors if the default combination is invalid.

Save-context — not submit-context — is intentional: a freshly created draft must be
*saveable*, but it is legitimately allowed to be incomplete for *submission* (e.g. a
required-at-submit field with no default stays empty until the user fills it).

---

## 3. Config Versioning Lifecycle

```
         ┌──────────────────────────────────────────────────────┐
         │              Staff creates FieldConfig               │
         │          (independent of any specific user_defined_model_type)           │
         └───────────────────────────┬──────────────────────────┘
                                     ▼
                              ┌─────DRAFT──────┐
                              │ editable freely │
                              │ field defs can  │
                              │ be added/removed│
                              └────────┬───────┘
                                       │  staff clicks "Publish"
                                       ▼
                             ┌────PUBLISHED────┐   new draft created automatically
                             │  immutable      │──►  (copy of published fields)
                             │  user_defined_model_entities bind │
                             │  to this version│
                             └────────┬───────┘
                                       │  next publish
                                       ▼
                             ┌────ARCHIVED─────┐
                             │  read-only      │
                             │  user_defined_model_entities still│
                             │  reference it   │
                             └─────────────────┘
```

- Publishing atomically archives the current PUBLISHED version.
- Publishing first validates that the field defaults form a valid save-time
  combination and is blocked with field errors otherwise (§2.8).
- The new DRAFT is an automatic deep-copy of the just-published version
  (field definitions, rules, workflow, and field defaults).
- UserDefinedModelEntities created before a republish continue to reference their original
  `ConfigVersion`; they are **not** silently upgraded.
- A user_defined_model_entity can be voluntarily upgraded to the new config version via the
  migration flow (see §5).
- Because a `FieldConfig` may be shared by N user_defined_model_types, publishing a new version
  surfaces a **pending-migration count** in the staff UI: the number of user_defined_model_entities
  across all user_defined_model_types using this `FieldConfig` that are still on a previous version.
  Staff can then run a bulk migration from that view (see §5.5).

---

## 4. Validation Rules

Rules are stored as model instances in the polymorphic hierarchy described in §2.5.
There are two places a rule can run:

1. **Save time** — every rule with `applies_to_save=True` runs on each PATCH / admin
   save of the node it belongs to. Save-time validation is *permissive*: it never
   requires a field to be filled (use a transition for that), it only rejects values
   that are actively wrong (bad type, too long, regex mismatch, a violated mutual
   exclusion, …).
2. **Workflow transitions** — strict checks (the old "submit rules") are attached to
   a `WorkflowTransition` via `TransitionValidatorAssignment` / `TransitionMandatoryField`
   (§2.6) and run only when that transition fires (§15). Submission is just the
   `submit` transition. A submit-only rule sets `applies_to_save=False` so it does not
   fire on every save.

There is no `validate_for_submit()` and no `applies_to_submit` flag.

### Validation entry points on `UserDefinedModelEntityNode`

| Method | Trigger | Rules fetched |
|---|---|---|
| `validate_for_save()` | API PATCH, Django admin save | rules where `applies_to_save=True` |
| transition engine (§15) | `POST /transition` (incl. `submit`) | the transition's `TransitionValidatorAssignment` rules + `TransitionMandatoryField`s, **plus** each node's save rules re-run across the subtree |
| `FieldValue.clean()` | Always, on every write | data-type correctness only (no rule models) |

The single-field / multi-field evaluation loop below is shared: `validate_for_save()`
passes its save-rule queryset, and the transition engine passes the transition's
assigned rules. Both build the same `errors` dict.

### Shared rule-evaluation loop

```python
def _evaluate_rules(self, single_rules, multi_rules):
    """single_rules / multi_rules are already-filtered querysets (save rules,
    or a transition's assigned rules). Returns a field-keyed error dict."""
    errors: dict[str, list[str]] = defaultdict(list)

    # Single-field rules — one DB query with select_related
    for rule in single_rules.select_related("field"):
        if rule.field.is_localized:
            # Run the rule independently for each stored language value.
            for fv in self.field_values.filter(field=rule.field):
                for msg in rule.get_real_instance().validate(fv.get_value()):
                    errors[f"{rule.field.slug}[{fv.language}]"].append(msg)
        else:
            value = self.get_field_value(rule.field.slug)
            for msg in rule.get_real_instance().validate(value):
                errors[rule.field.slug].append(msg)

    # Multi-field rules — one DB query with prefetch
    for rule in multi_rules.prefetch_related("associations__field"):
        # Multi-field rules receive non-localized values only; localized fields
        # are passed as {language: value} dicts so the rule can inspect them.
        field_values = {
            a.field.slug: (
                {fv.language: fv.get_value()
                 for fv in self.field_values.filter(field=a.field)}
                if a.field.is_localized
                else self.get_field_value(a.field.slug)
            )
            for a in rule.associations.all()
        }
        msg = rule.get_real_instance().validate(field_values)
        if msg:
            for slug in field_values:
                errors[slug].append(msg)

    return errors


def validate_for_save(self):
    single = SingleFieldValidationRule.objects.filter(
        field__version=self.config_version, applies_to_save=True)
    multi = MultiFieldValidationRule.objects.filter(
        config_version=self.config_version, applies_to_save=True)
    errors = self._evaluate_rules(single, multi)
    if errors:
        raise ValidationError(dict(errors))
```

### Strict (submit / transition) validation across the subtree

A transition does not have its own copy of the field rules — it carries only the
strict extras. To produce today's "submit checks the whole user_defined_model_entity" behaviour while
respecting that each node (user_defined_model_entity or submodel) lives in its **own** `ConfigVersion`
(and rules may not cross versions, §2.5), the transition engine validates the entire
subtree, **validation-only**, in one transaction (§15):

- For **every** node in the subtree (root + all descendants), re-run that node's own
  save rules (`applies_to_save=True`) via `_evaluate_rules`. This is the *save-rule
  floor* — it guarantees a workflow-less submodel (e.g. a migrated `Speaker`) is still
  checked against its own constraints at submit.
- **Additionally**, for any node whose `ConfigVersion` has a workflow with a transition
  of the same name (e.g. `submit`), run that transition's
  `TransitionValidatorAssignment` rules + `TransitionMandatoryField`s.
- No descendant changes state during this — only the node the transition was invoked
  on transitions. Any error anywhere aborts the whole transition (no partial submit).

Cascading a child's *state* (not just validating it) is a separate, explicit concern
handled by `TriggerChildTransitionAction` (§2.6), never an implicit side effect of
the parent transition.

### Data-type enforcement

`FieldValue.clean()` always verifies that the value is structurally valid for
`field.data_type` (e.g., an `INTEGER` field rejects the string `"hello"`) and that
the value lives in the one typed column mapped to that `data_type` (§2.3), with all
other value columns NULL. This check runs unconditionally — it is not a
`ValidationRule` instance and cannot be disabled. The rule-based checks (required,
min/max, regex, …) are layered on top — at save time (`applies_to_save`) and/or at a
workflow transition (§2.6, §15).

---

## 5. Migration System

### 5.1 When migration applies

| # | Trigger | Scope | Flow |
|---|---|---|---|
| 1 | **Cross-user_defined_model_type move** | one user_defined_model_entity | §5.3 single-user_defined_model_entity flow |
| 2 | **Config version upgrade** | one user_defined_model_entity | §5.3 single-user_defined_model_entity flow |
| 3 | **Config republish on shared config** | all user_defined_model_entities on any previous version of that `FieldConfig`, across all user_defined_model_types | §5.5 bulk flow |
| 4 | **UserDefinedModelType config switch** | all user_defined_model_entities under the user_defined_model_type being switched | §5.5 bulk flow |

Cases 1–2 use the existing single-user_defined_model_entity mapping mechanism. Cases 3–4 use
the `BulkMigrationPlan` mechanism which defines one field mapping and applies it
to many user_defined_model_entities at once.

All four cases share the same underlying per-user_defined_model_entity execution logic; the bulk
flow simply drives it in a loop.

### 5.2 Field mapping model

```python
class UserDefinedModelEntityMigration(HistoricalMetaBase):
    class Action(models.TextChoices):
        MAP      = "map"       # source field → target field
        DISCARD  = "discard"   # drop the value
        OVERFLOW = "overflow"  # keep in UserDefinedModelEntityNode.overflow_data

    user_defined_model_entity        = models.ForeignKey(UserDefinedModelEntity, on_delete=models.CASCADE,
                                        related_name="migrations")
    source_version  = models.ForeignKey(ConfigVersion, on_delete=models.PROTECT,
                                        related_name="+")
    # For cross-UserDefinedModelType moves, target_user_defined_model_type differs from user_defined_model_entity.user_defined_model_type.
    # For in-place version upgrades or config switches, target_user_defined_model_type == user_defined_model_entity.user_defined_model_type.
    target_user_defined_model_type     = models.ForeignKey(UserDefinedModelType, on_delete=models.PROTECT,
                                        related_name="received_user_defined_model_entity_migrations")
    target_version  = models.ForeignKey(ConfigVersion, on_delete=models.PROTECT,
                                        related_name="+")
    executed_at     = models.DateTimeField(null=True, blank=True)
    executed_by     = models.ForeignKey(OpenIDUser, on_delete=models.SET_NULL,
                                        null=True, blank=True)
    # Set when this migration was created by a BulkMigrationPlan execution.
    bulk_plan       = models.ForeignKey(
        "BulkMigrationPlan", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="proposal_migrations",
    )

class MigrationFieldMapping(MetaBase):
    migration      = models.ForeignKey(UserDefinedModelEntityMigration, on_delete=models.CASCADE,
                                       related_name="field_mappings")
    source_field   = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                       related_name="+")
    action         = models.CharField(max_length=10, choices=UserDefinedModelEntityMigration.Action)
    target_field   = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                       null=True, blank=True, related_name="+")
```

### 5.3 Migration flow

```
1. Staff/user requests migration (target user_defined_model_type selected)
2. GET /api/udm/entities/{id}/migration-preview/?target_user_defined_model_type={cid}
   → Returns auto-suggested mapping (matched by slug first, then label similarity)
   → Each source field has: suggested_action, suggested_target, conflict_reason
3. User reviews and confirms/overrides each field decision
4. POST /api/udm/entities/{id}/migrate/  { migration_id: ..., confirmed: true }
5. Server executes atomically:
   a. Create new UserDefinedModelEntity under target user_defined_model_type / version
   b. For MAP entries: copy FieldValue (run type-compat check first)
   c. For OVERFLOW entries: write to new_proposal.overflow_data
   d. For DISCARD entries: skip
   e. Recursively migrate SubmodelInstance children
   f. Mark old user_defined_model_entity status as MIGRATED (new Status choice)
   g. Set UserDefinedModelEntityMigration.executed_at
```

### 5.4 Type-compatibility during MAP

If source and target fields have different `data_type`, the migration executor
checks the permitted-conversion table (§2.1). Incompatible pairs are rejected
at the preview step with `conflict_reason` set; the user must choose DISCARD or
OVERFLOW instead.

---

### 5.5 Bulk migration plan

Used for trigger cases 3 (shared config republish) and 4 (user_defined_model_type config switch).
Staff configures one field mapping; the system applies it to every affected
user_defined_model_entity, each of which gets its own `UserDefinedModelEntityMigration` record for audit.

**Models**

```python
class BulkMigrationPlan(HistoricalMetaBase):
    class Status(models.TextChoices):
        DRAFT    = "draft"    # field mappings being configured
        RUNNING  = "running"  # execution in progress (locked)
        DONE     = "done"     # all user_defined_model_entities migrated
        PARTIAL  = "partial"  # completed with some per-user_defined_model_entity failures

    source_version   = models.ForeignKey(ConfigVersion, on_delete=models.PROTECT,
                                         related_name="+")
    target_version   = models.ForeignKey(ConfigVersion, on_delete=models.PROTECT,
                                         related_name="+")
    # Non-null for trigger 4 (user_defined_model_type config switch): restricts execution to user_defined_model_entities
    # under this user_defined_model_type only. Null for trigger 3: applies across all user_defined_model_types.
    user_defined_model_type_filter      = models.ForeignKey(UserDefinedModelType, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name="+")
    status           = models.CharField(max_length=10, choices=Status,
                                        default=Status.DRAFT)
    created_by       = models.ForeignKey(OpenIDUser, on_delete=models.SET_NULL,
                                         null=True, blank=True)
    executed_at      = models.DateTimeField(null=True, blank=True)
    total_proposals  = models.PositiveIntegerField(default=0)
    done_proposals   = models.PositiveIntegerField(default=0)
    failed_proposals = models.PositiveIntegerField(default=0)


class BulkMigrationFieldMapping(MetaBase):
    plan         = models.ForeignKey(BulkMigrationPlan, on_delete=models.CASCADE,
                                     related_name="field_mappings")
    source_field = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                     related_name="+")
    action       = models.CharField(max_length=10, choices=UserDefinedModelEntityMigration.Action)
    target_field = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                     null=True, blank=True, related_name="+")
```

**Trigger 3 — Config republish**

When `ConfigVersion.publish()` runs on a `FieldConfig` used by one or more user_defined_model_types:
1. Query all distinct `config_version` values among user_defined_model_entities whose user_defined_model_type references
   this `FieldConfig` and whose `config_version` is not the new published version.
2. For each distinct old version, automatically create a `BulkMigrationPlan`
   (`source_version=old, target_version=new, user_defined_model_type_filter=None`).
3. Surface the plans in the staff UI as "N user_defined_model_entities need migration" badges on the
   `FieldConfig` detail page.

**Trigger 4 — UserDefinedModelType config switch**

When `UserDefinedModelType.field_config` is changed (via `PATCH /api/udm/types/{id}/` with a new
`field_config_id`):
1. The API refuses to commit the change while any existing user_defined_model_entities under the user_defined_model_type
   are on a different `FieldConfig` without a confirmed `BulkMigrationPlan`.
2. Staff first previews the mapping: `POST /api/udm/bulk-migrations/preview/` with
   `source_version`, `target_version`, and `user_defined_model_type_filter`.
3. Staff creates the plan with confirmed field mappings.
4. Staff executes the plan; only then can the `UserDefinedModelType.field_config` be changed.
5. The field_config change and the plan execution are wrapped in the same
   `transaction.atomic()` so a failed execution rolls back the assignment.

If a user_defined_model_type currently has no user_defined_model_entities, step 1–4 are skipped and the assignment
takes effect immediately.

**Execution — always via Celery**

`POST /api/udm/bulk-migrations/{id}/execute/` enqueues a Celery task and returns
`HTTP 202 Accepted` immediately. Progress is polled via
`GET /api/udm/bulk-migrations/{id}/`. The task:

```
celery task: execute_bulk_migration(plan_id)
  1. Lock the plan row (SELECT FOR UPDATE NOWAIT).
     → If already RUNNING, raise and discard (idempotent).
  2. Set status = RUNNING, total_proposals = count of affected user_defined_model_entities.
  3. For each affected UserDefinedModelEntity (one transaction per user_defined_model_entity):
       a. Create UserDefinedModelEntityMigration(bulk_plan=plan, ...).
       b. Copy BulkMigrationFieldMapping → MigrationFieldMapping.
       c. Execute single-user_defined_model_entity migration (§5.3 steps 5a–5g),
          with full user_defined_model_entity locking per §14.3.
       d. Atomically increment done_proposals or failed_proposals.
  4. Set status = DONE (all succeeded) or PARTIAL (any failed).
     PARTIAL leaves the user_defined_model_type's field_config unchanged (see §5.5 trigger 4).
```

The preview endpoint (`GET /api/udm/bulk-migrations/{id}/preview/`) returns the
same per-field mapping format as the single-user_defined_model_entity preview, plus an
`affected_proposal_count` field and a breakdown by user_defined_model_type (when `user_defined_model_type_filter` is null).

**Stale-user_defined_model_entity count query** (used for badges in the staff UI)

```python
# UserDefinedModelEntities whose config version does not belong to their user_defined_model_type's current FieldConfig.
stale = UserDefinedModelEntity.objects.exclude(
    config_version__config=models.F("call__field_config")
).select_related("call__field_config", "config_version__config")
```

---

## 6. API Endpoints

All endpoints require authentication. Permission logic mirrors the existing
`UserDefinedModelEntity.has_object_permission` pattern, moved to `UserDefinedModelEntityNode`.

### FieldConfig (staff-only write)

`FieldConfig` objects are independent resources — not nested under a user_defined_model_type.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/udm/configs/` | List all FieldConfigs (staff) |
| `POST` | `/api/udm/configs/` | Create a new FieldConfig |
| `GET` | `/api/udm/configs/{cid}/` | Retrieve metadata (name, description, user_defined_model_types using it, stale-user_defined_model_entity count) |
| `PATCH` | `/api/udm/configs/{cid}/` | Update name / description |
| `DELETE` | `/api/udm/configs/{cid}/` | Delete only if no user_defined_model_types reference it and no user_defined_model_entities exist |
| `GET` | `/api/udm/configs/{cid}/versions/` | List all ConfigVersions |
| `GET` | `/api/udm/configs/{cid}/versions/published/` | Active published version as JSON schema |
| `GET` | `/api/udm/configs/{cid}/versions/draft/` | Current draft (staff) |
| `PUT` | `/api/udm/configs/{cid}/versions/draft/` | Replace draft field definitions |
| `POST` | `/api/udm/configs/{cid}/versions/draft/publish/` | Publish draft → auto-creates BulkMigrationPlans for stale user_defined_model_entities |

### UserDefinedModelType ↔ FieldConfig assignment

| Method | Path | Description |
|---|---|---|
| `PATCH` | `/api/udm/types/{id}/` | Change `field_config_id`; blocked if stale user_defined_model_entities exist without a confirmed BulkMigrationPlan |

### Convenience read aliases (user_defined_model_type-scoped, for the user_defined_model_entity form frontend)

These are read-only shortcuts; all writes go to `/api/udm/configs/`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/udm/types/{id}/config/` | Active published config for this user_defined_model_type (same shape as `/api/udm/configs/{cid}/versions/published/`) |

### Config JSON schema shape

```jsonc
{
  "version_id": 42,
  "status": "published",
  "fields": [
    {
      "id": 7,
      "slug": "abstract",
      "label": "Abstract",
      "data_type": "text_markdown",
      "type_config": { "max_length": 500 },
      "default": "Describe your session…",
      "save_rules": { "max_length": 500 },
      "sort_order": 1
    },
    {
      "id": 8,
      "slug": "speakers",
      "label": "Speakers",
      "data_type": "submodel_list",
      "submodel_config": {
        "version_id": 12,
        "fields": [ ... ]
      },
      "save_rules": {},
      "sort_order": 2
    }
  ],
  "workflow": {
    "initial_state": "draft",
    "states": [ { "name": "draft", ... }, { "name": "submitted", ... } ],
    "transitions": [
      {
        "name": "submit",
        "from_state": "draft",
        "to_state": "submitted",
        "permission_codename": "submit_proposal",
        "mandatory_fields": [ { "field_slug": "abstract" } ],
        "validators": [
          { "field_slug": "abstract", "rule": { "min_length": 50 } },
          { "field_slug": "speakers", "rule": { "min_items": 1 } }
        ]
      }
    ]
  }
}
```

Per-field `save_rules` carry only the rules with `applies_to_save=True`. The strict
checks that were previously `submit_rules` now live under `workflow.transitions[]`
as `mandatory_fields` (required-ness) and `validators` (everything else). A config
with no workflow has no `workflow` key and therefore only save-time validation.

The `default` key (§2.8) is omitted when the field has no default. For a localized
field it is a `{language_code: value}` dict, mirroring the PATCH payload convention
(§2.7); for `image`/`file`/`submodel_*` fields it is never present.

### User and group autocomplete

These endpoints power the search-as-you-type UI for `USER_SELECT*` and
`GROUP_SELECT*` fields. They are read-only and accessible to any authenticated user.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/udm/users/?q=alice&group_ids=3,7` | Search active users; `group_ids` restricts to those groups (mirrors `type_config.limit_to_group_ids`) |
| `GET` | `/api/udm/groups/?q=workshop` | Search groups |

Both return `[{ "id": …, "display_name"/"name": … }]` and support a `?ids=1,2,3`
param for bulk-resolving already-stored PKs on form load.

### Staging files

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/udm/staging-files/` | Upload a file; returns `staging_id`. Pre-validates MIME/size if `intended_field` is provided |
| `DELETE` | `/api/udm/staging-files/{sid}/` | Delete a staged file early (optional; it expires anyway) |

### UserDefinedModelEntities

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/udm/entities/` | Create draft; binds to user_defined_model_type's active published config; materialises field defaults (§2.8) into starting `FieldValue` rows |
| `GET` | `/api/udm/entities/{id}/` | Retrieve with all field values and child nodes |
| `PATCH` | `/api/udm/entities/{id}/` | Partial update — only send changed fields (see below) |
| `POST` | `/api/udm/entities/{id}/transition/` | Fire a workflow transition by name, e.g. `{ "transition": "submit" }`; runs the subtree validation (§15). Submission is just the `submit` transition — there is no separate `/submit/` endpoint |
| `DELETE` | `/api/udm/entities/{id}/` | Delete (DRAFT only, owner only) |
| `GET` | `/api/udm/entities/{id}/history/` | Edit history (EditGroups + FieldEdits, newest first) |
| `GET` | `/api/udm/entities/{id}/policy-document/` | Canonical full-tree JSON used as Rego `input` (§16); staff-only, for policy authoring/tests |

### PATCH payload — partial update format

Only fields the user explicitly changed are included. Omitted fields are left
untouched on the server; their stored values — even if another user modified them
in the meantime — are never overwritten.

```jsonc
// PATCH /api/udm/entities/{id}/
{
  "changed_fields": {
    // ── Scalar / file / localized fields ─────────────────────────────────
    "abstract":       "New abstract text",
    "duration_days":  3,
    "photo":          { "staging_id": "a1b2c3d4-..." },  // promote staged file
    "internal_notes": null,                               // clear the field

    // ── submodel_list field — list of operations on child instances ───────
    "speakers": [
      // Create a new instance; sort_order is optional (appended if omitted).
      { "op": "create", "sort_order": 0,
        "fields": { "name": "Alice", "bio": "Short bio" } },

      // Partial update of an existing instance — only named fields change.
      { "op": "update", "id": "550e8400-e29b-41d4-a716-446655440000",
        "fields": { "bio": "Longer bio now" } },

      // Delete an existing instance.
      { "op": "delete", "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8" }
    ]
  }
}
```

Rules for scalar / file / localized fields (unchanged):
- **Omit** a key → field is not touched.
- **`null`** → field value is cleared (and its `FileAttachment` deleted if present).
- **`{ "staging_id": "..." }`** → stage is promoted to `FileAttachment`;
  old attachment is replaced and deleted in the same transaction.
- Any other value → treated as the new scalar value for the field.

Rules for `submodel_list` fields:
- The value must be a list of operation objects; omitting the key leaves all child
  instances untouched.
- `"op": "create"` — creates a new `SubmodelInstance`; `fields` follows the same
  partial-update semantics as the root entity PATCH (only provided keys are set;
  defaults from §2.8 are applied first). `sort_order` defaults to one past the
  current maximum if omitted.
- `"op": "update"` — applies a partial field update to the instance identified by
  `id`; fields absent from `fields` are left untouched.
- `"op": "delete"` — deletes the instance identified by `id`; `fields` must be absent.
- Instance IDs not mentioned in the list are left entirely untouched.
- Submodel fields can themselves be `submodel_list` fields; nesting is handled
  recursively within the same transaction.
- The entire PATCH — root field writes and all submodel operations — executes in one
  `transaction.atomic()` under the single root-entity lock (§14.2). If any
  operation fails validation the whole PATCH is rolled back.

The response body always returns the **complete current state** of all fields on the
root entity and all its child nodes, so the frontend can refresh its full saved-state
in one round-trip.

### Submodel instances

Submodel create / update / delete operations are sent inline in the root entity
PATCH (see the `submodel_list` rules above). There are no separate per-node
endpoints. All operations share the root-entity lock and commit in one transaction.

### Single-user_defined_model_entity migration

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/udm/entities/{id}/migration-preview/` | Preview with `?target_user_defined_model_type=` or `?target_version=` |
| `POST` | `/api/udm/entities/{id}/migrate/` | Execute confirmed single-user_defined_model_entity migration |

### Bulk migration (config switch / republish)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/udm/bulk-migrations/preview/` | Suggest field mapping for `{ source_version, target_version, user_defined_model_type_filter? }`; returns `affected_proposal_count` |
| `POST` | `/api/udm/bulk-migrations/` | Create a `BulkMigrationPlan` with confirmed field mappings |
| `GET` | `/api/udm/bulk-migrations/{id}/` | Retrieve plan and current progress counters |
| `POST` | `/api/udm/bulk-migrations/{id}/execute/` | Execute; returns immediately, plan status polled via GET |

---

## 7. Frontend Integration

The JS frontend receives a **config schema** (see §6 JSON shape) and a
**user_defined_model_entity payload** (field values keyed by `field_id`). It is responsible for:

- Rendering each field by `data_type` (text, markdown editor, WYSIWYG, date
  picker, file drop zone, submodel list/table, etc.).
- Tracking per-field edit state (see §11).
- Sending only the changed fields on save (see §12).
- Showing per-field errors returned by the API (`400` with field-keyed
  `errors` object).
- Rendering the migration mapping UI when the user initiates a migration.
- Displaying the edit history timeline (see §13).
- For `USER_SELECT*` and `GROUP_SELECT*` fields: driving a search-as-you-type
  autocomplete via `GET /api/udm/users/` or `GET /api/udm/groups/`. On form load, bulk-resolve
  any already-stored PKs with `?ids=…` to display names without a query per value.

The frontend should request the config schema once per page load and cache it
for the session; config changes only take effect for newly created user_defined_model_entities.

### History endpoint response shape

```jsonc
// GET /api/udm/entities/{id}/history/
{
  "results": [
    {
      "id": 99,
      "saved_at": "2026-05-30T14:32:11Z",
      "saved_by": { "id": 5, "display_name": "Alice" },
      "node_id": 12,
      "node_type": "user_defined_model_entity",          // or "submodel:<slug>"
      "edits": [
        {
          "change_kind": "field_value",
          "field_slug": "abstract",
          "field_label": "Abstract",
          "old_value": "Old text...",
          "new_value": "New text..."
        },
        {
          "change_kind": "field_value",
          "field_slug": "photo",
          "field_label": "Photo",
          "old_file_name": "previous.jpg",
          "new_file_name": "new_photo.png"
        }
      ]
    }
  ]
}
```

---

## 8. Renderer Hints in Config

`FieldDefinition.type_config` can carry optional `renderer` hints consumed by
the frontend:

```jsonc
// TEXT_MARKDOWN field
{ "renderer": "markdown_wysiwyg" }   // or "markdown_preview", "plaintext"

// SUBMODEL_LIST field
{ "renderer": "table" }              // or "list" (default)
```

These are purely presentational; the backend ignores them.

---

## 11. Staged File Uploads

Files and images are **never permanently stored** when the user selects them.
They are held in a temporary `StagingFile` row and only promoted to a real
`FileAttachment` when the user explicitly saves.

### Upload flow

```
User selects file
      │
      ▼
POST /api/udm/staging-files/
  body: multipart { file, intended_field?, intended_node? }
  → 201 { "staging_id": "uuid", "original_name": "...", "mime_type": "...", "size_bytes": ... }
      │
      │  Frontend shows local preview via URL.createObjectURL(file)
      │  (no server round-trip needed for the visual preview)
      │
      │  User edits other fields...
      │
      ▼
PATCH /api/udm/entities/{id}/
  body: { "changed_fields": { "photo": { "staging_id": "uuid" } } }
      │
      ▼  server-side, inside transaction.atomic():
  1. Load StagingFile by staging_id; verify uploader == request.user
  2. Run definitive MIME / size validation against FieldDefinition rules
  3. Move file from staging/ to proposal_files/ (no filesystem copy)
  4. Create FileAttachment linked to FieldValue
  5. Delete StagingFile row
  6. Record FieldEdit (old_file_name → new_file_name)
      │
      ▼
  Response includes full current field values so frontend refreshes savedValue
```

### Reset / discard a staged file

If the user resets the field before saving, the frontend simply drops the
`staging_id` from its edit state. The `StagingFile` is eventually cleaned up
by the `cleanup_staging_files` management command when `expires_at` passes.
For immediate cleanup (e.g., on page unload), the frontend can send
`DELETE /api/udm/staging-files/{sid}/`.

### Clearing an existing file

```jsonc
{ "changed_fields": { "photo": null } }
```

The server deletes the `FileAttachment` and its physical file within the same
transaction, and records a `FieldEdit` with `old_file_name` set and
`new_file_name` empty.

---

## 12. Partial Field Updates and Per-Field Reset

### Server behaviour

The PATCH handler on `UserDefinedModelEntityNode` applies **field-level last-write-wins** inside a
single `transaction.atomic()` block. The root-user_defined_model_entity lock is acquired **before**
validation so that the validated state is guaranteed to still hold when the write
executes. See §14 for the full locking design.

1. Parse `changed_fields` from the request body; split into **scalar entries**
   (non-submodel fields) and **submodel-list entries** (fields whose `data_type`
   is `submodel_list`, whose values are lists of operation objects).
2. Open `transaction.atomic()`.
3. **Lock the root `UserDefinedModelEntity` row** (`SELECT FOR UPDATE NOWAIT,
   of=("self",)`; §14.2). This single lock serialises the entire tree for the
   duration of the PATCH — no `FieldValue` or node rows need separate locks.
4. **Authorize scalar fields** — compute `authz.editable_fields(node, user)`
   (§16.3) and reject the whole PATCH `403` if any scalar key in `changed_fields`
   is not in that set.
5. **Authorize submodel operations** — for each submodel-list entry, verify the
   user holds the `create` / `edit` / `delete` permission on the parent node for
   the respective op kind; reject `403` if any op is unauthorized.
6. Load current `FieldValue` rows for the root node (for history old-values).
7. Run `validate_for_save()` on the root node.
8. Apply scalar writes (create/update/delete `FieldValue` rows, promote staging
   files) on the root node.
9. **Process submodel-list operations in declaration order:**
   - `create` — instantiate a new `SubmodelInstance`, materialise its field
     defaults (§2.8), then apply the operation's `fields` as a partial update;
     run `validate_for_save()` on the new instance.
   - `update` — look up the addressed instance (404 if not found or belongs to a
     different parent); apply `fields` as a partial update; run
     `validate_for_save()` on the instance.
   - `delete` — look up and delete the addressed instance and all its descendants.
   - Each operation's `fields` may itself contain `submodel_list` entries;
     recurse into step 9 for those.
10. Create **one** `EditGroup` (on the root entity, `root_proposal` = self) covering
    all changes from this PATCH: `FieldEdit` rows for root scalar changes, plus
    `NODE_ADDED` / `NODE_REMOVED` / `NODE_REORDERED` edits and per-field
    `FIELD_VALUE` edits (with `affected_node` set) for each submodel op.
11. Return the complete current state of **all** fields on the root entity and all
    its child nodes.

Fields and submodel instances absent from `changed_fields` / the operations list
are never written; concurrent changes by another user to those fields or instances
are preserved exactly as-is.

### Frontend per-field state model

Each field in the form tracks two independent values:

```typescript
interface FieldState {
  // What the server last confirmed as saved.
  savedValue: ScalarValue | AttachmentInfo | null;

  // What the user has typed / selected but not yet saved.
  // Equals savedValue when the field is unmodified.
  editingValue: ScalarValue | AttachmentInfo | StagingRef | null;

  // Derived: true when editingValue !== savedValue
  isModified: boolean;
}

type StagingRef = { staging_id: string; local_preview_url: string };
```

On every successful PATCH response, the frontend updates `savedValue` for the
fields returned in `changed_fields` and clears `isModified` for those fields.
Other fields are left unchanged in the local state.

### Reset a single field

The reset button (shown next to any modified field) does:

```
editingValue ← savedValue
isModified   ← false
stagingId    ← undefined   (staging file left to expire)
```

No API call is required to reset a scalar field. For a staged file, the frontend
may optionally send `DELETE /api/udm/staging-files/{sid}/` as a courtesy cleanup.

### Dirty-state indicator

The form header shows a "unsaved changes" badge whenever any field has
`isModified = true`. The save button sends a single PATCH with all currently
modified fields collected into `changed_fields`. Fields with `isModified = false`
are never included.

---

## 13. Edit History

### Display model

The history timeline groups changes by `EditGroup` (one group per save user_defined_model_type).
Within a group, each `FieldEdit` is displayed as a diff row.

```
▼ Alice — 30 May 2026 14:32
   Abstract     "Old text…"  →  "New text…"
   Photo        previous.jpg  →  new_photo.png

▼ Bob — 30 May 2026 09:15  [Speaker: Alice Smith]
   Biography    "Short bio"  →  "Longer bio…"

▼ Alice — 29 May 2026 18:00
   ＋ Speaker added: "Alice Smith"
```

Submodel edits appear inline under the user_defined_model_entity history but are labelled with
the submodel type and display name so they are identifiable without navigating
to the child node.

### API pagination

```jsonc
// GET /api/udm/entities/{id}/history/?page=1&page_size=20
{
  "count": 42,
  "next": "/api/udm/entities/7/history/?page=2&page_size=20",
  "results": [ ... ]   // EditGroups with nested FieldEdits, newest first
}
```

### History for submitted user_defined_model_entities

`EditGroup` rows created after a node transitions to any non-initial state are
preserved for audit. They are readable by user_defined_model_entity owners and by staff, not by
reviewers.

### File / image diffs

`FieldEdit.old_attachment` and `new_attachment` carry FKs to the soft-deleted
previous and the active current `FileAttachment` rows respectively. The history
timeline API includes a pre-signed download URL for both so the frontend can
render the old and new image side by side. Physical cleanup of soft-deleted
attachments is handled by the `cleanup_deleted_attachments` management command
(runs on a schedule; configurable retention before physical deletion).

### Rich-text / markdown diffs

For `TEXT_MARKDOWN` and `TEXT_RICHTEXT` fields the history stores the full
`old_value` and `new_value` strings (via `nh3`-sanitised HTML for richtext).
The frontend is responsible for rendering a character-level or line-level diff.

---

## 14. Concurrent Write Safety (Pessimistic Locking)

### 14.1 Threat model

Without locking, validation that passes before a write can be invalidated by a
concurrent transaction that commits between the validation and the write. Concrete
races to prevent:

| Race | Description |
|---|---|
| **Status-then-edit** | User A validates that editing field X is permitted (user_defined_model_entity is DRAFT). User B transitions the user_defined_model_entity to SUBMITTED. User A writes field X — the edit should now be rejected but A's validation result is stale. |
| **Multi-field inconsistency** | Field rule: "at least one of A, B must be non-empty." User A reads B=filled, concludes clearing A is safe, starts writing A. User B concurrently clears B. Both writes succeed; the rule is now violated. |
| **Submit-then-edit** | Submit validation reads all fields and passes. A concurrent field edit changes a field to an invalid value before the status is written. UserDefinedModelEntity transitions to SUBMITTED with invalid data. |

**Approach: pessimistic locking.** Every write operation acquires `SELECT FOR UPDATE`
row locks before running any validation, holds them through the write, and releases
them only when the transaction commits. Validation is never cached across a transaction
boundary.

### 14.2 The root user_defined_model_entity row is the mutex

Every write to any node in a user_defined_model_entity tree — a field PATCH on the user_defined_model_entity or on
any nested `SubmodelInstance`, a submit, a workflow transition, a submodel
add/delete, and each per-user_defined_model_entity step of a bulk migration — **first** acquires a
`SELECT FOR UPDATE NOWAIT` lock on the single root `UserDefinedModelEntity` row. Submodel
instances belong to exactly one root user_defined_model_entity (walk `parent_node` up to the
`UserDefinedModelEntity`), so this one row serialises the entire tree.

That single lock alone defeats all three races in §14.1: each requires two
transactions committing concurrently against the same user_defined_model_entity, and the root lock
makes them mutually exclusive. There is therefore **no** per-`FieldValue` lock set
and **no** lock-ordering problem to manage — only one row is ever locked for write
serialisation, so deadlock between two user_defined_model_entity writes is impossible.

This is a deliberate trade-off: concurrent writes to *disjoint* fields of the same
user_defined_model_entity are serialised rather than allowed in parallel. That is acceptable — a
user_defined_model_entity is edited by its owner plus a small number of editors, contention is rare,
and the design already rejects contended writes outright via `NOWAIT` + 409 (§14.5)
rather than queueing them.

> **MTI note.** `UserDefinedModelEntity` is multi-table-inherited from `UserDefinedModelEntityNode`, so a plain
> `UserDefinedModelEntity.objects.select_for_update()` joins and locks *both* the `user_defined_model_entity` and
> `proposalnode` rows. Lock only the child row, consistently, with `of=("self",)`
> so the mutex is one unambiguous row:
> `UserDefinedModelEntity.objects.select_for_update(nowait=True, of=("self",)).get(pk=root_id)`.

### 14.3 Lock acquisition per operation

#### PATCH (save field values on any node)

```python
with transaction.atomic():
    # The root user_defined_model_entity row is the only write lock. For a submodel PATCH,
    # root_proposal_id is resolved by walking parent_node up from the node.
    user_defined_model_entity = (UserDefinedModelEntity.objects
                .select_for_update(nowait=True, of=("self",))
                .get(pk=root_proposal_id))

    # Validate under the lock, then write. No FieldValue rows are locked:
    # the root lock already serialises every write to this tree.
    node.validate_for_save(context_fields=changed_slugs)
    # ... apply writes, create EditGroup ...
```

#### POST /transition (incl. submit)

Every state change — including submission — is a workflow transition (§15). The
single root lock blocks any concurrent PATCH/transition on the tree, so the recursive
subtree validation (§4) sees a stable snapshot.

```python
with transaction.atomic():
    user_defined_model_entity = (UserDefinedModelEntity.objects
                .select_for_update(nowait=True, of=("self",))
                .get(pk=proposal_id))

    execute_transition(user_defined_model_entity, name=request.data["transition"], user=request.user)  # §15.1
```

This one block covers submit, accept, reject, revise and every other transition:
each runs under the root lock and sets `current_state` (the removed `Status` field
no longer exists). Holding the root lock prevents a concurrent PATCH from racing the
state change.

#### Submodel add / delete

```python
with transaction.atomic():
    user_defined_model_entity = (UserDefinedModelEntity.objects
                .select_for_update(nowait=True, of=("self",))
                .get(pk=root_proposal_id))
    # Create or delete SubmodelInstance; validate parent-level min/max_items rules.
```

### 14.4 Concurrent inserts of a new FieldValue

Because the root lock serialises every write to the tree, two requests can never
both be inside the critical section for the same user_defined_model_entity, so they cannot race to
INSERT the same `(node, field, language)` row. The
`UniqueConstraint(fields=["node", "field", "language"])` (§2.3) remains as a
defensive backstop only; if it ever fires, the handler returns a 409.

### 14.5 Lock contention — API response

All `SELECT FOR UPDATE` user_defined_model_types use `nowait=True`. If a lock cannot be immediately
acquired, Django raises `django.db.utils.OperationalError`. The API catches this
at the view layer and returns:

```
HTTP 409 Conflict
{
  "error": "concurrent_edit",
  "retry_after_ms": 500
}
```

The frontend displays a transient "Someone else is saving right now — please try
again" message and retries after `retry_after_ms`.

### 14.6 Interaction with bulk migration

The `BulkMigrationPlan` executor already holds a `SELECT FOR UPDATE` on the plan
row to prevent concurrent runs (§5.5). For each user_defined_model_entity within a batch, the
executor opens its own `transaction.atomic()` and takes the root-user_defined_model_entity lock
(§14.3) for that user_defined_model_entity. UserDefinedModelEntities in a batch are processed sequentially.

---

## 15. Workflow Transition Execution

Every state change on a `UserDefinedModelEntityNode` is a **transition**. The execution
sequence below runs inside a single `transaction.atomic()` with the root
UserDefinedModelEntity row locked first (§14.3).

### 15.1 Execution sequence

```
POST /api/udm/entities/{id}/transition/   { "transition": "submit" }

1.  Lock the root UserDefinedModelEntity row (SELECT FOR UPDATE NOWAIT, of=("self",); §14.2).
    This single lock covers the whole tree for the duration of the transition.
2.  Load WorkflowTransition by name within node.config_version.workflow.
    → 404 if no such transition exists in the workflow.
3.  Check from_state: node.current_state must match transition.from_state
    (or from_state is null = "any").
    → 409 if the node is in the wrong state.
4.  Check permission via the Rego authz evaluator (§16.3):
    authz.allows(node, "transition", user, transition=name), using
    transition.policy_rule if set, else the default data.user_defined_model_entities.allow rule.
    (permission_codename is consulted only as a fallback when no Rego rule exists.)
    → 403 if the policy denies.
5.  Execute PRE-phase TransitionActions (sorted by sort_order).
6.  **Subtree validation (validation-only; §4 "Strict validation across the subtree").**
    For every node in the subtree (root + all descendants), in one pass under the
    root lock from step 1:
      - re-run that node's save rules (the save-rule floor), and
      - if the node's ConfigVersion has a workflow transition of this same name,
        run that transition's TransitionMandatoryFields + TransitionValidatorAssignments.
    → 400 with field-keyed errors (slug, and node id for descendants) on any failure.
      Nothing has changed state yet, so the whole transition simply aborts.
7.  (Covered by step 6 — the transition's own validators are evaluated there as part
    of the root node's contribution.)
8.  (No additional locking — the root lock from step 1 already serialises the tree.)
9.  Atomically (only the invoked node transitions; descendants do not):
      a. Apply any SetFieldValueAction writes.
      b. Set node.current_state = transition.to_state.
      c. Save the node.
      d. Create an EditGroup + FieldEdit entries for field value changes (step 9a)
         and a NODE_TRANSITION FieldEdit for the state change.
10. Execute POST-phase TransitionActions (sorted by sort_order).
    → Post-action failures are logged but do not roll back the transition.
11. Return updated node representation (all field values + new current_state).
```

### 15.2 FieldEdit for state changes

`FieldEdit.ChangeKind` gains a new value:

```python
NODE_TRANSITION = "node_transition"
# old_value = {"state": "draft"},  new_value = {"state": "submitted"}
# field is null; affected_node points to the transitioning node
```

### 15.3 `WorkflowState.allows_edit` enforcement

Every PATCH request checks `node.current_state.allows_edit` after acquiring the
root-user_defined_model_entity lock (§14.2). If `False`, the request is rejected with
`HTTP 409 { "error": "editing_not_allowed_in_state" }` before any validation runs.

### 15.4 Nodes without a workflow

If `config_version.workflow` is null the node has no states, all field edits are
always permitted, and `POST /transition/` returns 404. This is the default for
configs that have not yet been assigned a workflow.

---

## 16. Authorization (Rego via regorus)

Authorization decisions — **view / create / edit / delete** on a node (user_defined_model_entity or
submodel) and on individual **fields**, plus workflow transitions — are evaluated
with [microsoft/regorus](https://github.com/microsoft/regorus), an **in-process**
Rego engine. There is no OPA server, no network call, and no `OPA_URL`: regorus is
embedded via its Python bindings and policies are compiled once at startup. The
user_defined_model_entity is serialised to a canonical JSON document (§16.1) that becomes the Rego
`input` (§16.2); decisions are evaluated by a small `authz` module (§16.3) and
enforced at the points listed in §16.4.

### 16.1 Node serialisation

`UserDefinedModelEntityNode.to_policy_document()` returns a plain, JSON-safe `dict` describing one
node and, recursively, its whole subtree. It reuses the typed-value accessor
(`FieldValue.get_value()`, §2.3) and resolves reference fields to bare PKs (policy
matching wants identifiers, not display names — see §16.2 for where attributes go).

```python
class UserDefinedModelEntityNode(HistoricalMetaBase):
    ...
    def to_policy_document(self) -> dict:
        """Canonical, deterministic JSON-safe representation of this node + subtree.
        Keys are sorted; children are ordered by (parent_field.slug, sort_order, id);
        datetimes are ISO-8601 UTC strings; Decimals are stringified. Determinism
        matters so policy decisions can be cached and diffed."""
        ...
```

Shape (root user_defined_model_entity example; submodel nodes use the same shape minus
`call_id` / `owner` / `editors`):

```jsonc
{
  "id": "0c1f…",
  "type": "user_defined_model_entity",                  // or "submodel:<parent_field_slug>"
  "config_version_id": "8a2d…",
  "config_id": "4b9e…",
  "call_id": "1f30…",                  // null for an unassigned user_defined_model_entity
  "owner": { "id": "5c…", "username": "alice", "is_active": true },
  "editors": [ { "id": "9d…", "username": "bob" } ],
  "current_state": "submitted",        // WorkflowState.name, null if no workflow
  "fields": {
    // key = field slug; value carries data_type so Rego need not look it up
    "abstract":  { "data_type": "text_markdown", "localized": false, "value": "…" },
    "title_i18n":{ "data_type": "text_short", "localized": true,
                   "value": { "en": "…", "de": "…" } },
    "duration_days": { "data_type": "integer", "localized": false, "value": 3 },
    "material_cost_eur": { "data_type": "float", "localized": false, "value": "12.50" },
    "reviewers": { "data_type": "user_select_multi", "localized": false, "value": ["5c…","9d…"] },
    "photo":     { "data_type": "image", "localized": false,
                   "value": { "attachment_id": "aa…", "mime_type": "image/png", "size_bytes": 40213 } }
  },
  "children": {
    // grouped by the parent SUBMODEL_LIST field slug, each ordered by sort_order
    "speakers": [ { "id": "…", "type": "submodel:speakers", "fields": { … }, "children": {} } ]
  },
  "overflow_data": {},
  "created_at": "2026-05-30T14:32:11Z",
  "updated_at": "2026-05-30T14:40:02Z"
}
```

Notes:
- Localized fields serialise as a `{language_code: value}` dict, matching the PATCH
  and config-schema conventions (§2.7).
- `file` / `image` values carry attachment metadata (not the bytes) so size/MIME
  policies are expressible without a second fetch.
- `submodel_select` serialises as the referenced node's `id`; the referenced node is
  **not** inlined (it may live under a different user_defined_model_entity tree) — follow the id if a
  policy needs it.
- The document is value-only: it deliberately excludes edit history and validation
  rules, which are config/audit concerns, not policy inputs.

### 16.2 Policy input

`build_policy_input(node, action, user, field=None)` wraps the document with the
subject and the attempted action. The whole **root** user_defined_model_entity is always included
(even for a submodel action) so policies can reason about the tree; `node_id` points
at the targeted node, and `field` is the slug for field-level actions (null for
node-level ones).

```jsonc
{
  "action": "edit",                 // one of: view | create | edit | delete | transition
  "transition": null,               // transition name when action == "transition", else null
  "node_id": "0c1f…",               // node the action targets (root or a submodel)
  "node_type": "user_defined_model_entity",          // or "submodel:<slug>"
  "field": null,                    // field slug for field-level checks; null otherwise
  "user": {
    "id": "5c…",
    "username": "alice",
    "is_active": true,
    "is_staff": false,
    "groups": [3, 7],               // auth.Group PKs the user belongs to
    "permissions": ["userdefinedmodel.submit_proposal", "userdefinedmodel.moderate_proposal"]
  },
  "user_defined_model_entity": { /* root node document from §16.1 */ }
}
```

The user's group memberships and Django permissions live on `user`, so reference
fields inside the user_defined_model_entity can stay as bare PKs and the policy joins the two. The
node's `current_state` is in the document, so state-dependent rules (e.g. "no edits
once submitted") are expressible in Rego — this subsumes `WorkflowState.allows_edit`
(§15.3), which remains only as an optional fast pre-check.

### 16.3 The `authz` evaluator

A single module owns regorus. Policies (`.rego` files shipped in the repo, e.g.
`backend/userdefinedmodel/policies/`) and any static `data` are loaded into one base
`regorus.Engine` **once** at startup. Per request the base engine is `clone()`d
(cheap; avoids recompiling policies and keeps evaluation thread-safe), the input is
set, and the relevant rule is evaluated:

```python
# Built once at process start.
_BASE = regorus.Engine()
for path in sorted(POLICY_DIR.glob("*.rego")):
    _BASE.add_policy_from_file(str(path))
# _BASE.add_data_json(...)  # optional static data (role tables, etc.)

def _eval(rule: str, input: dict):
    eng = _BASE.clone()
    eng.set_input_json(json.dumps(input))
    return eng.eval_rule(rule)          # returns the rule's value (bool / set / …)

def allows(node, action, user, *, field=None, transition=None) -> bool:
    inp = build_policy_input(node, action, user, field=field)
    inp["transition"] = transition
    return _eval("data.user_defined_model_entities.allow", inp) is True

def viewable_fields(node, user) -> set[str]:
    return set(_eval("data.user_defined_model_entities.viewable_fields",
                     build_policy_input(node, "view", user)))

def editable_fields(node, user) -> set[str]:
    return set(_eval("data.user_defined_model_entities.editable_fields",
                     build_policy_input(node, "edit", user)))
```

Rego entry points the policies must define:

| Rule | Returns | Used for |
|---|---|---|
| `data.user_defined_model_entities.allow` | boolean | node-level view / create / delete, and transitions (`action`/`transition` in input) |
| `data.user_defined_model_entities.viewable_fields` | set of slugs | which fields appear in a GET response |
| `data.user_defined_model_entities.editable_fields` | set of slugs | which fields a PATCH may write |

`viewable_fields` / `editable_fields` are returned as **sets in one evaluation** (not
one user_defined_model_type per field) so field-level decisions cost a single `clone()`+`eval` per
request, not one per field.

### 16.4 Enforcement points

| Action | Enforced in | Rule | On deny |
|---|---|---|---|
| **view node** | `GET /api/udm/entities/{id}/`, and list querysets | `allow` (`action="view"`) | 404 (list: filtered out) |
| **create node** | `POST /api/udm/entities/` (root); `op:"create"` in PATCH (submodel) | `allow` (`action="create"`) | 403 |
| **delete node** | `DELETE /api/udm/entities/{id}/` (root); `op:"delete"` in PATCH (submodel) | `allow` (`action="delete"`) | 403 |
| **view field** | GET serialiser | `viewable_fields` | field omitted from response |
| **edit field** | PATCH (§12), per slug in `changed_fields` | `editable_fields` | 403 listing the rejected slugs |
| **transition** | §15.1 step 4 | `allow` (`action="transition"`, `transition=<name>`) | 403 |

PATCH gating runs **before** validation (§12 step 4, after the lock is taken): any
slug in `changed_fields` not in `editable_fields` aborts the whole PATCH with a 403
naming the rejected fields — partial silent dropping is avoided so the client never
believes an edit was saved when it was refused. GET field filtering instead silently
omits non-viewable fields (a viewer simply does not see them).

This replaces the keyword-matching `UserDefinedModelEntity.has_object_permission` (existing code)
and the per-transition `permission_codename` as the **primary** authorization path for
user_defined_model_entity nodes and fields. `permission_codename` is retained only as a coarse fallback
for transitions whose config has no Rego rule yet (during migration); when a Rego
policy is present it is authoritative.

The serialiser is reusable for offline policy authoring and tests:
`GET /api/udm/entities/{id}/policy-document/` (staff-only) returns the §16.1 document so
it can be fed to `regorus eval` / unit tests as `input` while writing `.rego` rules.

---

## 17. Pydantic API Schemas (`userdefinedmodel/schemas.py`)

All `*In` schemas (request bodies) carry `model_config = {"extra": "forbid"}` and
hard field limits designed to prevent DoS via oversized payloads or deeply nested
structures. `*Out` schemas are permissive — they are server-generated and need no
extra-field guard.

### 17.1 Shared limits and type aliases

```python
"""
Pydantic / Django-Ninja schemas for the userdefinedmodel API (/api/udm/).
Lives in backend/userdefinedmodel/schemas.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Optional

from ninja import Schema
from pydantic import Field, field_validator, model_validator

# ── Cardinality / length caps (tune here to adjust the DoS profile) ───────────

_MAX_SLUG_LEN         = 80
_MAX_LABEL_LEN        = 200
_MAX_HELP_TEXT_LEN    = 2_000
_MAX_DESCRIPTION_LEN  = 5_000
_MAX_NOTES_LEN        = 2_000
_MAX_ADMIN_LABEL_LEN  = 200
_MAX_LANG_CODE_LEN    = 10        # BCP-47, e.g. "en", "zh-Hant"
_MAX_PERM_CODE_LEN    = 200
_MAX_STATE_NAME_LEN   = 100
_MAX_TRANS_NAME_LEN   = 100
_MAX_MIME_LEN         = 100
_MAX_REGEX_LEN        = 500
_MAX_FAIL_MSG_LEN     = 200
_MAX_POLICY_RULE_LEN  = 300
_MAX_SORT_ORDER       = 32_767    # fits PositiveSmallIntegerField

# List-cardinality caps — prevent one request from causing unbounded DB work
_MAX_FIELDS           = 200       # FieldDefinitions per ConfigVersion
_MAX_LANGUAGES        = 50        # ConfigLanguages per FieldConfig
_MAX_CHOICES          = 500       # options in a select-type field
_MAX_CHOICE_LEN       = 200       # each choice key
_MAX_STATES           = 100       # WorkflowStates per WorkflowDefinition
_MAX_TRANSITIONS      = 200       # WorkflowTransitions per WorkflowDefinition
_MAX_VALIDATORS       = 100       # TransitionValidatorAssignments per transition
_MAX_MANDATORY_FLDS   = 100       # TransitionMandatoryFields per transition
_MAX_RULES            = 50        # single-field rules per FieldDefinition
_MAX_MULTI_RULES      = 50        # multi-field rules per ConfigVersion
_MAX_MIME_ENTRIES     = 50        # entries in AllowedMimeTypesRule
_MAX_GROUP_IDS        = 100       # limit_to_group_ids in user/group type_config
_MAX_CHANGED_FIELDS   = 200       # keys in a PATCH changed_fields payload
_MAX_MAPPING_ENTRIES  = 300       # field mappings in a migration plan

# Numeric bounds for type_config and rule values
_MAX_TEXT_LENGTH      = 50_000    # max configurable max_length for text fields
_MAX_FILE_BYTES       = 500_000_000   # 500 MB hard ceiling for MaxFileSizeRule
_MAX_ITEMS_RULE       = 10_000    # min/max items for list-type fields

# ── Reusable annotated types ──────────────────────────────────────────────────

Slug     = Annotated[str, Field(min_length=1, max_length=_MAX_SLUG_LEN,
                                 pattern=r"^[a-z][a-z0-9_-]*$")]
LangCode = Annotated[str, Field(min_length=2, max_length=_MAX_LANG_CODE_LEN,
                                 pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]+)*$")]
Label    = Annotated[str, Field(min_length=1, max_length=_MAX_LABEL_LEN)]
HelpText = Annotated[str, Field(max_length=_MAX_HELP_TEXT_LEN)]

# Localized maps: {BCP-47 code → text}.  Pydantic v2 validates key + value types.
LocalizedLabel    = Annotated[dict[LangCode, Label],    Field(min_length=1, max_length=_MAX_LANGUAGES)]
LocalizedHelpText = Annotated[dict[LangCode, HelpText], Field(max_length=_MAX_LANGUAGES)]
```

### 17.2 Enums

```python
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

class ConfigVersionStatus(str, Enum):
    DRAFT = "draft"; PUBLISHED = "published"; ARCHIVED = "archived"

class MigrationAction(str, Enum):
    MAP = "map"; DISCARD = "discard"; OVERFLOW = "overflow"

class BulkMigrationStatus(str, Enum):
    DRAFT = "draft"; RUNNING = "running"; DONE = "done"; PARTIAL = "partial"
```

### 17.3 TypeConfig models (input, one per data-type group)

Each is used inside `FieldDefinitionIn.validate_type_config()` to validate the
otherwise-untyped `type_config` dict according to the field's `data_type`.

```python
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

class SubmodelTypeConfig(Schema):
    renderer: Optional[Literal["table", "list"]] = None
    model_config = {"extra": "forbid"}

# Dispatch table — None means the type accepts no type_config keys at all
_TYPE_CONFIG_CLS: dict[DataType, type[Schema] | None] = {
    DataType.TEXT_SHORT: TextTypeConfig,   DataType.TEXT_LONG: TextTypeConfig,
    DataType.TEXT_MARKDOWN: TextTypeConfig, DataType.TEXT_RICHTEXT: TextTypeConfig,
    DataType.INTEGER: NumberTypeConfig,    DataType.FLOAT: NumberTypeConfig,
    DataType.BOOLEAN: None, DataType.DATE: None,
    DataType.TIME: None,    DataType.DATETIME: None,
    DataType.SELECT_SINGLE: SelectTypeConfig, DataType.SELECT_MULTI: SelectTypeConfig,
    DataType.IMAGE: None,   DataType.FILE: None,
    DataType.USER_SELECT: UserGroupTypeConfig, DataType.USER_SELECT_MULTI: UserGroupTypeConfig,
    DataType.GROUP_SELECT: UserGroupTypeConfig, DataType.GROUP_SELECT_MULTI: UserGroupTypeConfig,
    DataType.SUBMODEL_SELECT: SubmodelTypeConfig, DataType.SUBMODEL_LIST: SubmodelTypeConfig,
}
```

### 17.4 Single-field validation rule schemas (input, discriminated union)

```python
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
```

### 17.5 Multi-field rule schemas (input)

```python
class MultiFieldRuleKind(str, Enum):
    AT_LEAST_ONE = "at_least_one_required"
    EXACTLY_ONE  = "exactly_one_required"
    MUTUAL_EXCL  = "mutual_exclusion"

class MultiFieldRuleIn(Schema):
    kind: MultiFieldRuleKind
    field_slugs: list[Slug] = Field(..., min_length=2, max_length=_MAX_FIELDS)
    applies_to_save: bool = False
    admin_label: Annotated[str, Field(max_length=_MAX_ADMIN_LABEL_LEN)] = ""
    model_config = {"extra": "forbid"}
```

### 17.6 FieldDefinition schemas

```python
class FieldDefinitionIn(Schema):
    slug: Slug
    data_type: DataType
    sort_order: int = Field(0, ge=0, le=_MAX_SORT_ORDER)
    is_localized: bool = False
    labels: LocalizedLabel
    help_texts: LocalizedHelpText = Field(default_factory=dict)
    type_config: dict[str, Any] = Field(default_factory=dict)
    submodel_config_version_id: Optional[int] = None
    rules: list[SingleFieldRuleIn] = Field(default_factory=list, max_length=_MAX_RULES)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_type_config(self) -> "FieldDefinitionIn":
        cls = _TYPE_CONFIG_CLS[self.data_type]
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
    id: int
    slug: str
    data_type: str
    sort_order: int
    is_localized: bool
    label: dict[str, str]      # {lang_code: label} from FieldDefinitionTranslation rows
    help_text: dict[str, str]  # {lang_code: help_text}
    type_config: dict[str, Any]
    submodel_config: Optional["ConfigVersionOut"] = None  # inlined for SUBMODEL_* types
    default: Optional[Any] = None   # omitted when no FieldDefaultValue exists
    save_rules: dict[str, Any]      # rule summary for frontend validation
```

### 17.7 Languages and FieldConfig schemas

```python
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
    id: int; name: str; description: str
    stale_entity_count: int
    type_ids: list[int]   # UserDefinedModelType IDs referencing this config
    languages: list[ConfigLanguageOut]
```

### 17.8 Workflow schemas

```python
class WorkflowStateIn(Schema):
    name: Annotated[str, Field(min_length=1, max_length=_MAX_STATE_NAME_LEN,
                                pattern=r"^[a-z][a-z0-9_-]*$")]
    label: LocalizedLabel
    is_initial: bool = False
    allows_edit: bool = True
    model_config = {"extra": "forbid"}

class MandatoryFieldIn(Schema):
    field_slug: Slug
    required_value: Optional[Any] = None   # null = "must merely be non-empty"
    sort_order: int = Field(0, ge=0, le=_MAX_SORT_ORDER)
    model_config = {"extra": "forbid"}

class ValidatorAssignmentIn(Schema):
    # References a rule by its admin_label (unique within a ConfigVersion draft).
    rule_admin_label: Annotated[str, Field(min_length=1, max_length=_MAX_ADMIN_LABEL_LEN)]
    sort_order: int = Field(0, ge=0, le=_MAX_SORT_ORDER)
    model_config = {"extra": "forbid"}

class WorkflowTransitionIn(Schema):
    name: Annotated[str, Field(min_length=1, max_length=_MAX_TRANS_NAME_LEN,
                                pattern=r"^[a-z][a-z0-9_-]*$")]
    label: LocalizedLabel
    from_state: Optional[Annotated[str, Field(max_length=_MAX_STATE_NAME_LEN)]] = None
    to_state: Annotated[str, Field(min_length=1, max_length=_MAX_STATE_NAME_LEN)]
    permission_codename: Annotated[str, Field(max_length=_MAX_PERM_CODE_LEN)] = ""
    policy_rule: Annotated[str, Field(max_length=_MAX_POLICY_RULE_LEN)] = ""
    mandatory_fields: list[MandatoryFieldIn] = Field(default_factory=list, max_length=_MAX_MANDATORY_FLDS)
    validators: list[ValidatorAssignmentIn] = Field(default_factory=list, max_length=_MAX_VALIDATORS)
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

class MandatoryFieldOut(Schema):
    field_slug: str; required_value: Optional[Any]

class ValidatorOut(Schema):
    field_slug: str; rule: dict[str, Any]

class WorkflowTransitionOut(Schema):
    name: str; label: dict[str, str]
    from_state: Optional[str]; to_state: str
    permission_codename: str
    mandatory_fields: list[MandatoryFieldOut]
    validators: list[ValidatorOut]

class WorkflowOut(Schema):
    initial_state: str
    states: list[WorkflowStateOut]
    transitions: list[WorkflowTransitionOut]
```

### 17.9 ConfigVersion schemas

```python
class ConfigDraftIn(Schema):
    """Body for PUT /api/udm/configs/{cid}/versions/draft/ – full replacement."""
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
    """Shape returned by GET .../versions/published/ and .../versions/draft/."""
    version_id: int
    status: str
    notes: str
    published_at: Optional[str]
    languages: list[ConfigLanguageOut]
    fields: list[FieldDefinitionOut]
    workflow: Optional[WorkflowOut] = None

FieldDefinitionOut.model_rebuild()  # resolve forward ref to ConfigVersionOut
```

### 17.10 Entity (UserDefinedModelEntity) operation schemas

```python
class EntityCreateIn(Schema):
    """POST /api/udm/entities/"""
    user_defined_model_type_id: int
    model_config = {"extra": "forbid"}

class EntityPatchIn(Schema):
    """PATCH /api/udm/entities/{id}/ — only send changed fields.
    Values may be: null (clear), scalar, {lang: value} (localized),
    {"staging_id": "…"} (file), or list (multi-select).
    Per-field type validation is deferred to the business logic layer
    (requires the live FieldDefinition rows). The dict size is bounded
    to prevent unbounded DB lookups in a single request."""
    changed_fields: dict[
        Annotated[str, Field(min_length=1, max_length=_MAX_SLUG_LEN)],
        Any,
    ] = Field(..., max_length=_MAX_CHANGED_FIELDS)
    model_config = {"extra": "forbid"}

class TransitionIn(Schema):
    """POST /api/udm/entities/{id}/transition/"""
    transition: Annotated[str, Field(min_length=1, max_length=_MAX_TRANS_NAME_LEN)]
    model_config = {"extra": "forbid"}

class SubmodelOpKind(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class SubmodelOperationIn(Schema):
    """One element in the list value of a submodel_list field in EntityPatchIn.
    The 'fields' dict follows the same partial-update rules as EntityPatchIn
    itself and may recursively contain submodel_list operations."""
    op: SubmodelOpKind
    # Required for UPDATE and DELETE; omitted (server-assigned) for CREATE.
    id: Optional[uuid.UUID] = None
    # Applied for CREATE and UPDATE; must be absent for DELETE.
    fields: dict[
        Annotated[str, Field(min_length=1, max_length=_MAX_SLUG_LEN)],
        Any,
    ] = Field(default_factory=dict, max_length=_MAX_CHANGED_FIELDS)
    # Position within the parent list. Defaults to max+1 on CREATE; unchanged on UPDATE if omitted.
    sort_order: Optional[int] = Field(None, ge=0, le=_MAX_SORT_ORDER)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_op_constraints(self) -> "SubmodelOperationIn":
        if self.op in (SubmodelOpKind.UPDATE, SubmodelOpKind.DELETE) and self.id is None:
            raise ValueError(f"id is required for op='{self.op}'")
        if self.op == SubmodelOpKind.DELETE and self.fields:
            raise ValueError("fields must be absent for op='delete'")
        return self

# The value type for a submodel_list key inside EntityPatchIn.changed_fields.
# Bounded to the same cardinality limit as fields per version.
SubmodelListPatch = Annotated[list[SubmodelOperationIn], Field(max_length=_MAX_FIELDS)]

class UserRefOut(Schema):
    id: uuid.UUID; display_name: str

class FieldValueOut(Schema):
    field_slug: str; data_type: str
    value: Any         # typed by the application layer, not the schema
    language: str = "" # "" for non-localized fields

class EntityOut(Schema):
    id: uuid.UUID
    config_version_id: int
    user_defined_model_type_id: Optional[int]
    current_state: Optional[str]
    owner: Optional[UserRefOut]
    editors: list[UserRefOut]
    field_values: list[FieldValueOut]
    overflow_data: dict[str, Any]
    created_at: str; updated_at: str
```

### 17.11 Edit history schemas

```python
class FieldEditOut(Schema):
    change_kind: str                    # FieldEdit.ChangeKind value
    field_slug: Optional[str] = None
    field_label: Optional[str] = None  # resolved from active translation
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    old_file_name: Optional[str] = None
    new_file_name: Optional[str] = None
    old_file_url: Optional[str] = None   # pre-signed URL for soft-deleted attachment
    new_file_url: Optional[str] = None
    affected_node_id: Optional[uuid.UUID] = None

class EditGroupOut(Schema):
    id: int; saved_at: str
    saved_by: Optional[UserRefOut]
    node_id: uuid.UUID; node_type: str  # "proposal" or "submodel:<slug>"
    edits: list[FieldEditOut]

class EditHistoryOut(Schema):
    count: int; next: Optional[str]; results: list[EditGroupOut]
```

### 17.12 Migration schemas

```python
class MigrationFieldMappingIn(Schema):
    source_field_slug: Slug
    action: MigrationAction
    target_field_slug: Optional[Slug] = None   # required when action=MAP
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def target_required_for_map(self) -> "MigrationFieldMappingIn":
        if self.action == MigrationAction.MAP and not self.target_field_slug:
            raise ValueError("target_field_slug required when action is 'map'")
        return self

class MigrationExecuteIn(Schema):
    """POST /api/udm/entities/{id}/migrate/"""
    migration_id: int
    confirmed: Literal[True]   # client must explicitly pass true
    field_mappings: list[MigrationFieldMappingIn] = Field(..., max_length=_MAX_MAPPING_ENTRIES)
    model_config = {"extra": "forbid"}

class MigrationPreviewFieldOut(Schema):
    source_slug: str; source_data_type: str
    suggested_action: MigrationAction
    suggested_target_slug: Optional[str]
    conflict_reason: Optional[str]

class MigrationPreviewOut(Schema):
    migration_id: int
    source_version_id: int; target_version_id: int
    field_previews: list[MigrationPreviewFieldOut]

class BulkMigrationCreateIn(Schema):
    """POST /api/udm/bulk-migrations/"""
    source_version_id: int; target_version_id: int
    user_defined_model_type_filter_id: Optional[int] = None
    field_mappings: list[MigrationFieldMappingIn] = Field(..., max_length=_MAX_MAPPING_ENTRIES)
    model_config = {"extra": "forbid"}

class BulkMigrationOut(Schema):
    id: int; status: BulkMigrationStatus
    source_version_id: int; target_version_id: int
    user_defined_model_type_filter_id: Optional[int]
    total_entities: int; done_entities: int; failed_entities: int
    executed_at: Optional[str]
```

### 17.13 Staging file and autocomplete schemas

```python
class StagingFileOut(Schema):
    staging_id: uuid.UUID
    original_name: str; mime_type: str; size_bytes: int; expires_at: str

class UserAutocompleteItem(Schema):
    id: uuid.UUID; display_name: str

class GroupAutocompleteItem(Schema):
    id: int; name: str
```

### 17.14 Standard error response schemas

```python
class ConcurrentEditError(Schema):
    """HTTP 409 — root proposal lock could not be acquired (§14.5)."""
    error: Literal["concurrent_edit"]
    retry_after_ms: int = 500

class FieldErrorsOut(Schema):
    """HTTP 400 — validation failure, field-keyed error lists."""
    errors: dict[str, list[str]]

class EditingNotAllowedError(Schema):
    """HTTP 409 — WorkflowState.allows_edit is False (§15.3)."""
    error: Literal["editing_not_allowed_in_state"]
    current_state: str
```

---

## 9. Implementation Phases

### Phase 1 — Config infrastructure (no UI changes yet)
- [ ] `FieldConfig`, `ConfigVersion` (+ `workflow` FK), `FieldDefinition` (+ `is_localized`) models + migrations
- [ ] `TypedValue` abstract base + `FieldDefaultValue` model (§2.8)
- [ ] `ConfigLanguage` model (supported languages per `FieldConfig`)
- [ ] `FieldDefinitionTranslation`, `WorkflowStateTranslation`, `WorkflowTransitionTranslation` models
- [ ] `field_config` FK added to `UserDefinedModelType`
- [ ] `WorkflowDefinition`, `WorkflowState`, `WorkflowTransition`, `TransitionMandatoryField`, `TransitionValidatorAssignment`, `TransitionAction` hierarchy models
- [ ] `SingleFieldValidationRule` root (+ `clean()` type-check) + all concrete single-field subclasses including `RequiredInLanguageRule`
- [ ] `AllowedMimeTypeEntry` child model
- [ ] `MultiFieldValidationRule` root + `MultiFieldRuleAssociation` + concrete subclasses
- [ ] `ConfigVersion.publish()` atomic method: validates the default combination (save-context, §2.8); deep-copies field defs, rules, workflow, and defaults into new DRAFT; auto-creates `BulkMigrationPlan` stubs for stale user_defined_model_entities
- [ ] Config + workflow admin (Django admin for staff)
- [ ] `/api/udm/configs/` CRUD endpoints + `/api/udm/types/{id}/config/` read alias
- [ ] Config JSON schema includes serialised rules and workflow states/transitions

### Phase 2 — UserDefinedModelEntityNode base + FieldValue storage
- [ ] `UserDefinedModelEntityNode` (+ `current_state` FK), `UserDefinedModelEntity` (MTI), `SubmodelInstance` models
- [ ] `FieldValue` (extends `TypedValue`, `language` column, unique constraint), `FileAttachment` (soft-delete with `deleted_at`) models
- [ ] `validate_for_save()` + shared `_evaluate_rules()` on `UserDefinedModelEntityNode`; recursive subtree (submit/transition) validation in the transition engine (§4, §15)
- [ ] `FieldValue.clean()` data-type enforcement
- [ ] Data migration: import existing hardcoded fields as `FieldDefinition` + `SingleFieldValidationRule` instances; convert existing `UserDefinedModelEntity` / `Speaker` rows
  - [ ] Map today's always-on validators (`Speaker.biography`/`abstract`/`description` `MinLengthValidator(50)`, etc.) to `applies_to_save=True` rules so workflow-less submodels keep being checked (save-rule floor, §4)
  - [ ] Build a default `WorkflowDefinition` from the current `UserDefinedModelEntity.Status` choices + permission verbs (`submit`/`accept`/`reject`/`revise`/`moderate`), and attach the user_defined_model_entity's submit-strict rules to its `submit` transition so the root keeps today's submit behaviour (§2.6)

### Phase 3 — UserDefinedModelEntity CRUD API
- [ ] Create / retrieve / update user_defined_model_entity endpoints (partial PATCH, §12); create materialises field defaults into starting `FieldValue` rows (§2.8)
- [ ] Root-user_defined_model_entity lock in every write path per §14.2/§14.3 (`select_for_update(nowait=True, of=("self",))`), including a helper to resolve the root `UserDefinedModelEntity` from any submodel node
- [ ] 409 handler for `OperationalError` (lock contention)
- [ ] `WorkflowState.allows_edit` check in PATCH (§15.3)
- [ ] Transition endpoint (`POST /api/udm/entities/{id}/transition/`) with full §15.1 sequence
- [ ] Staging file upload endpoint + `cleanup_staging_files` management command
- [ ] `cleanup_deleted_attachments` management command for soft-deleted `FileAttachment` rows
- [ ] File staging → promotion + soft-delete-old flow within PATCH transaction
- [ ] Inline submodel operations in the root entity PATCH: `op:"create"` (materialises defaults then applies `fields`), `op:"update"` (partial field update on addressed instance), `op:"delete"` (deletes instance and descendants); recursive for nested `submodel_list` fields; all in one `transaction.atomic()` under the root lock
- [ ] Edit history models with `old_attachment` / `new_attachment` FKs and `NODE_TRANSITION` kind
- [ ] History list endpoint (`GET /api/udm/entities/{id}/history/`)
- [ ] `UserDefinedModelEntityNode.to_policy_document()` + `build_policy_input()` serialiser and `GET /api/udm/entities/{id}/policy-document/` endpoint (§16.1–16.2)
- [ ] `authz` module embedding regorus: startup policy load, per-request `clone()`+eval, `allows()` / `viewable_fields()` / `editable_fields()` (§16.3)
- [ ] Enforce authz at every decision point (§16.4): view/create/delete node, GET field filtering, PATCH per-field gating (before validation), transition check in §15.1 step 4
- [ ] Seed `.rego` policies reproducing current permissions (owner/editor edit in editable states, reviewer/staff visibility) + tests using the policy-document endpoint

### Phase 4 — Migration system
- [ ] `UserDefinedModelEntityMigration` + `MigrationFieldMapping` models (with `bulk_plan` FK)
- [ ] `BulkMigrationPlan` + `BulkMigrationFieldMapping` models
- [ ] Celery task `execute_bulk_migration` with per-user_defined_model_entity locking (§5.5)
- [ ] Single-user_defined_model_entity migration preview + execute API
- [ ] Bulk migration preview + create + execute (202) + status-poll API
- [ ] UserDefinedModelType config-switch guard + stale-user_defined_model_entity count in `FieldConfig` / `UserDefinedModelType` responses
- [ ] Overflow data admin view

### Phase 5 — Config and workflow UI (staff)
- [ ] FieldConfig create/edit/assign to user_defined_model_types; language management (add/remove/reorder `ConfigLanguage`)
- [ ] Workflow designer (states + transitions) with per-language label editor
- [ ] Transition editor: permissions, validator assignments, mandatory fields, pre/post actions
- [ ] Rule editor: add / edit / delete / copy single-field rules (including `RequiredInLanguageRule`); multi-field rule picker
- [ ] `FieldDefinition` form with `is_localized` toggle, per-language label/help_text editing, and a per-language default-value editor (§2.8)
- [ ] Publish flow with diff preview (fields, rules, workflow changes) + bulk migration notice
- [ ] Datatype-change dry-run endpoint
- [ ] Bulk migration mapping UI
- [ ] Per-user_defined_model_entity config version upgrade flow

---

