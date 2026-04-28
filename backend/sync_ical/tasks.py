import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task
def import_ical_task():
    """Run the import_ical management command as a Celery task."""
    logger.info("Starting scheduled iCal import...")
    call_command("import_ical")
    logger.info("iCal import finished.")

