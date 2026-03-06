"""
Signal handlers for mailqueue app.

Automatically sends emails when MailQueueEntry objects are created.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from mailqueue.models import MailQueueEntry, MailQueueDeliveryAttempt


logger = logging.getLogger(__name__)

@receiver(post_save, sender=MailQueueEntry)
def create_delivery_attempt_on_creation(sender, instance, created, **kwargs):
    """
    Automatically send email when a new MailQueueEntry is created.

    This signal handler is triggered after a MailQueueEntry is saved.
    If it's a new entry (created=True) and hasn't been sent yet,
    it will attempt to send the email immediately.
    """
    if created:
        logger.debug(f"Creating delivery attempt for mail to {instance.recipient} with subject: {instance.subject}")
        try:
            instance.send_mail()
            logger.debug(f"Successfully sent mail to {instance.recipient}")
        except Exception as e:
            # Log the error but don't raise it - the delivery attempt is already recorded
            logger.debug(f"Failed to send mail to {instance.recipient}: {e}")
