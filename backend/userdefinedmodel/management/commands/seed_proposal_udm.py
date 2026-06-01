"""
Management command that seeds the Proposal UDM type: field configs, workflow,
Rego policy, and UDM type — using the same Django model layer as the draft API.

The canonical Rego policy lives in documentation/proposals_policy.rego.
This command reads it and patches the two configuration lines (SUDO_ACTIVE and
MODERATOR_GROUP_NAMES) before storing the result in the database.

Usage:
    uv run manage.py seed_proposal_udm
    uv run manage.py seed_proposal_udm --moderator-groups moderators,reviewers
    uv run manage.py seed_proposal_udm --sudo-active --no-publish
    uv run manage.py seed_proposal_udm --force   # re-seed even if type exists
"""

import pathlib
import re

from django.core.management.base import BaseCommand
from django.db import transaction

# Documentation directory relative to this file:
# commands/ → management/ → userdefinedmodel/ → backend/ → project root → documentation/
_POLICY_FILE = (
    pathlib.Path(__file__).resolve().parents[4] / "documentation" / "proposals_policy.rego"
)


def _render_policy(moderator_groups: list[str], sudo_active: bool) -> str:
    """Read the canonical .rego file and patch the two config lines."""
    source = _POLICY_FILE.read_text()
    groups_rego = "[" + ", ".join(f'"{g}"' for g in moderator_groups) + "]"
    source = re.sub(
        r'^SUDO_ACTIVE\s*:=\s*\S+',
        f'SUDO_ACTIVE := {"true" if sudo_active else "false"}',
        source, flags=re.MULTILINE,
    )
    source = re.sub(
        r'^MODERATOR_GROUP_NAMES\s*:=\s*\[.*?\]',
        f'MODERATOR_GROUP_NAMES := {groups_rego}',
        source, flags=re.MULTILINE,
    )
    return source


class Command(BaseCommand):
    help = "Seed the Proposal UDM type: workflow, field configs, Rego policy, and UDM type."

    def add_arguments(self, parser):
        parser.add_argument(
            "--moderator-groups",
            default="moderators",
            help="Comma-separated group names that act as moderators (default: moderators).",
        )
        parser.add_argument(
            "--no-publish",
            action="store_true",
            default=False,
            help="Leave configs as draft instead of publishing.",
        )
        parser.add_argument(
            "--sudo-active",
            action="store_true",
            default=False,
            help="Embed SUDO_ACTIVE := true in the generated policy.",
        )
        parser.add_argument(
            "--type-name",
            default="Proposal",
            help="Name of the UDM type to create (default: Proposal).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Re-seed even if the UDM type already exists.",
        )

    def handle(self, *args, **options):
        from userdefinedmodel.models import (
            ConfigLanguage,
            ConfigVersion,
            FieldConfig,
            FieldDefinition,
            FieldDefinitionTranslation,
            Policy,
            UserDefinedModelType,
            UserDefinedModelTypePolicy,
            WorkflowDefinition,
            WorkflowState,
            WorkflowStateTranslation,
            WorkflowTransition,
            WorkflowTransitionTranslation,
        )

        moderator_groups = [g.strip() for g in options["moderator_groups"].split(",") if g.strip()]
        publish = not options["no_publish"]
        sudo_active = options["sudo_active"]
        type_name = options["type_name"]

        existing_type = UserDefinedModelType.objects.filter(name=type_name).first()
        if existing_type and not options["force"]:
            self.stdout.write(
                self.style.WARNING(
                    f"UDM type '{type_name}' already exists. Use --force to re-seed."
                )
            )
            return

        with transaction.atomic():
            # ── 1. Review workflow definition ─────────────────────────────────
            # Use update_or_create so existing FieldValue references are preserved.
            review_wf, _ = WorkflowDefinition.objects.update_or_create(
                name="Review Workflow",
                defaults={"description": "Review vote lifecycle"},
            )

            review_states = {}
            for r_name, r_label, r_initial, r_x, r_y in [
                ("open",   "Open",   True,  0,   0),
                ("accept", "Accept", False, 250, 0),
                ("reject", "Reject", False, 250, 180),
                ("revise", "Revise", False, 250, 360),
            ]:
                s, _ = WorkflowState.objects.update_or_create(
                    workflow=review_wf, name=r_name,
                    defaults={"is_initial": r_initial, "position_x": r_x, "position_y": r_y},
                )
                WorkflowStateTranslation.objects.update_or_create(
                    state=s, language="en", defaults={"label": r_label},
                )
                review_states[r_name] = s

            review_wf.transitions.all().delete()
            for r_t_name, r_t_label, r_from_name, r_to_name in [
                ("accept", "Accept", "open",   "accept"),
                ("reject", "Reject", "open",   "reject"),
                ("revise", "Revise", "open",   "revise"),
                ("reset",  "Reset",  None,     "open"),
            ]:
                r_t = WorkflowTransition.objects.create(
                    workflow=review_wf,
                    name=r_t_name,
                    from_state=review_states.get(r_from_name) if r_from_name else None,
                    from_undefined_only=False,
                    to_state=review_states[r_to_name],
                )
                WorkflowTransitionTranslation.objects.create(
                    transition=r_t, language="en", label=r_t_label,
                )

            # ── 2. Review submodel field config ───────────────────────────────
            review_config, _ = FieldConfig.objects.get_or_create(name="Proposal Review")
            ConfigLanguage.objects.get_or_create(
                config=review_config, code="en",
                defaults={"label": "English", "is_default": True},
            )
            review_draft, _ = ConfigVersion.objects.get_or_create(
                config=review_config,
                status=ConfigVersion.Status.DRAFT,
                defaults={"notes": "Proposal review submodel"},
            )
            review_draft.notes = "Proposal review submodel"
            review_draft.save(update_fields=["notes"])
            review_draft.field_definitions.all().delete()

            _create_field(
                review_draft, "author", FieldDefinition.DataType.USER_SELECT, 0, "Author",
                type_config={"default_current_user": True}, is_preview=True,
            )
            _create_field(
                review_draft, "vote", FieldDefinition.DataType.WORKFLOW, 1, "Vote",
                workflow_definition=review_wf, is_preview=True,
            )
            _create_field(
                review_draft, "comment", FieldDefinition.DataType.TEXT_LONG, 2, "Comment",
                is_preview=True,
            )

            if publish:
                review_draft.publish()
                review_published = ConfigVersion.objects.get(
                    config=review_config, status=ConfigVersion.Status.PUBLISHED
                )
            else:
                review_published = review_draft

            # ── 3. Proposal workflow definition ───────────────────────────────
            # Use update_or_create for states so existing FieldValue references
            # (value_workflow_state FK) are preserved — deleting states would
            # SET_NULL them and corrupt all existing entities.
            wf, _ = WorkflowDefinition.objects.update_or_create(
                name="Proposal Workflow",
                defaults={"description": "Lifecycle for proposals: draft → submitted → accepted/rejected/revise"},
            )

            states = {}
            for name, label, is_initial, x, y in [
                ("draft",     "Draft",     True,  0,   0),
                ("submitted", "Submitted", False, 250, 0),
                ("revise",    "Revise",    False, 250, 180),
                ("accepted",  "Accepted",  False, 500, 0),
                ("rejected",  "Rejected",  False, 500, 180),
            ]:
                s, _ = WorkflowState.objects.update_or_create(
                    workflow=wf, name=name,
                    defaults={"is_initial": is_initial, "position_x": x, "position_y": y},
                )
                WorkflowStateTranslation.objects.update_or_create(
                    state=s, language="en", defaults={"label": label},
                )
                states[name] = s

            # Transitions don't hold FieldValues so safe to recreate.
            wf.transitions.all().delete()
            for t_name, label, from_name, to_name in [
                ("submit",           "Submit",           "draft",     "submitted"),
                ("resubmit",         "Resubmit",         "revise",    "submitted"),
                ("accept",           "Accept",           "submitted", "accepted"),
                ("reject",           "Reject",           "submitted", "rejected"),
                ("request-revision", "Request Revision", "submitted", "revise"),
                ("allow-revision",   "Allow Revision",   "rejected",  "revise"),
            ]:
                t = WorkflowTransition.objects.create(
                    workflow=wf,
                    name=t_name,
                    from_state=states[from_name],
                    from_undefined_only=False,
                    to_state=states[to_name],
                )
                WorkflowTransitionTranslation.objects.create(
                    transition=t, language="en", label=label,
                )

            # ── 4. Main proposal field config ─────────────────────────────────
            proposal_config, _ = FieldConfig.objects.get_or_create(name="Proposal")
            ConfigLanguage.objects.get_or_create(
                config=proposal_config, code="en",
                defaults={"label": "English", "is_default": True},
            )
            proposal_draft, _ = ConfigVersion.objects.get_or_create(
                config=proposal_config,
                status=ConfigVersion.Status.DRAFT,
                defaults={"notes": "Proposal configuration"},
            )
            proposal_draft.notes = "Proposal configuration"
            proposal_draft.save(update_fields=["notes"])
            proposal_draft.field_definitions.all().delete()

            _create_field(
                proposal_draft, "proposal-id", FieldDefinition.DataType.SLUG_ID, 0,
                "Proposal ID", type_config={"prefix": "PROP"}, is_preview=True,
            )
            _create_field(
                proposal_draft, "status", FieldDefinition.DataType.WORKFLOW, 1,
                "Status", is_preview=True, workflow_definition=wf,
            )
            _create_field(
                proposal_draft, "owner", FieldDefinition.DataType.USER_SELECT, 2, "Owner",
                type_config={"default_current_user": True},
            )
            _create_field(
                proposal_draft, "editors", FieldDefinition.DataType.USER_SELECT_MULTI, 3, "Editors",
            )
            _create_field(
                proposal_draft, "requested-reviewer-groups",
                FieldDefinition.DataType.GROUP_SELECT_MULTI, 4, "Requested Reviewer Groups",
            )
            _create_field(
                proposal_draft, "requested-reviewer-users",
                FieldDefinition.DataType.USER_SELECT_MULTI, 5, "Requested Reviewer Users",
            )
            _create_field(
                proposal_draft, "reviews", FieldDefinition.DataType.SUBMODEL_LIST, 6, "Reviews",
                type_config={"renderer": "list"},
                submodel_config=review_published,
            )

            if publish:
                proposal_draft.publish()

            # ── 4b. Bulk-migrate existing entities and repair orphaned submodels ─
            if publish:
                _migrate_stale_entities(proposal_config, self.stdout)
                from userdefinedmodel.management.commands.repair_submodel_nodes import Command as RepairCmd
                repair = RepairCmd()
                repair.stdout = self.stdout
                repair.style = self.style
                repair.handle(dry_run=False)

            # ── 4. Rego policy (read from canonical .rego file) ───────────────
            policy_source = _render_policy(moderator_groups, sudo_active)
            policy, _ = Policy.objects.update_or_create(
                slug="proposals",
                defaults={"source": policy_source},
            )

            # ── 5. UDM type ───────────────────────────────────────────────────
            udm_type, created = UserDefinedModelType.objects.update_or_create(
                name=type_name,
                defaults={"field_config": proposal_config},
            )

            UserDefinedModelTypePolicy.objects.get_or_create(
                user_defined_model_type=udm_type,
                policy=policy,
                defaults={"sort_order": 0},
            )

        verb = "Created" if created else "Updated"
        published_note = "(draft only — publish manually)" if not publish else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} '{type_name}' UDM type with Proposal workflow, field config, "
                f"and policy. Moderator groups: {moderator_groups}. {published_note}"
            )
        )


def _migrate_stale_entities(proposal_config, stdout) -> None:
    """Create and execute a BulkMigrationPlan for every archived proposal config
    version that still has entities on it, migrating them to the current published
    version. Runs synchronously (no Celery) so the seed command is self-contained."""
    from userdefinedmodel.models import (
        BulkMigrationPlan, BulkMigrationFieldMapping, ConfigVersion,
        UserDefinedModelEntity,
    )
    from userdefinedmodel.tasks import run_bulk_migration

    target = ConfigVersion.objects.filter(
        config=proposal_config, status=ConfigVersion.Status.PUBLISHED
    ).first()
    if target is None:
        return

    target_slugs = {fd.slug: fd for fd in target.field_definitions.all()}

    archived = ConfigVersion.objects.filter(
        config=proposal_config, status=ConfigVersion.Status.ARCHIVED
    ).exclude(pk=target.pk)

    for src in archived:
        stale_count = UserDefinedModelEntity.objects.filter(config_version=src).count()
        if stale_count == 0:
            continue

        stdout.write(f"  Migrating {stale_count} entities from config version {src.pk} …")

        plan = BulkMigrationPlan.objects.create(
            source_version=src,
            target_version=target,
            status=BulkMigrationPlan.Status.DRAFT,
        )

        # Map every source field whose slug exists in the target; discard the rest.
        for src_field in src.field_definitions.all():
            tgt_field = target_slugs.get(src_field.slug)
            if tgt_field:
                BulkMigrationFieldMapping.objects.create(
                    plan=plan,
                    source_field=src_field,
                    action="map",
                    target_field=tgt_field,
                )
            else:
                BulkMigrationFieldMapping.objects.create(
                    plan=plan,
                    source_field=src_field,
                    action="overflow",
                )

        run_bulk_migration(str(plan.pk))

        plan.refresh_from_db()
        stdout.write(f"    Done: {plan.done_entities} ok, {plan.failed_entities} failed (status={plan.status}).")


def _create_field(
    version,
    slug: str,
    data_type,
    sort_order: int,
    label_en: str,
    *,
    type_config: dict | None = None,
    is_preview: bool = False,
    is_localized: bool = False,
    workflow_definition=None,
    submodel_config=None,
) -> "FieldDefinition":
    from userdefinedmodel.models import FieldDefinition, FieldDefinitionTranslation

    fd = FieldDefinition.objects.create(
        version=version,
        slug=slug,
        data_type=data_type,
        sort_order=sort_order,
        is_preview=is_preview,
        is_localized=is_localized,
        type_config=type_config or {},
        workflow_definition=workflow_definition,
        submodel_config=submodel_config,
    )
    FieldDefinitionTranslation.objects.create(field=fd, language="en", label=label_en)
    return fd
