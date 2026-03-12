"""
Playwright tests for the admin interface.
Tests the login flow via the navbar form and admin panel snapshot.

Uses ViteStaticLiveServerTestCase to serve the built SPA and Django API
on a single port, eliminating the need for separate dev servers.
"""

from pathlib import Path
from django.contrib.auth import get_user_model
from project.test_utils import ViteStaticLiveServerTestCase, SnapshotMixin
from playwright.sync_api import sync_playwright


class AdminPlaywrightTest(SnapshotMixin, ViteStaticLiveServerTestCase):
    """Test admin functionality with Playwright"""

    def setUp(self):
        """Create a test user with staff permissions"""
        super().setUp()
        User = get_user_model()
        self.test_user = User.objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='testpassword123',
            is_staff=True,
            is_superuser=True,
        )

    def tearDown(self):
        """Clean up after each test"""
        User = get_user_model()
        User.objects.filter(username='adminuser').delete()
        super().tearDown()

    def test_login_and_navigate_to_admin(self):
        """
        Test logging in via navbar form and navigating to admin panel.
        Snapshots the admin interface showing available models.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            try:
                # Navigate to the application using the live server URL
                page.goto(self.live_server_url)
                page.wait_for_load_state('networkidle')

                # Click on the user menu button
                menu_button = page.locator('button[aria-label="User menu"]')
                menu_button.click()
                page.wait_for_timeout(300)

                # Fill in login credentials
                username_input = page.locator('input[id="username"]')
                password_input = page.locator('input[id="password"]')
                login_button = page.locator('button:has-text("Login")')

                username_input.fill('adminuser')
                password_input.fill('testpassword123')
                login_button.click()

                # Wait for redirect after login
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(500)

                # Verify user is logged in
                logged_in_username = page.locator('text=adminuser')
                logged_in_username.wait_for(timeout=5000)

                # Check that Admin link is available in navbar
                admin_link = page.locator('a[href="/admin/"]')
                assert admin_link.is_visible(), "Admin link should be visible for staff users"

                # Navigate to admin panel
                page.goto(f'{self.live_server_url}/admin/')
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(500)

                # Get the accessibility snapshot of the admin interface
                snapshot = page.accessibility.snapshot()

                # Use the SnapshotMixin to save and compare snapshot
                self.assert_snapshot(snapshot)

                print(f"\nAccessibility Snapshot saved")
                print(f"\nSnapshot content:\n{snapshot}")

            finally:
                browser.close()

