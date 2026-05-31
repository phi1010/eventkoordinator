"""
Celery tasks for userdefinedmodel.
"""
import logging

from celery import shared_task
from django.db import transaction
from django.db.utils import OperationalError
from django.utils.timezone import now

logger = logging.getLogger(__name__)


def run_bulk_migration(plan_id: str) -> None:
    """Execute a BulkMigrationPlan synchronously.

    Called by the Celery task wrapper below and directly by management commands
    that need synchronous execution without going through a broker.
    """
    from userdefinedmodel.models import (
        BulkMigrationPlan, UserDefinedModelEntity,
        UserDefinedModelEntityMigration, MigrationFieldMapping, FieldValue,
    )

    try:
        with transaction.atomic():
            try:
                plan = BulkMigrationPlan.objects.select_for_update(nowait=True).get(id=plan_id)
            except BulkMigrationPlan.DoesNotExist:
                logger.error("BulkMigrationPlan %s not found", plan_id)
                return
            except OperationalError:
                logger.warning("BulkMigrationPlan %s already running", plan_id)
                return

            if plan.status == BulkMigrationPlan.Status.RUNNING:
                logger.warning("BulkMigrationPlan %s already running", plan_id)
                return

            qs = UserDefinedModelEntity.objects.filter(config_version=plan.source_version)
            if plan.user_defined_model_type_filter:
                qs = qs.filter(user_defined_model_type=plan.user_defined_model_type_filter)

            plan.status = BulkMigrationPlan.Status.RUNNING
            plan.total_entities = qs.count()
            plan.save(update_fields=["status", "total_entities"])

        entity_ids = list(
            UserDefinedModelEntity.objects.filter(config_version=plan.source_version)
            .filter(**({} if not plan.user_defined_model_type_filter else {"user_defined_model_type": plan.user_defined_model_type_filter}))
            .values_list("id", flat=True)
        )

        mappings = list(plan.field_mappings.select_related("source_field", "target_field").all())
        tgt_version = plan.target_version

        for entity_id in entity_ids:
            try:
                with transaction.atomic():
                    try:
                        entity = (UserDefinedModelEntity.objects
                                  .select_for_update(nowait=True, of=("self",))
                                  .select_related("config_version", "user_defined_model_type")
                                  .get(id=entity_id))
                    except OperationalError:
                        _increment_failed(plan)
                        continue

                    migration = UserDefinedModelEntityMigration.objects.create(
                        user_defined_model_entity=entity,
                        source_version=entity.config_version,
                        target_user_defined_model_type=plan.user_defined_model_type_filter or entity.user_defined_model_type,
                        target_version=tgt_version,
                        bulk_plan=plan,
                        executed_by=None,
                    )

                    overflow = {}

                    for bm in mappings:
                        src_field = bm.source_field
                        fv = entity.field_values.filter(field=src_field).first()
                        if fv is None:
                            continue

                        MigrationFieldMapping.objects.create(
                            migration=migration, source_field=src_field,
                            action=bm.action, target_field=bm.target_field,
                        )

                        if bm.action == "map" and bm.target_field:
                            val = _resolve_migration_value(fv, bm.target_field)
                            if val is not None:
                                new_fv, _ = FieldValue.objects.get_or_create(
                                    node=entity, field=bm.target_field, language=fv.language
                                )
                                new_fv.set_value(val, field=bm.target_field)
                                new_fv.save()
                        elif bm.action == "overflow":
                            overflow[src_field.slug] = str(fv.get_value())

                    if overflow:
                        entity.overflow_data = {**entity.overflow_data, **overflow}

                    entity.config_version = tgt_version
                    entity.validate_for_save()
                    entity.save(update_fields=["config_version", "overflow_data"])
                    entity.materialize_defaults()

                    migration.executed_at = now()
                    migration.save(update_fields=["executed_at"])

                with transaction.atomic():
                    from django.db.models import F
                    BulkMigrationPlan.objects.filter(id=plan_id).update(done_entities=F("done_entities") + 1)

            except Exception as exc:
                from django.core.exceptions import ValidationError
                if isinstance(exc, ValidationError):
                    errs = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
                    logger.warning("Entity %s skipped: validation failed after migration: %s", entity_id, errs)
                else:
                    logger.exception("Entity %s migration failed: %s", entity_id, exc)
                _increment_failed(plan)

        plan.refresh_from_db()
        final_status = BulkMigrationPlan.Status.DONE if plan.failed_entities == 0 else BulkMigrationPlan.Status.PARTIAL
        BulkMigrationPlan.objects.filter(id=plan_id).update(status=final_status, executed_at=now())

    except Exception as exc:
        logger.exception("run_bulk_migration failed: %s", exc)
        BulkMigrationPlan.objects.filter(id=plan_id).update(status=BulkMigrationPlan.Status.PARTIAL)


@shared_task(bind=True, max_retries=0)
def execute_bulk_migration(self, plan_id: str):
    run_bulk_migration(plan_id)


def _resolve_migration_value(src_fv, tgt_field):
    """Return a value suitable for set_value(val, field=tgt_field), or None to skip."""
    from userdefinedmodel.models.config import FieldDefinition
    val = src_fv.get_value()
    if val is None:
        return None
    if tgt_field.data_type == FieldDefinition.DataType.WORKFLOW:
        if not tgt_field.workflow_definition_id or not isinstance(val, str):
            return None
        from userdefinedmodel.models import WorkflowState
        state = WorkflowState.objects.filter(
            workflow_id=tgt_field.workflow_definition_id, name=val
        ).first()
        return state
    return val


def _increment_failed(plan):
    from userdefinedmodel.models import BulkMigrationPlan
    from django.db.models import F
    BulkMigrationPlan.objects.filter(id=plan.id).update(failed_entities=F("failed_entities") + 1)
