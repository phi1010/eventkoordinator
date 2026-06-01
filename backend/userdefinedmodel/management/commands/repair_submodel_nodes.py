"""
Repair orphaned submodel nodes whose config_version is out of sync with
what the parent entity's current submodel field expects.

A node becomes orphaned when a parent entity is migrated without a
BulkMigrationSubmodelMapping, leaving the child's parent_field pointing to
a field definition from an older config version. Subsequent migration plans
cannot find the child because they match by exact parent_field FK.

This command detects such nodes, auto-infers field mappings (map when slug and
type match, discard otherwise), and migrates them to the expected version.
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Repair orphaned submodel nodes by migrating them to the expected config version"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from userdefinedmodel.models import (
            UserDefinedModelEntityNode, FieldDefinition,
        )
        from userdefinedmodel.tasks import _apply_field_mappings_to_node

        dry_run = options["dry_run"]

        # Find all submodel child nodes (those with a parent_node set).
        # For each, determine what version the parent's current field expects.
        repaired = 0
        skipped = 0

        child_nodes = (
            UserDefinedModelEntityNode.objects
            .filter(parent_node__isnull=False, parent_field__isnull=False)
            .select_related(
                "parent_node__config_version",
                "parent_field__submodel_config__config",
                "config_version__config",
            )
        )

        for node in child_nodes:
            parent = node.parent_node
            slug = node.parent_field.slug if node.parent_field else None
            if not slug:
                continue

            # Find the corresponding field in the parent's CURRENT config version.
            try:
                current_parent_field = parent.config_version.field_definitions.select_related(
                    "submodel_config"
                ).get(slug=slug)
            except FieldDefinition.DoesNotExist:
                self.stdout.write(
                    f"  SKIP {node.id}: no field '{slug}' in parent version {parent.config_version_id}"
                )
                skipped += 1
                continue

            expected_submodel_version = current_parent_field.submodel_config
            if expected_submodel_version is None:
                continue

            if node.config_version_id == expected_submodel_version.id:
                continue  # Already on the correct version.

            self.stdout.write(
                f"Repairing {node.id}: {node.config_version} → {expected_submodel_version}"
            )

            # Auto-build field mappings: map same-slug same-type fields, discard others.
            src_fields = {f.slug: f for f in node.config_version.field_definitions.all()}
            tgt_fields = {f.slug: f for f in expected_submodel_version.field_definitions.all()}
            mappings = []
            for src_slug, src_field in src_fields.items():
                tgt_field = tgt_fields.get(src_slug)

                class _Mapping:
                    pass

                m = _Mapping()
                m.source_field = src_field
                if tgt_field and tgt_field.data_type == src_field.data_type:
                    m.action = "map"
                    m.target_field = tgt_field
                    self.stdout.write(f"  map  {src_slug!r} ({src_field.data_type})")
                else:
                    m.action = "discard"
                    m.target_field = None
                    reason = f"type change: {src_field.data_type} → {tgt_field.data_type}" if tgt_field else "not in target"
                    self.stdout.write(f"  discard {src_slug!r} ({reason})")
                mappings.append(m)

            if dry_run:
                skipped += 1
                continue

            with transaction.atomic():
                _apply_field_mappings_to_node(node, mappings, expected_submodel_version, {})
                node.parent_field = current_parent_field
                node.save(update_fields=["parent_field"])

            repaired += 1
            self.stdout.write(self.style.SUCCESS(f"  Repaired {node.id}"))

        self.stdout.write(f"\nDone: {repaired} repaired, {skipped} skipped" + (" (dry-run)" if dry_run else ""))
