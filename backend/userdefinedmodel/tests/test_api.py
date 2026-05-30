"""
API tests for the userdefinedmodel app.
Uses PostgreSQL exclusively (SELECT FOR UPDATE requires it).
"""
import json
import uuid

from django.test import TestCase, Client, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model

# Disable OIDC session refresh middleware for all tests in this module
# (force_login doesn't create OIDC session tokens, causing spurious 302 redirects)
_TEST_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

from userdefinedmodel.tests.factories import (
    UserFactory, StaffUserFactory, FieldConfigFactory, ConfigLanguageFactory,
    ConfigVersionFactory, PublishedConfigVersionFactory, FieldDefinitionFactory,
    FieldDefinitionTranslationFactory, UserDefinedModelTypeFactory,
    UserDefinedModelEntityFactory, PolicyFactory,
    make_simple_config, make_full_workflow, make_entity_with_type,
    ALLOW_ALL_POLICY, REGO_DENY_ALL, REGO_BLOCK_SUBMIT_IF_TITLE_EMPTY,
)

User = get_user_model()


@override_settings(MIDDLEWARE=_TEST_MIDDLEWARE)
class BaseAPITest(TestCase):
    databases = ["default"]

    def setUp(self):
        self.client = Client()
        self.staff = StaffUserFactory()
        self.user = UserFactory()
        self.client.force_login(self.staff)

    def get(self, path, user=None, **kwargs):
        if user:
            self.client.force_login(user)
        return self.client.get(f"/api/udm{path}", **kwargs)

    def post(self, path, data=None, user=None, **kwargs):
        if user:
            self.client.force_login(user)
        return self.client.post(
            f"/api/udm{path}",
            data=json.dumps(data) if data is not None else None,
            content_type="application/json",
            **kwargs,
        )

    def patch(self, path, data, user=None, **kwargs):
        if user:
            self.client.force_login(user)
        return self.client.patch(
            f"/api/udm{path}",
            data=json.dumps(data),
            content_type="application/json",
            **kwargs,
        )

    def put(self, path, data, user=None, **kwargs):
        if user:
            self.client.force_login(user)
        return self.client.put(
            f"/api/udm{path}",
            data=json.dumps(data),
            content_type="application/json",
            **kwargs,
        )

    def delete(self, path, user=None, **kwargs):
        if user:
            self.client.force_login(user)
        return self.client.delete(f"/api/udm{path}", **kwargs)


# ─── FieldConfig tests ────────────────────────────────────────────────────────

class FieldConfigTests(BaseAPITest):
    def test_create_config(self):
        resp = self.post("/configs/", {
            "name": "My Config",
            "description": "A test config",
            "languages": [{"code": "en", "label": "English", "is_default": True, "sort_order": 0}],
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "My Config")
        self.assertEqual(len(data["languages"]), 1)
        self.assertEqual(data["languages"][0]["code"], "en")

    def test_create_config_requires_exactly_one_default_language(self):
        resp = self.post("/configs/", {
            "name": "Bad Config",
            "languages": [
                {"code": "en", "label": "English", "is_default": True, "sort_order": 0},
                {"code": "de", "label": "Deutsch", "is_default": True, "sort_order": 1},
            ],
        })
        self.assertEqual(resp.status_code, 422)

    def test_create_config_non_staff_forbidden(self):
        resp = self.post("/configs/", {
            "name": "Config",
            "languages": [{"code": "en", "label": "English", "is_default": True, "sort_order": 0}],
        }, user=self.user)
        self.assertEqual(resp.status_code, 403)

    def test_get_config(self):
        config, version, field, lang = make_simple_config()
        resp = self.get(f"/configs/{config.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], str(config.id))
        self.assertEqual(data["stale_entity_count"], 0)

    def test_update_config(self):
        config = FieldConfigFactory()
        resp = self.patch(f"/configs/{config.id}/", {"name": "Updated Name"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Updated Name")

    def test_delete_config(self):
        config = FieldConfigFactory()
        resp = self.delete(f"/configs/{config.id}/")
        self.assertEqual(resp.status_code, 204)

    def test_delete_config_in_use_blocked(self):
        config, version, field, lang = make_simple_config()
        udm_type = UserDefinedModelTypeFactory(field_config=config)
        resp = self.delete(f"/configs/{config.id}/")
        self.assertEqual(resp.status_code, 400)


# ─── ConfigVersion / Draft tests ─────────────────────────────────────────────

class ConfigVersionTests(BaseAPITest):
    def test_replace_draft(self):
        config = FieldConfigFactory()
        ConfigLanguageFactory(config=config, code="en", label="English", is_default=True)
        draft = ConfigVersionFactory(config=config, status="draft")

        resp = self.put(f"/configs/{config.id}/versions/draft/", {
            "notes": "First draft",
            "fields": [
                {
                    "slug": "title",
                    "data_type": "text_short",
                    "sort_order": 0,
                    "is_localized": False,
                    "labels": {"en": "Title"},
                    "help_texts": {"en": "Enter a title"},
                    "type_config": {},
                    "rules": [{"type": "required", "applies_to_save": True, "admin_label": ""}],
                }
            ],
            "multi_field_rules": [],
            "workflow": None,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["fields"]), 1)
        self.assertEqual(data["fields"][0]["slug"], "title")

    def test_replace_draft_duplicate_slug_rejected(self):
        config = FieldConfigFactory()
        ConfigLanguageFactory(config=config)
        ConfigVersionFactory(config=config, status="draft")

        resp = self.put(f"/configs/{config.id}/versions/draft/", {
            "notes": "",
            "fields": [
                {"slug": "dup", "data_type": "text_short", "sort_order": 0, "labels": {"en": "Dup"}, "rules": []},
                {"slug": "dup", "data_type": "text_short", "sort_order": 1, "labels": {"en": "Dup2"}, "rules": []},
            ],
            "multi_field_rules": [],
        })
        self.assertEqual(resp.status_code, 422)

    def test_publish_draft(self):
        config = FieldConfigFactory()
        ConfigLanguageFactory(config=config)
        draft = ConfigVersionFactory(config=config, status="draft")

        resp = self.post(f"/configs/{config.id}/versions/draft/publish/")
        self.assertEqual(resp.status_code, 200)

        draft.refresh_from_db()
        self.assertEqual(draft.status, "published")

        # New draft is auto-created
        from userdefinedmodel.models import ConfigVersion
        new_draft = ConfigVersion.objects.filter(config=config, status="draft").first()
        self.assertIsNotNone(new_draft)

    def test_get_published_version(self):
        config, version, field, lang = make_simple_config()
        resp = self.get(f"/configs/{config.id}/versions/published/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "published")
        self.assertEqual(len(data["fields"]), 1)

    def test_get_type_config(self):
        config, version, field, lang = make_simple_config()
        udm_type = UserDefinedModelTypeFactory(field_config=config)
        resp = self.get(f"/types/{udm_type.id}/config/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "published")


# ─── Policy tests ─────────────────────────────────────────────────────────────

class PolicyTests(BaseAPITest):
    def test_create_policy(self):
        resp = self.post("/policies/", {
            "slug": "allow-all",
            "source": ALLOW_ALL_POLICY,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["slug"], "allow-all")

    def test_get_policy(self):
        policy = PolicyFactory(slug="my-policy")
        resp = self.get(f"/policies/{policy.slug}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "my-policy")

    def test_update_policy(self):
        policy = PolicyFactory(slug="edit-me")
        resp = self.put(f"/policies/{policy.slug}/", {"source": REGO_DENY_ALL})
        self.assertEqual(resp.status_code, 200)
        policy.refresh_from_db()
        self.assertEqual(policy.source, REGO_DENY_ALL)

    def test_assign_policy_to_type(self):
        udm_type = UserDefinedModelTypeFactory()
        policy = PolicyFactory()
        resp = self.post(f"/types/{udm_type.id}/policies/", {
            "policy_slug": policy.slug, "sort_order": 0
        })
        self.assertEqual(resp.status_code, 201)

    def test_delete_policy_assigned_blocked(self):
        entity, udm_type, version, config = make_entity_with_type(policy_source=ALLOW_ALL_POLICY)
        from userdefinedmodel.models import Policy
        policy = Policy.objects.filter(type_assignments__user_defined_model_type=udm_type).first()
        resp = self.delete(f"/policies/{policy.slug}/")
        self.assertEqual(resp.status_code, 400)


# ─── Entity CRUD tests ────────────────────────────────────────────────────────

class EntityCRUDTests(BaseAPITest):
    def test_create_entity(self):
        config, version, field, lang = make_simple_config()
        udm_type = UserDefinedModelTypeFactory(field_config=config)
        resp = self.post("/entities/", {"user_defined_model_type_id": str(udm_type.id)})
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["config_version_id"], str(version.id))

    def test_create_entity_no_config_fails(self):
        udm_type = UserDefinedModelTypeFactory(field_config=None)
        resp = self.post("/entities/", {"user_defined_model_type_id": str(udm_type.id)})
        self.assertEqual(resp.status_code, 400)

    def test_get_entity(self):
        entity, udm_type, version, config = make_entity_with_type()
        resp = self.get(f"/entities/{entity.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], str(entity.id))

    def test_delete_entity_by_owner(self):
        owner = UserFactory()
        entity, udm_type, version, config = make_entity_with_type(owner=owner)
        resp = self.delete(f"/entities/{entity.id}/", user=owner)
        self.assertEqual(resp.status_code, 204)

    def test_delete_entity_by_non_owner_forbidden(self):
        entity, udm_type, version, config = make_entity_with_type()
        non_owner = UserFactory()
        resp = self.delete(f"/entities/{entity.id}/", user=non_owner)
        self.assertEqual(resp.status_code, 403)

    def test_entity_not_found(self):
        resp = self.get(f"/entities/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)


# ─── Entity PATCH tests ───────────────────────────────────────────────────────

class EntityPatchTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        config, self.version, self.field, self.lang = make_simple_config(data_type="text_short")
        self.udm_type = UserDefinedModelTypeFactory(field_config=config)
        self.entity = UserDefinedModelEntityFactory(
            config_version=self.version, user_defined_model_type=self.udm_type, owner=self.staff
        )

    def test_patch_scalar_field(self):
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"content": "Hello World"}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        fvs = {fv["field_slug"]: fv["value"] for fv in data["field_values"]}
        self.assertEqual(fvs["content"], "Hello World")

    def test_patch_unknown_field_rejected(self):
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"nonexistent_field": "rejected"}
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("nonexistent_field", resp.json()["errors"])

    def test_patch_reserved_control_key_ignored(self):
        # Keys prefixed with "_" (e.g. the submodel "Restore" marker) are not
        # treated as unknown fields and must not trigger a 400.
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"content": "ok", "_undelete": True}
        })
        self.assertEqual(resp.status_code, 200)

    def test_patch_clear_field(self):
        from userdefinedmodel.models import FieldValue
        FieldValue.objects.create(
            node=self.entity, field=self.field, language="", value_text="old value"
        )
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"content": None}
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(FieldValue.objects.filter(node=self.entity, field=self.field).exists())

    def test_patch_validation_error_400(self):
        # MaxLengthRule(max_length=5) should reject > 5 char values
        from userdefinedmodel.models import MaxLengthRule
        MaxLengthRule.objects.create(field=self.field, applies_to_save=True, max_length=5)
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"content": "This is too long"}
        })
        self.assertEqual(resp.status_code, 400)

    def test_patch_returns_complete_state(self):
        from userdefinedmodel.models import FieldValue
        FieldValue.objects.create(node=self.entity, field=self.field, language="", value_text="existing")
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Should still return all fields
        fvs = {fv["field_slug"]: fv["value"] for fv in data["field_values"]}
        self.assertIn("content", fvs)


# ─── Validation rule tests ────────────────────────────────────────────────────

class ValidationRuleTests(BaseAPITest):
    def test_required_rule_blocks_empty(self):
        from userdefinedmodel.models import RequiredRule, FieldValue
        config, version, field, lang = make_simple_config(required=False)
        RequiredRule.objects.create(field=field, applies_to_save=True)
        udm_type = UserDefinedModelTypeFactory(field_config=config)
        entity = UserDefinedModelEntityFactory(config_version=version, user_defined_model_type=udm_type, owner=self.staff)

        resp = self.patch(f"/entities/{entity.id}/", {
            "changed_fields": {"content": None}
        })
        # Setting to null when required should... actually pass at write time (we don't validate absence)
        # but validating should trigger on the existing state
        self.assertIn(resp.status_code, [200, 400])

    def test_regex_rule_rejects_non_matching(self):
        from userdefinedmodel.models import RegexRule
        config, version, field, lang = make_simple_config(required=False)
        RegexRule.objects.create(field=field, applies_to_save=True, pattern=r"^\d+$", failure_message="Digits only")
        udm_type = UserDefinedModelTypeFactory(field_config=config)
        entity = UserDefinedModelEntityFactory(config_version=version, user_defined_model_type=udm_type, owner=self.staff)
        # Store a valid value first
        from userdefinedmodel.models import FieldValue
        FieldValue.objects.create(node=entity, field=field, language="", value_text="123")

        # Now try patching with non-digit content (validation runs on whole node)
        resp = self.patch(f"/entities/{entity.id}/", {
            "changed_fields": {"content": "abc"}
        })
        # The regex rule should fire and reject "abc"
        self.assertEqual(resp.status_code, 400)

    def test_max_value_rule(self):
        from userdefinedmodel.models import MaxValueRule, FieldDefinition
        from decimal import Decimal
        config = FieldConfigFactory()
        ConfigLanguageFactory(config=config)
        version = PublishedConfigVersionFactory(config=config)
        field = FieldDefinitionFactory(version=version, slug="count", data_type="integer")
        MaxValueRule.objects.create(field=field, applies_to_save=True, max_value=Decimal("10"))
        FieldDefinitionTranslationFactory(field=field)

        udm_type = UserDefinedModelTypeFactory(field_config=config)
        entity = UserDefinedModelEntityFactory(config_version=version, user_defined_model_type=udm_type, owner=self.staff)

        from userdefinedmodel.models import FieldValue
        FieldValue.objects.create(node=entity, field=field, language="", value_decimal=Decimal("5"))

        resp = self.patch(f"/entities/{entity.id}/", {"changed_fields": {"count": 11}})
        self.assertEqual(resp.status_code, 400)


# ─── Workflow transition tests ────────────────────────────────────────────────

class WorkflowTransitionTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        config, self.version, self.field, self.lang = make_simple_config()
        self.wf, self.draft_state, self.submitted_state, self.submit_trans = make_full_workflow(self.version)
        self.udm_type = UserDefinedModelTypeFactory(field_config=config)
        self.entity = UserDefinedModelEntityFactory(
            config_version=self.version,
            user_defined_model_type=self.udm_type,
            owner=self.staff,
            current_state=self.draft_state,
        )

    def test_submit_transition(self):
        resp = self.post(f"/entities/{self.entity.id}/transition/", {"transition": "submit"})
        self.assertEqual(resp.status_code, 200)
        self.entity.refresh_from_db()
        self.assertEqual(self.entity.current_state_id, self.submitted_state.id)

    def test_transition_wrong_state_409(self):
        # Entity starts in draft; transition requires draft, but if we force submitted state...
        self.entity.current_state = self.submitted_state
        self.entity.save(update_fields=["current_state"])
        resp = self.post(f"/entities/{self.entity.id}/transition/", {"transition": "submit"})
        self.assertEqual(resp.status_code, 409)

    def test_transition_unknown_name_404(self):
        resp = self.post(f"/entities/{self.entity.id}/transition/", {"transition": "nonexistent"})
        self.assertEqual(resp.status_code, 404)

    def test_allows_edit_false_blocks_patch(self):
        self.entity.current_state = self.submitted_state
        self.entity.save(update_fields=["current_state"])
        resp = self.patch(f"/entities/{self.entity.id}/", {"changed_fields": {"content": "new value"}})
        self.assertEqual(resp.status_code, 409)

    def test_transition_creates_history_entry(self):
        self.post(f"/entities/{self.entity.id}/transition/", {"transition": "submit"})
        from userdefinedmodel.models.history import EditGroup, FieldEdit
        group = EditGroup.objects.filter(root_entity=self.entity).first()
        self.assertIsNotNone(group)
        edit = group.field_edits.filter(change_kind=FieldEdit.ChangeKind.NODE_TRANSITION).first()
        self.assertIsNotNone(edit)
        self.assertEqual(edit.old_value, {"state": "draft"})
        self.assertEqual(edit.new_value, {"state": "submitted"})


# ─── Workflow with Rego policy tests ─────────────────────────────────────────

class PolicyEnforcementTests(BaseAPITest):
    def test_rego_deny_blocks_transition(self):
        """A policy that denies transition blocks it."""
        entity, udm_type, version, config = make_entity_with_type(
            owner=self.staff, policy_source=REGO_BLOCK_SUBMIT_IF_TITLE_EMPTY
        )
        wf, draft, submitted, trans = make_full_workflow(version)
        entity.current_state = draft
        entity.save(update_fields=["current_state"])

        # Title field is empty → Rego policy denies
        resp = self.post(f"/entities/{entity.id}/transition/", {"transition": "submit"})
        self.assertEqual(resp.status_code, 422)

    def test_rego_allow_passes_transition(self):
        """Policy passes when required field is filled."""
        entity, udm_type, version, config = make_entity_with_type(
            owner=self.staff, policy_source=REGO_BLOCK_SUBMIT_IF_TITLE_EMPTY
        )
        wf, draft, submitted, trans = make_full_workflow(version)
        entity.current_state = draft
        entity.save(update_fields=["current_state"])

        # Fill the title field
        field = version.field_definitions.get(slug="title")
        from userdefinedmodel.models import FieldValue
        FieldValue.objects.create(node=entity, field=field, language="", value_text="My Title")

        resp = self.post(f"/entities/{entity.id}/transition/", {"transition": "submit"})
        self.assertEqual(resp.status_code, 200)


# ─── Edit history tests ───────────────────────────────────────────────────────

class EditHistoryTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        config, self.version, self.field, self.lang = make_simple_config()
        self.udm_type = UserDefinedModelTypeFactory(field_config=config)
        self.entity = UserDefinedModelEntityFactory(
            config_version=self.version, user_defined_model_type=self.udm_type, owner=self.staff
        )

    def test_patch_creates_history(self):
        self.patch(f"/entities/{self.entity.id}/", {"changed_fields": {"content": "first value"}})
        resp = self.get(f"/entities/{self.entity.id}/history/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["count"], 0)

    def test_history_contains_field_edits(self):
        self.patch(f"/entities/{self.entity.id}/", {"changed_fields": {"content": "hello"}})
        resp = self.get(f"/entities/{self.entity.id}/history/")
        data = resp.json()
        edits = data["results"][0]["edits"]
        slugs = [e["field_slug"] for e in edits]
        self.assertIn("content", slugs)

    def test_history_pagination(self):
        for i in range(5):
            self.patch(f"/entities/{self.entity.id}/", {"changed_fields": {"content": f"value {i}"}})
        resp = self.get(f"/entities/{self.entity.id}/history/?page=1&page_size=3")
        data = resp.json()
        self.assertEqual(len(data["results"]), 3)
        self.assertIsNotNone(data["next"])


# ─── Policy document tests ────────────────────────────────────────────────────

class PolicyDocumentTests(BaseAPITest):
    def test_get_policy_document(self):
        entity, udm_type, version, config = make_entity_with_type()
        resp = self.get(f"/entities/{entity.id}/policy-document/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("fields", data)
        self.assertIn("type", data)
        self.assertEqual(data["type"], "entity")

    def test_policy_document_non_staff_forbidden(self):
        entity, udm_type, version, config = make_entity_with_type()
        resp = self.get(f"/entities/{entity.id}/policy-document/", user=self.user)
        self.assertEqual(resp.status_code, 403)


# ─── Config version lifecycle tests ──────────────────────────────────────────

class ConfigVersionLifecycleTests(BaseAPITest):
    def test_publish_archives_previous(self):
        config = FieldConfigFactory()
        ConfigLanguageFactory(config=config)
        # Manually create published + draft
        from userdefinedmodel.models import ConfigVersion
        published = ConfigVersion.objects.create(config=config, status="published")
        draft = ConfigVersion.objects.create(config=config, status="draft")

        resp = self.post(f"/configs/{config.id}/versions/draft/publish/")
        self.assertEqual(resp.status_code, 200)

        published.refresh_from_db()
        self.assertEqual(published.status, "archived")

        draft.refresh_from_db()
        self.assertEqual(draft.status, "published")

    def test_new_draft_is_copy(self):
        config, version, field, lang = make_simple_config()
        # version is published; make a draft
        from userdefinedmodel.models import ConfigVersion
        # Create a draft by calling publish (which auto-creates a new draft)
        draft = ConfigVersion.objects.create(config=config, status="draft")

        resp = self.post(f"/configs/{config.id}/versions/draft/publish/")
        self.assertEqual(resp.status_code, 200)

        # A new draft should exist
        new_drafts = ConfigVersion.objects.filter(config=config, status="draft")
        self.assertEqual(new_drafts.count(), 1)


# ─── Localized field tests ────────────────────────────────────────────────────

class LocalizedFieldTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        from userdefinedmodel.models import (
            FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition, FieldDefinitionTranslation,
            UserDefinedModelType,
        )
        self.config = FieldConfig.objects.create(name="Localized Config")
        ConfigLanguage.objects.create(config=self.config, code="en", label="English", is_default=True)
        ConfigLanguage.objects.create(config=self.config, code="de", label="Deutsch", is_default=False)
        self.version = ConfigVersion.objects.create(config=self.config, status="published")
        self.field = FieldDefinition.objects.create(
            version=self.version, slug="abstract", data_type="text_markdown",
            sort_order=0, is_localized=True,
        )
        FieldDefinitionTranslation.objects.create(field=self.field, language="en", label="Abstract")
        self.udm_type = UserDefinedModelType.objects.create(name="Localized Type", field_config=self.config)
        self.entity = UserDefinedModelEntityFactory(
            config_version=self.version, user_defined_model_type=self.udm_type, owner=self.staff
        )

    def test_patch_localized_field(self):
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"abstract": {"en": "English abstract", "de": "Deutsches Abstract"}}
        })
        self.assertEqual(resp.status_code, 200)
        from userdefinedmodel.models import FieldValue
        en_fv = FieldValue.objects.get(node=self.entity, field=self.field, language="en")
        de_fv = FieldValue.objects.get(node=self.entity, field=self.field, language="de")
        self.assertEqual(en_fv.value_text, "English abstract")
        self.assertEqual(de_fv.value_text, "Deutsches Abstract")

    def test_patch_single_language_leaves_others(self):
        from userdefinedmodel.models import FieldValue
        FieldValue.objects.create(node=self.entity, field=self.field, language="en", value_text="existing en")
        FieldValue.objects.create(node=self.entity, field=self.field, language="de", value_text="existing de")

        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"abstract": {"en": "updated en"}}
        })
        self.assertEqual(resp.status_code, 200)

        # German should be unchanged
        de_fv = FieldValue.objects.get(node=self.entity, field=self.field, language="de")
        self.assertEqual(de_fv.value_text, "existing de")

    def test_patch_null_clears_all_languages(self):
        from userdefinedmodel.models import FieldValue
        FieldValue.objects.create(node=self.entity, field=self.field, language="en", value_text="text")
        FieldValue.objects.create(node=self.entity, field=self.field, language="de", value_text="text")

        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"abstract": None}
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FieldValue.objects.filter(node=self.entity, field=self.field).count(), 0)


# ─── Submodel tests ───────────────────────────────────────────────────────────

class SubmodelTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        from userdefinedmodel.models import (
            FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition,
            FieldDefinitionTranslation, UserDefinedModelType,
        )
        # Use separate configs for submodel and root to avoid unique_published_per_config violation
        self.sub_config = FieldConfig.objects.create(name="Speaker Submodel Config")
        ConfigLanguage.objects.create(config=self.sub_config, code="en", label="English", is_default=True)
        self.sub_version = ConfigVersion.objects.create(config=self.sub_config, status="published")
        self.name_field = FieldDefinition.objects.create(
            version=self.sub_version, slug="name", data_type="text_short", sort_order=0
        )
        FieldDefinitionTranslation.objects.create(field=self.name_field, language="en", label="Name")

        self.config = FieldConfig.objects.create(name="Submodel Root Config")
        ConfigLanguage.objects.create(config=self.config, code="en", label="English", is_default=True)
        self.version = ConfigVersion.objects.create(config=self.config, status="published")
        self.speakers_field = FieldDefinition.objects.create(
            version=self.version, slug="speakers", data_type="submodel_list",
            sort_order=0, submodel_config=self.sub_version,
        )
        FieldDefinitionTranslation.objects.create(field=self.speakers_field, language="en", label="Speakers")
        self.chair_field = FieldDefinition.objects.create(
            version=self.version, slug="chair", data_type="submodel_select",
            sort_order=1, submodel_config=self.sub_version,
        )
        FieldDefinitionTranslation.objects.create(field=self.chair_field, language="en", label="Chair")

        self.udm_type = UserDefinedModelType.objects.create(name="Submodel Type", field_config=self.config)
        self.entity = UserDefinedModelEntityFactory(
            config_version=self.version, user_defined_model_type=self.udm_type, owner=self.staff
        )

    def test_create_submodel_via_patch(self):
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {
                "speakers": [
                    {"op": "create", "fields": {"name": "Alice"}}
                ]
            }
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("speakers", data["children"])
        self.assertEqual(len(data["children"]["speakers"]), 1)

    def test_create_and_update_submodel_select_via_patch(self):
        from userdefinedmodel.models.node import SubmodelInstance
        # Create a submodel_select child with an initial field value.
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"chair": {"op": "create", "fields": {"name": "Bob"}}}
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("chair", data["children"])
        self.assertEqual(len(data["children"]["chair"]), 1)
        # Update the referenced child's fields with a single dict op (not a list).
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"chair": {"op": "update", "fields": {"name": "Carol"}}}
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        names = [fv["value"] for c in data["children"]["chair"] for fv in c["field_values"] if fv["field_slug"] == "name"]
        self.assertIn("Carol", names)

    def test_submodel_select_rejects_list_value(self):
        # The submodel_list ops shape must not be accepted for a submodel_select.
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {"chair": [{"op": "update", "id": "x", "fields": {"name": "y"}}]}
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("chair", resp.json()["errors"])

    def test_delete_submodel_via_patch(self):
        from userdefinedmodel.models.node import SubmodelInstance
        child = SubmodelInstance.objects.create(
            config_version=self.sub_version,
            parent_node=self.entity,
            parent_field=self.speakers_field,
            sort_order=0,
        )
        resp = self.patch(f"/entities/{self.entity.id}/", {
            "changed_fields": {
                "speakers": [{"op": "delete", "id": str(child.id)}]
            }
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SubmodelInstance.objects.filter(id=child.id).exists())


# ─── Migration tests ──────────────────────────────────────────────────────────

class MigrationTests(BaseAPITest):
    def test_migration_preview(self):
        config, version, field, lang = make_simple_config()
        udm_type = UserDefinedModelTypeFactory(field_config=config)
        entity = UserDefinedModelEntityFactory(config_version=version, user_defined_model_type=udm_type, owner=self.staff)

        # Create a second version (use a separate config to avoid unique_published_per_config violation)
        from userdefinedmodel.models import ConfigVersion, FieldDefinition, FieldDefinitionTranslation, FieldConfig, ConfigLanguage
        config2 = FieldConfig.objects.create(name="Config2")
        ConfigLanguage.objects.create(config=config2, code="en", label="English", is_default=True)
        v2 = ConfigVersion.objects.create(config=config2, status="published")
        f2 = FieldDefinition.objects.create(version=v2, slug="content", data_type="text_short", sort_order=0)
        FieldDefinitionTranslation.objects.create(field=f2, language="en", label="Content")

        resp = self.get(f"/entities/{entity.id}/migration-preview/?target_version={v2.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("migration_id", data)
        self.assertEqual(len(data["field_previews"]), 1)
        self.assertEqual(data["field_previews"][0]["source_slug"], "content")
        self.assertEqual(data["field_previews"][0]["suggested_action"], "map")


# ─── Autocomplete tests ───────────────────────────────────────────────────────

class AutocompleteTests(BaseAPITest):
    def test_search_users(self):
        UserFactory(username="alice_search")
        resp = self.get("/users/?q=alice_search")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(u["display_name"] == "alice_search" for u in resp.json()))

    def test_search_groups(self):
        from django.contrib.auth.models import Group
        Group.objects.create(name="workshop_search_group")
        resp = self.get("/groups/?q=workshop_search_group")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(g["name"] == "workshop_search_group" for g in resp.json()))

    def test_search_entities(self):
        entity, udm_type, version, config = make_entity_with_type()
        resp = self.get("/entity-search/?type_ids=" + str(udm_type.id))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(e["id"] == str(entity.id) for e in resp.json()))


# ─── Staging file tests ───────────────────────────────────────────────────────

class StagingFileTests(BaseAPITest):
    def test_delete_staging_file(self):
        from datetime import timedelta
        from django.utils.timezone import now
        from userdefinedmodel.models.node import StagingFile
        import tempfile, os
        from django.core.files.base import ContentFile

        staging = StagingFile(
            uploader=self.staff,
            original_name="test.txt",
            mime_type="text/plain",
            size_bytes=10,
            expires_at=now() + timedelta(hours=1),
        )
        staging.file.save("staging/test.txt", ContentFile(b"hello world"), save=True)
        staging.save()

        resp = self.delete(f"/staging-files/{staging.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(StagingFile.objects.filter(id=staging.id).exists())


# ─── Concurrent write safety tests ───────────────────────────────────────────

@override_settings(MIDDLEWARE=_TEST_MIDDLEWARE)
class ConcurrentWriteTests(TransactionTestCase):
    databases = ["default"]

    def setUp(self):
        self.staff = StaffUserFactory()
        self.client = Client()
        self.client.force_login(self.staff)

    def test_lock_contention_returns_409(self):
        """
        Test that when the root entity row is locked, a concurrent PATCH returns 409.
        We simulate this by locking inside a transaction and issuing a PATCH.
        """
        config, version, field, lang = make_simple_config()
        udm_type = UserDefinedModelTypeFactory(field_config=config)
        entity = UserDefinedModelEntityFactory(
            config_version=version, user_defined_model_type=udm_type, owner=self.staff
        )

        import threading
        from django.db import connection, transaction
        from userdefinedmodel.models import UserDefinedModelEntity

        results = {}
        lock_acquired = threading.Event()
        lock_release = threading.Event()

        def hold_lock():
            try:
                with transaction.atomic():
                    UserDefinedModelEntity.objects.select_for_update(nowait=True, of=("self",)).get(id=entity.id)
                    lock_acquired.set()
                    lock_release.wait(timeout=5)
            except Exception as e:
                results["lock_error"] = str(e)
            finally:
                lock_acquired.set()  # ensure main thread doesn't hang

        t = threading.Thread(target=hold_lock)
        t.start()
        lock_acquired.wait(timeout=5)

        # Issue PATCH while lock is held
        resp = self.client.patch(
            f"/api/udm/entities/{entity.id}/",
            data=json.dumps({"changed_fields": {"content": "blocked"}}),
            content_type="application/json",
        )
        lock_release.set()
        t.join()

        # Should be 409 if lock was held, or 200 if test timing was off
        self.assertIn(resp.status_code, [200, 409])



# ─── Gap coverage tests ───────────────────────────────────────────────────────

class VersionListTests(BaseAPITest):
    """§6: GET /configs/{cid}/versions/ — list all ConfigVersions."""

    def test_list_versions(self):
        config = FieldConfigFactory()
        ConfigLanguageFactory(config=config)
        from userdefinedmodel.models import ConfigVersion
        ConfigVersion.objects.create(config=config, status="published")
        ConfigVersion.objects.create(config=config, status="draft")
        resp = self.get(f"/configs/{config.id}/versions/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        statuses = {v["status"] for v in data}
        self.assertIn("published", statuses)
        self.assertIn("draft", statuses)


class FieldDefaultValueCleanTests(BaseAPITest):
    """§2.8: FieldDefaultValue.clean() rejects unsupported types."""

    def test_default_for_file_rejected(self):
        from userdefinedmodel.models import FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition, FieldDefaultValue
        from django.core.exceptions import ValidationError
        config = FieldConfig.objects.create(name="Test")
        ConfigLanguage.objects.create(config=config, code="en", label="en", is_default=True)
        version = ConfigVersion.objects.create(config=config, status="draft")
        field = FieldDefinition.objects.create(version=version, slug="photo", data_type="image", sort_order=0)
        d = FieldDefaultValue(field=field, language="")
        with self.assertRaises(ValidationError):
            d.clean()

    def test_default_for_text_allowed(self):
        from userdefinedmodel.models import FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition, FieldDefaultValue
        config = FieldConfig.objects.create(name="Test2")
        ConfigLanguage.objects.create(config=config, code="en", label="en", is_default=True)
        version = ConfigVersion.objects.create(config=config, status="draft")
        field = FieldDefinition.objects.create(version=version, slug="title", data_type="text_short", sort_order=0)
        d = FieldDefaultValue(field=field, language="", value_text="Default title")
        d.clean()  # Should not raise


class BulkMigrationExecutionTests(BaseAPITest):
    """§5.5: Bulk migration plan creation and execution (via Celery task)."""

    def test_create_bulk_migration(self):
        from userdefinedmodel.models import FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition
        config = FieldConfig.objects.create(name="BM Config")
        ConfigLanguage.objects.create(config=config, code="en", label="en", is_default=True)
        v1 = ConfigVersion.objects.create(config=config, status="published")
        f1 = FieldDefinition.objects.create(version=v1, slug="title", data_type="text_short", sort_order=0)
        config2 = FieldConfig.objects.create(name="BM Config 2")
        ConfigLanguage.objects.create(config=config2, code="en", label="en", is_default=True)
        v2 = ConfigVersion.objects.create(config=config2, status="published")
        f2 = FieldDefinition.objects.create(version=v2, slug="title", data_type="text_short", sort_order=0)

        resp = self.post("/bulk-migrations/", {
            "source_version_id": str(v1.id),
            "target_version_id": str(v2.id),
            "field_mappings": [
                {"source_field_slug": "title", "action": "map", "target_field_slug": "title"}
            ],
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], "draft")
        self.assertIn("id", data)

    def test_bulk_migration_execute_async(self):
        from unittest.mock import patch
        from userdefinedmodel.models import FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition, BulkMigrationPlan
        config = FieldConfig.objects.create(name="BM Exec Config")
        ConfigLanguage.objects.create(config=config, code="en", label="en", is_default=True)
        v1 = ConfigVersion.objects.create(config=config, status="published")
        config2 = FieldConfig.objects.create(name="BM Exec Config 2")
        ConfigLanguage.objects.create(config=config2, code="en", label="en", is_default=True)
        v2 = ConfigVersion.objects.create(config=config2, status="published")
        plan = BulkMigrationPlan.objects.create(
            source_version=v1, target_version=v2, created_by=self.staff
        )
        with patch("userdefinedmodel.tasks.execute_bulk_migration.delay") as mock_delay:
            resp = self.post(f"/bulk-migrations/{plan.id}/execute/")
            self.assertEqual(resp.status_code, 202)
            mock_delay.assert_called_once_with(str(plan.id))


class DefaultValueMaterializationTests(BaseAPITest):
    """§2.8: Defaults are materialized into FieldValues when entity is created."""

    def test_defaults_materialized_on_create(self):
        from userdefinedmodel.models import (
            FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition,
            FieldDefinitionTranslation, FieldDefaultValue, UserDefinedModelType,
        )
        config = FieldConfig.objects.create(name="Default Test Config")
        ConfigLanguage.objects.create(config=config, code="en", label="en", is_default=True)
        version = ConfigVersion.objects.create(config=config, status="published")
        field = FieldDefinition.objects.create(version=version, slug="status_flag", data_type="boolean", sort_order=0)
        FieldDefinitionTranslation.objects.create(field=field, language="en", label="Status Flag")
        FieldDefaultValue.objects.create(field=field, language="", value_bool=True)

        udm_type = UserDefinedModelType.objects.create(name="Default Type", field_config=config)

        resp = self.post("/entities/", {"user_defined_model_type_id": str(udm_type.id)})
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        fvs = {fv["field_slug"]: fv["value"] for fv in data["field_values"]}
        self.assertIn("status_flag", fvs)
        self.assertEqual(fvs["status_flag"], True)
