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
# Staff users see an info message for each member of the selected groups,
# showing their email address and phone number.
messages contains msg if {
    input.user.is_staff
    some group in input.entity.fields.groupselectmulti.value
    some u in group.members
    msg := {
        "level": "info",
        "text": sprintf("User %v: email=%v, phone=%v", [u.username, u.email, u.phone_number]),
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
# Staff can edit everything; others are read-only.

editable_fields := all_fields if {
    input.user.is_staff
}

editable_fields := [] if {
    not input.user.is_staff
}
