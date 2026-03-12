"""SPA fallback view – serves the built index.html for any unmatched URL.

This is intentionally separate from urls.py so it can be imported without
pulling in the full URL configuration, and so the file path logic stays
testable in isolation.
"""

from __future__ import annotations

import logging
import posixpath
from pathlib import Path

from django.conf import settings
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    HttpResponseBase,
)
from django.views import View

logger = logging.getLogger(__name__)
# File extensions that indicate a static asset request rather than a
# client-side route.  If the URL ends with one of these, the view should
# return 404 instead of serving ``index.html`` with ``text/html``.
_STATIC_ASSET_EXTENSIONS = frozenset((
    ".js", ".css", ".map", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".json", ".webp", ".avif",
))


def _index_html_path() -> Path:
    """Return the absolute path to the built ``index.html``."""
    return Path(__file__).parents[2] / "dist" / "index.html"


def _looks_like_static_asset(path: str) -> bool:
    """Return ``True`` if *path* looks like a request for a static file."""
    _, ext = posixpath.splitext(path)
    return ext.lower() in _STATIC_ASSET_EXTENSIONS


class SpaFallbackView(View):
    """Return the Vite-built ``index.html`` for every unmatched URL.

    This lets React-Router handle client-side routes (e.g. ``/coordinator``,
    ``/proposal-editor/123``) when the app is served through Django rather
    than the Vite dev server.

    Requests that look like static assets (e.g. ``.js``, ``.css``) are
    **not** served as HTML – they receive a 404 so the browser does not
    interpret an HTML page with the wrong MIME type.

    Raises ``Http404`` if the build hasn't been run yet so that the error
    is obvious during development rather than serving a silent blank page.
    """

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponseBase:  # noqa: ARG002
        # Never serve index.html for what is clearly a static-asset request.
        if _looks_like_static_asset(request.path):
            logger.error(f"Static asset not found: {request.path}")
            raise Http404(
                f"Static asset not found: {request.path}. "
                "Ensure the Vite build was run with VITE_DJANGO_BASE=1 "
                "so asset URLs include the /static/spa/ prefix."
            )
        return FileResponse(_index_html_path().open("rb"), content_type="text/html")

