package udm

import rego.v1

# ─── allow ────────────────────────────────────────────────────────────────────
# Allow staff unconditionally; allow others only on view/save.
allow if {
    input.user.is_staff
}

allow if {
    input.action in {"view", "save"}
    input.user.is_active
}

# ─── deny ─────────────────────────────────────────────────────────────────────
# deny entries block the action and are merged into messages.
deny contains msg if {
    input.action == "save"
    not input.user.is_staff
    not _in_group("editors")
    msg := {"level": "error", "text": "Only staff or editors may save this record."}
}

# ─── messages (save-time validation) ──────────────────────────────────────────
# Warnings and errors on save. Errors with level "critical"/"error" block
# the transition engine; level "warning" is advisory only.

messages contains msg if {
    input.action == "save"
    cf := input.changed_fields
    cf != null
    name := object.get(cf, ["proposal_name2", "value"], null)
    name != null
    count(name) < 3
    msg := {
        "level": "error",
        "field": "proposal_name2",
        "text": "Proposal name must be at least 3 characters.",
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
        "field": "singleselect",
        "text": "Option 'singleselect2' is reserved for staff. Your selection has been noted.",
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
        "field": "date",
        "text": "Date must not be before 2024.",
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
        "field": "groupselectmulti",
        "text": "More than 3 groups selected — please confirm this is intentional.",
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
