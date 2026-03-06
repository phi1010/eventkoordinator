from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend

from mailqueue.models import MailQueueEntry


class MailQueueBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        for email in email_messages:
            # noinspection PyUnboundLocalVariable
            html_body =None
            if isinstance(email, EmailMultiAlternatives):
                for alt in email.alternatives:
                    if alt[1] == "text/html":
                        html_body = alt[0]
                        break
            for recipient in email.to:
                MailQueueEntry.objects.create(
                    recipient=recipient,
                    subject=email.subject,
                    body=email.body,
                    body_html=html_body,
                    sender=email.from_email,
                )
        return len(email_messages)
