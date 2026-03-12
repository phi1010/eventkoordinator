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
                login_button = page.get_by_role('button', name='Login', exact=True)

                username_input.fill('adminuser')
                password_input.fill('testpassword123')
                login_button.click()

                # Wait for redirect after login
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(500)

                # Verify user is logged in
                logged_in_username = page.locator('text=adminuser')
                logged_in_username.wait_for(timeout=5000)

                page.get_by_label("Admin panel").click()

                # Navigate to admin panel and verify admin index is shown
                #page.goto(f'{self.live_server_url}/admin/')
                page.wait_for_load_state('networkidle')
                page.get_by_role('heading', name='Site administration').wait_for(timeout=5000)
                page.wait_for_timeout(500)

                # Get the accessibility snapshot of the admin interface
                snapshot = page.locator("body").aria_snapshot()

                # Use the SnapshotMixin to save and compare snapshot
                self.assert_snapshot(snapshot)

                print(f"\nAccessibility Snapshot saved")
                print(f"\nSnapshot content:\n{snapshot}")

            finally:
                browser.close()
