"""
Workflow transition engine (§15) and policy evaluation (§16).
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

if TYPE_CHECKING:
    from userdefinedmodel.models import (
        UserDefinedModelEntityNode,
        UserDefinedModelEntity,
        WorkflowTransition,
    )
    from openid_user_management.models import OpenIDUser

logger = logging.getLogger(__name__)

# regorus renders an undefined rule result as this JSON string. It must never be
# treated as a truthy value (bool("<undefined>") is True), or deny-by-default fails open.
_UNDEFINED = "<undefined>"


# ─── Policy evaluation (§16) ──────────────────────────────────────────────────

def build_policy_input(node: "UserDefinedModelEntityNode", user: "OpenIDUser", action: str, **kwargs) -> dict:
    """Build the input document passed to regorus for a given action.

    For SAVE action, pass changed_fields=<incoming_dict> so Rego can see both
    the new entity state (input.entity, post-write) and which fields changed
    (input.changed_fields, each wrapped as {"value": ...}).
    """
    policy_doc = node.to_policy_document()
    logger.debug("build_policy_input node=%s action=%s user=%s", node.id, action, user.username)

    user_doc = {
        "id": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "groups": list(user.groups.values("id", "name")),
        "permissions": list(user.user_permissions.values_list("codename", flat=True)),
    }

    input_doc = {
        "action": action,
        "entity": policy_doc,      # current (old) values + unchanged fields
        "user": user_doc,
        "type_id": policy_doc.get("type_id"),
        "changed_fields": None,    # overridden for SAVE action
        "transition": None,        # overridden for TRANSITION action
        "field": None,
        **kwargs,
    }
    return input_doc


def get_udm_type_for_node(node: "UserDefinedModelEntityNode"):
    """Return the UserDefinedModelType for a node (root or submodel)."""
    try:
        return node.userdefinedmodelentity.user_defined_model_type
    except Exception:
        root = node.get_root()
        return root.user_defined_model_type if root else None


def evaluate_policy(node: "UserDefinedModelEntityNode", user: "OpenIDUser", action: str, **kwargs) -> dict:
    """Evaluate all policies for node's UDMType; return PolicyOutput dict.

    Default-deny: if the node has no UDMType, or its type has no policies attached,
    nothing is permitted and no fields are exposed. Access must be granted by an
    explicit policy clause.
    """
    udm_type = get_udm_type_for_node(node)
    if udm_type is None:
        return {"allow": False, "messages": [], "viewable_fields": [], "editable_fields": []}

    from userdefinedmodel.models import UserDefinedModelTypePolicy
    type_policies = list(
        udm_type.type_policies.select_related("policy").order_by("sort_order")
    )
    if not type_policies:
        return {"allow": False, "messages": [], "viewable_fields": [], "editable_fields": []}

    try:
        import regorus
        eng = regorus.Engine()
        for tp in type_policies:
            logger.debug("loading policy slug=%s for node=%s", tp.policy.slug, node.id)
            eng.add_policy(f"policy_{tp.policy.slug}.rego", tp.policy.source)

        input_doc = build_policy_input(node, user, action, **kwargs)
        logger.debug("policy input node=%s action=%s: %s", node.id, action, json.dumps(input_doc))
        eng.set_input_json(json.dumps(input_doc))

        def _eval_list(rule_path: str, default=None):
            """Evaluate a Rego rule that should return a list; return default on undefined."""
            try:
                raw = json.loads(eng.eval_rule_as_json(rule_path))
                if isinstance(raw, list):
                    return raw
                return default  # includes the "<undefined>" sentinel
            except Exception:
                return default

        def _eval_bool(rule_path: str, default: bool = True) -> bool:
            """Evaluate a Rego rule that should return a bool; return default on undefined."""
            try:
                raw = json.loads(eng.eval_rule_as_json(rule_path))
                # regorus serializes an undefined rule (no matching clause) as the
                # JSON string "<undefined>". Treat it as the default — NOT as a
                # truthy non-empty string — so deny-by-default actually denies.
                if raw is None or raw == _UNDEFINED:
                    return default
                if isinstance(raw, list):
                    return bool(raw[0]) if raw else default
                return bool(raw)
            except Exception:
                return default

        # Deny by default: undefined allow rule = false (secure by default)
        allow = _eval_bool("data.udm.allow", default=False)
        messages = _eval_list("data.udm.messages", default=[])
        viewable_fields = _eval_list("data.udm.viewable_fields", default=None)
        editable_fields = _eval_list("data.udm.editable_fields", default=[])

        result = {
            "allow": allow,
            "messages": messages,
            "viewable_fields": viewable_fields,
            "editable_fields": editable_fields,
        }
        logger.debug(
            "policy result node=%s action=%s allow=%s messages=%d viewable=%s editable=%s",
            node.id, action, allow, len(messages),
            viewable_fields, editable_fields,
        )
        return result
    except Exception as exc:
        logger.exception("Policy evaluation failed: %s", exc)
        return {"allow": False, "messages": [], "viewable_fields": [], "editable_fields": []}


# ─── Policy / transition exceptions ──────────────────────────────────────────

class PolicyError(Exception):
    """Raised when policy blocks a save. Carries the full messages list so the
    API can return structured highlight information to the frontend."""
    def __init__(self, messages: list):
        super().__init__("Save blocked by policy")
        self.messages = messages


class TransitionError(Exception):
    """Raised when a workflow transition cannot proceed."""
    def __init__(self, message: str, http_status: int = 422, details=None):
        super().__init__(message)
        self.http_status = http_status
        self.details = details or {}


def execute_transition(node: "UserDefinedModelEntityNode", name: str, user: "OpenIDUser") -> None:
    """
    Execute a named workflow transition on `node` (§15.1).
    Must be called inside an existing transaction.atomic() with the root lock held.
    """
    from userdefinedmodel.models import WorkflowTransition, WorkflowState
    from userdefinedmodel.models.history import EditGroup, FieldEdit

    # 2. Load transition
    if node.config_version.workflow_id is None:
        raise TransitionError(f"No workflow defined for this node's config version.", http_status=404)

    try:
        transition = WorkflowTransition.objects.get(
            workflow=node.config_version.workflow, name=name
        )
    except WorkflowTransition.DoesNotExist:
        raise TransitionError(f"Transition '{name}' not found.", http_status=404)

    # 3. Check from_state
    if transition.from_state is not None:
        if node.current_state_id != transition.from_state_id:
            current = node.current_state.name if node.current_state else "None"
            raise TransitionError(
                f"Node is in state '{current}', but transition '{name}' requires '{transition.from_state.name}'.",
                http_status=409,
            )

    # 4. Evaluate policy
    output = evaluate_policy(node, user, "transition", transition=name)
    if not output["allow"]:
        raise TransitionError(f"Policy denied transition '{name}'.", http_status=403)

    blocking_messages = [
        m for m in output["messages"]
        if isinstance(m, dict) and m.get("level") in ("critical", "error")
    ]

    # 5. Execute PRE-phase actions
    from userdefinedmodel.models.workflow import TransitionAction
    pre_actions = list(transition.actions.filter(phase=TransitionAction.Phase.PRE).order_by("sort_order"))
    for action in pre_actions:
        action.get_real_instance().execute(node, user)

    # 6. Subtree validation (save-rule floor)
    _validate_subtree(node)

    # Check blocking policy messages after subtree validation
    if blocking_messages:
        raise TransitionError(
            "Transition blocked by policy.",
            http_status=422,
            details={"messages": blocking_messages},
        )

    # 9. Apply state change
    old_state_name = node.current_state.name if node.current_state else None
    node.current_state = transition.to_state
    node.save(update_fields=["current_state"])

    # Record transition in history
    root_entity = None
    try:
        root_entity = node.userdefinedmodelentity
    except Exception:
        root = node.get_root()
        root_entity = root

    edit_group = EditGroup.objects.create(
        node=node,
        root_entity=root_entity,
        saved_by=user,
    )
    FieldEdit.objects.create(
        group=edit_group,
        change_kind=FieldEdit.ChangeKind.NODE_TRANSITION,
        affected_node=node,
        old_value={"state": old_state_name},
        new_value={"state": transition.to_state.name},
    )

    # 10. Execute POST-phase actions (failures logged, don't roll back)
    post_actions = list(transition.actions.filter(phase=TransitionAction.Phase.POST).order_by("sort_order"))
    for action in post_actions:
        try:
            action.get_real_instance().execute(node, user)
        except Exception as exc:
            logger.warning("Post-transition action %s failed: %s", action.pk, exc)


def _validate_subtree(node: "UserDefinedModelEntityNode") -> None:
    """Re-run save rules on every node in the subtree (§4)."""
    from django.core.exceptions import ValidationError
    try:
        node.validate_for_save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, "message_dict") else {"__all__": exc.messages}
        raise TransitionError(
            "Subtree validation failed",
            http_status=422,
            details={"field_errors": errors},
        )
    for child in node.children.all():
        _validate_subtree(child)
