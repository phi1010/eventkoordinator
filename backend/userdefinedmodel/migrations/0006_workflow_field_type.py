"""
Migration 0006: Move workflow from per-ConfigVersion to a WORKFLOW field type.

Changes:
- Remove ConfigVersion.workflow FK
- Remove UserDefinedModelEntityNode.current_state FK
- Add FieldDefinition.workflow_definition FK
- Add TypedValue.value_workflow_state FK (FieldValue + FieldDefaultValue)
- Add WorkflowTransition.from_undefined_only BooleanField
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("userdefinedmodel", "0005_add_slug_id_sequence"),
    ]

    operations = [
        # Remove old single-workflow FK from ConfigVersion
        migrations.RemoveField(
            model_name="configversion",
            name="workflow",
        ),

        # Remove single current_state FK from entity node
        migrations.RemoveField(
            model_name="userdefinedmodelentitynode",
            name="current_state",
        ),

        # Add WORKFLOW data type support: workflow_definition FK on FieldDefinition
        migrations.AddField(
            model_name="fielddefinition",
            name="workflow_definition",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="field_definitions",
                to="userdefinedmodel.workflowdefinition",
            ),
        ),

        # Add value_workflow_state FK to FieldValue
        migrations.AddField(
            model_name="fieldvalue",
            name="value_workflow_state",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="userdefinedmodel.workflowstate",
            ),
        ),

        # Add value_workflow_state FK to FieldDefaultValue
        migrations.AddField(
            model_name="fielddefaultvalue",
            name="value_workflow_state",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="userdefinedmodel.workflowstate",
            ),
        ),

        # Add from_undefined_only to WorkflowTransition
        migrations.AddField(
            model_name="workflowtransition",
            name="from_undefined_only",
            field=models.BooleanField(default=False),
        ),
    ]
