"""
Signal handlers for mailqueue app.

Automatically enqueues email sending via Celery when MailQueueEntry objects are created.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from mailqueue.models import MailQueueEntry


logger = logging.getLogger(__name__)


@receiver(post_save, sender=MailQueueEntry)
def enqueue_mail_on_creation(sender, instance, created, **kwargs):
    """Dispatch a Celery task to send the mail when a new MailQueueEntry is created."""
    if created:
        from mailqueue.tasks import send_mail_task

        logger.debug(
            f"Enqueuing mail to {instance.recipient} with subject: {instance.subject}"
        )
        send_mail_task.delay(instance.pk)
