"""Playwright UX tests for proposal-event linking flow."""

from __future__ import annotations

import logging
import re

from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.models import Permission
from playwright.sync_api import Page, sync_playwright

from apiv1.models.basedata import (
    ProposalArea,
    ProposalLanguage,
    Series,
    SubmissionType,
)
from project.test_utils import (
    SnapshotMixin,
    ViteStaticLiveServerTestCase,
    playwright_launch_options,
    print_aria_on_timeout,
)

logger = logging.getLogger(__name__)


class ProposalEventLinkUxTest(SnapshotMixin, ViteStaticLiveServerTestCase):
    """Covers the flow: accept a proposal -> create event from proposal -> verify linked events."""

    vite_force_rebuild = True

    def setUp(self) -> None:
        super().setUp()

        self.username = "proposaleventux-user"
        self.password = "password123"

        User = get_user_model()
        User.objects.filter(username=self.username).delete()
        user, _ = User.objects.get_or_create(
            username=self.username,
            defaults={"email": f"{self.username}@example.com"},
        )
        user.set_password(self.password)
        user.save(update_fields=["password"])
        self.assertIsNotNone(
            authenticate(username=self.username, password=self.password)
        )

        required_permission_codenames = [
            "add_proposal",
            "change_proposal",
            "view_proposal",
            "browse_proposal",
            "submit_proposal",
            "accept_proposal",
            "reject_proposal",
            "revise_proposal",
            "add_event",
            "change_event",
            "view_event",
            "add_series",
            "change_series",
            "view_series",
            "browse_series",
        ]
        user.user_permissions.add(
            *Permission.objects.filter(codename__in=required_permission_codenames)
        )

        SubmissionType.objects.get_or_create(
            code="workshop",
            defaults={"label": "Workshop", "description": "Workshop format"},
        )
        ProposalArea.objects.get_or_create(
            code="woodworking",
            defaults={"label": "Woodworking", "description": "Wood workshop"},
        )
        ProposalLanguage.objects.get_or_create(
            code="de",
            defaults={"label": "German", "description": "German language"},
        )

        # Create a series for linking events to
        self.test_series = Series.objects.create(
            name="Test Workshop Series",
            description="A series for testing event linking",
        )

    def tearDown(self) -> None:
        User = get_user_model()
        User.objects.filter(username=self.username).delete()
        super().tearDown()

    def _login_via_navbar(self, page: Page, base_url: str) -> None:
        page.goto(base_url + "/")
        page.get_by_role("button", name="User menu").click()
        page.get_by_role("form", name="Login form").wait_for(timeout=5000)
        page.get_by_label("Username").fill(self.username)
        page.get_by_label("Password").fill(self.password)
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/authenticate")
            and response.status == 200,
            timeout=5000,
        ):
            page.get_by_role("button", name="Login", exact=True).click()

        page.get_by_text(self.username, exact=True).wait_for(timeout=5000)

    def _create_and_accept_proposal(self, page: Page, base_url: str) -> None:
        """Create a proposal, fill required fields, save, submit, and accept it."""
        page.get_by_role("button", name="Create a Proposal").click()
        page.get_by_role("main", name="Proposals content").wait_for(timeout=5000)
        page.get_by_role("button", name="Create New Proposal").click()
        page.get_by_role("form", name="Proposal editor").wait_for(timeout=5000)
        page.wait_for_load_state("networkidle")

        # Fill required fields
        page.get_by_label("Title (max 30 characters)").fill("Test Event Link")
        page.get_by_label("Submission Type").select_option("workshop")
        page.get_by_label("Area (optional)").select_option("woodworking")
        page.get_by_label("Language").select_option("de")
        page.get_by_label("Abstract (50-250 characters)").fill(
            "A hands-on workshop introducing simple woodworking joints for beginners."
        )
        page.get_by_label("Description (50-1000 characters)").fill(
            "Participants learn safe tool handling and build sample joints with guided practice and feedback."
        )
        page.get_by_label("Number of Days").fill("1")
        page.get_by_label("Time per Day (HH:MM or minutes)").fill("02:00")
        page.get_by_label("How often would you offer this event?").fill("1")

        # Open additional information
        page.locator("summary", has_text="Additional Information").click()
        page.get_by_label("Max. Number of Participants").fill("10")
        page.get_by_label("Preferred Date and Alternatives").fill(
            "2026-08-10 to 2026-08-11"
        )

        # Open about yourself section and add a speaker
        page.locator("summary", has_text="About Yourself").click()
        page.get_by_label("Email (required):").fill("speaker@example.com")
        page.get_by_label("Display Name:").fill("Sample Speaker")
        page.get_by_label("Biography:").fill(
            "Sample Speaker has many years of workshop facilitation and practical making experience."
        )
        page.get_by_role("button", name="+ Add Speaker").click()
        page.get_by_text("Added Speakers (1)").wait_for(timeout=5000)

        # Save
        page.wait_for_timeout(500)
        page.get_by_role("button", name="Save Proposal").click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Submit
        submit_button = page.get_by_role(
            "button",
            name=re.compile(r"^(Submit proposal|Resubmit proposal)$", re.IGNORECASE),
        )
        submit_button.wait_for(timeout=5000)
        submit_button.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Accept
        accept_button = page.get_by_role(
            "button",
            name=re.compile(r"^Accept proposal$", re.IGNORECASE),
        )
        accept_button.wait_for(timeout=5000)
        accept_button.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

    def test_proposal_event_link_flow(self) -> None:
        """Test the complete flow: accept proposal, create event, verify linked events list."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**playwright_launch_options())
            page = browser.new_page()
            try:
                with print_aria_on_timeout(page):
                    base_url = self.live_server_url
                    if callable(base_url):
                        base_url = base_url()

                    self._login_via_navbar(page, base_url)
                    self._create_and_accept_proposal(page, base_url)

                    with self.subTest(stage="accepted_with_linked_events_section"):
                        # After acceptance, linked events section should appear
                        page.get_by_text("Linked Events (0)").wait_for(timeout=5000)
                        self.assert_snapshot(
                            page.locator("body").aria_snapshot()
                        )

                    with self.subTest(stage="create_event_from_proposal"):
                        # Select the series from the dropdown
                        page.get_by_role("combobox", name="Series").select_option(
                            label=self.test_series.name
                        )
                        page.wait_for_timeout(500)

                        # Click "Create New Event" button
                        page.get_by_role("button", name="Create New Event").click()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(500)

                        # Should navigate to the event editor page
                        page.get_by_text("Edit Event").wait_for(timeout=5000)
                        # Should show proposal info on the left
                        page.get_by_text("Test Event Link").wait_for(timeout=5000)
                        page.get_by_text("Duration Days").wait_for(timeout=5000)
                        self.assert_snapshot(
                            page.locator("body").aria_snapshot()
                        )

                    with self.subTest(stage="verify_linked_event_in_proposal"):
                        # Go back to proposal
                        page.get_by_role("link", name="Back to Proposal").click()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(500)

                        # Should show 1 linked event
                        page.get_by_text("Linked Events (1)").wait_for(
                            timeout=5000
                        )
                        self.assert_snapshot(
                            page.locator("body").aria_snapshot()
                        )

            finally:
                browser.close()


