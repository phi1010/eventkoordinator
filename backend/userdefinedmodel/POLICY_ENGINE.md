# Policy Engine — Input & Output Reference

Policies are [Rego](https://www.openpolicyagent.org/docs/latest/policy-language/) programs evaluated by the
[regorus](https://github.com/microsoft/regorus) engine. All rules live under the `data.udm` package. Every
policy evaluation receives one JSON input document. The structure of that document varies by action.

---

## 1. Policy evaluation actions

| Action | Triggered by | Extra top-level keys |
|---|---|---|
| `view` | `GET /entities/{id}/` and history endpoint | — |
| `browse` | `GET /entity-search/` | — |
| `save` | `PATCH /entities/{id}/` (after writes are flushed) | `changed_fields` |
| `delete` | `DELETE /entities/{id}/` | — |
| `transition` | `POST /entities/{id}/transition/` | `transition`, `field` |

---

## 2. Common input document shape

Every action receives the following top-level structure.

```json
{
  "action": "<string>",
  "entity": { /* EntityDocument — see §3 */ },
  "user": { /* UserDocument — see §4 */ },
  "type_id": "<uuid | null>",
  "changed_fields": null,
  "transition": null,
  "field": null
}
```

`type_id` is a convenience copy of `entity.type_id` — the UUID of the `UserDefinedModelType`.

The `changed_fields`, `transition`, and `field` keys are always present but are `null` unless the action
populates them (see §5, §6).

---

## 3. EntityDocument (`input.entity`)

Built by `UserDefinedModelEntityNode.to_policy_document()`.

### 3.1 Root entity

```json
{
  "id": "<uuid>",
  "type": "entity",
  "config_version_id": "<uuid>",
  "config_id": "<uuid>",
  "type_id": "<uuid | null>",
  "fields": { /* FieldsMap — see §3.3 */ },
  "children": { /* ChildrenMap — see §3.4 */ },
  "overflow_data": { /* arbitrary JSON from archived fields */ },
  "created_at": "<ISO-8601>",
  "updated_at": "<ISO-8601>"
}
```

### 3.2 Submodel node

When the policy engine recurses into a child node (submodel), `to_policy_document()` is also called on the
child. The child document has the same shape except:

- `type` is `"submodel:<parent_field_slug>"` instead of `"entity"`.
- `type_id` is `null` — this is only set on root entities.

### 3.3 FieldsMap (`input.entity.fields`)

A dictionary keyed by field slug. Each entry describes the current stored value of that field.

**Non-localized field:**
```json
{
  "<slug>": {
    "data_type": "<DataType>",
    "localized": false,
    "value": <scalar>
  }
}
```

**Localized field:**
```json
{
  "<slug>": {
    "data_type": "<DataType>",
    "localized": true,
    "value": {
      "en": <scalar>,
      "de": <scalar>
    }
  }
}
```

Only fields that have a stored `FieldValue` row appear in the map. Fields with no saved value are absent.

#### Value encoding by data type

| `data_type` | JSON value type | Notes |
|---|---|---|
| `text_short` | `string` | |
| `text_long` | `string` | |
| `text_markdown` | `string` | |
| `text_richtext` | `string` | HTML-sanitised by nh3 on write |
| `integer` | `number` (int) | |
| `float` | `number` | |
| `boolean` | `boolean` | |
| `date` | `string` | ISO-8601 date `"YYYY-MM-DD"` |
| `time` | `string` | ISO-8601 time `"HH:MM:SS"` |
| `datetime` | `string` | ISO-8601 datetime with timezone |
| `select_single` | `string` | One of the configured choices |
| `select_multi` | `array[string]` | |
| `image` | `string` | UUID of the `FileAttachment` record |
| `file` | `string` | UUID of the `FileAttachment` record |
| `user_select` | `string` | UUID of the `OpenIDUser` record |
| `user_select_multi` | `array[string]` | UUIDs |
| `group_select` | `string` | Integer PK of the Django `Group` record |
| `group_select_multi` | `array[string\|int]` | |
| `submodel_select` | `string` | UUID of the child `UserDefinedModelEntityNode` |
| `entity_select` | `string` | UUID of the `UserDefinedModelEntityNode` |
| `entity_select_multi` | `array[string]` | UUIDs |
| `slug_id` | `number` (int) | Auto-assigned sequence number |
| `workflow` | `string` | Current state `name` |
| `submodel_list` | *(absent)* | No scalar value; child nodes appear in `children` |

### 3.4 ChildrenMap (`input.entity.children`)

A dictionary keyed by field slug (for `submodel_list` and `submodel_select` fields). Each value is an array
of child EntityDocuments (same structure, type = `"submodel:<slug>"`).

```json
{
  "<submodel_list_slug>": [
    { /* child EntityDocument */ },
    { /* child EntityDocument */ }
  ],
  "<submodel_select_slug>": [
    { /* child EntityDocument */ }
  ]
}
```

---

## 4. UserDocument (`input.user`)

```json
{
  "id": "<uuid>",
  "username": "<string>",
  "is_active": true,
  "is_staff": false,
  "groups": [
    { "id": 1, "name": "editors" }
  ],
  "permissions": ["add_entity", "change_entity"]
}
```

`groups` is a list of objects with integer `id` and string `name`. `permissions` is a flat list of
Django permission codenames (not content-type qualified).

---

## 5. Save action — `changed_fields`

When `action == "save"`, the `changed_fields` key contains the fields that were explicitly submitted in
this PATCH request.

All writes (scalar fields and submodel operations) are flushed to the database **within the open
transaction** before policy evaluation runs. This means `input.entity.fields` reflects the **post-write
state**. If the policy denies the save (returns `allow: false` or any `critical` message), the exception
propagates out of `transaction.atomic()` and the entire transaction is rolled back — nothing is permanently
committed. `changed_fields` tells the policy **which** fields were part of this request.

```json
{
  "changed_fields": {
    "<slug>": { "value": <scalar> },
    "<slug>": { "value": <scalar> }
  }
}
```

Each entry wraps the submitted value in `{"value": ...}` using the same scalar encoding as
`input.entity.fields[slug].value`. This means a Rego policy can use the same `.value` path for both
the field map and the changed-fields map.

Fields that were not submitted (unchanged) do not appear in `changed_fields`.

`changed_fields` is the raw submitted payload, so it includes **all** submitted keys:
- Scalar field slugs — value is the new scalar, encoded as above.
- `submodel_list` slugs — value is the raw ops array `[{"op": "create"|"update"|"delete", ...}]` wrapped as `{"value": [...]}`. The child nodes are already written; the `children` key of `input.entity` reflects the result.
- `_`-prefixed control keys (e.g. `_undelete`) — these are skipped by the writer but still appear in `changed_fields` passed to the policy engine.

`workflow` field slugs are never present — the writer raises a `ValidationError` before reaching policy evaluation if one is submitted.

**Example:**
```json
{
  "action": "save",
  "entity": {
    "fields": {
      "title": { "data_type": "text_short", "localized": false, "value": "New title" },
      "status": { "data_type": "select_single", "localized": false, "value": "draft" }
    },
    ...
  },
  "changed_fields": {
    "title": { "value": "New title" }
  },
  ...
}
```

---

## 6. Transition action — `transition` and `field`

When `action == "transition"`, two extra keys are populated:

```json
{
  "action": "transition",
  "transition": "<transition_name>",
  "field": "<workflow_field_slug>",
  ...
}
```

- `transition` — the name of the `WorkflowTransition` being executed (e.g. `"submit"`, `"approve"`).
- `field` — the slug of the workflow field on the node that owns this transition.

The entity snapshot (`input.entity`) reflects the state **before** the transition (the workflow field still
holds the old state name at evaluation time).

**Example:**
```json
{
  "action": "transition",
  "transition": "approve",
  "field": "review_status",
  "entity": {
    "fields": {
      "review_status": { "data_type": "workflow", "localized": false, "value": "pending" }
    },
    ...
  }
}
```

---

## 7. Policy output format

The engine reads four Rego rules from `data.udm`:

| Rego rule | Type | Default when undefined | Meaning |
|---|---|---|---|
| `data.udm.allow` | `boolean` | `false` (deny-by-default) | Gate: is this action permitted at all? |
| `data.udm.messages` | `array[Message]` | `[]` | Advisory / blocking messages to surface to the caller |
| `data.udm.viewable_fields` | `array[string]` | `null` (no restriction) | Field slugs the caller may see; `null` means all fields are visible |
| `data.udm.editable_fields` | `array[string]` | `[]` | Field slugs the caller may edit |

If a rule is undefined (regorus returns the sentinel `"<undefined>"`), the engine uses the default shown
above. An undefined `allow` rule therefore **denies** access — secure by default.

### 7.1 Message object

```json
{
  "level": "critical | error | warning | info | debug",
  "message": { "en": "Human-readable text", "de": "..." },
  "field_slug": "<slug | null>"
}
```

| `level` | Effect |
|---|---|
| `critical` | Blocks the save or transition; the API returns HTTP 422 with the messages list |
| `error` | Blocks a transition (but not a save unless `allow` is false) |
| `warning` | Non-blocking; returned to the frontend in the entity response |
| `info` | Non-blocking |
| `debug` | Non-blocking |

`field_slug` is optional. When set, the frontend can highlight the named field alongside the message.

`message` is a localisation dict. At minimum it should contain one language key.

### 7.2 How the output is consumed

**View / browse:**  
If `allow` is `false`, the entity is not returned (HTTP 404 — avoids existence leaks).  
`viewable_fields` is used to filter the `field_values` and `children` keys before responding.  
`editable_fields` is forwarded to the frontend in the entity response.

**Save:**  
`allow` must be `true` and no message with `level == "critical"` may be present, or the save is
rolled back (HTTP 422).  
Non-critical messages are returned in the response body.

**Transition:**  
`allow` must be `true` and no message with `level in ("critical", "error")` may be present.  
The policy is evaluated before the state is written; a denial leaves the entity unchanged.

**Delete:**  
Only `allow` is checked (HTTP 403 on denial).

### 7.3 Minimal policy example

```rego
package udm

# Allow staff users to do anything
allow if {
    input.user.is_staff
}

# Everyone may view and browse
allow if {
    input.action in {"view", "browse"}
}

# Restrict which fields non-staff users can modify
editable_fields := ["title", "description"] if {
    input.action == "save"
    not input.user.is_staff
}

# Block save if a required workflow field is still in the initial state
messages contains msg if {
    input.action == "save"
    input.entity.fields.review_status.value == "draft"
    msg := {
        "level": "warning",
        "message": {"en": "Document is still in draft — submit for review when ready."},
        "field_slug": "review_status",
    }
}
```

---

## 8. Multiple policies per type

A `UserDefinedModelType` can have multiple `Policy` records attached via `UserDefinedModelTypePolicy`
(ordered by `sort_order`). All policy sources are loaded into the same regorus engine instance before
evaluation. Rules from different files compose via Rego's set-union semantics:

- `allow` — any one file defining `allow := true` makes the overall decision true.
- `messages` — entries from all files are unioned into a single set.
- `viewable_fields` / `editable_fields` — entries from all files are unioned.

If **no** policies are attached to the type, the engine returns the default-deny result without running
any Rego.
