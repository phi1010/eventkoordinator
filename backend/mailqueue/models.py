import django.core.mail.backends.smtp
from django.conf import settings
from django.db import models
from django.db.models import functions
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from project.basemodels import MetaBase


class MailQueueEntry(MetaBase):
    recipient = models.EmailField(max_length=254)
    sender = models.EmailField(max_length=254, default=None, blank=True, null=True)
    subject = models.CharField(max_length=1024)
    body = models.TextField()
    body_html = models.TextField(blank=True, null=True)

    @property
    def number_of_attempts(self):
        return self.delivery_attempts.count()

    @property
    def last_attempt_date(self):
        last_attempt = self.delivery_attempts.order_by("-created_at").first()
        return last_attempt.created_at if last_attempt else None

    @property
    def successful_attempt(self):
        return self.delivery_attempts.filter(success=True).exists()

    class Meta:
        ordering = (
            "-created_at",
            "recipient",
        )

    def __str__(self):
        return f"Mail to {self.recipient!r} on {self.created_at} with subject {self.subject!r}"

    def create(self, *args, **kwargs):
        super().create(*args, **kwargs)

    def send_mail(self):
        """
        Send the mail using Django's SMTP backend.
        Creates a delivery attempt record and updates sent status.
        """
        from django.core.mail import get_connection

        # Create delivery attempt record
        attempt = MailQueueDeliveryAttempt(mail_entry=self)

        try:
            # Get a real SMTP connection (not the queue backend)
            connection = get_connection(
                backend="django.core.mail.backends.smtp.EmailBackend"
            )

            # Create email message
            msg = EmailMultiAlternatives(
                subject=self.subject,
                body=self.body,
                to=[self.recipient],
                connection=connection,
                from_email=self.sender or settings.DEFAULT_FROM_EMAIL,
            )

            # Add HTML alternative if available
            if self.body_html:
                msg.attach_alternative(self.body_html, "text/html")

            # Send the email
            backend = django.core.mail.backends.smtp.EmailBackend(timeout=5)
            backend.send_messages([msg])

            # Mark as successful
            attempt.success = True

        except Exception as e:
            # Record the error
            attempt.success = False
            attempt.error_message = str(e)
            raise
        finally:
            # Save the attempt record
            attempt.save()
            self.save()


class MailQueueDeliveryAttempt(MetaBase):
    mail_entry = models.ForeignKey(
        MailQueueEntry, on_delete=models.CASCADE, related_name="delivery_attempts"
    )
    success = models.BooleanField(default=False)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Attempted Mail Delivery to {self.mail_entry.recipient!r}, at {self.created_at} with success={self.success}"
