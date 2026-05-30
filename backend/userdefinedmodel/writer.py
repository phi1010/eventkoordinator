"""
Entity write logic: PATCH handler, submodel operations, file promotion.
All writes go through apply_patch() which runs inside transaction.atomic()
with the root UserDefinedModelEntity lock already held.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now

if TYPE_CHECKING:
    from userdefinedmodel.models import (
        UserDefinedModelEntityNode,
        UserDefinedModelEntity,
        FieldDefinition,
        FieldValue,
    )
    from openid_user_management.models import OpenIDUser

logger = logging.getLogger(__name__)


def serialize_node(node: "UserDefinedModelEntityNode") -> dict:
    """Build the EntityOut-compatible dict for a node and its children."""
    from userdefinedmodel.models import UserDefinedModelEntity

    field_values = []
    for fv in node.field_values.select_related("field").all():
        val = fv.get_value()
        field_values.append({
            "field_slug": fv.field.slug,
            "data_type": fv.field.data_type,
            "value": _serialize_value(val, fv.field),
            "language": fv.language,
        })

    children = {}
    for child in node.children.select_related("parent_field").order_by("submodelinstance__sort_order", "id"):
        slug = child.parent_field.slug if child.parent_field else "unknown"
        if slug not in children:
            children[slug] = []
        children[slug].append(serialize_node(child))

    result = {
        "id": str(node.id),
        "config_version_id": str(node.config_version_id),
        "user_defined_model_type_id": None,
        "current_state": node.current_state.name if node.current_state else None,
        "owner": None,
        "editors": [],
        "field_values": field_values,
        "children": children,
        "overflow_data": node.overflow_data,
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }

    try:
        entity = node.userdefinedmodelentity
        result["user_defined_model_type_id"] = str(entity.user_defined_model_type_id) if entity.user_defined_model_type_id else None
        result["owner"] = {
            "id": str(entity.owner_id),
            "display_name": entity.owner.username if entity.owner else "",
        } if entity.owner_id else None
        result["editors"] = [
            {"id": str(e.id), "display_name": e.username}
            for e in entity.editors.all()
        ]
    except UserDefinedModelEntity.DoesNotExist:
        pass

    return result


def _serialize_value(val, field: "FieldDefinition") -> Any:
    """Serialize a stored value for API output."""
    from userdefinedmodel.models.node import FileAttachment
    if val is None:
        return None
    if isinstance(val, FileAttachment):
        return {"id": str(val.id), "original_name": val.original_name, "mime_type": val.mime_type}
    # Defensive: if an ORM object slipped through, return its PK as string
    if hasattr(val, "pk") and not isinstance(val, (str, int, float, bool, list, dict)):
        return str(val.pk)
    return val


def apply_patch(
    node: "UserDefinedModelEntityNode",
    changed_fields: dict[str, Any],
    user: "OpenIDUser",
    edit_group=None,
) -> "EditGroup":
    """
    Apply a partial PATCH to node. Must be called inside transaction.atomic()
    with root lock held. Returns the EditGroup created.
    """
    from userdefinedmodel.models import FieldDefinition, FieldValue, UserDefinedModelEntity
    from userdefinedmodel.models.history import EditGroup, FieldEdit
    from userdefinedmodel.models.node import StagingFile, FileAttachment

    # 1. Check allows_edit
    if node.current_state and not node.current_state.allows_edit:
        from userdefinedmodel.engine import TransitionError
        raise TransitionError(
            "editing_not_allowed_in_state",
            http_status=409,
            details={"current_state": node.current_state.name},
        )

    # Build field map for this version
    field_map = {
        f.slug: f
        for f in node.config_version.field_definitions.all()
    }

    # Split into scalar vs submodel_list entries
    scalar_changes = {}
    submodel_changes = {}
    for slug, value in changed_fields.items():
        field = field_map.get(slug)
        if field is None:
            continue  # unknown slug: silently skip
        if field.data_type == FieldDefinition.DataType.SUBMODEL_LIST:
            submodel_changes[slug] = value
        else:
            scalar_changes[slug] = (field, value)

    # Build or reuse edit group
    try:
        root_entity = node.userdefinedmodelentity
    except UserDefinedModelEntity.DoesNotExist:
        root_entity = node.get_root()

    if edit_group is None:
        edit_group = EditGroup.objects.create(node=node, root_entity=root_entity, saved_by=user)

    # 8. Apply scalar writes first (so validate_for_save sees the new values)
    for slug, (field, value) in scalar_changes.items():
        _apply_scalar_write(node, field, value, user, edit_group)

    # 9. Process submodel_list operations
    for slug, ops in submodel_changes.items():
        field = field_map[slug]
        if isinstance(ops, list):
            _apply_submodel_ops(node, field, ops, user, edit_group)

    # 7. Validate for save (runs on the new state; transaction rolls back on failure)
    node.validate_for_save()

    # Evaluate policy for SAVE with changed_fields (gives Rego access to old+new values)
    # Note: entity.to_policy_document() already includes unchanged fields (old values)
    # and changed_fields contains the new values being written.
    _evaluate_save_policy(node, user, changed_fields)

    return edit_group


def _evaluate_save_policy(node, user, changed_fields: dict) -> None:
    """Evaluate Rego policy for SAVE action. Raises ValidationError on blocking messages."""
    from userdefinedmodel.engine import evaluate_policy, get_udm_type_for_node
    from django.core.exceptions import ValidationError

    udm_type = get_udm_type_for_node(node)
    if udm_type is None or not udm_type.type_policies.exists():
        return

    # Serialize changed_fields to JSON-safe form
    import json, decimal, datetime

    def _safe(v):
        if isinstance(v, decimal.Decimal):
            return float(v)
        if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
            return v.isoformat()
        if hasattr(v, "pk"):
            return str(v.pk)
        return v

    safe_changed = {slug: _safe(val) for slug, val in changed_fields.items()}

    output = evaluate_policy(node, user, "save", changed_fields=safe_changed)
    if not output["allow"]:
        raise ValidationError({"policy": ["Save denied by policy."]})

    # critical messages block save
    blocking = [
        m for m in output["messages"]
        if isinstance(m, dict) and m.get("level") == "critical"
    ]
    if blocking:
        errors = {}
        for msg in blocking:
            slug = msg.get("field_slug") or "__all__"
            text = msg.get("message", {}).get("en", "Policy error") if isinstance(msg.get("message"), dict) else str(msg.get("message", ""))
            errors.setdefault(slug, []).append(text)
        raise ValidationError(errors)


def _apply_scalar_write(node, field, value, user, edit_group) -> None:
    from userdefinedmodel.models.node import FieldValue, StagingFile, FileAttachment
    from userdefinedmodel.models.history import FieldEdit

    lang = ""  # non-localized by default

    if field.is_localized and isinstance(value, dict):
        # Localized: value is {lang_code: val} dict
        for lang_code, lang_val in value.items():
            _write_field_value(node, field, lang_val, lang_code, user, edit_group)
        return
    elif field.is_localized and value is None:
        # Clear all language values
        for fv in node.field_values.filter(field=field):
            _record_field_edit(edit_group, field, fv.get_value(), None, lang=fv.language, affected_node=node)
            fv.delete()
        return

    _write_field_value(node, field, value, lang, user, edit_group)


def _write_field_value(node, field, value, language, user, edit_group) -> None:
    from userdefinedmodel.models.node import FieldValue, StagingFile, FileAttachment
    from userdefinedmodel.models.history import FieldEdit

    fv = node.field_values.filter(field=field, language=language).first()
    old_value = fv.get_value() if fv else None
    old_attachment = fv.value_file if fv and hasattr(fv, "value_file") else None

    # submodel_select: {"op": "create"} or {"op": "delete"}
    if field.data_type == "submodel_select" and isinstance(value, dict):
        op = value.get("op")
        if op == "create":
            from userdefinedmodel.models.node import SubmodelInstance
            if not field.submodel_config_id:
                raise ValidationError({field.slug: "No submodel_config set on this field."})
            child = SubmodelInstance.objects.create(
                config_version_id=field.submodel_config_id,
                parent_node=node,
                parent_field=field,
                sort_order=0,
            )
            if field.submodel_config and field.submodel_config.workflow_id:
                initial = field.submodel_config.workflow.states.filter(is_initial=True).first()
                if initial:
                    child.current_state = initial
                    child.save(update_fields=["current_state"])
            child.materialize_defaults()
            value = child.id  # fall through to set value_node_id
        elif op == "delete":
            if fv and fv.value_node_id:
                from userdefinedmodel.models.node import SubmodelInstance
                try:
                    SubmodelInstance.objects.get(id=fv.value_node_id, parent_node=node).delete()
                except SubmodelInstance.DoesNotExist:
                    pass
            value = None  # clear the FK

    # Handle file staging promotion
    if isinstance(value, dict) and "staging_id" in value:
        staging_id = value["staging_id"]
        try:
            staging = StagingFile.objects.get(id=staging_id, uploader=user)
        except StagingFile.DoesNotExist:
            raise ValidationError({field.slug: "Staging file not found or not owned by you."})

        # Create FileAttachment from staging
        attachment = FileAttachment.objects.create(
            original_name=staging.original_name,
            mime_type=staging.mime_type,
            size_bytes=staging.size_bytes,
            file=staging.file,
        )

        # Soft-delete old attachment if nothing else references it
        if old_attachment:
            other_refs = FieldValue.objects.filter(value_file=old_attachment).exclude(pk=fv.pk if fv else None).count()
            if other_refs == 0:
                from django.utils.timezone import now
                old_attachment.deleted_at = now()
                old_attachment.save(update_fields=["deleted_at"])

        if fv is None:
            fv = FieldValue(node=node, field=field, language=language)
        fv.value_file = attachment
        fv.save()
        staging.delete()

        _record_field_edit(edit_group, field, None, None, old_attachment=old_attachment, new_attachment=attachment, lang=language, affected_node=node)
        return

    # Null = clear
    if value is None:
        if fv:
            if old_attachment:
                other_refs = FieldValue.objects.filter(value_file=old_attachment).exclude(pk=fv.pk).count()
                if other_refs == 0:
                    from django.utils.timezone import now
                    old_attachment.deleted_at = now()
                    old_attachment.save(update_fields=["deleted_at"])
            _record_field_edit(edit_group, field, old_value, None, old_attachment=old_attachment, lang=language, affected_node=node)
            fv.delete()
        return

    # Normal scalar write
    if fv is None:
        fv = FieldValue(node=node, field=field, language=language)
    fv.set_value(value, field=field)
    fv.full_clean()
    fv.save()
    _record_field_edit(edit_group, field, old_value, value, lang=language, affected_node=node)


def _record_field_edit(edit_group, field, old_value, new_value, *, old_attachment=None, new_attachment=None, lang="", affected_node=None) -> None:
    from userdefinedmodel.models.history import FieldEdit

    # Serialize old/new values to JSON-compatible
    def _json(v):
        if v is None:
            return None
        if hasattr(v, "pk"):
            return str(v.pk)
        return v

    FieldEdit.objects.create(
        group=edit_group,
        change_kind=FieldEdit.ChangeKind.FIELD_VALUE,
        field=field,
        old_value=_json(old_value),
        new_value=_json(new_value),
        old_attachment=old_attachment,
        new_attachment=new_attachment,
        affected_node=affected_node,
    )


def _apply_submodel_ops(parent_node, field, ops, user, edit_group) -> None:
    from userdefinedmodel.models.node import SubmodelInstance
    from userdefinedmodel.models.history import FieldEdit

    for op_data in ops:
        op = op_data.get("op")
        op_id = op_data.get("id")
        op_fields = op_data.get("fields", {})
        sort_order = op_data.get("sort_order")

        if op == "create":
            # Determine sort_order
            if sort_order is None:
                max_order = parent_node.children.filter(parent_field=field).aggregate(
                    m=__import__("django.db.models", fromlist=["Max"]).Max("submodelinstance__sort_order")
                )["m"] or 0
                sort_order = max_order + 1

            child = SubmodelInstance.objects.create(
                config_version=field.submodel_config,
                parent_node=parent_node,
                parent_field=field,
                sort_order=sort_order,
            )
            # Assign initial workflow state
            if field.submodel_config and field.submodel_config.workflow_id:
                initial = field.submodel_config.workflow.states.filter(is_initial=True).first()
                if initial:
                    child.current_state = initial
                    child.save(update_fields=["current_state"])

            child.materialize_defaults()

            FieldEdit.objects.create(
                group=edit_group,
                change_kind=FieldEdit.ChangeKind.NODE_ADDED,
                field=field,
                affected_node=child,
            )

            if op_fields:
                apply_patch(child, op_fields, user, edit_group=edit_group)

        elif op == "update":
            try:
                child = SubmodelInstance.objects.get(id=op_id, parent_node=parent_node)
            except SubmodelInstance.DoesNotExist:
                raise ValidationError({field.slug: f"Submodel instance {op_id} not found."})

            if sort_order is not None and child.sort_order != sort_order:
                old_order = child.sort_order
                child.sort_order = sort_order
                child.save(update_fields=["sort_order"])
                FieldEdit.objects.create(
                    group=edit_group,
                    change_kind=FieldEdit.ChangeKind.NODE_REORDERED,
                    field=field,
                    affected_node=child,
                    old_value={"sort_order": old_order},
                    new_value={"sort_order": sort_order},
                )

            if op_fields:
                apply_patch(child, op_fields, user, edit_group=edit_group)

        elif op == "delete":
            try:
                child = SubmodelInstance.objects.get(id=op_id, parent_node=parent_node)
            except SubmodelInstance.DoesNotExist:
                raise ValidationError({field.slug: f"Submodel instance {op_id} not found."})

            FieldEdit.objects.create(
                group=edit_group,
                change_kind=FieldEdit.ChangeKind.NODE_REMOVED,
                field=field,
                affected_node=child,
            )
            child.delete()
