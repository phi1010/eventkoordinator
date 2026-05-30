"""
factory_boy factories for userdefinedmodel test data.

Usage:
    config = FieldConfigFactory()          # with one language
    version = PublishedConfigVersionFactory(config=config)
    udm_type = UserDefinedModelTypeFactory(field_config=config)
    entity = UserDefinedModelEntityFactory(
        user_defined_model_type=udm_type,
        config_version=version,
    )
"""
import factory
from django.contrib.auth.models import Group
from factory.django import DjangoModelFactory


# ─── User ────────────────────────────────────────────────────────────────────

class UserFactory(DjangoModelFactory):
    class Meta:
        model = "openid_user_management.OpenIDUser"
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    is_active = True
    is_staff = False

    @classmethod
    def staff(cls, **kwargs):
        return cls(is_staff=True, **kwargs)


class StaffUserFactory(UserFactory):
    is_staff = True


# ─── FieldConfig ─────────────────────────────────────────────────────────────

class FieldConfigFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.FieldConfig"

    name = factory.Sequence(lambda n: f"Config {n}")
    description = ""


class ConfigLanguageFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.ConfigLanguage"

    config = factory.SubFactory(FieldConfigFactory)
    code = "en"
    label = "English"
    is_default = True
    sort_order = 0


class WorkflowDefinitionFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.WorkflowDefinition"

    name = factory.Sequence(lambda n: f"Workflow {n}")
    description = ""


class WorkflowStateFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.WorkflowState"

    workflow = factory.SubFactory(WorkflowDefinitionFactory)
    name = factory.Sequence(lambda n: f"state{n}")
    is_initial = False
    allows_edit = True


class WorkflowTransitionFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.WorkflowTransition"

    workflow = factory.SubFactory(WorkflowDefinitionFactory)
    name = factory.Sequence(lambda n: f"transition{n}")
    from_state = None
    to_state = factory.SubFactory(WorkflowStateFactory)


class ConfigVersionFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.ConfigVersion"

    config = factory.SubFactory(FieldConfigFactory)
    status = "draft"
    notes = ""
    workflow = None


class PublishedConfigVersionFactory(ConfigVersionFactory):
    status = "published"


class FieldDefinitionFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.FieldDefinition"

    version = factory.SubFactory(ConfigVersionFactory)
    slug = factory.Sequence(lambda n: f"field{n}")
    data_type = "text_short"
    sort_order = factory.Sequence(lambda n: n)
    is_localized = False
    type_config = {}


class FieldDefinitionTranslationFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.FieldDefinitionTranslation"

    field = factory.SubFactory(FieldDefinitionFactory)
    language = "en"
    label = factory.LazyAttribute(lambda obj: obj.field.slug.replace("_", " ").title())
    help_text = ""


# ─── Validation rules ─────────────────────────────────────────────────────────

class RequiredRuleFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.RequiredRule"

    field = factory.SubFactory(FieldDefinitionFactory)
    applies_to_save = True
    admin_label = "Required"


class MaxLengthRuleFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.MaxLengthRule"

    field = factory.SubFactory(FieldDefinitionFactory)
    applies_to_save = True
    max_length = 500
    admin_label = ""


class MinValueRuleFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.MinValueRule"

    field = factory.SubFactory(FieldDefinitionFactory, data_type="integer")
    applies_to_save = True
    min_value = 0
    admin_label = ""


# ─── Policy ───────────────────────────────────────────────────────────────────

# Minimal allow-all policy for tests that need auth but don't care about rules
ALLOW_ALL_POLICY = """
package udm

import rego.v1

allow := true
"""

# Owner/editor edit policy
OWNER_EDITOR_POLICY = """
package udm

import rego.v1

allow if {
    input.action in {"view", "edit", "save", "create", "delete", "browse"}
    user_is_participant
}

allow if {
    input.user.is_staff
}

user_is_participant if {
    input.entity.owner.id == input.user.id
}
user_is_participant if {
    some editor in input.entity.editors
    editor.id == input.user.id
}
"""


class PolicyFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.Policy"
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"policy-{n}")
    source = ALLOW_ALL_POLICY


# ─── UserDefinedModelType ─────────────────────────────────────────────────────

class UserDefinedModelTypeFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.UserDefinedModelType"

    name = factory.Sequence(lambda n: f"Type {n}")
    description = ""
    field_config = None


# ─── Entity nodes ─────────────────────────────────────────────────────────────

class UserDefinedModelEntityFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.UserDefinedModelEntity"

    config_version = factory.SubFactory(PublishedConfigVersionFactory)
    user_defined_model_type = factory.SubFactory(UserDefinedModelTypeFactory)
    owner = factory.SubFactory(UserFactory)
    overflow_data = {}


class SubmodelInstanceFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.SubmodelInstance"

    config_version = factory.SubFactory(PublishedConfigVersionFactory)
    parent_node = factory.SubFactory(UserDefinedModelEntityFactory)
    parent_field = factory.SubFactory(FieldDefinitionFactory, data_type="submodel_list")
    sort_order = factory.Sequence(lambda n: n)


class FieldValueFactory(DjangoModelFactory):
    class Meta:
        model = "userdefinedmodel.FieldValue"

    node = factory.SubFactory(UserDefinedModelEntityFactory)
    field = factory.SubFactory(FieldDefinitionFactory)
    language = ""
    value_text = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_simple_config(data_type="text_short", required=True, max_length=None):
    """
    Create a complete FieldConfig→published ConfigVersion→FieldDefinition set
    suitable for testing entities.

    Returns: (config, version, field_def, language)
    """
    from userdefinedmodel.models import (
        FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition,
        FieldDefinitionTranslation, RequiredRule, MaxLengthRule,
    )

    config = FieldConfig.objects.create(name="Test Config", description="")
    lang = ConfigLanguage.objects.create(config=config, code="en", label="English", is_default=True)

    version = ConfigVersion.objects.create(config=config, status="published")
    field = FieldDefinition.objects.create(
        version=version, slug="content", data_type=data_type,
        sort_order=0, type_config={},
    )
    FieldDefinitionTranslation.objects.create(field=field, language="en", label="Content")

    if required:
        RequiredRule.objects.create(field=field, applies_to_save=True)
    if max_length:
        MaxLengthRule.objects.create(field=field, applies_to_save=True, max_length=max_length)

    return config, version, field, lang


def make_full_workflow(version=None):
    """
    Create a WorkflowDefinition with draft→submitted states and a submit transition.
    If version is provided, assigns it as version.workflow.

    Returns: (workflow, draft_state, submitted_state, submit_transition)
    """
    from userdefinedmodel.models import (
        WorkflowDefinition, WorkflowState, WorkflowStateTranslation,
        WorkflowTransition, WorkflowTransitionTranslation,
    )

    wf = WorkflowDefinition.objects.create(name="Test Workflow")
    draft = WorkflowState.objects.create(workflow=wf, name="draft", is_initial=True, allows_edit=True)
    WorkflowStateTranslation.objects.create(state=draft, language="en", label="Draft")
    submitted = WorkflowState.objects.create(workflow=wf, name="submitted", is_initial=False, allows_edit=False)
    WorkflowStateTranslation.objects.create(state=submitted, language="en", label="Submitted")

    trans = WorkflowTransition.objects.create(
        workflow=wf, name="submit", from_state=draft, to_state=submitted
    )
    WorkflowTransitionTranslation.objects.create(transition=trans, language="en", label="Submit")

    if version is not None:
        version.workflow = wf
        version.save(update_fields=["workflow"])

    return wf, draft, submitted, trans


def make_entity_with_type(owner=None, policy_source=None):
    """
    Create a complete entity with UDMType, published config, and optionally a policy.

    Returns: (entity, udm_type, version, config)
    """
    from userdefinedmodel.models import (
        FieldConfig, ConfigLanguage, ConfigVersion, FieldDefinition,
        FieldDefinitionTranslation, UserDefinedModelType, UserDefinedModelEntity,
        Policy, UserDefinedModelTypePolicy,
    )

    if owner is None:
        owner = UserFactory()

    config = FieldConfig.objects.create(name="Entity Config")
    ConfigLanguage.objects.create(config=config, code="en", label="English", is_default=True)
    version = ConfigVersion.objects.create(config=config, status="published")
    field = FieldDefinition.objects.create(version=version, slug="title", data_type="text_short", sort_order=0)
    FieldDefinitionTranslation.objects.create(field=field, language="en", label="Title")

    udm_type = UserDefinedModelType.objects.create(name="Test Type", field_config=config)

    entity = UserDefinedModelEntity.objects.create(
        config_version=version, user_defined_model_type=udm_type, owner=owner,
    )

    if policy_source:
        policy = Policy.objects.create(slug=f"policy-{entity.id}", source=policy_source)
        UserDefinedModelTypePolicy.objects.create(
            user_defined_model_type=udm_type, policy=policy, sort_order=0
        )

    return entity, udm_type, version, config


# ─── Rego policy fixtures ─────────────────────────────────────────────────────

REGO_ALLOW_ALL = ALLOW_ALL_POLICY

REGO_DENY_ALL = """
package udm
import rego.v1
allow := false
"""

REGO_STAFF_ONLY = """
package udm
import rego.v1

allow if {
    input.user.is_staff
}
"""

REGO_OWNER_EDIT = """
package udm
import rego.v1

allow if {
    input.action in {"view", "browse"}
}

allow if {
    input.action in {"edit", "save", "create", "delete"}
    input.entity.owner.id == input.user.id
}

allow if {
    input.user.is_staff
}
"""

REGO_BLOCK_SUBMIT_IF_TITLE_EMPTY = """
package udm
import rego.v1

allow := true

deny contains msg if {
    input.action == "transition"
    input.transition == "submit"
    not input.entity.fields.title.value
    msg := {
        "level": "error",
        "message": {"en": "Title is required for submission"},
        "field_slug": "title",
    }
}
"""
