"""
Playwright end-to-end tests for the SPA.

Run with::

    python manage.py test project.tests

The ARIA snapshot files are written next to this file so they can be
reviewed and committed as living documentation.
"""

from __future__ import annotations

import logging
from os import mkdir
from pathlib import Path

from playwright.sync_api import sync_playwright

from project.test_utils import ViteStaticLiveServerTestCase

logger = logging.getLogger(__name__)

# Directory that contains this file – snapshots are written here.
_HERE = Path(__file__).parent

class SpaAriaSnapshotTests(ViteStaticLiveServerTestCase):
    """Open the SPA and capture an ARIA accessibility snapshot."""

    vite_force_rebuild = False

    def _snapshot_path(self) -> Path:
        """Return the path for the snapshot file for the running test method.

        Uses ``self.id()`` which returns the fully-qualified test name
        including any ``subTest`` parameters, e.g.::

            project.tests.SpaAriaSnapshotTests.test_homepage_aria_snapshot
            project.tests.SpaAriaSnapshotTests.test_example (param=1)
        """
        filename = f"{self.id()}.aria.txt"
        logger.debug(f"Snapshot will be written to {filename}")
        return _HERE / filename

    def test_homepage_aria_snapshot(self) -> None:
        """Navigate to the root URL and write an ARIA snapshot to disk."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            try:
                page = browser.new_page()
                logger.debug(f"Navigating to {self.live_server_url}/ and capturing ARIA snapshot")
                page.goto(self.live_server_url + "/")
                # Wait until the React root has mounted something visible.
                page.locator("main").is_visible(timeout=1000)
                page.locator("nav").is_visible(timeout=1000)
                page.wait_for_load_state("networkidle")
                #sys.stdin.readline()
                snapshot: str = page.locator("body").aria_snapshot()
                out = self._snapshot_path()
                out.write_text(snapshot, encoding="utf-8")
                self.assertTrue(out.exists(), f"Snapshot not written to {out}")
                self.assertTrue(len(snapshot) > 0, "ARIA snapshot is empty")
            finally:
                browser.close()

