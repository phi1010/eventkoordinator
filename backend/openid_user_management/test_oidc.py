"""
Tests for OIDC Authentication Backend.

Tests the custom OIDCAuthenticationBackend integration with OpenIDUser model.
"""

from django.test import TestCase
from unittest.mock import Mock, patch
from openid_user_management.models import OpenIDUser
from openid_user_management.auth import OIDCAuthenticationBackend, generate_username


class OIDCAuthenticationBackendTests(TestCase):
    """Tests for the custom OIDC authentication backend."""

    def setUp(self):
        """Set up test fixtures."""
        self.backend = OIDCAuthenticationBackend()
        self.sample_claims = {
            'sub': 'google_12345',
            'email': 'test@example.com',
            'preferred_username': 'testuser',
            'picture': 'https://example.com/pic.jpg',
            'locale': 'en-US',
            'phone_number': '+1234567890',
            'iss': 'https://accounts.google.com',
        }

    def test_create_user_from_claims(self):
        """Test that a user is created from OIDC claims."""
        user = self.backend.create_user(self.sample_claims)

        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.openid_subject, 'google_12345')
        self.assertEqual(user.openid_provider, 'google')
        self.assertEqual(user.picture, 'https://example.com/pic.jpg')
        self.assertEqual(user.locale, 'en-US')
        self.assertEqual(user.phone_number, '+1234567890')

    def test_create_user_unique_username(self):
        """Test that duplicate usernames are handled."""
        # Create first user
        user1 = self.backend.create_user(self.sample_claims)
        self.assertEqual(user1.username, 'testuser')

        # Create second user with same preferred_username
        claims2 = self.sample_claims.copy()
        claims2['sub'] = 'google_67890'
        claims2['email'] = 'test2@example.com'

        user2 = self.backend.create_user(claims2)
        self.assertEqual(user2.username, 'testuser1')  # Auto-incremented

    def test_update_user(self):
        """Test that user is updated with new claims."""
        user = self.backend.create_user(self.sample_claims)

        # Update claims
        new_claims = self.sample_claims.copy()
        new_claims['email'] = 'newemail@example.com'
        new_claims['picture'] = 'https://example.com/newpic.jpg'

        updated_user = self.backend.update_user(user, new_claims)

        self.assertEqual(updated_user.email, 'newemail@example.com')
        self.assertEqual(updated_user.picture, 'https://example.com/newpic.jpg')

    def test_filter_users_by_sub(self):
        """Test finding users by OpenID subject."""
        user = self.backend.create_user(self.sample_claims)

        found_users = self.backend.filter_users_by_claims(self.sample_claims)

        self.assertEqual(found_users.count(), 1)
        self.assertEqual(found_users.first().id, user.id)

    def test_filter_users_by_email_fallback(self):
        """Test finding users by email when sub doesn't match."""
        user = self.backend.create_user(self.sample_claims)

        # Search with different sub but same email
        claims = {
            'sub': 'different_sub',
            'email': 'test@example.com'
        }

        found_users = self.backend.filter_users_by_claims(claims)

        self.assertEqual(found_users.count(), 1)
        self.assertEqual(found_users.first().id, user.id)

    def test_get_provider_name_google(self):
        """Test provider name extraction for Google."""
        claims = {'iss': 'https://accounts.google.com'}
        provider = self.backend.get_provider_name(claims)
        self.assertEqual(provider, 'google')

    def test_get_provider_name_keycloak(self):
        """Test provider name extraction for Keycloak."""
        claims = {'iss': 'http://localhost:8080/realms/keycloak'}
        provider = self.backend.get_provider_name(claims)
        self.assertEqual(provider, 'keycloak')

    def test_get_provider_name_generic(self):
        """Test provider name extraction for generic provider."""
        claims = {'iss': 'https://auth.example.com'}
        provider = self.backend.get_provider_name(claims)
        self.assertEqual(provider, 'auth.example.com')

    def test_verify_claims_with_sub(self):
        """Test claim verification with sub."""
        claims = {'sub': 'user123'}
        self.assertTrue(self.backend.verify_claims(claims))

    def test_verify_claims_with_email(self):
        """Test claim verification with email."""
        claims = {'email': 'user@example.com'}
        self.assertTrue(self.backend.verify_claims(claims))

    def test_verify_claims_missing(self):
        """Test claim verification fails when required claims missing."""
        claims = {}
        self.assertFalse(self.backend.verify_claims(claims))

    def test_generate_username_from_email(self):
        """Test username generation from email."""
        username = generate_username('john.doe@example.com')
        self.assertEqual(username, 'john.doe')

    def test_generate_username_unique(self):
        """Test that generated usernames are unique."""
        # Create user with username 'john'
        OpenIDUser.objects.create_user(
            username='john',
            email='john@example.com',
            password='test123'
        )

        # Generate username for same email pattern
        username = generate_username('john@different.com')
        self.assertEqual(username, 'john1')

    def test_create_user_without_password(self):
        """Test that OIDC users are created without password."""
        user = self.backend.create_user(self.sample_claims)

        # User should not be able to login with password
        self.assertFalse(user.has_usable_password())

    def test_create_user_minimal_claims(self):
        """Test user creation with minimal claims."""
        minimal_claims = {
            'sub': 'user123',
            'email': 'minimal@example.com'
        }

        user = self.backend.create_user(minimal_claims)

        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'minimal@example.com')
        self.assertEqual(user.openid_subject, 'user123')
        self.assertEqual(user.username, 'minimal')  # From email

    def test_update_user_preserves_existing_data(self):
        """Test that update doesn't overwrite data if not in claims."""
        user = self.backend.create_user(self.sample_claims)
        original_picture = user.picture

        # Update with claims that don't include picture
        claims_without_picture = {
            'sub': 'google_12345',
            'email': 'test@example.com',
            'locale': 'fr-FR'
        }

        updated_user = self.backend.update_user(user, claims_without_picture)

        # Picture should be preserved
        self.assertEqual(updated_user.picture, original_picture)
        # Locale should be updated
        self.assertEqual(updated_user.locale, 'fr-FR')

