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
# Snapshot helpers
# ---------------------------------------------------------------------------

# Two levels above backend/ → repo root, then into backend/test_aria_snapshots
_BACKEND_DIR: Path = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR: Path = _BACKEND_DIR / "test_aria_snapshots"


def _git_show_committed(path: Path) -> str | None:
    """Return the content of *path* as last committed in git, or ``None``.

    Returns ``None`` when the file is untracked, not yet committed, or
    git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{path.relative_to(_git_repo_root(path))}"],
            capture_output=True,
            text=True,
            cwd=path.parent,
            check=True,
        )
        return result.stdout
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def _git_repo_root(path: Path) -> Path:
    """Return the root of the git repository containing *path*."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=path.parent,
        check=True,
    )
    return Path(result.stdout.strip())


class SnapshotMixin:
    """Mixin that writes snapshot files and compares them against git HEAD.

    The snapshot file is derived from ``self.id()`` so it automatically
    includes class name, method name, and any ``subTest`` parameters.

    Usage::

        class MyTest(SnapshotMixin, SomeTestCase):
            def test_something(self):
                content = capture_something()
                self.assert_snapshot(content)
    """

    def _snapshot_path(self) -> Path:
        """Return the snapshot file path derived from the test id.

        Files are placed in ``backend/test_aria_snapshots/`` and named
        after ``self.id()`` (e.g.
        ``project.tests.SpaAriaSnapshotTests.test_homepage.aria.txt``).
        """
        filename = f"{self.id()}.aria.txt"
        return SNAPSHOT_DIR / filename

    def assert_snapshot(self, content: str) -> None:
        """Write *content* to the snapshot file and compare with git HEAD.

        The snapshot is always written to disk (so it can be committed).
        If the file already existed in git and the new content differs,
        the test fails with a unified diff showing the changes.

        A brand-new snapshot (not yet tracked by git) never causes a
        failure — the developer is expected to review and commit it.
        """
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

        out = self._snapshot_path()
        out.write_text(content, encoding="utf-8")
        logger.debug("Snapshot written to %s", out)

        committed = _git_show_committed(out)
        if committed is None:
            # File is new / untracked — nothing to compare against.
            logger.info("New snapshot %s — commit it to establish a baseline.", out.name)
            return

        if content != committed:
            import difflib

            diff = difflib.unified_diff(
                committed.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{out.name}  (committed)",
                tofile=f"b/{out.name}  (current)",
            )
            patch = "".join(diff)
            self.fail(
                f"Snapshot {out.name} differs from the committed version.\n"
                f"Run the test with --update-snapshots or commit the new "
                f"file to accept the change.\n\n{patch}"
            )

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

