from __future__ import annotations

import json
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from apiv1.models.basedata import Event, Proposal, Series
from apiv1.models.sync.syncbasedata import SyncBaseTarget
from sync_ical.models import IcalCalendarSyncTarget, IcalCalenderSyncItem
from sync_pretix.models import PretixSyncItem, PretixSyncTarget, PretixSyncTargetAreaAssociation
from apiv1.models.basedata import ProposalArea


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
        self.assertEqual(statuses[0]["target_id"], str(target.pk))
        self.assertEqual(statuses[0]["platform"], "IcalCalendarSyncTarget")
        self.assertEqual(statuses[0]["status"], "no entry exists")
        self.assertIsNone(statuses[0]["last_synced"])

    def test_sync_status_shows_up_to_date_when_item_exists(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        IcalCalenderSyncItem.objects.create(
            sync_target=target,
            related_event=self.event,
            uid="test-uid-status",
            ical_definition="BEGIN:VEVENT\nEND:VEVENT",
        )
        self._grant_permissions("view_event")
        self._login(self.user)

        response = self.client.get(f"/api/v1/sync/status/{self.series.pk}/{self.event.pk}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        statuses = payload["sync_statuses"]
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["target_id"], str(target.pk))
        self.assertEqual(statuses[0]["status"], "entry up-to-date")
        self.assertIsNotNone(statuses[0]["last_synced"])

    def test_sync_status_distinguishes_multiple_targets_of_same_type(self) -> None:
        """Two iCal targets must appear as separate status entries with distinct target_ids."""
        target1 = IcalCalendarSyncTarget.objects.create(
            name="Calendar A",
            url="https://example.com/a.ics",
        )
        target2 = IcalCalendarSyncTarget.objects.create(
            name="Calendar B",
            url="https://example.com/b.ics",
        )
        IcalCalenderSyncItem.objects.create(
            sync_target=target1,
            related_event=self.event,
            uid="test-uid-multi-1",
            ical_definition="BEGIN:VEVENT\nEND:VEVENT",
        )
        self._grant_permissions("view_event")
        self._login(self.user)

        response = self.client.get(f"/api/v1/sync/status/{self.series.pk}/{self.event.pk}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        statuses = payload["sync_statuses"]
        self.assertEqual(len(statuses), 2)
        target_ids = {s["target_id"] for s in statuses}
        self.assertIn(str(target1.pk), target_ids)
        self.assertIn(str(target2.pk), target_ids)

        by_target = {s["target_id"]: s for s in statuses}
        self.assertEqual(by_target[str(target1.pk)]["status"], "entry up-to-date")
        self.assertEqual(by_target[str(target2.pk)]["status"], "no entry exists")

    # ------------------------------------------------------------------ #
    # POST /sync/push/{series_id}/{event_id}/{target_id}
    # ------------------------------------------------------------------ #

    def test_push_requires_auth(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        response = self.client.post(
            f"/api/v1/sync/push/{self.series.pk}/{self.event.pk}/{target.pk}"
        )
        self.assertEqual(response.status_code, 401)

    def test_push_requires_change_event_permission(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._login(self.user)
        response = self.client.post(
            f"/api/v1/sync/push/{self.series.pk}/{self.event.pk}/{target.pk}"
        )
        self.assertEqual(response.status_code, 403)

    def test_push_returns_404_for_unknown_target(self) -> None:
        self._grant_permissions("change_event")
        self._login(self.user)
        response = self.client.post(
            f"/api/v1/sync/push/{self.series.pk}/{self.event.pk}/00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(response.status_code, 404)

    def test_push_returns_success_false_when_no_items(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._grant_permissions("change_event")
        self._login(self.user)
        response = self.client.post(
            f"/api/v1/sync/push/{self.series.pk}/{self.event.pk}/{target.pk}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["target_id"], str(target.pk))

    def test_push_only_pushes_matching_target(self) -> None:
        """Push to target1 must not affect target2."""
        target1 = IcalCalendarSyncTarget.objects.create(
            name="Calendar A",
            url="https://example.com/a.ics",
        )
        target2 = IcalCalendarSyncTarget.objects.create(
            name="Calendar B",
            url="https://example.com/b.ics",
        )
        IcalCalenderSyncItem.objects.create(
            sync_target=target1,
            related_event=self.event,
            uid="push-test-uid",
            ical_definition="BEGIN:VEVENT\nEND:VEVENT",
        )
        self._grant_permissions("change_event")
        self._login(self.user)

        # Push to target2 (no items there)
        response = self.client.post(
            f"/api/v1/sync/push/{self.series.pk}/{self.event.pk}/{target2.pk}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["target_id"], str(target2.pk))

        # Push to target1 (has an item)
        response = self.client.post(
            f"/api/v1/sync/push/{self.series.pk}/{self.event.pk}/{target1.pk}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["target_id"], str(target1.pk))

    # ------------------------------------------------------------------ #
    # GET /sync/diff/{series_id}/{event_id}/{target_id}
    # ------------------------------------------------------------------ #

    def test_diff_requires_auth(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        response = self.client.get(
            f"/api/v1/sync/diff/{self.series.pk}/{self.event.pk}/{target.pk}"
        )
        self.assertEqual(response.status_code, 401)

    def test_diff_requires_view_event_permission(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._login(self.user)
        response = self.client.get(
            f"/api/v1/sync/diff/{self.series.pk}/{self.event.pk}/{target.pk}"
        )
        self.assertEqual(response.status_code, 403)

    def test_diff_returns_404_for_unknown_target(self) -> None:
        self._grant_permissions("view_event")
        self._login(self.user)
        response = self.client.get(
            f"/api/v1/sync/diff/{self.series.pk}/{self.event.pk}/00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(response.status_code, 404)

    def test_diff_returns_empty_properties_when_no_items(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        self._grant_permissions("view_event")
        self._login(self.user)
        response = self.client.get(
            f"/api/v1/sync/diff/{self.series.pk}/{self.event.pk}/{target.pk}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["target_id"], str(target.pk))
        self.assertEqual(payload["properties"], [])

    def test_diff_only_returns_diff_for_requested_target(self) -> None:
        """Diff for target2 must not include items from target1."""
        target1 = IcalCalendarSyncTarget.objects.create(
            name="Calendar A",
            url="https://example.com/a.ics",
        )
        target2 = IcalCalendarSyncTarget.objects.create(
            name="Calendar B",
            url="https://example.com/b.ics",
        )
        IcalCalenderSyncItem.objects.create(
            sync_target=target1,
            related_event=self.event,
            uid="diff-test-uid",
            ical_definition="BEGIN:VEVENT\nEND:VEVENT",
        )
        self._grant_permissions("view_event")
        self._login(self.user)

        response = self.client.get(
            f"/api/v1/sync/diff/{self.series.pk}/{self.event.pk}/{target2.pk}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["target_id"], str(target2.pk))
        self.assertEqual(payload["properties"], [])


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
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/status-test.ics",
        )
        series = Series.objects.create(name="Test Series")
        now = timezone.now()
        event = Event.objects.create(
            series=series,
            name="Test Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        IcalCalenderSyncItem.objects.create(
            sync_target=target,
            related_event=event,
            uid="test-uid-get-status",
            ical_definition="BEGIN:VEVENT\nEND:VEVENT",
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


# ---------------------------------------------------------------------------
# POST /sync/create/{series_id}/{event_id}/{target_id}
# ---------------------------------------------------------------------------

class CreateSyncItemEndpointTest(TestCase):
    """Tests for the POST /sync/create endpoint."""

    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="create-item-user",
            password="create-item-pass-123",
            email="create-item-user@example.com",
        )
        self.area = ProposalArea.objects.create(code="laser", label="Laser")
        self.series = Series.objects.create(name="Create Item Series")
        now = timezone.now()
        self.proposal = Proposal.objects.create(
            title="Workshop",
            abstract="a" * 50,
            description="d" * 50,
            material_cost_eur="0.00",
            preferred_dates="Any",
            area=self.area,
        )
        self.event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Create Item Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=2),
        )
        self.pretix_target = PretixSyncTarget.objects.create(
            api_token="token",
            api_url="https://pretix.example.com/api/v1",
            organizer_slug="zam",
        )
        PretixSyncTargetAreaAssociation.objects.create(
            sync_target=self.pretix_target,
            area=self.area,
            event_slug="laser-2026",
        )

    def _login(self) -> None:
        self.client.force_login(self.user)
        session = self.client.session
        session["oidc_id_token_expiration"] = time.time() + 3600
        session.save()

    def _grant_permissions(self, *codenames: str) -> None:
        perms = Permission.objects.filter(codename__in=codenames)
        self.user.user_permissions.add(*perms)
        self.user = get_user_model().objects.get(pk=self.user.pk)

    def _url(self, target=None):
        t = target or self.pretix_target
        return f"/api/v1/sync/create/{self.series.pk}/{self.event.pk}/{t.pk}"

    # ------------------------------------------------------------------
    # Auth / permission guards
    # ------------------------------------------------------------------

    def test_requires_auth(self) -> None:
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 401)

    def test_requires_add_syncbaseitem_permission(self) -> None:
        self._login()
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 403)

    def test_returns_404_for_unknown_target(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()
        response = self.client.post(
            f"/api/v1/sync/create/{self.series.pk}/{self.event.pk}/00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(response.status_code, 404)

    def test_returns_404_for_wrong_series(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()
        other_series = Series.objects.create(name="Other")
        response = self.client.post(
            f"/api/v1/sync/create/{other_series.pk}/{self.event.pk}/{self.pretix_target.pk}"
        )
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Pretix target – success path
    # ------------------------------------------------------------------

    def test_creates_pretix_sync_item_and_returns_it(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()

        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("id", payload)
        self.assertEqual(payload["target_id"], str(self.pretix_target.pk))
        self.assertEqual(payload["event_id"], str(self.event.pk))

        self.assertTrue(
            PretixSyncItem.objects.filter(
                sync_target=self.pretix_target,
                related_event=self.event,
                event_slug="laser-2026",
            ).exists()
        )

    def test_create_is_idempotent(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()

        r1 = self.client.post(self._url())
        r2 = self.client.post(self._url())
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(PretixSyncItem.objects.filter(related_event=self.event).count(), 1)

    # ------------------------------------------------------------------
    # Pretix target – error paths
    # ------------------------------------------------------------------

    def test_returns_400_when_event_has_no_proposal(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()
        now = timezone.now()
        event_no_proposal = Event.objects.create(
            series=self.series,
            name="No Proposal Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        response = self.client.post(
            f"/api/v1/sync/create/{self.series.pk}/{event_no_proposal.pk}/{self.pretix_target.pk}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_returns_400_when_proposal_has_no_area(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()
        proposal_no_area = Proposal.objects.create(
            title="No Area",
            abstract="a" * 50,
            description="d" * 50,
            material_cost_eur="0.00",
            preferred_dates="Any",
        )
        now = timezone.now()
        event = Event.objects.create(
            series=self.series,
            proposal=proposal_no_area,
            name="No Area Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        response = self.client.post(
            f"/api/v1/sync/create/{self.series.pk}/{event.pk}/{self.pretix_target.pk}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_returns_400_when_no_association_for_area(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()
        other_area = ProposalArea.objects.create(code="wood", label="Wood")
        proposal = Proposal.objects.create(
            title="Wood Workshop",
            abstract="a" * 50,
            description="d" * 50,
            material_cost_eur="0.00",
            preferred_dates="Any",
            area=other_area,
        )
        now = timezone.now()
        event = Event.objects.create(
            series=self.series,
            proposal=proposal,
            name="Wood Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        response = self.client.post(
            f"/api/v1/sync/create/{self.series.pk}/{event.pk}/{self.pretix_target.pk}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    # ------------------------------------------------------------------
    # iCal target – not implemented
    # ------------------------------------------------------------------

    def test_returns_400_for_ical_target(self) -> None:
        self._grant_permissions("add_syncbaseitem")
        self._login()
        ical_target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        response = self.client.post(
            f"/api/v1/sync/create/{self.series.pk}/{self.event.pk}/{ical_target.pk}"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


# ---------------------------------------------------------------------------
# PretixSyncTarget.create_new_sync_item – unit tests
# ---------------------------------------------------------------------------

class PretixCreateNewSyncItemTest(TestCase):
    """Unit tests for PretixSyncTarget.create_new_sync_item."""

    def setUp(self) -> None:
        self.area = ProposalArea.objects.create(code="metal", label="Metal")
        self.series = Series.objects.create(name="Pretix Create Test Series")
        now = timezone.now()
        self.proposal = Proposal.objects.create(
            title="Metal Workshop",
            abstract="a" * 50,
            description="d" * 50,
            material_cost_eur="0.00",
            preferred_dates="Any",
            area=self.area,
        )
        self.event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Metal Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=2),
        )
        self.target = PretixSyncTarget.objects.create(
            api_token="token",
            api_url="https://pretix.example.com/api/v1",
            organizer_slug="zam",
        )
        PretixSyncTargetAreaAssociation.objects.create(
            sync_target=self.target,
            area=self.area,
            event_slug="metal-2026",
        )

    def test_creates_pretix_sync_item_with_correct_slug(self) -> None:
        item = self.target.create_new_sync_item(self.event)
        self.assertIsInstance(item, PretixSyncItem)
        self.assertEqual(item.sync_target, self.target)
        self.assertEqual(item.related_event, self.event)
        self.assertEqual(item.event_slug, "metal-2026")

    def test_is_idempotent(self) -> None:
        item1 = self.target.create_new_sync_item(self.event)
        item2 = self.target.create_new_sync_item(self.event)
        self.assertEqual(item1.pk, item2.pk)
        self.assertEqual(PretixSyncItem.objects.filter(related_event=self.event).count(), 1)

    def test_raises_for_event_without_proposal(self) -> None:
        now = timezone.now()
        event = Event.objects.create(
            series=self.series,
            name="No Proposal",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        with self.assertRaises(ValueError):
            self.target.create_new_sync_item(event)

    def test_raises_for_proposal_without_area(self) -> None:
        proposal = Proposal.objects.create(
            title="No Area",
            abstract="a" * 50,
            description="d" * 50,
            material_cost_eur="0.00",
            preferred_dates="Any",
        )
        now = timezone.now()
        event = Event.objects.create(
            series=self.series,
            proposal=proposal,
            name="No Area",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        with self.assertRaises(ValueError):
            self.target.create_new_sync_item(event)

    def test_raises_when_no_association_for_area(self) -> None:
        other_area = ProposalArea.objects.create(code="wood", label="Wood")
        proposal = Proposal.objects.create(
            title="Wood",
            abstract="a" * 50,
            description="d" * 50,
            material_cost_eur="0.00",
            preferred_dates="Any",
            area=other_area,
        )
        now = timezone.now()
        event = Event.objects.create(
            series=self.series,
            proposal=proposal,
            name="Wood",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        with self.assertRaises(ValueError):
            self.target.create_new_sync_item(event)


class IcalCreateNewSyncItemTest(TestCase):
    """IcalCalendarSyncTarget.create_new_sync_item must raise NotImplementedError."""

    def test_raises_not_implemented(self) -> None:
        target = IcalCalendarSyncTarget.objects.create(
            name="Calendar",
            url="https://example.com/cal.ics",
        )
        series = Series.objects.create(name="iCal Test")
        now = timezone.now()
        event = Event.objects.create(
            series=series,
            name="Event",
            start_time=now,
            end_time=now + timezone.timedelta(hours=1),
        )
        with self.assertRaises(NotImplementedError):
            target.create_new_sync_item(event)
