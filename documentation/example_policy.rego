package udm

import rego.v1

# ─── allow ────────────────────────────────────────────────────────────────────
# Allowed when the user is active, the action is permitted, and no critical
# messages were produced.
allow if {
    input.user.is_active
    input.action in {"view", "save"}
    no_critical_messages
}

allow if {
    input.user.is_staff
    no_critical_messages
}

no_critical_messages if {
    count([m | some m in messages; m.level == "critical"]) == 0
}

# ─── messages ─────────────────────────────────────────────────────────────────
# All validation feedback lives here. level "critical" blocks the action;
# level "error" blocks transitions; level "warning" is advisory only.

messages contains msg if {
    input.action == "save"
    not input.user.is_staff
    not _in_group("editors")
    msg := {
        "level": "critical",
        "text": "Only staff or editors may save this record.",
    }
}

messages contains msg if {
    input.action == "save"
    cf := input.changed_fields
    cf != null
    name := object.get(cf, ["proposal_name2", "value"], null)
    name != null
    count(name) < 3
    msg := {
        "level": "error",
        "text": "Proposal name must be at least 3 characters.",
        "highlight_fields": ["proposal_name2"],
    }
}

messages contains msg if {
    input.action == "save"
    cf := input.changed_fields
    cf != null
    sel := object.get(cf, ["singleselect", "value"], null)
    sel == "singleselect2"
    not input.user.is_staff
    msg := {
        "level": "warning",
        "text": "Option 'singleselect2' is reserved for staff. Your selection has been noted.",
        "highlight_fields": ["singleselect"],
    }
}

messages contains msg if {
    input.action == "save"
    cf := input.changed_fields
    cf != null
    dt := object.get(cf, ["date", "value"], null)
    dt != null
    # dates arrive as ISO strings "YYYY-MM-DD"
    dt < "2024-01-01"
    msg := {
        "level": "error",
        "text": "Date must not be before 2024.",
        "highlight_fields": ["date"],
    }
}

messages contains msg if {
    input.action == "save"
    cf := input.changed_fields
    cf != null
    groups := object.get(cf, ["groupselectmulti", "value"], null)
    groups != null
    count(groups) > 3
    msg := {
        "level": "warning",
        "text": "More than 3 groups selected — please confirm this is intentional.",
        "highlight_fields": ["groupselectmulti"],
    }
}

# Cross-field example: highlight both the date and a submodel sub-field.
# "submodel.int" highlights the "int" field inside the submodel_select child.
messages contains msg if {
    input.action == "save"
    dt := object.get(input.entity.fields, ["date", "value"], null)
    si := object.get(input.entity.fields, ["submodel", "value"], null)
    dt != null
    si != null
    # find the selected child and compare
    some child in input.entity.children.submodel
    child.id == si
    child.fields.int.value > 100
    msg := {
        "level": "error",
        "text": "Submodel int must not exceed 100 when a date is set.",
        "highlight_fields": ["date", "submodel.int"],
    }
}

# ─── viewable_fields ──────────────────────────────────────────────────────────
# Staff see everything; regular users see a restricted subset.

viewable_fields := all_fields if {
    input.user.is_staff
}

viewable_fields := restricted_fields if {
    not input.user.is_staff
}

all_fields := [
    "proposal_name2",
    "submodel",
    "submodel_list",
    "markdown",
    "date",
    "datetime",
    "time",
    "singleselect",
    "entity",
    "groupselectmulti",
    "image",
    "file",
    "shorttext",
]

restricted_fields := [
    "proposal_name2",
    "markdown",
    "date",
    "datetime",
    "time",
    "singleselect",
    "image",
    "file",
    "shorttext",
]

# ─── editable_fields ──────────────────────────────────────────────────────────
# Staff can edit everything; editors get a subset; others read-only.

editable_fields := all_fields if {
    input.user.is_staff
}

editable_fields := editor_fields if {
    not input.user.is_staff
    _in_group("editors")
}

editable_fields := [] if {
    not input.user.is_staff
    not _in_group("editors")
}

editor_fields := [
    "proposal_name2",
    "markdown",
    "date",
    "datetime",
    "time",
    "singleselect",
    "shorttext",
]

# ─── helpers ──────────────────────────────────────────────────────────────────

_in_group(name) if {
    some g in input.user.groups
    g.name == name
}
