"""
Unit tests for OpenID User Management.

Tests user model functionality, API endpoints, and authentication.
"""

import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model

from openid_user_management.models import OpenIDUser

User = get_user_model()


class OpenIDUserModelTests(TestCase):
    """Tests for the OpenIDUser model."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = OpenIDUser.objects.create_user(
            email='test@example.com',
            username="johndoe",
            password='testpass123',
        )

    def test_user_creation(self):
        """Test that a user can be created successfully."""
        self.assertIsNotNone(self.user.id)
        self.assertIsInstance(self.user.id, uuid.UUID)
        self.assertEqual(self.user.email, 'test@example.com')

    def test_user_has_uuid_primary_key(self):
        """Test that user has a UUID primary key."""
        self.assertIsInstance(self.user.pk, uuid.UUID)

    def test_user_email_is_unique(self):
        """Test that user emails are unique."""
        with self.assertRaises(Exception):
            OpenIDUser.objects.create_user(
                email='test@example.com',
                password='different'
            )

    def test_user_password_hashing(self):
        """Test that passwords are hashed correctly."""
        self.assertTrue(self.user.check_password('testpass123'))
        self.assertFalse(self.user.check_password('wrongpassword'))

    def test_user_str_representation(self):
        """Test the string representation of a user."""
        user_str = str(self.user)
        self.assertIn('test@example.com', user_str)
        self.assertIn('johndoe', user_str)

    def test_user_is_active_by_default(self):
        """Test that users are active by default."""
        self.assertTrue(self.user.is_active)

    def test_user_is_not_staff_by_default(self):
        """Test that users are not staff by default."""
        self.assertFalse(self.user.is_staff)

    def test_user_is_not_superuser_by_default(self):
        """Test that users are not superusers by default."""
        self.assertFalse(self.user.is_superuser)

    def test_superuser_creation(self):
        """Test that superusers can be created."""
        superuser = OpenIDUser.objects.create_superuser(
            username="admin",
            email='admin@example.com',
            password='adminpass123'
        )
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_active)

    def test_openid_fields(self):
        """Test OpenID Connect fields."""
        user = OpenIDUser.objects.create_user(
            username="oidcuser",
            email='oidc@example.com',
            password='test123',
            openid_subject='user123',
            openid_provider='google'
        )
        self.assertEqual(user.openid_subject, 'user123')
        self.assertEqual(user.openid_provider, 'google')

    def test_optional_profile_fields(self):
        """Test that optional profile fields work correctly."""
        user = OpenIDUser.objects.create_user(
            username="profileuser",
            email='profile@example.com',
            password='test123',
            phone_number='+1234567890',
            picture='https://example.com/pic.jpg',
            locale='en-US'
        )
        self.assertEqual(user.phone_number, '+1234567890')
        self.assertEqual(user.picture, 'https://example.com/pic.jpg')
        self.assertEqual(user.locale, 'en-US')

