from __future__ import annotations

import json
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from apiv1.models.basedata import Event, Series
from apiv1.models.sync.syncbasedata import SyncBaseItem, SyncBaseTarget
from sync_ical.models import IcalCalendarSyncTarget
from sync_pretix.models import PretixSyncTarget


class SyncTargetsApiTest(TestCase):
    """Tests for the sync targets listing and sync item creation endpoints."""

    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="sync-api-user",
            password="sync-api-pass-123",
            email="sync-api-user@example.com",
        )
        self.series = Series.objects.create(name="Sync API Series")
        now = timezone.now()
        self.event = Event.objects.create(
            series=self.series,
            name="Sync API Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=2),
        )

    def _login(self, user) -> None:
        """Log in and set a valid OIDC session expiry so SessionRefresh does not redirect."""
        self.client.force_login(user)
        session = self.client.session
        session["oidc_id_token_expiration"] = time.time() + 3600
        session.save()

    def _grant_permissions(self, *codenames: str) -> None:
        perms = Permission.objects.filter(codename__in=codenames)
        self.user.user_permissions.add(*perms)
        # Re-fetch user to clear permission cache
        self.user = get_user_model().objects.get(pk=self.user.pk)

    # ------------------------------------------------------------------ #
    # GET /sync/targets
    # ------------------------------------------------------------------ #

    def test_list_targets_requires_auth(self) -> None:
        response = self.client.get("/api/v1/sync/targets")
        self.assertEqual(response.status_code, 401)

    def test_list_targets_requires_viewrestricted_permission(self) -> None:
        self._login(self.user)
        response = self.client.get("/api/v1/sync/targets")
        self.assertEqual(response.status_code, 403)

    def test_list_targets_returns_empty_when_none_exist(self) -> None:
        self._grant_permissions("viewrestricted_syncbasetarget")
        self._login(self.user)
        response = self.client.get("/api/v1/sync/targets")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_targets_returns_pretix_target_without_secrets(self) -> None:
        PretixSyncTarget.objects.create(
            api_token="super-secret-token",
            api_url="https://pretix.example.com/api/v1",
            organizer_slug="my-org",
        )
        self._grant_permissions("viewrestricted_syncbasetarget")
        self._login(self.user)

        response = self.client.get("/api/v1/sync/targets")
        self.assertEqual(response.status_code, 200)
        targets = response.json()
        self.assertEqual(len(targets), 1)

        target = targets[0]
        self.assertEqual(target["type"], "PretixSyncTarget")
        self.assertIn("api_url", target["public_properties"])
        self.assertIn("organizer_slug", target["public_properties"])
        self.assertNotIn("api_token", target["public_properties"])
        self.assertEqual(
            target["public_properties"]["api_url"],
            "https://pretix.example.com/api/v1",
        )

    def test_list_targets_returns_ical_target(self) -> None:
        IcalCalendarSyncTarget.objects.create(
            name="Test Calendar",
            description="A test iCal calendar",
            url="https://example.com/cal.ics",
        )
        self._grant_permissions("viewrestricted_syncbasetarget")
        self._login(self.user)

        response = self.client.get("/api/v1/sync/targets")
        self.assertEqual(response.status_code, 200)
        targets = response.json()
        self.assertEqual(len(targets), 1)

        target = targets[0]
        self.assertEqual(target["type"], "IcalCalendarSyncTarget")
        self.assertIn("name", target["public_properties"])
        self.assertEqual(target["public_properties"]["name"], "Test Calendar")

    def test_list_targets_returns_multiple_targets(self) -> None:
        PretixSyncTarget.objects.create(
            api_token="token1",
            api_url="https://pretix.example.com/api/v1",
            organizer_slug="org1",
        )
        IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._grant_permissions("viewrestricted_syncbasetarget")
        self._login(self.user)

        response = self.client.get("/api/v1/sync/targets")
        self.assertEqual(response.status_code, 200)
        targets = response.json()
        self.assertEqual(len(targets), 2)
        types = {t["type"] for t in targets}
        self.assertEqual(types, {"PretixSyncTarget", "IcalCalendarSyncTarget"})

    # ------------------------------------------------------------------ #
    # POST /sync/items
    # ------------------------------------------------------------------ #

    def test_create_sync_item_requires_auth(self) -> None:
        response = self.client.post(
            "/api/v1/sync/items",
            data=json.dumps({"sync_target_id": "00000000-0000-0000-0000-000000000000", "event_id": str(self.event.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_create_sync_item_requires_add_syncbaseitem_permission(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._login(self.user)
        response = self.client.post(
            "/api/v1/sync/items",
            data=json.dumps({"sync_target_id": str(target.pk), "event_id": str(self.event.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_create_sync_item_creates_and_returns_item(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._grant_permissions("add_syncbaseitem")
        self._login(self.user)

        response = self.client.post(
            "/api/v1/sync/items",
            data=json.dumps({"sync_target_id": str(target.pk), "event_id": str(self.event.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("id", payload)
        self.assertEqual(payload["sync_target_id"], str(target.pk))
        self.assertEqual(payload["event_id"], str(self.event.pk))

        # Verify item was created in the database
        self.assertTrue(
            SyncBaseItem.objects.filter(
                sync_target=target, related_event=self.event
            ).exists()
        )

    def test_create_sync_item_is_idempotent(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._grant_permissions("add_syncbaseitem")
        self._login(self.user)

        body = json.dumps({"sync_target_id": str(target.pk), "event_id": str(self.event.pk)})
        response1 = self.client.post("/api/v1/sync/items", data=body, content_type="application/json")
        response2 = self.client.post("/api/v1/sync/items", data=body, content_type="application/json")
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response1.json()["id"], response2.json()["id"])

        # Only one item should exist
        self.assertEqual(
            SyncBaseItem.objects.filter(sync_target=target, related_event=self.event).count(),
            1,
        )

    def test_create_sync_item_returns_404_for_missing_target(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login(self.user)

        response = self.client.post(
            "/api/v1/sync/items",
            data=json.dumps({
                "sync_target_id": "00000000-0000-0000-0000-000000000000",
                "event_id": str(self.event.pk),
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------ #
    # GET /sync/status/{series_id}/{event_id}
    # ------------------------------------------------------------------ #

    def test_sync_status_shows_no_entry_when_no_item_exists(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._grant_permissions("view_event")
        self._login(self.user)

        response = self.client.get(f"/api/v1/sync/status/{self.series.pk}/{self.event.pk}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        statuses = payload["sync_statuses"]
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["platform"], "IcalCalendarSyncTarget")
        self.assertEqual(statuses[0]["status"], "no entry exists")
        self.assertIsNone(statuses[0]["last_synced"])

    def test_sync_status_shows_up_to_date_when_item_exists(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        SyncBaseItem.objects.create(
            sync_target=target,
            related_event=self.event,
        )
        self._grant_permissions("view_event")
        self._login(self.user)

        response = self.client.get(f"/api/v1/sync/status/{self.series.pk}/{self.event.pk}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        statuses = payload["sync_statuses"]
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["status"], "entry up-to-date")
        self.assertIsNotNone(statuses[0]["last_synced"])


class SyncBaseTargetModelTest(TestCase):
    """Unit tests for SyncBaseTarget model methods."""

    def test_type_property_returns_concrete_class_name(self) -> None:
        target = PretixSyncTarget.objects.create(
            api_token="token",
            api_url="https://pretix.example.com",
            organizer_slug="org",
        )
        base = SyncBaseTarget.objects.get(pk=target.pk)
        self.assertEqual(base.type, "PretixSyncTarget")

    def test_public_properties_excludes_secret_fields(self) -> None:
        target = PretixSyncTarget.objects.create(
            api_token="secret-token",
            api_url="https://pretix.example.com",
            organizer_slug="org",
        )
        props = target.public_properties
        self.assertNotIn("api_token", props)
        self.assertIn("api_url", props)
        self.assertIn("organizer_slug", props)

    def test_public_properties_excludes_infrastructure_fields(self) -> None:
        target = PretixSyncTarget.objects.create(
            api_token="token",
            api_url="https://pretix.example.com",
            organizer_slug="org",
        )
        props = target.public_properties
        self.assertNotIn("id", props)
        self.assertNotIn("created_at", props)
        self.assertNotIn("updated_at", props)
        self.assertNotIn("polymorphic_ctype", props)

    def test_get_status_returns_no_entry_when_no_item(self) -> None:
        target = PretixSyncTarget.objects.create(
            api_token="token",
            api_url="https://pretix.example.com",
            organizer_slug="org",
        )
        series = Series.objects.create(name="Test Series")
        now = timezone.now()
        event = Event.objects.create(
            series=series,
            name="Test Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        self.assertEqual(
            target.get_status(event),
            SyncBaseTarget.SyncTargetStatus.NO_ENTRY_EXISTS,
        )

    def test_get_status_returns_up_to_date_when_item_exists(self) -> None:
        target = PretixSyncTarget.objects.create(
            api_token="token",
            api_url="https://pretix.example.com",
            organizer_slug="org",
        )
        series = Series.objects.create(name="Test Series")
        now = timezone.now()
        event = Event.objects.create(
            series=series,
            name="Test Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        SyncBaseItem.objects.create(
            sync_target=target,
            related_event=event,
        )
        self.assertEqual(
            target.get_status(event),
            SyncBaseTarget.SyncTargetStatus.ENTRY_UP_TO_DATE,
        )

    def test_ical_target_has_no_secret_fields(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        props = target.public_properties
        self.assertIn("name", props)
        self.assertIn("url", props)


