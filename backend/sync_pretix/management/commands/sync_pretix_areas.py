from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
import random

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apiv1.models.basedata import ProposalArea

logger = logging.getLogger(__name__)


def _normalize_api_base_url(url: str) -> str:
    return url.rstrip("/")


def _build_event_slug(prefix: str, area_code: str) -> str:
    slug = slugify(f"{prefix}-{area_code}")
    if not slug:
        raise CommandError(
            f"Could not build a valid pretix event slug for area code {area_code!r}."
        )
    return slug[:64]


@dataclass
class PretixSettings:
    api_base_url: str
    api_token: str
    organizer_slug: str
    organizer_name: str
    event_slug_prefix: str
    event_currency: str
    event_timezone: str
    event_locale: str


class PretixApiClient:
    def __init__(self, *, api_base_url: str, token: str, timeout_seconds: float = 15.0):
        self.api_base_url = _normalize_api_base_url(api_base_url)
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.token = token
        logger.info(
            f"Connecting to Pretix API at {self.api_base_url} with token {token!r}"
        )
        self.session.headers.update(self._get_headers(token))

    def _get_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Token {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.api_base_url}{path}"

    def _request(
        self, method: str, path: str, *, json_payload: dict | None = None
    ) -> dict:
        try:
            response = self.session.request(
                method,
                self._url(path),
                json=json_payload,
                timeout=self.timeout_seconds,
                headers=self._get_headers(self.token),
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.RequestException as exc:
            raise CommandError(
                f"Pretix API request failed for {method} {path}: {exc}"
            ) from exc

    def _request_paginated(self, path: str) -> list[dict]:
        payload = self._request("GET", path)
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            raise CommandError(
                f"Unexpected Pretix API response for {path}: {payload!r}"
            )

        results = list(payload.get("results") or [])
        next_url = payload.get("next")
        while next_url:
            try:
                response = self.session.get(next_url, timeout=self.timeout_seconds)
                response.raise_for_status()
                page = response.json()
            except requests.RequestException as exc:
                raise CommandError(
                    f"Pretix API pagination failed for {path}: {exc}"
                ) from exc

            if not isinstance(page, dict):
                raise CommandError(
                    f"Unexpected Pretix API response page for {path}: {page!r}"
                )

            results.extend(page.get("results") or [])
            next_url = page.get("next")

        return results

    def get_organizer(self, organizer_slug: str) -> dict | None:
        organizers = self._request_paginated("/organizers/")
        for organizer in organizers:
            if organizer.get("slug") == organizer_slug:
                return organizer
        return None

    def create_organizer(self, *, slug: str, name: str) -> dict:
        return self._request(
            "POST", "/organizers/", json_payload={"slug": slug, "name": name}
        )

    def patch_organizer(self, *, slug: str, payload: dict) -> dict:
        return self._request("PATCH", f"/organizers/{slug}/", json_payload=payload)

    def list_events(self, organizer_slug: str) -> list[dict]:
        return self._request_paginated(f"/organizers/{organizer_slug}/events/")

    def create_event(self, *, organizer_slug: str, payload: dict) -> dict:
        return self._request(
            "POST", f"/organizers/{organizer_slug}/events/", json_payload=payload
        )

    def patch_event(
        self, *, organizer_slug: str, event_slug: str, payload: dict
    ) -> dict:
        return self._request(
            "PATCH",
            f"/organizers/{organizer_slug}/events/{event_slug}/",
            json_payload=payload,
        )


class Command(BaseCommand):
    help = "Ensure one pretix organizer and one pretix event per active proposal area."

    def add_arguments(self, parser):
        parser.add_argument("--api-base-url", type=str, default=None)
        parser.add_argument("--api-token", type=str, default=None)
        parser.add_argument("--organizer-slug", type=str, default=None)
        parser.add_argument("--organizer-name", type=str, default=None)
        parser.add_argument("--event-slug-prefix", type=str, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def _read_settings(self, options: dict) -> PretixSettings:
        return PretixSettings(
            api_base_url=options.get("api_base_url") or settings.PRETIX_API_BASE_URL,
            api_token=options.get("api_token") or settings.PRETIX_API_TOKEN,
            organizer_slug=options.get("organizer_slug")
            or settings.PRETIX_ORGANIZER_SLUG,
            organizer_name=options.get("organizer_name")
            or settings.PRETIX_ORGANIZER_NAME,
            event_slug_prefix=options.get("event_slug_prefix")
            or settings.PRETIX_EVENT_SLUG_PREFIX,
            event_currency=settings.PRETIX_EVENT_CURRENCY,
            event_timezone=settings.PRETIX_EVENT_TIMEZONE,
            event_locale=settings.PRETIX_EVENT_LOCALE,
        )

    def _build_client(self, runtime_settings: PretixSettings) -> PretixApiClient:
        if not runtime_settings.api_token:
            self._setup_pretix(runtime_settings)
        return PretixApiClient(
            api_base_url=runtime_settings.api_base_url,
            token=runtime_settings.api_token,
        )

    def _event_payload(
        self, *, runtime_settings: PretixSettings, event_slug: str, area_label: str
    ) -> dict:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        return {
            "slug": event_slug,
            "name": {runtime_settings.event_locale: area_label},
            "currency": runtime_settings.event_currency,
            "timezone": runtime_settings.event_timezone,
            "date_from": today.isoformat(),
            "date_to": tomorrow.isoformat(),
            "live": False,
            "has_subevents": True,
        }

    def handle(self, *args, **options):
        runtime_settings = self._read_settings(options)

        dry_run = bool(options.get("dry_run"))
        client = self._build_client(runtime_settings)

        organizer = client.get_organizer(runtime_settings.organizer_slug)
        if organizer is None:
            raise Exception("Failed to get organizer from pretix.")
        elif organizer.get("name") != runtime_settings.organizer_name:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"[dry-run] Would update organizer name to {runtime_settings.organizer_name!r}."
                    )
                )
            else:
                client.patch_organizer(
                    slug=runtime_settings.organizer_slug,
                    payload={"name": runtime_settings.organizer_name},
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated organizer {runtime_settings.organizer_slug!r} name."
                    )
                )

        area_rows = list(
            ProposalArea.objects.filter(is_active=True).order_by("sort_order", "label")
        )
        if not area_rows:
            self.stdout.write(
                self.style.WARNING("No active proposal areas found. Nothing to sync.")
            )
            return

        existing_events = {
            event.get("slug"): event
            for event in client.list_events(runtime_settings.organizer_slug)
            if event.get("slug")
        }

        created_events = 0
        updated_events = 0
        reused_events = 0

        for area in area_rows:
            event_slug = _build_event_slug(
                runtime_settings.event_slug_prefix, area.code
            )
            expected_name = {runtime_settings.event_locale: area.label}
            payload = self._event_payload(
                runtime_settings=runtime_settings,
                event_slug=event_slug,
                area_label=area.label,
            )
            existing = existing_events.get(event_slug)

            if existing is None:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[dry-run] Would create event {event_slug!r} for area {area.code!r}."
                        )
                    )
                else:
                    client.create_event(
                        organizer_slug=runtime_settings.organizer_slug,
                        payload=payload,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created event {event_slug!r} for area {area.code!r}."
                        )
                    )
                created_events += 1
                continue

            patch_payload = {}
            current_name = existing.get("name")
            if current_name != expected_name:
                patch_payload["name"] = expected_name

            if not existing.get("has_subevents"):
                patch_payload["has_subevents"] = True

            if patch_payload:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[dry-run] Would update event {event_slug!r} with payload {patch_payload!r}."
                        )
                    )
                else:
                    client.patch_event(
                        organizer_slug=runtime_settings.organizer_slug,
                        event_slug=event_slug,
                        payload=patch_payload,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated event {event_slug!r} for area {area.code!r}."
                        )
                    )
                updated_events += 1
            else:
                reused_events += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Pretix sync finished: "
                f"created={created_events}, updated={updated_events}, unchanged={reused_events}."
            )
        )

    def _setup_pretix(self, runtime_settings: PretixSettings):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            home_url = runtime_settings.api_base_url.rstrip("/").rstrip("/api/v1")
            page.goto(home_url)

            page.get_by_role("link", name="head over here").click()
            page.get_by_role("textbox", name="Email").fill("admin@localhost")
            page.get_by_role("textbox", name="Password").fill("admin")
            page.get_by_role("button", name="Log in").click()
            page.get_by_role("link", name=" Organizers").click()
            page.get_by_role("button", name=" Admin mode").click()
            page.get_by_role("link", name=" Create a new organizer").click()
            page.get_by_role("textbox", name="Name").click()
            number = str(random.randint(1, 999999))
            runtime_settings.organizer_slug = runtime_settings.organizer_slug + number
            runtime_settings.organizer_name = runtime_settings.organizer_name + number
            page.get_by_role("textbox", name="Name").fill(
                runtime_settings.organizer_name
            )
            page.get_by_role("textbox", name="Short form").fill(
                runtime_settings.organizer_slug
            )
            page.get_by_role("button", name="Save").click()
            page.get_by_role("link", name=" Teams").click()
            page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(2).click()
            apitokenname = "APITOKEN" + number
            page.get_by_role("textbox", name="Token name").fill("%s" % apitokenname)
            page.get_by_role(
                "row", name=("Token name %s  Add" % apitokenname)
            ).get_by_role("button").click()
            locator = page.get_by_text("A new API token has been")
            expect(locator).to_be_visible()
            page.wait_for_timeout(500)
            apitoken_message = locator.inner_html()
            logger.info(apitoken_message)
            apitoken_message_strip = apitoken_message.strip()
            message_strip__lstrip = apitoken_message_strip.removeprefix("A new API token has been created with the following secret:")
            apitoken = (
                message_strip__lstrip.split("<br>")[0]
            )
            runtime_settings.api_token = apitoken
            logger.info(runtime_settings.api_token)
            if not 55 < len(runtime_settings.api_token) < 70:  # sometimes 64, sometimes 61 chars
                raise Exception("Invalid API token")
            page.close()
            browser.close()
