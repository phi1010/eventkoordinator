"""
Migration: Speaker belongs to exactly one Proposal.

Changes:
- Remove ProposalSpeaker through-model and its historical record
- Remove Proposal.speakers ManyToManyField
- Remove unique constraint from Speaker.email, allow blank
- Add Speaker.proposal ForeignKey (CASCADE)
- Add Speaker.role CharField
- Add Speaker.sort_order PositiveSmallIntegerField
- Update HistoricalSpeaker to match
"""

import django.db.models.deletion
from django.db import migrations, models


def delete_all_speakers(apps, schema_editor):
    """Delete all existing speaker and ProposalSpeaker rows before schema change."""
    Speaker = apps.get_model("apiv1", "Speaker")
    Speaker.objects.all().delete()
    try:
        ProposalSpeaker = apps.get_model("apiv1", "ProposalSpeaker")
        ProposalSpeaker.objects.all().delete()
    except LookupError:
        pass


class Migration(migrations.Migration):
    atomic = False  # Needed: PostgreSQL can't mix DML and DDL in same transaction

    dependencies = [
        ("apiv1", "0011_alter_historicalproposal_photo_and_more"),
    ]

    operations = [
        # 1. Clear existing speaker data so we can safely restructure
        migrations.RunPython(delete_all_speakers, migrations.RunPython.noop),

        # 2. Remove constraints on ProposalSpeaker before deleting it
        migrations.RemoveConstraint(
            model_name="proposalspeaker",
            name="unique_proposal_speaker",
        ),
        migrations.RemoveConstraint(
            model_name="proposalspeaker",
            name="unique_primary_speaker_per_proposal",
        ),

        # 3. Delete the ProposalSpeaker model and its historical counterpart
        migrations.DeleteModel(name="HistoricalProposalSpeaker"),
        migrations.DeleteModel(name="ProposalSpeaker"),

        # 4. Remove the speakers ManyToManyField from Proposal
        migrations.RemoveField(
            model_name="proposal",
            name="speakers",
        ),

        # 5. Update Speaker.email: remove unique, allow blank
        migrations.AlterField(
            model_name="speaker",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AlterField(
            model_name="historicalspeaker",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),

        # 6. Add Speaker.proposal as nullable FK first (required for ADD COLUMN on SQLite)
        migrations.AddField(
            model_name="speaker",
            name="proposal",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="speakers",
                to="apiv1.proposal",
            ),
        ),
        # 7. Make Speaker.proposal non-nullable (safe: all existing rows deleted above)
        migrations.AlterField(
            model_name="speaker",
            name="proposal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="speakers",
                to="apiv1.proposal",
            ),
        ),

        # 8. Add Speaker.role
        migrations.AddField(
            model_name="speaker",
            name="role",
            field=models.CharField(
                choices=[("primary", "Primary speaker"), ("co_speaker", "Co-speaker")],
                default="co_speaker",
                max_length=20,
            ),
        ),

        # 9. Add Speaker.sort_order
        migrations.AddField(
            model_name="speaker",
            name="sort_order",
            field=models.PositiveSmallIntegerField(default=0),
        ),

        # 10. Update HistoricalSpeaker to add proposal_id, role, sort_order fields
        migrations.AddField(
            model_name="historicalspeaker",
            name="proposal_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalspeaker",
            name="role",
            field=models.CharField(
                choices=[("primary", "Primary speaker"), ("co_speaker", "Co-speaker")],
                default="co_speaker",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="historicalspeaker",
            name="sort_order",
            field=models.PositiveSmallIntegerField(default=0),
        ),

        # 11. Update Meta ordering on Speaker
        migrations.AlterModelOptions(
            name="speaker",
            options={"ordering": ["sort_order", "id"]},
        ),
    ]


