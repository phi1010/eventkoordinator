"""
userdefinedmodel API — mounted at /api/udm/ in project urls.py.
All endpoints use typed response schemas for OpenAPI compatibility:
  - Success: response={N: SchemaType} + return (N, schema_obj)
  - Errors:  return JsonResponse({...}, status=N) — passes through Ninja unchanged
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.utils.timezone import now
from ninja import NinjaAPI, File, UploadedFile
from ninja.security import django_auth

from userdefinedmodel.schemas import (
    BulkMigrationCreateIn,
    BulkMigrationOut,
    BulkMigrationStatus,
    ConfigDraftIn,
    ConfigLanguageOut,
    ConfigVersionOut,
    EditHistoryOut,
    EditGroupOut,
    EntityCreateIn,
    EntityOut,
    EntityPatchIn,
    FieldConfigCreateIn,
    FieldConfigOut,
    FieldConfigUpdateIn,
    FieldDefinitionOut,
    FieldEditOut,
    GroupAutocompleteItem,
    EntityAutocompleteItem,
    MigrationExecuteIn,
    MigrationPreviewOut,
    PolicyAssignIn,
    PolicyCreateIn,
    PolicyOut,
    PolicyEvalOut,
    PolicyUpdateIn,
    StagingFileOut,
    TransitionIn,
    UDMTypeOut,
    UDMTypeCreateIn,
    UserAutocompleteItem,
    UserRefOut,
    WorkflowStateOut,
    WorkflowTransitionOut,
    WorkflowOut,
)

logger = logging.getLogger(__name__)

api = NinjaAPI(urls_namespace="udm", auth=django_auth)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _http409_concurrent() -> JsonResponse:
    return JsonResponse({"error": "concurrent_edit", "retry_after_ms": 500}, status=409)


def _entity_out(entity) -> EntityOut:
    from userdefinedmodel.writer import serialize_node
    data = serialize_node(entity)
    return EntityOut(**data)


def _serialize_config_version(version) -> ConfigVersionOut:
    fields_out = []
    for fd in version.field_definitions.prefetch_related("translations", "defaults", "single_field_rules").all():
        label_dict = {t.language: t.label for t in fd.translations.all()}
        help_dict = {t.language: t.help_text for t in fd.translations.all()}

        save_rules = {}
        for rule in fd.single_field_rules.filter(applies_to_save=True):
            real = rule.get_real_instance()
            rule_type = real.__class__.__name__
            save_rules[rule_type] = {"id": str(rule.id), "admin_label": rule.admin_label}

        defaults_qs = list(fd.defaults.all())
        default_val = None
        if defaults_qs:
            if fd.is_localized:
                default_val = {d.language: d.get_value(field=fd) for d in defaults_qs}
            else:
                default_val = defaults_qs[0].get_value(field=fd)

        fields_out.append(FieldDefinitionOut(
            id=fd.id,
            slug=fd.slug,
            data_type=fd.data_type,
            sort_order=fd.sort_order,
            is_localized=fd.is_localized,
            label=label_dict,
            help_text=help_dict,
            type_config=fd.type_config or {},
            default=default_val,
            save_rules=save_rules,
            submodel_config=_serialize_config_version(fd.submodel_config) if fd.submodel_config else None,
        ))

    workflow_out = None
    if version.workflow:
        wf = version.workflow
        states = []
        for state in wf.states.prefetch_related("translations").all():
            label_dict = {t.language: t.label for t in state.translations.all()}
            states.append(WorkflowStateOut(
                name=state.name, label=label_dict,
                is_initial=state.is_initial, allows_edit=state.allows_edit,
            ))
        transitions = []
        for trans in wf.transitions.prefetch_related("translations").all():
            label_dict = {t.language: t.label for t in trans.translations.all()}
            transitions.append(WorkflowTransitionOut(
                name=trans.name, label=label_dict,
                from_state=trans.from_state.name if trans.from_state else None,
                to_state=trans.to_state.name,
            ))
        initial = next((s for s in states if s.is_initial), None)
        workflow_out = WorkflowOut(
            initial_state=initial.name if initial else "",
            states=states,
            transitions=transitions,
        )

    return ConfigVersionOut(
        version_id=version.id,
        status=version.status,
        notes=version.notes,
        published_at=version.published_at.isoformat() if version.published_at else None,
        languages=[
            ConfigLanguageOut(code=l.code, label=l.label, is_default=l.is_default, sort_order=l.sort_order)
            for l in version.config.languages.all()
        ],
        fields=fields_out,
        workflow=workflow_out,
    )


def _field_config_out(cfg) -> FieldConfigOut:
    from userdefinedmodel.models import UserDefinedModelEntity
    stale_count = UserDefinedModelEntity.objects.filter(
        user_defined_model_type__field_config=cfg
    ).exclude(config_version__config=cfg).count()
    return FieldConfigOut(
        id=cfg.id, name=cfg.name, description=cfg.description,
        stale_entity_count=stale_count,
        type_ids=[t.id for t in cfg.user_defined_model_types.all()],
        languages=[
            ConfigLanguageOut(code=l.code, label=l.label, is_default=l.is_default, sort_order=l.sort_order)
            for l in cfg.languages.all()
        ],
    )


# ─── FieldConfig CRUD ─────────────────────────────────────────────────────────

@api.get("/configs/", response=list[FieldConfigOut], auth=django_auth)
def list_configs(request):
    from userdefinedmodel.models import FieldConfig
    configs = FieldConfig.objects.prefetch_related("languages", "user_defined_model_types")
    return [_field_config_out(cfg) for cfg in configs]


@api.post("/configs/", response={201: FieldConfigOut}, auth=django_auth)
def create_config(request, payload: FieldConfigCreateIn):
    from userdefinedmodel.models import FieldConfig, ConfigLanguage, ConfigVersion
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    with transaction.atomic():
        cfg = FieldConfig.objects.create(name=payload.name, description=payload.description)
        for lang in payload.languages:
            ConfigLanguage.objects.create(
                config=cfg, code=lang.code, label=lang.label,
                is_default=lang.is_default, sort_order=lang.sort_order,
            )
        ConfigVersion.objects.create(config=cfg, status=ConfigVersion.Status.DRAFT)
    return 201, FieldConfigOut(
        id=cfg.id, name=cfg.name, description=cfg.description,
        stale_entity_count=0, type_ids=[],
        languages=[
            ConfigLanguageOut(code=l.code, label=l.label, is_default=l.is_default, sort_order=l.sort_order)
            for l in cfg.languages.all()
        ],
    )


@api.get("/configs/{config_id}/", response=FieldConfigOut, auth=django_auth)
def get_config(request, config_id: uuid.UUID):
    from userdefinedmodel.models import FieldConfig
    try:
        cfg = FieldConfig.objects.prefetch_related("languages", "user_defined_model_types").get(id=config_id)
    except FieldConfig.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    return _field_config_out(cfg)


@api.patch("/configs/{config_id}/", response=FieldConfigOut, auth=django_auth)
def update_config(request, config_id: uuid.UUID, payload: FieldConfigUpdateIn):
    from userdefinedmodel.models import FieldConfig
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        cfg = FieldConfig.objects.prefetch_related("languages", "user_defined_model_types").get(id=config_id)
    except FieldConfig.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    if payload.name is not None:
        cfg.name = payload.name
    if payload.description is not None:
        cfg.description = payload.description
    cfg.save()
    return _field_config_out(cfg)


@api.delete("/configs/{config_id}/", auth=django_auth)
def delete_config(request, config_id: uuid.UUID):
    from userdefinedmodel.models import FieldConfig
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        cfg = FieldConfig.objects.get(id=config_id)
    except FieldConfig.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    if cfg.user_defined_model_types.exists():
        return JsonResponse({"detail": "Config is still in use by UDMTypes"}, status=400)
    if cfg.versions.filter(nodes__isnull=False).exists():
        return JsonResponse({"detail": "Config has entities referencing it"}, status=400)
    cfg.delete()
    return JsonResponse({}, status=204)


@api.get("/configs/{config_id}/versions/", auth=django_auth)
def list_config_versions(request, config_id: uuid.UUID):
    from userdefinedmodel.models import ConfigVersion, FieldConfig
    try:
        FieldConfig.objects.get(id=config_id)
    except FieldConfig.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    versions = ConfigVersion.objects.filter(config_id=config_id).order_by("-published_at", "-created_at")
    return JsonResponse([
        {
            "id": str(v.id),
            "status": v.status,
            "notes": v.notes,
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ], safe=False)


@api.get("/configs/{config_id}/versions/published/", response=ConfigVersionOut, auth=django_auth)
def get_published_version(request, config_id: uuid.UUID):
    from userdefinedmodel.models import ConfigVersion
    try:
        version = ConfigVersion.objects.get(config_id=config_id, status=ConfigVersion.Status.PUBLISHED)
    except ConfigVersion.DoesNotExist:
        return JsonResponse({"detail": "No published version"}, status=404)
    return _serialize_config_version(version)


@api.get("/configs/{config_id}/versions/draft/", response=ConfigVersionOut, auth=django_auth)
def get_draft_version(request, config_id: uuid.UUID):
    from userdefinedmodel.models import ConfigVersion
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        version = ConfigVersion.objects.get(config_id=config_id, status=ConfigVersion.Status.DRAFT)
    except ConfigVersion.DoesNotExist:
        return JsonResponse({"detail": "No draft version"}, status=404)
    return _serialize_config_version(version)


@api.put("/configs/{config_id}/versions/draft/", response=ConfigVersionOut, auth=django_auth)
def replace_draft(request, config_id: uuid.UUID, payload: ConfigDraftIn):
    from userdefinedmodel.models import (
        ConfigVersion, FieldConfig, FieldDefinition, FieldDefinitionTranslation,
        WorkflowDefinition, WorkflowState, WorkflowStateTranslation,
        WorkflowTransition, WorkflowTransitionTranslation,
    )
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        cfg = FieldConfig.objects.get(id=config_id)
    except FieldConfig.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)

    with transaction.atomic():
        draft, _ = ConfigVersion.objects.get_or_create(
            config=cfg, status=ConfigVersion.Status.DRAFT,
            defaults={"notes": payload.notes},
        )
        draft.notes = payload.notes

        if payload.workflow:
            wf_data = payload.workflow
            wf = WorkflowDefinition.objects.create(name=wf_data.name, description=wf_data.description)
            state_map = {}
            for state_in in wf_data.states:
                state = WorkflowState.objects.create(
                    workflow=wf, name=state_in.name,
                    is_initial=state_in.is_initial, allows_edit=state_in.allows_edit,
                )
                state_map[state_in.name] = state
                for lang, label in state_in.label.items():
                    WorkflowStateTranslation.objects.create(state=state, language=lang, label=label)
            for trans_in in wf_data.transitions:
                trans = WorkflowTransition.objects.create(
                    workflow=wf,
                    name=trans_in.name,
                    from_state=state_map.get(trans_in.from_state) if trans_in.from_state else None,
                    to_state=state_map[trans_in.to_state],
                )
                for lang, label in trans_in.label.items():
                    WorkflowTransitionTranslation.objects.create(transition=trans, language=lang, label=label)
            draft.workflow = wf

        draft.save()
        draft.field_definitions.all().delete()

        field_map = {}
        for fd_in in payload.fields:
            submodel_config = None
            if fd_in.submodel_config_version_id:
                try:
                    submodel_config = ConfigVersion.objects.get(id=fd_in.submodel_config_version_id)
                except ConfigVersion.DoesNotExist:
                    return JsonResponse({"detail": f"ConfigVersion {fd_in.submodel_config_version_id} not found"}, status=400)

            fd = FieldDefinition.objects.create(
                version=draft,
                slug=fd_in.slug,
                data_type=fd_in.data_type.value,
                sort_order=fd_in.sort_order,
                is_localized=fd_in.is_localized,
                submodel_config=submodel_config,
                type_config=fd_in.type_config,
            )
            field_map[fd_in.slug] = fd

            for lang, label in fd_in.labels.items():
                help_text = fd_in.help_texts.get(lang, "")
                FieldDefinitionTranslation.objects.create(
                    field=fd, language=lang, label=label, help_text=help_text
                )
            for rule_in in fd_in.rules:
                _create_single_field_rule(fd, rule_in)

        for mfr_in in payload.multi_field_rules:
            _create_multi_field_rule(draft, field_map, mfr_in)

    return _serialize_config_version(draft)


def _create_single_field_rule(field, rule_in):
    from userdefinedmodel.models.rules import (
        RequiredRule, MinLengthRule, MaxLengthRule, RegexRule,
        MinValueRule, MaxValueRule, MinItemsRule, MaxItemsRule,
        MaxFileSizeRule, AllowedMimeTypesRule, AllowedMimeTypeEntry,
        RequiredInLanguageRule,
    )
    common = {"field": field, "applies_to_save": rule_in.applies_to_save, "admin_label": rule_in.admin_label}
    t = rule_in.type
    if t == "required":
        RequiredRule.objects.create(**common)
    elif t == "min_length":
        MinLengthRule.objects.create(**common, min_length=rule_in.min_length)
    elif t == "max_length":
        MaxLengthRule.objects.create(**common, max_length=rule_in.max_length)
    elif t == "regex":
        RegexRule.objects.create(**common, pattern=rule_in.pattern, failure_message=rule_in.failure_message)
    elif t == "min_value":
        MinValueRule.objects.create(**common, min_value=rule_in.min_value)
    elif t == "max_value":
        MaxValueRule.objects.create(**common, max_value=rule_in.max_value)
    elif t == "min_items":
        MinItemsRule.objects.create(**common, min_items=rule_in.min_items)
    elif t == "max_items":
        MaxItemsRule.objects.create(**common, max_items=rule_in.max_items)
    elif t == "max_file_size":
        MaxFileSizeRule.objects.create(**common, max_bytes=rule_in.max_bytes)
    elif t == "allowed_mime_types":
        rule = AllowedMimeTypesRule.objects.create(**common)
        for mime in rule_in.mime_types:
            AllowedMimeTypeEntry.objects.create(rule=rule, mime_type=mime)
    elif t == "required_in_language":
        RequiredInLanguageRule.objects.create(**common, language=rule_in.language)


def _create_multi_field_rule(version, field_map, mfr_in):
    from userdefinedmodel.models.rules import (
        AtLeastOneRequiredRule, ExactlyOneRequiredRule, MutualExclusionRule,
        MultiFieldRuleAssociation,
    )
    common = {"config_version": version, "applies_to_save": mfr_in.applies_to_save, "admin_label": mfr_in.admin_label}
    kind = mfr_in.kind.value
    if kind == "at_least_one_required":
        rule = AtLeastOneRequiredRule.objects.create(**common)
    elif kind == "exactly_one_required":
        rule = ExactlyOneRequiredRule.objects.create(**common)
    elif kind == "mutual_exclusion":
        rule = MutualExclusionRule.objects.create(**common)
    else:
        return
    for slug in mfr_in.field_slugs:
        field = field_map.get(slug)
        if field:
            MultiFieldRuleAssociation.objects.create(rule=rule, field=field)


@api.post("/configs/{config_id}/versions/draft/publish/", response=ConfigVersionOut, auth=django_auth)
def publish_draft(request, config_id: uuid.UUID):
    from userdefinedmodel.models import ConfigVersion, FieldConfig
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        cfg = FieldConfig.objects.get(id=config_id)
    except FieldConfig.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    try:
        draft = ConfigVersion.objects.get(config=cfg, status=ConfigVersion.Status.DRAFT)
    except ConfigVersion.DoesNotExist:
        return JsonResponse({"detail": "No draft to publish"}, status=404)
    try:
        draft.publish()
    except ValidationError as exc:
        return JsonResponse({"errors": exc.message_dict if hasattr(exc, "message_dict") else str(exc)}, status=422)
    return _serialize_config_version(draft)


# ─── UDMType ──────────────────────────────────────────────────────────────────

@api.get("/types/", response=list[UDMTypeOut], auth=django_auth)
def list_udm_types(request):
    from userdefinedmodel.models import UserDefinedModelType
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    types = UserDefinedModelType.objects.select_related("field_config").all()
    return [UDMTypeOut(id=t.id, name=t.name, description=t.description, field_config_id=t.field_config_id)
            for t in types]


@api.post("/types/", response={201: UDMTypeOut}, auth=django_auth)
def create_udm_type(request, payload: UDMTypeCreateIn):
    from userdefinedmodel.models import UserDefinedModelType
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    udm_type = UserDefinedModelType.objects.create(name=payload.name, description=payload.description)
    return 201, UDMTypeOut(id=udm_type.id, name=udm_type.name, description=udm_type.description, field_config_id=None)


@api.get("/types/{type_id}/", response=UDMTypeOut, auth=django_auth)
def get_udm_type(request, type_id: uuid.UUID):
    from userdefinedmodel.models import UserDefinedModelType
    try:
        t = UserDefinedModelType.objects.get(id=type_id)
    except UserDefinedModelType.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    return UDMTypeOut(id=t.id, name=t.name, description=t.description, field_config_id=t.field_config_id)


@api.get("/types/{type_id}/eval-policy/", response=PolicyEvalOut, auth=django_auth)
def eval_policy_for_type(
    request,
    type_id: uuid.UUID,
    entity_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str = "view",
    transition: Optional[str] = None,
):
    """Superuser-only: evaluate the Rego policy for a given entity + user and return the full
    input document, the raw policy sources, and the structured output."""
    if not request.user.is_superuser:
        return JsonResponse({"detail": "Superuser only"}, status=403)

    from userdefinedmodel.models import UserDefinedModelEntity, UserDefinedModelType
    from userdefinedmodel.engine import build_policy_input, get_udm_type_for_node

    try:
        entity = UserDefinedModelEntity.objects.select_related(
            "config_version__workflow", "current_state", "user_defined_model_type"
        ).get(id=entity_id)
    except UserDefinedModelEntity.DoesNotExist:
        return JsonResponse({"detail": "Entity not found"}, status=404)

    try:
        from openid_user_management.models import OpenIDUser
        eval_user = OpenIDUser.objects.prefetch_related("groups", "user_permissions").get(id=user_id)
    except Exception:
        return JsonResponse({"detail": "User not found"}, status=404)

    # Collect policy sources
    udm_type = get_udm_type_for_node(entity)
    policy_entries = []
    if udm_type:
        for tp in udm_type.type_policies.select_related("policy").order_by("sort_order"):
            policy_entries.append({"slug": tp.policy.slug, "source": tp.policy.source})

    # Build input document
    kwargs = {}
    if transition:
        kwargs["transition"] = transition
    input_doc = build_policy_input(entity, eval_user, action, **kwargs)

    # Run evaluation
    error_msg = None
    output = {"allow": True, "messages": [], "viewable_fields": [], "editable_fields": []}
    if policy_entries:
        try:
            import json as _json
            import regorus
            eng = regorus.Engine()
            for entry in policy_entries:
                eng.add_policy(f"policy_{entry['slug']}.rego", entry["source"])
            eng.set_input_json(_json.dumps(input_doc))

            def _eval_list(rule_path):
                try:
                    raw = _json.loads(eng.eval_rule_as_json(rule_path))
                    return raw if isinstance(raw, list) else []
                except Exception:
                    return []

            def _eval_bool(rule_path, default=True):
                try:
                    raw = _json.loads(eng.eval_rule_as_json(rule_path))
                    if raw is None:
                        return default
                    if isinstance(raw, list):
                        return bool(raw[0]) if raw else default
                    return bool(raw)
                except Exception:
                    return default

            output = {
                "allow": _eval_bool("data.udm.allow", default=False),
                "deny": _eval_list("data.udm.deny"),
                "messages": _eval_list("data.udm.messages"),
                "viewable_fields": _eval_list("data.udm.viewable_fields"),
                "editable_fields": _eval_list("data.udm.editable_fields"),
            }
        except Exception as exc:
            error_msg = str(exc)
            output = {"allow": False, "messages": [], "viewable_fields": [], "editable_fields": []}

    return PolicyEvalOut(
        input_document=input_doc,
        policies=policy_entries,
        output=output,
        error=error_msg,
    )


@api.get("/types/{type_id}/config/", response=ConfigVersionOut, auth=django_auth)
def get_type_config(request, type_id: uuid.UUID):
    from userdefinedmodel.models import UserDefinedModelType, ConfigVersion
    try:
        udm_type = UserDefinedModelType.objects.select_related("field_config").get(id=type_id)
    except UserDefinedModelType.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    if not udm_type.field_config:
        return JsonResponse({"detail": "No field config assigned"}, status=404)
    try:
        version = ConfigVersion.objects.get(config=udm_type.field_config, status=ConfigVersion.Status.PUBLISHED)
    except ConfigVersion.DoesNotExist:
        return JsonResponse({"detail": "No published version"}, status=404)
    return _serialize_config_version(version)


@api.patch("/types/{type_id}/", response=UDMTypeOut, auth=django_auth)
def update_udm_type(request, type_id: uuid.UUID, field_config_id: Optional[uuid.UUID] = None):
    from userdefinedmodel.models import UserDefinedModelType, FieldConfig
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        udm_type = UserDefinedModelType.objects.get(id=type_id)
    except UserDefinedModelType.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    if field_config_id is not None:
        try:
            cfg = FieldConfig.objects.get(id=field_config_id)
        except FieldConfig.DoesNotExist:
            return JsonResponse({"detail": "FieldConfig not found"}, status=404)
        from userdefinedmodel.models import BulkMigrationPlan, UserDefinedModelEntity
        stale = UserDefinedModelEntity.objects.filter(user_defined_model_type=udm_type).exclude(config_version__config=cfg)
        if stale.exists():
            confirmed_plans = BulkMigrationPlan.objects.filter(
                target_version__config=cfg,
                user_defined_model_type_filter=udm_type,
                status=BulkMigrationPlan.Status.DONE,
            )
            if not confirmed_plans.exists():
                return JsonResponse({"detail": "Stale entities exist without a confirmed BulkMigrationPlan"}, status=400)
        udm_type.field_config = cfg
        udm_type.save()
    return UDMTypeOut(id=udm_type.id, name=udm_type.name, description=udm_type.description, field_config_id=udm_type.field_config_id)


# ─── Policies ─────────────────────────────────────────────────────────────────

@api.get("/policies/", response=list[PolicyOut], auth=django_auth)
def list_policies(request):
    from userdefinedmodel.models import Policy
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    return [PolicyOut(slug=p.slug, source=p.source) for p in Policy.objects.all()]


@api.post("/policies/", response={201: PolicyOut}, auth=django_auth)
def create_policy(request, payload: PolicyCreateIn):
    from userdefinedmodel.models import Policy
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    policy = Policy.objects.create(slug=payload.slug, source=payload.source)
    return 201, PolicyOut(slug=policy.slug, source=policy.source)


@api.get("/policies/{slug}/", response=PolicyOut, auth=django_auth)
def get_policy(request, slug: str):
    from userdefinedmodel.models import Policy
    try:
        p = Policy.objects.get(slug=slug)
    except Policy.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    return PolicyOut(slug=p.slug, source=p.source)


@api.put("/policies/{slug}/", response=PolicyOut, auth=django_auth)
def update_policy(request, slug: str, payload: PolicyUpdateIn):
    from userdefinedmodel.models import Policy
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        p = Policy.objects.get(slug=slug)
    except Policy.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    p.source = payload.source
    p.save()
    return PolicyOut(slug=p.slug, source=p.source)


@api.delete("/policies/{slug}/", auth=django_auth)
def delete_policy(request, slug: str):
    from userdefinedmodel.models import Policy
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        p = Policy.objects.get(slug=slug)
    except Policy.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    if p.type_assignments.exists():
        return JsonResponse({"detail": "Policy is assigned to UDMTypes"}, status=400)
    p.delete()
    return JsonResponse({}, status=204)


@api.get("/types/{type_id}/policies/", response=list[PolicyOut], auth=django_auth)
def list_type_policies(request, type_id: uuid.UUID):
    from userdefinedmodel.models import UserDefinedModelType
    try:
        udm_type = UserDefinedModelType.objects.get(id=type_id)
    except UserDefinedModelType.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    return [PolicyOut(slug=tp.policy.slug, source=tp.policy.source)
            for tp in udm_type.type_policies.select_related("policy").order_by("sort_order")]


@api.post("/types/{type_id}/policies/", response={201: PolicyOut}, auth=django_auth)
def assign_policy(request, type_id: uuid.UUID, payload: PolicyAssignIn):
    from userdefinedmodel.models import UserDefinedModelType, Policy, UserDefinedModelTypePolicy
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        udm_type = UserDefinedModelType.objects.get(id=type_id)
    except UserDefinedModelType.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    try:
        policy = Policy.objects.get(slug=payload.policy_slug)
    except Policy.DoesNotExist:
        return JsonResponse({"detail": "Policy not found"}, status=404)
    UserDefinedModelTypePolicy.objects.get_or_create(
        user_defined_model_type=udm_type, policy=policy,
        defaults={"sort_order": payload.sort_order},
    )
    return 201, PolicyOut(slug=policy.slug, source=policy.source)


@api.delete("/types/{type_id}/policies/{slug}/", auth=django_auth)
def remove_policy(request, type_id: uuid.UUID, slug: str):
    from userdefinedmodel.models import UserDefinedModelType, UserDefinedModelTypePolicy
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        udm_type = UserDefinedModelType.objects.get(id=type_id)
    except UserDefinedModelType.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    UserDefinedModelTypePolicy.objects.filter(user_defined_model_type=udm_type, policy__slug=slug).delete()
    return JsonResponse({}, status=204)


# ─── Entities ─────────────────────────────────────────────────────────────────

@api.post("/entities/", response={201: EntityOut}, auth=django_auth)
def create_entity(request, payload: EntityCreateIn):
    from userdefinedmodel.models import UserDefinedModelType, UserDefinedModelEntity, ConfigVersion
    try:
        udm_type = UserDefinedModelType.objects.select_related("field_config").get(id=payload.user_defined_model_type_id)
    except UserDefinedModelType.DoesNotExist:
        return JsonResponse({"detail": "UDMType not found"}, status=404)
    if not udm_type.field_config:
        return JsonResponse({"detail": "UDMType has no field config"}, status=400)
    try:
        version = ConfigVersion.objects.get(config=udm_type.field_config, status=ConfigVersion.Status.PUBLISHED)
    except ConfigVersion.DoesNotExist:
        return JsonResponse({"detail": "No published config version"}, status=400)
    with transaction.atomic():
        entity = UserDefinedModelEntity.objects.create(
            config_version=version, user_defined_model_type=udm_type, owner=request.user,
        )
        if version.workflow_id:
            initial_state = version.workflow.states.filter(is_initial=True).first()
            if initial_state:
                entity.current_state = initial_state
                entity.save(update_fields=["current_state"])
        entity.materialize_defaults()
    return 201, _entity_out(entity)


@api.get("/entities/{entity_id}/", response=EntityOut, auth=django_auth)
def get_entity(request, entity_id: uuid.UUID):
    from userdefinedmodel.models import UserDefinedModelEntity
    try:
        entity = UserDefinedModelEntity.objects.select_related(
            "config_version", "user_defined_model_type", "owner", "current_state"
        ).prefetch_related("editors", "field_values__field", "children").get(id=entity_id)
    except UserDefinedModelEntity.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    return _entity_out(entity)


@api.patch("/entities/{entity_id}/", response=EntityOut, auth=django_auth)
def patch_entity(request, entity_id: uuid.UUID, payload: EntityPatchIn):
    from userdefinedmodel.models import UserDefinedModelEntity
    from userdefinedmodel.writer import apply_patch
    from userdefinedmodel.engine import TransitionError
    try:
        with transaction.atomic():
            try:
                entity = (UserDefinedModelEntity.objects
                          .select_for_update(nowait=True, of=("self",))
                          .select_related("config_version", "current_state")
                          .get(id=entity_id))
            except UserDefinedModelEntity.DoesNotExist:
                return JsonResponse({"detail": "Not found"}, status=404)
            except OperationalError:
                return _http409_concurrent()
            try:
                apply_patch(entity, payload.changed_fields, request.user)
            except TransitionError as e:
                if e.http_status == 409:
                    return JsonResponse({"error": e.args[0], **e.details}, status=409)
                return JsonResponse({"error": str(e)}, status=e.http_status)
            except ValidationError as exc:
                errors = exc.message_dict if hasattr(exc, "message_dict") else {"__all__": [str(exc)]}
                return JsonResponse({"errors": errors}, status=400)
    except OperationalError:
        return _http409_concurrent()
    return _entity_out(entity)


@api.delete("/entities/{entity_id}/", auth=django_auth)
def delete_entity(request, entity_id: uuid.UUID):
    from userdefinedmodel.models import UserDefinedModelEntity
    try:
        entity = UserDefinedModelEntity.objects.get(id=entity_id)
    except UserDefinedModelEntity.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    if entity.owner_id != request.user.id and not request.user.is_staff:
        return JsonResponse({"detail": "Only owner can delete"}, status=403)
    entity.delete()
    return JsonResponse({}, status=204)


@api.post("/entities/{entity_id}/transition/", response=EntityOut, auth=django_auth)
def transition_entity(request, entity_id: uuid.UUID, payload: TransitionIn):
    from userdefinedmodel.models import UserDefinedModelEntity
    from userdefinedmodel.engine import execute_transition, TransitionError
    try:
        with transaction.atomic():
            try:
                entity = (UserDefinedModelEntity.objects
                          .select_for_update(nowait=True, of=("self",))
                          .select_related("config_version__workflow", "current_state")
                          .get(id=entity_id))
            except UserDefinedModelEntity.DoesNotExist:
                return JsonResponse({"detail": "Not found"}, status=404)
            except OperationalError:
                return _http409_concurrent()
            try:
                execute_transition(entity, payload.transition, request.user)
            except TransitionError as e:
                return JsonResponse({"error": str(e), **e.details}, status=e.http_status)
    except OperationalError:
        return _http409_concurrent()
    return _entity_out(entity)


@api.get("/entities/{entity_id}/history/", response=EditHistoryOut, auth=django_auth)
def entity_history(request, entity_id: uuid.UUID, page: int = 1, page_size: int = 20):
    from userdefinedmodel.models import UserDefinedModelEntity
    from userdefinedmodel.models.history import EditGroup
    try:
        entity = UserDefinedModelEntity.objects.get(id=entity_id)
    except UserDefinedModelEntity.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)

    qs = EditGroup.objects.filter(root_entity=entity).prefetch_related(
        "field_edits__field__translations",
        "field_edits__old_attachment",
        "field_edits__new_attachment",
        "saved_by",
    ).order_by("-saved_at")

    total = qs.count()
    offset = (page - 1) * page_size
    groups = list(qs[offset:offset + page_size])

    results = []
    for group in groups:
        edits = []
        for fe in group.field_edits.all():
            slug = fe.field.slug if fe.field else None
            label = None
            if fe.field:
                trans = fe.field.translations.first()
                label = trans.label if trans else slug
            edits.append(FieldEditOut(
                change_kind=fe.change_kind,
                field_slug=slug,
                field_label=label,
                old_value=fe.old_value,
                new_value=fe.new_value,
                old_file_name=fe.old_attachment.original_name if fe.old_attachment else None,
                new_file_name=fe.new_attachment.original_name if fe.new_attachment else None,
                affected_node_id=fe.affected_node_id,
            ))

        node_type = "entity"
        try:
            group.node.userdefinedmodelentity
        except Exception:
            pf = getattr(group.node, "parent_field", None)
            if pf:
                node_type = f"submodel:{pf.slug}"

        results.append(EditGroupOut(
            id=group.id,
            saved_at=group.saved_at.isoformat(),
            saved_by=UserRefOut(id=group.saved_by.id, display_name=group.saved_by.username) if group.saved_by else None,
            node_id=group.node_id,
            node_type=node_type,
            edits=edits,
        ))

    next_url = None
    if offset + page_size < total:
        next_url = f"/api/udm/entities/{entity_id}/history/?page={page + 1}&page_size={page_size}"

    return EditHistoryOut(count=total, next=next_url, results=results)


@api.get("/entities/{entity_id}/policy-document/", auth=django_auth)
def entity_policy_document(request, entity_id: uuid.UUID):
    from userdefinedmodel.models import UserDefinedModelEntity
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        entity = UserDefinedModelEntity.objects.get(id=entity_id)
    except UserDefinedModelEntity.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    return JsonResponse(entity.to_policy_document())


# ─── Staging files ────────────────────────────────────────────────────────────

@api.post("/staging-files/", response={201: StagingFileOut}, auth=django_auth)
def upload_staging_file(
    request,
    file: UploadedFile = File(...),
    intended_field_id: Optional[uuid.UUID] = None,
):
    from userdefinedmodel.models.node import StagingFile
    staging = StagingFile.objects.create(
        uploader=request.user,
        file=file,
        original_name=file.name,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=file.size,
        expires_at=now() + timedelta(hours=24),
        intended_field_id=intended_field_id,
    )
    return 201, StagingFileOut(
        staging_id=staging.id,
        original_name=staging.original_name,
        mime_type=staging.mime_type,
        size_bytes=staging.size_bytes,
        expires_at=staging.expires_at.isoformat(),
    )


@api.delete("/staging-files/{staging_id}/", auth=django_auth)
def delete_staging_file(request, staging_id: uuid.UUID):
    from userdefinedmodel.models.node import StagingFile
    try:
        staging = StagingFile.objects.get(id=staging_id, uploader=request.user)
    except StagingFile.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    staging.file.delete(save=False)
    staging.delete()
    return JsonResponse({}, status=204)


# ─── Autocomplete ─────────────────────────────────────────────────────────────

@api.get("/users/", response=list[UserAutocompleteItem], auth=django_auth)
def search_users(request, q: str = "", group_ids: str = "", ids: str = ""):
    from openid_user_management.models import OpenIDUser
    from django.db.models import Q as DQ
    qs = OpenIDUser.objects.filter(is_active=True)
    if group_ids:
        gids = [int(x) for x in group_ids.split(",") if x.strip().isdigit()]
        qs = qs.filter(groups__id__in=gids)
    if q:
        qs = qs.filter(DQ(username__icontains=q) | DQ(email__icontains=q))
    if ids:
        uid_list = [x.strip() for x in ids.split(",") if x.strip()]
        qs = OpenIDUser.objects.filter(id__in=uid_list)
    return [UserAutocompleteItem(id=u.id, display_name=u.username) for u in qs[:50]]


@api.get("/groups/", response=list[GroupAutocompleteItem], auth=django_auth)
def search_groups(request, q: str = "", ids: str = ""):
    from django.contrib.auth.models import Group
    qs = Group.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        qs = Group.objects.filter(id__in=id_list)
    return [GroupAutocompleteItem(id=g.id, name=g.name) for g in qs[:50]]


@api.get("/entity-search/", response=list[EntityAutocompleteItem], auth=django_auth)
def search_entities(request, q: str = "", type_ids: str = "", ids: str = ""):
    from userdefinedmodel.models import UserDefinedModelEntity
    qs = UserDefinedModelEntity.objects.select_related("config_version", "user_defined_model_type")
    if type_ids:
        tid_list = [x.strip() for x in type_ids.split(",") if x.strip()]
        qs = qs.filter(user_defined_model_type_id__in=tid_list)
    if ids:
        id_list = [x.strip() for x in ids.split(",") if x.strip()]
        qs = UserDefinedModelEntity.objects.filter(id__in=id_list)
    return [EntityAutocompleteItem(id=entity.id, display=str(entity.id), type_id=entity.user_defined_model_type_id)
            for entity in qs[:50]]


# ─── Migration ────────────────────────────────────────────────────────────────

@api.get("/entities/{entity_id}/migration-preview/", response=MigrationPreviewOut, auth=django_auth)
def migration_preview(
    request,
    entity_id: uuid.UUID,
    target_user_defined_model_type: Optional[uuid.UUID] = None,
    target_version: Optional[uuid.UUID] = None,
):
    from userdefinedmodel.models import (
        UserDefinedModelEntity, ConfigVersion, UserDefinedModelType, UserDefinedModelEntityMigration,
    )
    from userdefinedmodel.schemas import MigrationAction, MigrationPreviewFieldOut
    try:
        entity = UserDefinedModelEntity.objects.select_related("config_version").get(id=entity_id)
    except UserDefinedModelEntity.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)

    if target_version:
        try:
            tgt_version = ConfigVersion.objects.get(id=target_version)
        except ConfigVersion.DoesNotExist:
            return JsonResponse({"detail": "Target version not found"}, status=404)
        tgt_type = entity.user_defined_model_type
    elif target_user_defined_model_type:
        try:
            tgt_type = UserDefinedModelType.objects.select_related("field_config").get(id=target_user_defined_model_type)
        except UserDefinedModelType.DoesNotExist:
            return JsonResponse({"detail": "Target type not found"}, status=404)
        try:
            tgt_version = ConfigVersion.objects.get(config=tgt_type.field_config, status=ConfigVersion.Status.PUBLISHED)
        except ConfigVersion.DoesNotExist:
            return JsonResponse({"detail": "Target type has no published config"}, status=404)
    else:
        return JsonResponse({"detail": "Either target_user_defined_model_type or target_version is required"}, status=400)

    migration = UserDefinedModelEntityMigration.objects.create(
        user_defined_model_entity=entity,
        source_version=entity.config_version,
        target_user_defined_model_type=tgt_type,
        target_version=tgt_version,
    )

    source_fields = {f.slug: f for f in entity.config_version.field_definitions.all()}
    target_fields = {f.slug: f for f in tgt_version.field_definitions.all()}
    _ALLOWED = {
        ("integer", "float"), ("text_short", "text_long"), ("text_long", "text_markdown"),
        ("select_single", "select_multi"), ("user_select", "user_select_multi"),
        ("group_select", "group_select_multi"), ("entity_select", "entity_select_multi"),
    }

    previews = []
    for slug, src_field in source_fields.items():
        if slug in target_fields:
            tgt_field = target_fields[slug]
            if src_field.data_type == tgt_field.data_type or (src_field.data_type, tgt_field.data_type) in _ALLOWED:
                previews.append(MigrationPreviewFieldOut(
                    source_slug=slug, source_data_type=src_field.data_type,
                    suggested_action=MigrationAction.MAP, suggested_target_slug=slug, conflict_reason=None,
                ))
            else:
                previews.append(MigrationPreviewFieldOut(
                    source_slug=slug, source_data_type=src_field.data_type,
                    suggested_action=MigrationAction.OVERFLOW, suggested_target_slug=None,
                    conflict_reason=f"Incompatible: {src_field.data_type} → {tgt_field.data_type}",
                ))
        else:
            previews.append(MigrationPreviewFieldOut(
                source_slug=slug, source_data_type=src_field.data_type,
                suggested_action=MigrationAction.OVERFLOW, suggested_target_slug=None, conflict_reason=None,
            ))

    return MigrationPreviewOut(
        migration_id=migration.id,
        source_version_id=entity.config_version_id,
        target_version_id=tgt_version.id,
        field_previews=previews,
    )


@api.post("/entities/{entity_id}/migrate/", response=EntityOut, auth=django_auth)
def execute_migration(request, entity_id: uuid.UUID, payload: MigrationExecuteIn):
    from userdefinedmodel.models import (
        UserDefinedModelEntity, UserDefinedModelEntityMigration, MigrationFieldMapping, FieldValue,
    )
    try:
        entity = UserDefinedModelEntity.objects.get(id=entity_id)
    except UserDefinedModelEntity.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    try:
        migration = UserDefinedModelEntityMigration.objects.select_related(
            "target_version", "target_user_defined_model_type"
        ).get(id=payload.migration_id, user_defined_model_entity=entity)
    except UserDefinedModelEntityMigration.DoesNotExist:
        return JsonResponse({"detail": "Migration not found"}, status=404)

    with transaction.atomic():
        try:
            entity = (UserDefinedModelEntity.objects
                      .select_for_update(nowait=True, of=("self",))
                      .get(id=entity_id))
        except OperationalError:
            return _http409_concurrent()

        tgt_version = migration.target_version
        source_field_map = {f.slug: f for f in entity.config_version.field_definitions.all()}
        target_field_map = {f.slug: f for f in tgt_version.field_definitions.all()}
        overflow = {}

        for mapping_in in payload.field_mappings:
            src_field = source_field_map.get(mapping_in.source_field_slug)
            if not src_field:
                continue
            fv = entity.field_values.filter(field=src_field).first()
            if not fv:
                continue
            action = mapping_in.action.value
            if action == "map" and mapping_in.target_field_slug:
                tgt_field = target_field_map.get(mapping_in.target_field_slug)
                if tgt_field:
                    new_fv, _ = FieldValue.objects.get_or_create(node=entity, field=tgt_field, language=fv.language)
                    new_fv.set_value(fv.get_value(), field=tgt_field)
                    new_fv.save()
            elif action == "overflow":
                overflow[src_field.slug] = str(fv.get_value())
            MigrationFieldMapping.objects.create(
                migration=migration,
                source_field=src_field,
                action=action,
                target_field=target_field_map.get(mapping_in.target_field_slug) if mapping_in.target_field_slug else None,
            )

        if overflow:
            entity.overflow_data = {**entity.overflow_data, **overflow}
        entity.config_version = tgt_version
        entity.user_defined_model_type = migration.target_user_defined_model_type
        entity.save(update_fields=["config_version", "user_defined_model_type", "overflow_data"])
        migration.executed_at = now()
        migration.executed_by = request.user
        migration.save(update_fields=["executed_at", "executed_by"])

    return _entity_out(entity)


# ─── Bulk migration ───────────────────────────────────────────────────────────

@api.post("/bulk-migrations/preview/", auth=django_auth)
def bulk_migration_preview(
    request,
    source_version_id: uuid.UUID,
    target_version_id: uuid.UUID,
    type_filter_id: Optional[uuid.UUID] = None,
):
    from userdefinedmodel.models import ConfigVersion, UserDefinedModelEntity
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        src = ConfigVersion.objects.get(id=source_version_id)
        tgt = ConfigVersion.objects.get(id=target_version_id)
    except ConfigVersion.DoesNotExist:
        return JsonResponse({"detail": "Version not found"}, status=404)
    qs = UserDefinedModelEntity.objects.filter(config_version=src)
    if type_filter_id:
        qs = qs.filter(user_defined_model_type_id=type_filter_id)
    return JsonResponse({
        "affected_entity_count": qs.count(),
        "source_version_id": str(src.id),
        "target_version_id": str(tgt.id),
    })


@api.post("/bulk-migrations/", response={201: BulkMigrationOut}, auth=django_auth)
def create_bulk_migration(request, payload: BulkMigrationCreateIn):
    from userdefinedmodel.models import ConfigVersion, UserDefinedModelType, BulkMigrationPlan, BulkMigrationFieldMapping
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        src = ConfigVersion.objects.get(id=payload.source_version_id)
        tgt = ConfigVersion.objects.get(id=payload.target_version_id)
    except ConfigVersion.DoesNotExist:
        return JsonResponse({"detail": "Version not found"}, status=404)

    type_filter = None
    if payload.user_defined_model_type_filter_id:
        try:
            type_filter = UserDefinedModelType.objects.get(id=payload.user_defined_model_type_filter_id)
        except UserDefinedModelType.DoesNotExist:
            return JsonResponse({"detail": "Type filter not found"}, status=404)

    with transaction.atomic():
        plan = BulkMigrationPlan.objects.create(
            source_version=src, target_version=tgt,
            user_defined_model_type_filter=type_filter,
            created_by=request.user,
        )
        src_fields = {f.slug: f for f in src.field_definitions.all()}
        tgt_fields = {f.slug: f for f in tgt.field_definitions.all()}
        for mapping in payload.field_mappings:
            src_field = src_fields.get(mapping.source_field_slug)
            if src_field:
                BulkMigrationFieldMapping.objects.create(
                    plan=plan, source_field=src_field,
                    action=mapping.action.value,
                    target_field=tgt_fields.get(mapping.target_field_slug) if mapping.target_field_slug else None,
                )

    return 201, BulkMigrationOut(
        id=plan.id, status=BulkMigrationStatus(plan.status),
        source_version_id=plan.source_version_id,
        target_version_id=plan.target_version_id,
        user_defined_model_type_filter_id=plan.user_defined_model_type_filter_id,
        total_entities=plan.total_entities,
        done_entities=plan.done_entities,
        failed_entities=plan.failed_entities,
        executed_at=plan.executed_at.isoformat() if plan.executed_at else None,
    )


@api.get("/bulk-migrations/{plan_id}/", response=BulkMigrationOut, auth=django_auth)
def get_bulk_migration(request, plan_id: uuid.UUID):
    from userdefinedmodel.models import BulkMigrationPlan
    try:
        plan = BulkMigrationPlan.objects.get(id=plan_id)
    except BulkMigrationPlan.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    return BulkMigrationOut(
        id=plan.id, status=BulkMigrationStatus(plan.status),
        source_version_id=plan.source_version_id,
        target_version_id=plan.target_version_id,
        user_defined_model_type_filter_id=plan.user_defined_model_type_filter_id,
        total_entities=plan.total_entities,
        done_entities=plan.done_entities,
        failed_entities=plan.failed_entities,
        executed_at=plan.executed_at.isoformat() if plan.executed_at else None,
    )


@api.post("/bulk-migrations/{plan_id}/execute/", auth=django_auth)
def execute_bulk_migration_plan(request, plan_id: uuid.UUID):
    from userdefinedmodel.models import BulkMigrationPlan
    from userdefinedmodel.tasks import execute_bulk_migration
    if not request.user.is_staff:
        return JsonResponse({"detail": "Staff only"}, status=403)
    try:
        plan = BulkMigrationPlan.objects.get(id=plan_id)
    except BulkMigrationPlan.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    if plan.status in (BulkMigrationPlan.Status.RUNNING, BulkMigrationPlan.Status.DONE):
        return JsonResponse({"detail": f"Plan is already {plan.status}"}, status=409)
    execute_bulk_migration.delay(str(plan_id))
    return JsonResponse({"status": "accepted", "plan_id": str(plan_id)}, status=202)
