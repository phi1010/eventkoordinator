"""
Management command to create OpenID users for testing.

Usage:
    python manage.py create_openid_user --username user123 --email user@example.com
"""

from django.core.management.base import BaseCommand, CommandError
from openid_user_management.models import OpenIDUser


class Command(BaseCommand):
    help = 'Create an OpenID user with UUID primary key'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            required=True,
            help='Username for the user'
        )
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='Email address for the user'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='',
            help='Password for the user (leave empty for no password)'
        )
        parser.add_argument(
            '--is-staff',
            action='store_true',
            help='Make the user a staff member'
        )
        parser.add_argument(
            '--is-superuser',
            action='store_true',
            help='Make the user a superuser'
        )
        parser.add_argument(
            '--openid-subject',
            type=str,
            default='',
            help='OpenID Connect subject (sub) claim'
        )
        parser.add_argument(
            '--openid-provider',
            type=str,
            default='',
            help='OpenID Connect provider name'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        is_staff = options['is_staff']
        is_superuser = options['is_superuser']
        openid_subject = options['openid_subject']
        openid_provider = options['openid_provider']

        # Check if user already exists
        if OpenIDUser.objects.filter(username=username).exists():
            raise CommandError(f'User with username "{username}" already exists')
        if OpenIDUser.objects.filter(email=email).exists():
            raise CommandError(f'User with email "{email}" already exists')

        try:
            # Create the user
            if password:
                user = OpenIDUser.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    is_staff=is_staff,
                    is_superuser=is_superuser,
                    openid_subject=openid_subject,
                    openid_provider=openid_provider,
                )
            else:
                user = OpenIDUser.objects.create(
                    username=username,
                    email=email,
                    is_staff=is_staff,
                    is_superuser=is_superuser,
                    openid_subject=openid_subject,
                    openid_provider=openid_provider,
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created OpenID user with UUID: {user.id}'
                )
            )
            self.stdout.write(f'  Username: {user.username}')
            self.stdout.write(f'  Email: {user.email}')
            self.stdout.write(f'  Staff: {user.is_staff}')
            self.stdout.write(f'  Superuser: {user.is_superuser}')
            if openid_provider:
                self.stdout.write(f'  OpenID Provider: {openid_provider}')
                self.stdout.write(f'  OpenID Subject: {openid_subject}')

        except Exception as e:
            raise CommandError(f'Failed to create user: {str(e)}')

