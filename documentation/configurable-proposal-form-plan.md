# Configurable Proposal Form — Implementation Plan

## Requirements

### Field configuration
- Per-call, configurable proposal form with a defined set of field types → §2.1, §8
- Supported types: `text_short`, `text_long`, `text_markdown`, `text_richtext`, `integer`, `float`, `boolean`, `date`, `time`, `datetime`, `select_single`, `select_multi`, `image`, `file`, `user_select`, `user_select_multi`, `group_select`, `group_select_multi`, `submodel_select`, `submodel_list` → §2.1
- Multiple calls may share the same field configuration → §2.1, §3
- A call's configuration can be switched to a different one → §5.5, §6

### Config versioning
- Field configuration is versioned with an explicit DRAFT → PUBLISHED → ARCHIVED lifecycle → §3
- Published versions are immutable; editing creates a new draft automatically → §3
- A call's proposals remain bound to the version they were created under until migrated → §3, §5

### Submodels
- Submodel instances (e.g. Speakers) are stored as separate Django model rows → §2.2
- Submodels share a common base (`ProposalNode`) with proposals for reuse of validation and migration logic → §2.2
- Submodels may be nested to any depth; the UI warns beyond 2 levels → §2.2, §10

### File and image attachments
- File and image fields are supported on proposals and submodels at any nesting level → §2.3
- Files are only permanently stored when the user explicitly saves; selections are held in a temporary staging area until then → §2.3, §11
- Storage backend is configurable (filesystem default, S3 via django-storages) → §2.3

### Validation rules
- Validation rules are stored as model instances in a polymorphic hierarchy, not as JSON → §2.5
- Single-field rules are attached to exactly one field via FK; reuse on another field requires an explicit copy → §2.5
- Multi-field rules are associated with multiple fields via a join table → §2.5
- Each rule independently declares whether it applies at save time, submit time, or both → §2.5, §4
- Save-time rules are permissive (allow partial/incomplete data); submit-time rules are strict → §4

### Migration
- Proposals can be migrated to a different call or re-bound to a newer config version → §5.1–§5.4
- Migration is user-confirmed per field: each orphaned source field can be mapped, discarded, or kept in an overflow store → §5.3
- Config republish and call config-switch both trigger a bulk migration flow: one field mapping is defined once and applied to all affected proposals → §5.5
- Orphaned field values from any migration are preserved in `ProposalNode.overflow_data` for staff review → §5.3

### Partial saves and per-field undo
- PATCH requests send only the fields the user changed; other fields are never overwritten → §12
- The frontend tracks saved vs. editing state per field; a reset button reverts a single field to its last saved value without a server call → §12
- Unchanged fields retain their stored value even if another user modified them in the meantime → §12

### Edit history
- All field changes within a single save are grouped together as one `EditGroup` → §2.4, §13
- History is scoped to the root proposal and includes edits from nested submodel instances → §2.4, §13
- File/image edits record the old and new filenames; rich-text/markdown edits store the full old and new strings for client-side diff rendering → §13

### Concurrent write safety
- All relevant rows are locked (`SELECT FOR UPDATE NOWAIT`) before any validation runs, and locks are held through the write → §14
- Validation results are never cached across a transaction boundary → §14.1
- Lock acquisition follows a fixed order (Proposal → SubmodelInstance → FieldValue by PK) to prevent deadlocks → §14.2
- Status transitions (submit, accept, reject, revise) lock the proposal row so no concurrent field edit can race against the status change → §14.3
- Lock contention returns HTTP 409 immediately; the frontend retries → §14.6

---

## Overview

Replace the current hardcoded `Proposal` / `Speaker` fields with a versioned,
**shareable** field configuration system. A `FieldConfig` is an independent entity;
multiple calls can reference the same one. The same validation and migration logic
applies to proposals and all submodel instances through a shared base model.

---

## 1. Core Concepts

| Term | Meaning |
|---|---|
| **FieldConfig** | Independent, named configuration entity; may be shared by multiple calls |
| **SingleFieldValidationRule** | Polymorphic rule attached to exactly one `FieldDefinition` via FK; must be copied to reuse on a different field |
| **MultiFieldValidationRule** | Polymorphic rule associated with multiple `FieldDefinition`s via a join table; expresses cross-field constraints |
| **ConfigVersion** | One immutable snapshot of field definitions (DRAFT → PUBLISHED → ARCHIVED) |
| **FieldDefinition** | A single configured field within a version |
| **ProposalNode** | Concrete base model shared by `Proposal` and all submodel instances |
| **FieldValue** | Stores the actual value of one field on one ProposalNode |
| **FileAttachment** | File or image permanently bound to a FieldValue (created only at save time) |
| **StagingFile** | Temporary file upload held server-side until the user saves; promoted or discarded |
| **EditGroup** | Records all field changes made in a single save operation |
| **FieldEdit** | One changed field within an EditGroup (old value → new value) |
| **ProposalMigration** | A recorded move of one Proposal to a different call / config version |
| **BulkMigrationPlan** | A staff-configured mapping applied to many proposals at once (config switch or republish) |
| **Validation lock set** | The minimal set of rows that must be locked before validation can be treated as authoritative for a given write |

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
   Call            FieldDefinition (recursive, for sub-fields)
```

A `FieldConfig` is an independent entity — not owned by any single call. Many
calls may share one `FieldConfig`. Each `Call` holds a nullable FK to the
`FieldConfig` it currently uses.

**`FieldConfig`**
```python
class FieldConfig(HistoricalMetaBase):
    name        = models.CharField(max_length=200)  # e.g. "Standard Workshop Form"
    description = models.TextField(blank=True)
```

**On `Call`** (new field, added alongside existing Call fields):
```python
field_config = models.ForeignKey(
    FieldConfig,
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name="calls",
)
```

Changing `Call.field_config` triggers the **config-switch migration flow** (see §5.5).

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
    slug            = models.SlugField(max_length=80)  # stable identifier for migration mapping
    label           = models.CharField(max_length=200)
    help_text       = models.TextField(blank=True)
    data_type       = models.CharField(max_length=30, choices=DataType)
    sort_order      = models.PositiveSmallIntegerField(default=0)

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

**API serialisation** — Proposal GET responses resolve user/group PKs to display
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

### 2.2 Shared proposal node

```
ProposalNode  ──1:N──  FieldValue  ──0:1──  FileAttachment
     │
     ├── Proposal  (root nodes; one per submission)
     └── SubmodelInstance  (child nodes)
```

**`ProposalNode`** (concrete, not abstract — enables self-referential FK for nesting)

```python
class ProposalNode(HistoricalMetaBase):
    config_version = models.ForeignKey(
        ConfigVersion, on_delete=models.PROTECT, related_name="nodes"
    )
    # Non-null for submodel instances; null for root Proposal nodes.
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

    def get_field_value(self, slug: str) -> "FieldValue | None": ...

    def validate_for_save(self):
        """Run save_rules for all fields in this node's config_version."""
        ...

    def validate_for_submit(self):
        """Run submit_rules for all fields; recurse into child nodes."""
        ...

    def _validate_with_rules(self, rule_key: str):
        """
        For each FieldDefinition in config_version:
          1. Fetch the FieldValue (or None).
          2. Build a validator instance from field.{rule_key}.
          3. Run it; collect ValidationErrors.
        Raise ValidationError with all collected errors if any.
        """
        ...
```

**`Proposal`** extends `ProposalNode` via multi-table inheritance:

```python
class Proposal(ProposalNode):
    class Status(models.TextChoices):
        DRAFT     = "draft"
        SUBMITTED = "submitted"
        REVISE    = "revise"
        ACCEPTED  = "accepted"
        REJECTED  = "rejected"

    call    = models.ForeignKey(Call, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="proposals")
    owner   = models.ForeignKey(OpenIDUser, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="owned_proposals")
    editors = models.ManyToManyField(OpenIDUser, blank=True,
                                     related_name="edited_proposals")
    status  = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    moderation_comment = models.TextField(blank=True)
    # ... existing permission logic migrated here
```

**`SubmodelInstance`** extends `ProposalNode`:

```python
class SubmodelInstance(ProposalNode):
    sort_order = models.PositiveSmallIntegerField(default=0)
    # The type of submodel is inferred from parent_field.submodel_config.

    class Meta:
        ordering = ["sort_order", "id"]
```

---

### 2.3 Field values

**`FieldValue`**

```python
class FieldValue(MetaBase):
    node       = models.ForeignKey(ProposalNode, on_delete=models.CASCADE,
                                   related_name="field_values")
    field      = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                   related_name="values")
    # Scalar types (text, number, bool, date, datetime, time, select) stored here.
    value      = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["node", "field"], name="unique_value_per_node_field")
        ]

    def clean(self):
        """Validate `value` matches field.data_type and type_config constraints."""
        ...
```

**`FileAttachment`** — created only when a save is committed, never on file selection.

```python
class FileAttachment(MetaBase):
    field_value   = models.OneToOneField(FieldValue, on_delete=models.CASCADE,
                                         related_name="attachment")
    file          = models.FileField(upload_to=UUIDFilenameUploadTo("proposal_files"))
    original_name = models.CharField(max_length=255)
    mime_type     = models.CharField(max_length=100)
    size_bytes    = models.PositiveIntegerField()
    # For IMAGE types, also store dimensions:
    image_width   = models.PositiveSmallIntegerField(null=True, blank=True)
    image_height  = models.PositiveSmallIntegerField(null=True, blank=True)
```

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
    intended_node  = models.ForeignKey(ProposalNode, on_delete=models.SET_NULL,
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
    """All FieldEdits produced by a single save call."""
    node          = models.ForeignKey(ProposalNode, on_delete=models.CASCADE,
                                      related_name="edit_groups")
    # Denormalised shortcut to the root proposal so the history page can
    # show changes from nested submodel edits without a recursive query.
    root_proposal = models.ForeignKey(
        "Proposal", on_delete=models.CASCADE,
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

    # File/image fields store names instead of (possibly large) values:
    old_file_name = models.CharField(max_length=255, blank=True)
    new_file_name = models.CharField(max_length=255, blank=True)

    # For NODE_ADDED / NODE_REMOVED / NODE_REORDERED:
    affected_node = models.ForeignKey(ProposalNode, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name="+")
```

**Creation rule:** An `EditGroup` (with its `FieldEdit` children) is created inside
the same `transaction.atomic()` block as the `FieldValue` updates. If no field
actually changed (the sent value equals the stored value), no `EditGroup` is created
for that field — the group is only persisted if at least one `FieldEdit` would be
non-empty.

**Immutability:** `EditGroup` and `FieldEdit` rows are never updated after creation.
They are deleted only if the parent `ProposalNode` is deleted.

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
`FieldDefinition` rows and all attached rules into the new DRAFT. Single-field rule
copies get new PKs and point to the new field copies. Multi-field rule copies get new
PKs, a new `config_version` FK, and new `MultiFieldRuleAssociation` rows pointing to
the new field copies.

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
    applies_to_save   = models.BooleanField(default=False)
    applies_to_submit = models.BooleanField(default=True)
    # Human-readable label shown in the admin rule list.
    admin_label       = models.CharField(max_length=200, blank=True)

    def validate(self, value) -> list[str]:
        """Return a (possibly empty) list of error strings for *value*."""
        raise NotImplementedError

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
    applies_to_save   = models.BooleanField(default=False)
    applies_to_submit = models.BooleanField(default=True)
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

## 3. Config Versioning Lifecycle

```
         ┌──────────────────────────────────────────────────────┐
         │              Staff creates FieldConfig               │
         │          (independent of any specific call)           │
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
                             │  proposals bind │
                             │  to this version│
                             └────────┬───────┘
                                       │  next publish
                                       ▼
                             ┌────ARCHIVED─────┐
                             │  read-only      │
                             │  proposals still│
                             │  reference it   │
                             └─────────────────┘
```

- Publishing atomically archives the current PUBLISHED version.
- The new DRAFT is an automatic deep-copy of the just-published version.
- Proposals created before a republish continue to reference their original
  `ConfigVersion`; they are **not** silently upgraded.
- A proposal can be voluntarily upgraded to the new config version via the
  migration flow (see §5).
- Because a `FieldConfig` may be shared by N calls, publishing a new version
  surfaces a **pending-migration count** in the staff UI: the number of proposals
  across all calls using this `FieldConfig` that are still on a previous version.
  Staff can then run a bulk migration from that view (see §5.5).

---

## 4. Validation Rules

Rules are stored as model instances in the polymorphic hierarchy described in §2.5.
Each rule has `applies_to_save` and `applies_to_submit` boolean fields — a rule can
apply to one or both contexts. There are no separate "save rule set" and "submit rule
set" containers; context membership is a property of the rule itself.

### Validation entry points on `ProposalNode`

| Method | Trigger | Rules fetched |
|---|---|---|
| `validate_for_save()` | API PATCH, Django admin save | all rules where `applies_to_save=True` |
| `validate_for_submit()` | API POST /submit | all rules where `applies_to_submit=True` |
| `FieldValue.clean()` | Always, on every write | data-type correctness only (no rule models) |

`validate_for_submit()` recurses into all `SubmodelInstance` children.

### Execution inside `validate_for_save()` / `validate_for_submit()`

```python
def _validate(self, context: str):  # context = "save" or "submit"
    errors: dict[str, list[str]] = defaultdict(list)
    filter_kwarg = {"applies_to_save": True} if context == "save" \
                   else {"applies_to_submit": True}

    # Single-field rules — one DB query with select_related
    for rule in SingleFieldValidationRule.objects.filter(
        field__version=self.config_version, **filter_kwarg
    ).select_related("field"):
        value = self.get_field_value(rule.field.slug)
        for msg in rule.get_real_instance().validate(value):
            errors[rule.field.slug].append(msg)

    # Multi-field rules — one DB query with prefetch
    for rule in MultiFieldValidationRule.objects.filter(
        config_version=self.config_version, **filter_kwarg
    ).prefetch_related("associations__field"):
        field_values = {
            a.field.slug: self.get_field_value(a.field.slug)
            for a in rule.associations.all()
        }
        msg = rule.get_real_instance().validate(field_values)
        if msg:
            for slug in field_values:
                errors[slug].append(msg)

    if errors:
        raise ValidationError(dict(errors))
```

### Data-type enforcement

`FieldValue.clean()` always verifies that `value` is structurally valid for
`field.data_type` (e.g., an `INTEGER` field rejects the string `"hello"`).
This check runs unconditionally — it is not a `ValidationRule` instance and
cannot be disabled. The rule-based checks (required, min/max, regex, …) are
layered on top and are context-dependent.

---

## 5. Migration System

### 5.1 When migration applies

| # | Trigger | Scope | Flow |
|---|---|---|---|
| 1 | **Cross-call move** | one proposal | §5.3 single-proposal flow |
| 2 | **Config version upgrade** | one proposal | §5.3 single-proposal flow |
| 3 | **Config republish on shared config** | all proposals on any previous version of that `FieldConfig`, across all calls | §5.5 bulk flow |
| 4 | **Call config switch** | all proposals under the call being switched | §5.5 bulk flow |

Cases 1–2 use the existing single-proposal mapping mechanism. Cases 3–4 use
the `BulkMigrationPlan` mechanism which defines one field mapping and applies it
to many proposals at once.

All four cases share the same underlying per-proposal execution logic; the bulk
flow simply drives it in a loop.

### 5.2 Field mapping model

```python
class ProposalMigration(HistoricalMetaBase):
    class Action(models.TextChoices):
        MAP      = "map"       # source field → target field
        DISCARD  = "discard"   # drop the value
        OVERFLOW = "overflow"  # keep in ProposalNode.overflow_data

    proposal        = models.ForeignKey(Proposal, on_delete=models.CASCADE,
                                        related_name="migrations")
    source_version  = models.ForeignKey(ConfigVersion, on_delete=models.PROTECT,
                                        related_name="+")
    # For cross-call moves, target_call differs from proposal.call.
    # For in-place version upgrades or config switches, target_call == proposal.call.
    target_call     = models.ForeignKey(Call, on_delete=models.PROTECT,
                                        related_name="received_migrations")
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
    migration      = models.ForeignKey(ProposalMigration, on_delete=models.CASCADE,
                                       related_name="field_mappings")
    source_field   = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                       related_name="+")
    action         = models.CharField(max_length=10, choices=ProposalMigration.Action)
    target_field   = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                       null=True, blank=True, related_name="+")
```

### 5.3 Migration flow

```
1. Staff/user requests migration (target call selected)
2. GET /api/proposals/{id}/migration-preview/?target_call={cid}
   → Returns auto-suggested mapping (matched by slug first, then label similarity)
   → Each source field has: suggested_action, suggested_target, conflict_reason
3. User reviews and confirms/overrides each field decision
4. POST /api/proposals/{id}/migrate/  { migration_id: ..., confirmed: true }
5. Server executes atomically:
   a. Create new Proposal under target call / version
   b. For MAP entries: copy FieldValue (run type-compat check first)
   c. For OVERFLOW entries: write to new_proposal.overflow_data
   d. For DISCARD entries: skip
   e. Recursively migrate SubmodelInstance children
   f. Mark old proposal status as MIGRATED (new Status choice)
   g. Set ProposalMigration.executed_at
```

### 5.4 Type-compatibility during MAP

If source and target fields have different `data_type`, the migration executor
checks the permitted-conversion table (§2.1). Incompatible pairs are rejected
at the preview step with `conflict_reason` set; the user must choose DISCARD or
OVERFLOW instead.

---

### 5.5 Bulk migration plan

Used for trigger cases 3 (shared config republish) and 4 (call config switch).
Staff configures one field mapping; the system applies it to every affected
proposal, each of which gets its own `ProposalMigration` record for audit.

**Models**

```python
class BulkMigrationPlan(HistoricalMetaBase):
    class Status(models.TextChoices):
        DRAFT    = "draft"    # field mappings being configured
        RUNNING  = "running"  # execution in progress (locked)
        DONE     = "done"     # all proposals migrated
        PARTIAL  = "partial"  # completed with some per-proposal failures

    source_version   = models.ForeignKey(ConfigVersion, on_delete=models.PROTECT,
                                         related_name="+")
    target_version   = models.ForeignKey(ConfigVersion, on_delete=models.PROTECT,
                                         related_name="+")
    # Non-null for trigger 4 (call config switch): restricts execution to proposals
    # under this call only. Null for trigger 3: applies across all calls.
    call_filter      = models.ForeignKey(Call, on_delete=models.SET_NULL,
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
    action       = models.CharField(max_length=10, choices=ProposalMigration.Action)
    target_field = models.ForeignKey(FieldDefinition, on_delete=models.PROTECT,
                                     null=True, blank=True, related_name="+")
```

**Trigger 3 — Config republish**

When `ConfigVersion.publish()` runs on a `FieldConfig` used by one or more calls:
1. Query all distinct `config_version` values among proposals whose call references
   this `FieldConfig` and whose `config_version` is not the new published version.
2. For each distinct old version, automatically create a `BulkMigrationPlan`
   (`source_version=old, target_version=new, call_filter=None`).
3. Surface the plans in the staff UI as "N proposals need migration" badges on the
   `FieldConfig` detail page.

**Trigger 4 — Call config switch**

When `Call.field_config` is changed (via `PATCH /api/calls/{id}/` with a new
`field_config_id`):
1. The API refuses to commit the change while any existing proposals under the call
   are on a different `FieldConfig` without a confirmed `BulkMigrationPlan`.
2. Staff first previews the mapping: `POST /api/bulk-migrations/preview/` with
   `source_version`, `target_version`, and `call_filter`.
3. Staff creates the plan with confirmed field mappings.
4. Staff executes the plan; only then can the `Call.field_config` be changed.
5. The field_config change and the plan execution are wrapped in the same
   `transaction.atomic()` so a failed execution rolls back the assignment.

If a call currently has no proposals, step 1–4 are skipped and the assignment
takes effect immediately.

**Execution**

```
POST /api/bulk-migrations/{id}/execute/
  server-side, inside transaction.atomic():
    1. Lock the plan row (SELECT FOR UPDATE) to prevent concurrent runs.
    2. Set status = RUNNING, total_proposals = count of affected proposals.
    3. For each affected Proposal (batched):
         a. Create ProposalMigration(bulk_plan=plan, ...).
         b. Copy BulkMigrationFieldMapping entries → MigrationFieldMapping.
         c. Execute single-proposal migration (§5.3 steps 5a–5g).
         d. Increment done_proposals or failed_proposals.
    4. Set status = DONE or PARTIAL.
```

The preview endpoint (`GET /api/bulk-migrations/{id}/preview/`) returns the
same per-field mapping format as the single-proposal preview, plus an
`affected_proposal_count` field and a breakdown by call (when `call_filter` is null).

**Stale-proposal count query** (used for badges in the staff UI)

```python
# Proposals whose config version does not belong to their call's current FieldConfig.
stale = Proposal.objects.exclude(
    config_version__config=models.F("call__field_config")
).select_related("call__field_config", "config_version__config")
```

---

## 6. API Endpoints

All endpoints require authentication. Permission logic mirrors the existing
`Proposal.has_object_permission` pattern, moved to `ProposalNode`.

### FieldConfig (staff-only write)

`FieldConfig` objects are independent resources — not nested under a call.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/configs/` | List all FieldConfigs (staff) |
| `POST` | `/api/configs/` | Create a new FieldConfig |
| `GET` | `/api/configs/{cid}/` | Retrieve metadata (name, description, calls using it, stale-proposal count) |
| `PATCH` | `/api/configs/{cid}/` | Update name / description |
| `DELETE` | `/api/configs/{cid}/` | Delete only if no calls reference it and no proposals exist |
| `GET` | `/api/configs/{cid}/versions/` | List all ConfigVersions |
| `GET` | `/api/configs/{cid}/versions/published/` | Active published version as JSON schema |
| `GET` | `/api/configs/{cid}/versions/draft/` | Current draft (staff) |
| `PUT` | `/api/configs/{cid}/versions/draft/` | Replace draft field definitions |
| `POST` | `/api/configs/{cid}/versions/draft/publish/` | Publish draft → auto-creates BulkMigrationPlans for stale proposals |

### Call ↔ FieldConfig assignment

| Method | Path | Description |
|---|---|---|
| `PATCH` | `/api/calls/{id}/` | Change `field_config_id`; blocked if stale proposals exist without a confirmed BulkMigrationPlan |

### Convenience read aliases (call-scoped, for the proposal form frontend)

These are read-only shortcuts; all writes go to `/api/configs/`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/calls/{id}/config/` | Active published config for this call (same shape as `/api/configs/{cid}/versions/published/`) |

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
      "save_rules": { "required": false },
      "submit_rules": { "required": true, "min_length": 50 },
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
      "save_rules": { "required": false, "min_items": 0 },
      "submit_rules": { "required": true, "min_items": 1 },
      "sort_order": 2
    }
  ]
}
```

### User and group autocomplete

These endpoints power the search-as-you-type UI for `USER_SELECT*` and
`GROUP_SELECT*` fields. They are read-only and accessible to any authenticated user.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/users/?q=alice&group_ids=3,7` | Search active users; `group_ids` restricts to those groups (mirrors `type_config.limit_to_group_ids`) |
| `GET` | `/api/groups/?q=workshop` | Search groups |

Both return `[{ "id": …, "display_name"/"name": … }]` and support a `?ids=1,2,3`
param for bulk-resolving already-stored PKs on form load.

### Staging files

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/staging-files/` | Upload a file; returns `staging_id`. Pre-validates MIME/size if `intended_field` is provided |
| `DELETE` | `/api/staging-files/{sid}/` | Delete a staged file early (optional; it expires anyway) |

### Proposals

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/proposals/` | Create draft; binds to call's active published config |
| `GET` | `/api/proposals/{id}/` | Retrieve with all field values and child nodes |
| `PATCH` | `/api/proposals/{id}/` | Partial update — only send changed fields (see below) |
| `POST` | `/api/proposals/{id}/submit/` | Submit (submit-validates) |
| `DELETE` | `/api/proposals/{id}/` | Delete (DRAFT only, owner only) |
| `GET` | `/api/proposals/{id}/history/` | Edit history (EditGroups + FieldEdits, newest first) |

### PATCH payload — partial update format

Only fields the user explicitly changed are included. Omitted fields are left
untouched on the server; their stored values — even if another user modified them
in the meantime — are never overwritten.

```jsonc
// PATCH /api/proposals/{id}/
{
  "changed_fields": {
    "abstract":      "New abstract text",
    "duration_days": 3,
    "photo":         { "staging_id": "a1b2c3d4-..." },  // new file
    "internal_notes": null                               // clear the field
  }
}
```

Rules:
- **Omit** a key → field is not touched.
- **`null`** → field value is cleared (and its `FileAttachment` deleted if present).
- **`{ "staging_id": "..." }`** → stage is promoted to `FileAttachment`;
  old attachment is replaced and deleted in the same transaction.
- Any other value → treated as the new scalar value for the field.

The response body always returns the **complete current state** of all fields on
the node (including fields not touched by this save), so the frontend can update
its `savedValue` store without a separate GET.

### Submodel instances (nested endpoints)

Each submodel operation creates its own `EditGroup` on the child node and sets
`root_proposal` so it appears in the proposal's history.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/proposals/{id}/nodes/` | Create child SubmodelInstance (NODE_ADDED edit recorded) |
| `PATCH` | `/api/proposals/{id}/nodes/{nid}/` | Partial update of child (same format as proposal PATCH) |
| `DELETE` | `/api/proposals/{id}/nodes/{nid}/` | Delete child (NODE_REMOVED edit recorded) |

### Single-proposal migration

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/proposals/{id}/migration-preview/` | Preview with `?target_call=` or `?target_version=` |
| `POST` | `/api/proposals/{id}/migrate/` | Execute confirmed single-proposal migration |

### Bulk migration (config switch / republish)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/bulk-migrations/preview/` | Suggest field mapping for `{ source_version, target_version, call_filter? }`; returns `affected_proposal_count` |
| `POST` | `/api/bulk-migrations/` | Create a `BulkMigrationPlan` with confirmed field mappings |
| `GET` | `/api/bulk-migrations/{id}/` | Retrieve plan and current progress counters |
| `POST` | `/api/bulk-migrations/{id}/execute/` | Execute; returns immediately, plan status polled via GET |

---

## 7. Frontend Integration

The JS frontend receives a **config schema** (see §6 JSON shape) and a
**proposal payload** (field values keyed by `field_id`). It is responsible for:

- Rendering each field by `data_type` (text, markdown editor, WYSIWYG, date
  picker, file drop zone, submodel list/table, etc.).
- Tracking per-field edit state (see §11).
- Sending only the changed fields on save (see §12).
- Showing per-field errors returned by the API (`400` with field-keyed
  `errors` object).
- Rendering the migration mapping UI when the user initiates a migration.
- Displaying the edit history timeline (see §13).
- For `USER_SELECT*` and `GROUP_SELECT*` fields: driving a search-as-you-type
  autocomplete via `GET /api/users/` or `GET /api/groups/`. On form load, bulk-resolve
  any already-stored PKs with `?ids=…` to display names without a query per value.

The frontend should request the config schema once per page load and cache it
for the session; config changes only take effect for newly created proposals.

### History endpoint response shape

```jsonc
// GET /api/proposals/{id}/history/
{
  "results": [
    {
      "id": 99,
      "saved_at": "2026-05-30T14:32:11Z",
      "saved_by": { "id": 5, "display_name": "Alice" },
      "node_id": 12,
      "node_type": "proposal",          // or "submodel:<slug>"
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
POST /api/staging-files/
  body: multipart { file, intended_field?, intended_node? }
  → 201 { "staging_id": "uuid", "original_name": "...", "mime_type": "...", "size_bytes": ... }
      │
      │  Frontend shows local preview via URL.createObjectURL(file)
      │  (no server round-trip needed for the visual preview)
      │
      │  User edits other fields...
      │
      ▼
PATCH /api/proposals/{id}/
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
`DELETE /api/staging-files/{sid}/`.

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

The PATCH handler on `ProposalNode` applies **field-level last-write-wins** inside a
single `transaction.atomic()` block. Locks are acquired **before** validation so that
the validated state is guaranteed to still hold when the write executes. See §14 for
the full locking design.

1. Parse `changed_fields` from the request body.
2. Open `transaction.atomic()`.
3. **Acquire locks** (see §14.3):
   a. Lock the root `Proposal` row (`SELECT FOR UPDATE NOWAIT`).
   b. If editing a `SubmodelInstance`, also lock its `ProposalNode` row.
   c. Compute the validation lock set from `changed_fields` and the multi-field
      rules that reference them.
   d. Lock all existing `FieldValue` rows in the lock set, ordered by PK.
4. Load current `FieldValue` rows under the acquired locks (these are the `old_value`
   entries for history).
5. Run `validate_for_save()` — now authoritative because all relevant rows are locked.
6. Apply writes (create/update/delete `FieldValue` rows, promote staging files).
7. Create `EditGroup` + `FieldEdit` rows for fields whose value actually changed.
8. Return the complete current state of **all** fields on the node.

Fields absent from `changed_fields` are never written; concurrent edits by another
user to those fields are preserved exactly as-is.

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
may optionally send `DELETE /api/staging-files/{sid}/` as a courtesy cleanup.

### Dirty-state indicator

The form header shows a "unsaved changes" badge whenever any field has
`isModified = true`. The save button sends a single PATCH with all currently
modified fields collected into `changed_fields`. Fields with `isModified = false`
are never included.

---

## 13. Edit History

### Display model

The history timeline groups changes by `EditGroup` (one group per save call).
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

Submodel edits appear inline under the proposal history but are labelled with
the submodel type and display name so they are identifiable without navigating
to the child node.

### API pagination

```jsonc
// GET /api/proposals/{id}/history/?page=1&page_size=20
{
  "count": 42,
  "next": "/api/proposals/7/history/?page=2&page_size=20",
  "results": [ ... ]   // EditGroups with nested FieldEdits, newest first
}
```

### History for submitted proposals

`EditGroup` rows created after `Proposal.status` transitions to SUBMITTED are
preserved for audit. They are readable by proposal owners and by staff, not by
reviewers.

### Rich-text / markdown diffs

For `TEXT_MARKDOWN` and `TEXT_RICHTEXT` fields the history stores the full
`old_value` and `new_value` strings. The frontend is responsible for rendering
a character-level or line-level diff if desired; the server returns raw strings.

---

## 14. Concurrent Write Safety (Pessimistic Locking)

### 14.1 Threat model

Without locking, validation that passes before a write can be invalidated by a
concurrent transaction that commits between the validation and the write. Concrete
races to prevent:

| Race | Description |
|---|---|
| **Status-then-edit** | User A validates that editing field X is permitted (proposal is DRAFT). User B transitions the proposal to SUBMITTED. User A writes field X — the edit should now be rejected but A's validation result is stale. |
| **Multi-field inconsistency** | Field rule: "at least one of A, B must be non-empty." User A reads B=filled, concludes clearing A is safe, starts writing A. User B concurrently clears B. Both writes succeed; the rule is now violated. |
| **Submit-then-edit** | Submit validation reads all fields and passes. A concurrent field edit changes a field to an invalid value before the status is written. Proposal transitions to SUBMITTED with invalid data. |

**Approach: pessimistic locking.** Every write operation acquires `SELECT FOR UPDATE`
row locks before running any validation, holds them through the write, and releases
them only when the transaction commits. Validation is never cached across a transaction
boundary.

### 14.2 Deadlock prevention — consistent lock order

All code that acquires multiple row locks must do so in this fixed order:

1. Root `Proposal` rows — ordered by PK ascending
2. `SubmodelInstance` / `ProposalNode` rows — ordered by PK ascending
3. `FieldValue` rows — ordered by PK ascending

Any path that deviates from this order risks a deadlock.

### 14.3 Lock sets per operation

#### PATCH (save field values on any node)

```python
with transaction.atomic():
    # 1. Root proposal — always first
    proposal = Proposal.objects.select_for_update(nowait=True).get(pk=root_proposal_id)

    # 2. Node being edited (only when it's a SubmodelInstance, not the proposal itself)
    if node_id != proposal.proposalnode_ptr_id:
        ProposalNode.objects.select_for_update(nowait=True).get(pk=node_id)

    # 3. Validation lock set: changed fields + all fields touched by any multi-field
    #    save-rule that references at least one changed field
    lock_slugs = _compute_validation_lock_set(changed_slugs, proposal.config_version)

    # 4. Lock existing FieldValue rows in PK order (non-existent rows are covered
    #    by the proposal lock + UniqueConstraint insert-serialisation; see §14.5)
    list(FieldValue.objects.select_for_update(nowait=True)
         .filter(node_id=node_id, field__slug__in=lock_slugs)
         .order_by("pk"))

    # 5. Validate under lock, then write
    node.validate_for_save(context_fields=changed_slugs)
    # ... apply writes, create EditGroup ...
```

#### POST /submit

```python
with transaction.atomic():
    proposal = Proposal.objects.select_for_update(nowait=True).get(pk=proposal_id)

    # Lock all descendant SubmodelInstance rows
    list(ProposalNode.objects.select_for_update(nowait=True)
         .filter(parent_node__in=proposal.all_node_pks())
         .order_by("pk"))

    # Lock all FieldValue rows across the whole proposal tree
    list(FieldValue.objects.select_for_update(nowait=True)
         .filter(node__in=proposal.all_node_pks())
         .order_by("pk"))

    # Validate under full lock, then transition status
    proposal.validate_for_submit()
    proposal.status = Proposal.Status.SUBMITTED
    proposal.save()
```

#### Status transitions (accept / reject / revise)

```python
with transaction.atomic():
    proposal = Proposal.objects.select_for_update(nowait=True).get(pk=proposal_id)
    # Verify permission + transition; no field data read needed.
    proposal.status = new_status
    proposal.save()
```

Locking the proposal row here prevents a concurrent PATCH from reading the old
status between this transition and the commit.

#### Submodel add / delete

```python
with transaction.atomic():
    proposal = Proposal.objects.select_for_update(nowait=True).get(pk=root_proposal_id)
    # Create or delete SubmodelInstance; validate parent-level min/max_items rules.
```

### 14.4 Validation lock set computation

```python
def _compute_validation_lock_set(
    changed_slugs: set[str],
    config_version: ConfigVersion,
) -> set[str]:
    """
    Return the set of field slugs whose FieldValue rows must be locked before
    save-time validation is authoritative for the given changed fields.
    """
    lock_set = set(changed_slugs)

    # Multi-field save-rules that touch any changed field pull in all their fields.
    rules = (
        MultiFieldValidationRule.objects
        .filter(
            config_version=config_version,
            applies_to_save=True,
            associations__field__slug__in=changed_slugs,
        )
        .prefetch_related("associations__field")
        .distinct()
    )
    for rule in rules:
        for assoc in rule.associations.all():
            lock_set.add(assoc.field.slug)

    return lock_set
```

Single-field rules affect only one field; that field is already in `changed_slugs`
(you can only trigger a single-field rule by changing the field it is attached to),
so no additional fields need to be added for them.

### 14.5 Non-existent FieldValue rows

`SELECT FOR UPDATE` cannot lock a row that does not yet exist. When a field has
never been set, no `FieldValue` row is present to lock. This is safe because:

- The **root Proposal lock** prevents any status transition from racing with the
  INSERT of a new `FieldValue`.
- If two concurrent requests both attempt to INSERT a `FieldValue` for the same
  `(node, field)` pair, the `UniqueConstraint(fields=["node", "field"])` causes
  one to fail with an `IntegrityError`, which the handler retries once or returns
  as a 409.

### 14.6 Lock contention — API response

All `SELECT FOR UPDATE` calls use `nowait=True`. If a lock cannot be immediately
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

### 14.7 Interaction with bulk migration

The `BulkMigrationPlan` executor already holds a `SELECT FOR UPDATE` on the plan
row to prevent concurrent runs (§5.5). For each proposal within a batch, the
executor opens its own `transaction.atomic()` and follows the PATCH lock order
(§14.3) for that proposal. Proposals in a batch are processed sequentially, not
in parallel, to avoid cross-proposal deadlocks.

---

## 9. Implementation Phases

### Phase 1 — Config infrastructure (no UI changes yet)
- [ ] `FieldConfig`, `ConfigVersion`, `FieldDefinition` models + migrations
- [ ] `field_config` FK added to `Call`
- [ ] `SingleFieldValidationRule` root + all concrete single-field subclasses
- [ ] `AllowedMimeTypeEntry` child model
- [ ] `MultiFieldValidationRule` root + `MultiFieldRuleAssociation` + concrete subclasses
- [ ] `ConfigVersion.publish()` atomic method: freezes rules, deep-copies all field defs
      + rules into new DRAFT, auto-creates `BulkMigrationPlan` stubs for stale proposals
- [ ] Config admin (Django admin for staff), including inline rule editing
- [ ] `/api/configs/` CRUD endpoints + `/api/calls/{id}/config/` read alias
- [ ] Config JSON schema includes serialised rules (see §6) so the frontend can display
      rule summaries alongside each field

### Phase 2 — ProposalNode base + FieldValue storage
- [ ] `ProposalNode`, `Proposal` (MTI), `SubmodelInstance` models
- [ ] `FieldValue`, `FileAttachment` models
- [ ] `validate_for_save()` / `validate_for_submit()` on `ProposalNode` using rule model queries
- [ ] `FieldValue.clean()` data-type enforcement
- [ ] Data migration: import all existing hardcoded proposal fields and their implicit
      validation constraints as `SingleFieldValidationRule` instances; convert existing
      `Proposal` / `Speaker` rows into `ProposalNode` + `FieldValue` rows

### Phase 3 — Proposal CRUD API
- [ ] Create / retrieve / update proposal endpoints (partial PATCH semantics from §12)
- [ ] Lock acquisition in every write path per §14.3 (`select_for_update(nowait=True)`)
- [ ] `_compute_validation_lock_set()` utility + 409 handler for `OperationalError`
- [ ] Staging file upload endpoint + `cleanup_staging_files` management command
- [ ] File staging → promotion flow within PATCH transaction
- [ ] Submodel nested endpoints (create / partial-update / delete) with root proposal lock
- [ ] Submit endpoint: full-tree lock → submit-validates → status transition (§14.3)
- [ ] Status transition endpoints: proposal lock only
- [ ] Edit history models (`EditGroup`, `FieldEdit`) created alongside each PATCH
- [ ] History list endpoint (`GET /api/proposals/{id}/history/`)

### Phase 4 — Migration system
- [ ] `ProposalMigration` + `MigrationFieldMapping` models (with `bulk_plan` FK)
- [ ] `BulkMigrationPlan` + `BulkMigrationFieldMapping` models
- [ ] Single-proposal migration preview + execute API
- [ ] Bulk migration preview + create + execute API
- [ ] Call config-switch guard (reject PATCH if stale proposals exist without a confirmed plan)
- [ ] Stale-proposal count query wired into `FieldConfig` detail and `Call` detail responses
- [ ] Overflow data admin view

### Phase 5 — Config versioning UI
- [ ] Draft editing UI (staff), including FieldConfig create/edit/assign to calls
- [ ] Rule editor UI: add / edit / delete / copy single-field rules per field;
      add / edit / delete multi-field rules per version with field picker
- [ ] Publish flow with diff preview (includes rule changes) + bulk migration plan notice
- [ ] Datatype-change dry-run endpoint
- [ ] Bulk migration mapping UI (shared by republish and config-switch flows)
- [ ] Per-proposal config version upgrade flow (re-uses single-proposal migration UI)

---

## 10. Open Questions / Decisions Deferred

| Question | Notes |
|---|---|
| Should `Proposal` keep its existing `Status` workflow? | The existing accept/reject/revise flow can remain on `Proposal`; `ProposalNode` only needs DRAFT/SUBMITTED for validation gating |
| Rich-text sanitisation library | `bleach` or `nh3`; must be decided before `TEXT_RICHTEXT` type is implemented |
| Max nesting depth | No hard limit in the model, but the UI should warn beyond 2 levels |
| Full-text search across FieldValues | Out of scope for initial implementation; JSONField values can be indexed later with `SearchVector` if needed |
| Staging file storage location | Should staged files use the same backend as committed files, or a separate bucket/path with cheaper/shorter retention settings? |
| Bulk migration execution mode | The plan shows execution as synchronous (request blocks until done). For large proposal sets this should move to a background task (Celery). Decide the threshold before implementing. |
| Config-switch atomicity vs. partial failure | If a `BulkMigrationPlan` execution partly fails (some proposals error), the call's `field_config` is not changed (the outer transaction rolls back). Decide whether a PARTIAL outcome should still commit the successful migrations and allow the switch, or always roll back entirely. |
| FieldConfig deletion guard | A `FieldConfig` can only be deleted if no calls reference it and no proposals exist on any of its versions. Decide whether orphaned archived versions (no living proposals) should be auto-deletable or require explicit cleanup. |
| Rule applicability checking | `SingleFieldValidationRule` subclasses are only meaningful on certain `data_type`s (e.g. `MinLengthRule` makes no sense on a `BOOLEAN` field). Decide whether to enforce compatible (rule type, field type) pairs at the DB level (a check constraint or custom `clean()`) or only in the admin UI. |
| Multi-field rule cross-version integrity | `MultiFieldRuleAssociation` must only reference `FieldDefinition`s that belong to the same `ConfigVersion` as the rule. This is enforced at the application level. Decide whether a DB-level constraint (e.g. a trigger or a generated FK via an intermediate denormalised column) is worth the complexity. |
| SQLite compatibility | `SELECT FOR UPDATE NOWAIT` and `SELECT FOR UPDATE` are PostgreSQL features; SQLite (used in tests via `db.sqlite3`) does not support them. All locking code must be wrapped in a `connection.features.has_select_for_update` guard or replaced with a no-op in tests. Confirm the production DB is PostgreSQL before implementing §14. |
| History retention policy | Edit history is currently kept forever. A retention limit (e.g. keep last N groups, or purge groups older than X years) may be needed for GDPR compliance. |
| File diff in history | The plan stores filenames only for file edits. If users need to view the previous version of an image or file, old `FileAttachment` rows would need to be retained rather than deleted on replace. Decide before implementing the promotion step. |
