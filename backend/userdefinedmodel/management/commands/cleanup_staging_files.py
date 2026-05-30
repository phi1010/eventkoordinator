from django.core.management.base import BaseCommand
from django.utils.timezone import now


class Command(BaseCommand):
    help = "Delete expired StagingFile rows and their physical files"

    def handle(self, *args, **options):
        from userdefinedmodel.models.node import StagingFile

        expired = StagingFile.objects.filter(expires_at__lt=now())
        count = 0
        for staging in expired:
            staging.file.delete(save=False)
            staging.delete()
            count += 1

        self.stdout.write(f"Deleted {count} expired staging files.")
