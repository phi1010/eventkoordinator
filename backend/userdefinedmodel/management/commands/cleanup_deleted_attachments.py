from django.core.management.base import BaseCommand
from django.utils.timezone import now


class Command(BaseCommand):
    help = "Physically delete soft-deleted FileAttachment files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-days", type=int, default=30,
            help="Only delete attachments soft-deleted more than N days ago",
        )

    def handle(self, *args, **options):
        from userdefinedmodel.models.node import FileAttachment
        from django.utils.timezone import timedelta

        cutoff = now() - timedelta(days=options["retention_days"])
        qs = FileAttachment.objects.filter(deleted_at__lt=cutoff)
        count = 0
        for attachment in qs:
            # Skip if still referenced by any active FieldValue
            if attachment.fieldvalue_set.exists():
                continue
            attachment.file.delete(save=False)
            attachment.delete()
            count += 1

        self.stdout.write(f"Deleted {count} soft-deleted file attachments.")
