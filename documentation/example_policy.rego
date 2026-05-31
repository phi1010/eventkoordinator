package udm

import rego.v1

# ─── allow ────────────────────────────────────────────────────────────────────
# Allowed when the user is active, the action is permitted, and no critical
# messages were produced.
allow if {
    input.action == "view"
}

allow if {
    input.action == "transition"
    input.user.is_staff
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
        "field_slug": "groupselectmulti",
    }
}

messages contains msg if {
    input.action == "view"
    not input.user.is_staff
    msg := {
        "level": "info",
        "text": "You have limited access to this proposal.",
    }
}
messages contains msg if {
    input.action == "transition"
    msg := {
        "level": "info",
        "text": "You might have transitioned this proposal.",
    }
}

messages contains msg if {
    input.action == "save"
    not input.user.is_staff
    msg := {
        "level": "warning",
        "text": "You cannot edit this proposal; your changes will not be saved.",
    }
}

messages contains msg if {
    smid := input.entity.fields.submodel.value
    submodel := input.entity.children.submodel[_]
    submodel.id == smid
    submodel.fields.int.value > 100
    msg := {
        "level": "error",
        "text": "Value in submodel is greater than 100.",
        "field_slug": "submodel",
    }
}
messages contains msg if {
    smid := input.entity.fields.submodel.value
    submodel := input.entity.children.submodel[_]
    submodel.id == smid
    submodel.fields.int.value > 1000
    msg := {
        "level": "critical",
        "text": "Value in submodel is greater than 1000.",
        "field_slug": "submodel",
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

all_fields contains field if {
    input.entity.fields[field]
}

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
