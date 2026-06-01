from django.db import models
from django.db.models import Q, UniqueConstraint

from userdefinedmodel.basemodels import MetaBase, PolymorphicMetaBase


class WorkflowDefinition(MetaBase):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    virtual_node_positions = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class WorkflowState(MetaBase):
    workflow = models.ForeignKey(WorkflowDefinition, on_delete=models.CASCADE, related_name="states")
    name = models.CharField(max_length=100)
    is_initial = models.BooleanField(default=False)
    position_x = models.FloatField(default=0.0)
    position_y = models.FloatField(default=0.0)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["workflow"],
                condition=Q(is_initial=True),
                name="one_initial_state_per_workflow",
            ),
            UniqueConstraint(
                fields=["workflow", "name"],
                name="unique_state_name_per_workflow",
            ),
        ]

    def __str__(self):
        return f"{self.workflow} / {self.name}"


class WorkflowStateTranslation(MetaBase):
    state = models.ForeignKey(WorkflowState, on_delete=models.CASCADE, related_name="translations")
    language = models.CharField(max_length=10)
    label = models.CharField(max_length=200)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["state", "language"],
                name="unique_state_translation_per_language",
            )
        ]

    def __str__(self):
        return f"{self.state} [{self.language}]"


class WorkflowTransition(MetaBase):
    workflow = models.ForeignKey(WorkflowDefinition, on_delete=models.CASCADE, related_name="transitions")
    name = models.CharField(max_length=100)
    from_state = models.ForeignKey(
        WorkflowState,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="outgoing_transitions",
    )
    # When True and from_state is null: only allowed when current state is undefined (null).
    # When False and from_state is null: allowed from any state (including undefined).
    from_undefined_only = models.BooleanField(default=False)
    to_state = models.ForeignKey(
        WorkflowState,
        on_delete=models.CASCADE,
        related_name="incoming_transitions",
    )
    source_handle = models.CharField(max_length=30, blank=True, default="")
    target_handle = models.CharField(max_length=30, blank=True, default="")

    def __str__(self):
        return f"{self.workflow} / {self.name}"


class WorkflowTransitionTranslation(MetaBase):
    transition = models.ForeignKey(
        WorkflowTransition, on_delete=models.CASCADE, related_name="translations"
    )
    language = models.CharField(max_length=10)
    label = models.CharField(max_length=200)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["transition", "language"],
                name="unique_transition_translation_per_language",
            )
        ]

    def __str__(self):
        return f"{self.transition} [{self.language}]"


class TransitionAction(PolymorphicMetaBase):
    class Phase(models.TextChoices):
        PRE = "pre"
        POST = "post"

    transition = models.ForeignKey(
        WorkflowTransition, on_delete=models.CASCADE, related_name="actions"
    )
    phase = models.CharField(max_length=4, choices=Phase)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def execute(self, node, triggered_by) -> None:
        raise NotImplementedError


class SendNotificationAction(TransitionAction):
    # Recipients stored as JSON list of config dicts
    recipients_config = models.JSONField(default=list)
    subject_template = models.TextField(blank=True)
    body_template = models.TextField(blank=True)

    def execute(self, node, triggered_by) -> None:
        pass  # Email sending via mailqueue or similar


class SetFieldValueAction(TransitionAction):
    field_slug = models.CharField(max_length=80)
    value_json = models.JSONField(null=True, blank=True)

    def execute(self, node, triggered_by) -> None:
        field_def = node.config_version.field_definitions.filter(slug=self.field_slug).first()
        if field_def:
            fv, _ = node.field_values.get_or_create(field=field_def, language="")
            fv.set_value(self.value_json, field=field_def)
            fv.save()


class TriggerChildTransitionAction(TransitionAction):
    child_transition_name = models.CharField(max_length=100)

    def execute(self, node, triggered_by) -> None:
        from userdefinedmodel.engine import execute_transition
        for child in node.children.all():
            try:
                execute_transition(child, self.child_transition_name, triggered_by)
            except Exception:
                pass  # Post-action failures are logged but don't roll back
