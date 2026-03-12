"""
Test utilities for Django Playwright end-to-end tests.

Usage in a test file::

    from project.test_utils import ViteStaticLiveServerTestCase

    class MyPlaywrightTest(ViteStaticLiveServerTestCase):
        def test_homepage(self):
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(self.live_server_url)
                ...

``ViteStaticLiveServerTestCase`` guarantees that:

1. ``npm run build`` has been run (or re-used from a cached build) before any
   test in the class executes.
2. The Vite ``dist/`` output is copied into Django's ``STATIC_ROOT`` via
   ``collectstatic``.
3. Django's ``StaticLiveServerTestCase`` serves both the API and all static
   assets on a single port, so Playwright doesn't need a separate dev server.
4. Any URL that doesn't match a Django urlconf entry is answered with the
   built ``index.html`` (SPA fallback), allowing React-Router to handle
   client-side routing.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# Root of the repository (two levels above backend/)
_REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# Where ``npm run build`` writes its output
VITE_DIST_DIR: Path = _REPO_ROOT / "dist"

# Django STATIC_ROOT – where collectstatic writes its output
_STATIC_ROOT: Path = Path(settings.STATIC_ROOT)


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def build_vite(*, force: bool = False) -> None:
    """Run ``npm run build`` in the repository root.

    The build is skipped when *force* is ``False`` and ``dist/index.html``
    already exists, so repeated test runs don't rebuild from scratch unless
    the caller explicitly requests it.

    Raises ``subprocess.CalledProcessError`` if the build fails.
    """
    index_html = VITE_DIST_DIR / "index.html"
    if not force and index_html.exists():
        logger.debug("Vite dist/ already present – skipping build.")
        return

    logger.info("Running npm run build in %s …", _REPO_ROOT)
    subprocess.run(
        ["npm", "run", "build"],
        cwd=_REPO_ROOT,
        check=True,
        # VITE_DJANGO_BASE tells vite.config.ts to set base='/static/spa/'
        # so built asset paths match Django's staticfiles URL prefix.
        env={**os.environ, "VITE_DJANGO_BASE": "1"},
        # Capture output so it doesn't clutter test output; on failure
        # CalledProcessError will include stdout/stderr.
        capture_output=True,
        text=True,
    )
    logger.info("Vite build finished.")


def populate_static_root(*, vite_dist: Path = VITE_DIST_DIR) -> None:
    """Copy the Vite build output into Django's STATIC_ROOT.

    The files are placed under ``STATIC_ROOT/spa/`` so they live alongside
    any other collected static files without collision.  The destination
    directory is wiped before copying so stale assets are never served.
    """
    dest = _STATIC_ROOT / "spa"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src=vite_dist, dst=dest, dirs_exist_ok=True)
    logger.info("Copied Vite dist → %s", dest)


# ---------------------------------------------------------------------------
# Test case
# ---------------------------------------------------------------------------

class ViteStaticLiveServerTestCase(StaticLiveServerTestCase):
    """``StaticLiveServerTestCase`` that builds the Vite SPA before tests run.

    The build + copy step runs once per *class* (``setUpClass``), not once per
    test, to keep the suite fast.

    ``StaticLiveServerTestCase`` serves static files through Django's
    *finders* (not from ``STATIC_ROOT``), so the Vite ``dist/`` directory
    is added to ``STATICFILES_DIRS`` with the ``spa`` prefix via
    ``override_settings``.  This ensures the ``FileSystemFinder`` can
    resolve URLs like ``/static/spa/assets/…`` and that the finder cache
    is properly cleared and restored.

    Override ``vite_force_rebuild = True`` on a subclass to always rebuild::

        class MyTest(ViteStaticLiveServerTestCase):
            vite_force_rebuild = True
    """

    #: Set to True to force a fresh ``npm run build`` even if dist/ exists.
    vite_force_rebuild: bool = False

    @classmethod
    def setUpClass(cls) -> None:
        build_vite(force=cls.vite_force_rebuild)
        populate_static_root()

        # StaticLiveServerTestCase serves files via staticfiles *finders*,
        # not from STATIC_ROOT.  Use override_settings so Django's
        # setting_changed signal clears the finder cache and the
        # FileSystemFinder picks up the Vite dist directory.
        # enterClassContext applies the override before super().setUpClass()
        # starts the live-server thread and reverses it in tearDownClass.
        cls.enterClassContext(override_settings(
            STATICFILES_DIRS=list(getattr(settings, "STATICFILES_DIRS", [])) + [
                ("spa", str(VITE_DIST_DIR)),
            ],
        ))

        super().setUpClass()

