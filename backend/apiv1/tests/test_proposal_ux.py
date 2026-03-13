"""Playwright UX snapshots for the proposal flow."""

from __future__ import annotations

import logging
import random
import re

from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.models import Permission
from playwright.sync_api import Page, sync_playwright

from apiv1.models.basedata import ProposalArea, ProposalLanguage, SubmissionType
from project.test_utils import (
    SnapshotMixin,
    ViteStaticLiveServerTestCase,
    print_aria_on_timeout,
)


logger = logging.getLogger(__name__)


class ProposalUxPlaywrightTest(SnapshotMixin, ViteStaticLiveServerTestCase):
    """Covers create -> save -> submit proposal flow with stage snapshots."""

    vite_force_rebuild = True

    def setUp(self) -> None:
        super().setUp()

        self.username = "proposalux-user"
        self.password = "password123"

        User = get_user_model()
        User.objects.filter(username=self.username).delete()
        user, _ = User.objects.get_or_create(
            username=self.username,
            defaults={"email": f"{self.username}@example.com"},
        )
        user.set_password(self.password)
        user.save(update_fields=["password"])
        logger.debug(f"Created user: {user}, {user.__dict__!r}")
        self.assertIsNotNone(authenticate(username=self.username, password=self.password))
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
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/authenticate") and response.status == 200,
            timeout=5000,
        ):
            page.get_by_role("button", name="Login", exact=True).click()

        # Wait for UI state to reflect authenticated user.
        user_menu_button = page.get_by_role("button", name="User menu")
        page.get_by_text(self.username, exact=True).wait_for(timeout=5000)

        # Open the menu only when needed to avoid toggle races.
        if user_menu_button.get_attribute("aria-expanded") != "true":
            user_menu_button.click()
        page.get_by_role("menuitem", name="Logout").wait_for(timeout=5000)

    def _log_field_step(self, label: str) -> None:
        logger.info("Proposal form step: %s", label)

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
                    page.get_by_role("button", name="Create a Proposal").click()

                    page.get_by_role("main", name="Proposals content").wait_for(timeout=5000)
                    page.get_by_role("button", name="Create New Proposal").click()
                    page.get_by_role("form", name="Proposal editor").wait_for(timeout=5000)

                    page.get_by_label("Submission Type").is_enabled()
                    page.get_by_label("Area").is_enabled()
                    page.get_by_label("Language").is_enabled()

                    page.wait_for_load_state("networkidle")

                    with self.subTest(stage="create"):
                        self._log_field_step("submission type")
                        page.get_by_label("Submission Type").is_enabled()
                        self._log_field_step("area")
                        page.get_by_label("Area (optional)").is_enabled()
                        self._log_field_step("language")
                        page.get_by_label("Language").is_enabled()
                        self.assert_snapshot(page.locator("body").aria_snapshot())
                    with self.subTest(stage="save"):
                        self._log_field_step("title")
                        page.get_by_label("Title (max 30 characters)").fill("Intro to wood joints")
                        page.locator("body").screenshot(path=self._snapshot_path().with_suffix(".create.png"))
                        self._log_field_step("submission type")
                        page.get_by_label("Submission Type").select_option("workshop")
                        self._log_field_step("area")
                        page.get_by_label("Area (optional)").select_option("woodworking")
                        self._log_field_step("language")
                        page.get_by_label("Language").select_option("de")
                        self._log_field_step("abstract")
                        page.get_by_label("Abstract (50-250 characters)").fill(
                            "A hands-on workshop introducing simple woodworking joints for beginners."
                        )
                        self._log_field_step("description")
                        page.get_by_label("Description (50-1000 characters)").fill(
                            "Participants learn safe tool handling and build sample joints with guided practice and feedback."
                        )
                        self._log_field_step("Number of Days")
                        page.get_by_label("Number of Days").fill("1")
                        self._log_field_step("Time per Day")
                        page.get_by_label("Time per Day (HH:MM or minutes)").fill("02:00")
                        self._log_field_step("How often")
                        page.get_by_label("How often would you offer this event?").fill("1")

                        self._log_field_step("Additional Information")
                        page.locator("summary", has_text="Additional Information").click()

                        self._log_field_step("max participants")
                        page.get_by_label("Max. Number of Participants").fill("10")
                        self._log_field_step("preferred dates")
                        page.get_by_label("Preferred Date and Alternatives").fill("2026-08-10 to 2026-08-11")

                        self._log_field_step("About Yourself")
                        page.locator("summary", has_text="About Yourself").click()

                        self._log_field_step("speaker email")
                        page.get_by_label("Email (required):").fill("speaker@example.com")
                        self._log_field_step("speaker display name")
                        page.get_by_label("Display Name:").fill("Sample Speaker")
                        self._log_field_step("speaker biography")
                        page.get_by_label("Biography:").fill(
                            "Sample Speaker has many years of workshop facilitation and practical making experience."
                        )
                        self._log_field_step("add speaker")
                        page.get_by_role("button", name="+ Add Speaker").click()
                        page.get_by_text("Added Speakers (1)").wait_for(timeout=5000)

                        page.wait_for_timeout(500)
                        self._log_field_step("save proposal")
                        page.get_by_role("button", name="Save Proposal").click()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(500)
                        page.get_by_label("Loading proposal").is_hidden()
                        page.get_by_label("Loading transitions").is_hidden()
                        self._log_field_step("submission type")
                        page.get_by_label("Submission Type").is_enabled()
                        self._log_field_step("area")
                        page.get_by_label("Area (optional)").is_enabled()
                        self._log_field_step("language")
                        page.get_by_label("Language").is_enabled()
                        page.locator("body").screenshot(path=self._snapshot_path().with_suffix(".save.png"))
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
                        page.get_by_label("Loading proposal").is_hidden()
                        page.get_by_label("Loading transitions").is_hidden()
                        self._log_field_step("submission type")
                        page.get_by_label("Submission Type").is_enabled()
                        self._log_field_step("area")
                        page.get_by_label("Area (optional)").is_enabled()
                        self._log_field_step("language")
                        page.get_by_label("Language").is_enabled()
                        page.locator("body").screenshot(path=self._snapshot_path().with_suffix(".submit.png"))
                        self.assert_snapshot(page.locator("body").aria_snapshot())
            finally:
                browser.close()
