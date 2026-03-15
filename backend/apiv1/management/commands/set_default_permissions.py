from django.core.management.base import BaseCommand

from apiv1.auth_groups import assign_authenticated_group_to_all_users, ensure_authenticated_users_group


class Command(BaseCommand):
    help = "Create the default 'Authenticated Users' group with base permissions and assign all existing users to it."

    def handle(self, *args, **options):
        ensure_authenticated_users_group()
        assign_authenticated_group_to_all_users()
        self.stdout.write(self.style.SUCCESS("Default permissions set successfully."))

