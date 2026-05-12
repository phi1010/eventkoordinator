import logging
import uuid

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_mail_task(mail_entry_pk: uuid.UUID) -> None:
    from mailqueue.models import MailQueueEntry

    try:
        entry = MailQueueEntry.objects.get(pk=mail_entry_pk)
    except MailQueueEntry.DoesNotExist:
        logger.error(f"MailQueueEntry {mail_entry_pk} not found, skipping send")
        return

    try:
        entry.send_mail()
        logger.debug(f"Successfully sent mail to {entry.recipient}")
    except Exception as e:
        logger.error(f"Failed to send mail to {entry.recipient}: {e}")
