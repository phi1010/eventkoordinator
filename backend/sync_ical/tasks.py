import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task
def import_ical_task():
    """Run the import_ical management command as a Celery task.
    
    Clears existing data before importing to ensure a clean sync.
    The entire operation (clear + import) runs in a single transaction,
    so either both succeed or both are rolled back.
    """
    logger.info("Starting scheduled iCal import with clear...")
    call_command("import_ical", clear=True)
    logger.info("iCal import finished.")

