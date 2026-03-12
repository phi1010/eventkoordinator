"""Playwright UX snapshots for the proposal flow."""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from playwright.sync_api import Page, sync_playwright

from apiv1.models.basedata import ProposalArea, ProposalLanguage, SubmissionType
from project.test_utils import (
    SnapshotMixin,
    ViteStaticLiveServerTestCase,
    print_aria_on_timeout,
)


class ProposalUxPlaywrightTest(SnapshotMixin, ViteStaticLiveServerTestCase):
    """Covers create -> save -> submit proposal flow with stage snapshots."""

    vite_force_rebuild = False

    def setUp(self) -> None:
        super().setUp()

        self.username = "proposalux_user"
        self.password = "testpassword123"

        User = get_user_model()
        User.objects.filter(username=self.username).delete()
        user = User.objects.create_user(
            username=self.username,
            email=f"{self.username}@example.com",
            password=self.password,
        )

        required_permission_codenames = [
            "add_proposal",
            "change_proposal",
            "view_proposal",
            "browse_proposal",
            "submit_proposal",
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
        page.get_by_role("button", name="Login", exact=True).click()
        page.wait_for_load_state("networkidle")

        # Re-open the user menu and assert authenticated state.
        page.get_by_role("button", name="User menu").click()
        page.get_by_role("menuitem", name="Logout").wait_for(timeout=5000)

    def test_create_save_submit_proposal(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            try:
                with print_aria_on_timeout(page):
                    base_url = self.live_server_url
                    if callable(base_url):
                        base_url = base_url()

                    self._login_via_navbar(page, base_url)
                    page.goto(base_url + "/proposal-editor")

                    page.get_by_role("main", name="Proposals content").wait_for(timeout=5000)
                    page.get_by_role("button", name="Create New Proposal").click()
                    page.get_by_role("form", name="Proposal editor").wait_for(timeout=5000)

                    with self.subTest(stage="create"):
                        self.assert_snapshot(page.locator("body").aria_snapshot())

                    with self.subTest(stage="save"):
                        page.get_by_label("Title (max 30 characters)").fill("Intro to wood joints")
                        page.get_by_label("Submission Type").select_option("workshop")
                        page.get_by_label("Area (optional)").select_option("woodworking")
                        page.get_by_label("Language").select_option("de")
                        page.get_by_label("Abstract (50-250 characters)").fill(
                            "A hands-on workshop introducing simple woodworking joints for beginners."
                        )
                        page.get_by_label("Description (50-1000 characters)").fill(
                            "Participants learn safe tool handling and build sample joints with guided practice and feedback."
                        )
                        page.get_by_label("Duration (days)").fill("1")
                        page.get_by_label("Duration per day").fill("02:00")
                        page.get_by_label("Occurrence Count").fill("1")
                        page.get_by_label("Max Participants").fill("10")
                        page.get_by_label("Preferred Dates").fill("2026-08-10 to 2026-08-11")

                        page.get_by_label("Email (required):").fill("speaker@example.com")
                        page.get_by_label("Display Name:").fill("Sample Speaker")
                        page.get_by_label("Biography:").fill(
                            "Sample Speaker has many years of workshop facilitation and practical making experience."
                        )
                        page.get_by_role("button", name="+ Add Speaker").click()
                        page.get_by_text("Added Speakers (1)").wait_for(timeout=5000)

                        page.get_by_role("button", name="Save Proposal").click()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(500)
                        self.assert_snapshot(page.locator("body").aria_snapshot())

                    with self.subTest(stage="submit"):
                        submit_button = page.get_by_role(
                            "button", name=re.compile(r"^(Submit proposal|Resubmit proposal)$", re.IGNORECASE)
                        )
                        submit_button.wait_for(timeout=5000)
                        self.assertTrue(submit_button.is_enabled(), "Submit button is disabled after save")
                        submit_button.click()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(500)
                        self.assert_snapshot(page.locator("body").aria_snapshot())
            finally:
                browser.close()
