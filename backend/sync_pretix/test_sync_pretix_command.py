from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apiv1.models.basedata import ProposalArea


class _FakePretixApiClient:
    def __init__(self, organizer=None, events=None):
        self.organizer = organizer
        self.events = list(events or [])
        self.created_organizers = []
        self.patched_organizers = []
        self.created_events = []
        self.patched_events = []

    def get_organizer(self, organizer_slug):
        if self.organizer and self.organizer.get("slug") == organizer_slug:
            return self.organizer
        return None

    def create_organizer(self, *, slug, name):
        self.created_organizers.append({"slug": slug, "name": name})
        self.organizer = {"slug": slug, "name": name}
        return self.organizer

    def patch_organizer(self, *, slug, payload):
        self.patched_organizers.append({"slug": slug, "payload": payload})
        if self.organizer and self.organizer.get("slug") == slug:
            self.organizer.update(payload)
        return self.organizer or {"slug": slug}

    def list_events(self, organizer_slug):
        return list(self.events)

    def create_event(self, *, organizer_slug, payload):
        self.created_events.append({"organizer_slug": organizer_slug, "payload": payload})
        self.events.append({"slug": payload["slug"], "name": payload["name"]})
        return self.events[-1]

    def patch_event(self, *, organizer_slug, event_slug, payload):
        self.patched_events.append(
            {"organizer_slug": organizer_slug, "event_slug": event_slug, "payload": payload}
        )
        for event in self.events:
            if event.get("slug") == event_slug:
                event.update(payload)
                return event
        return {"slug": event_slug, **payload}


@override_settings(
    PRETIX_API_BASE_URL="http://pretix.local/api/v1",
    PRETIX_API_TOKEN="test-token",
    PRETIX_ORGANIZER_SLUG="zam",
    PRETIX_ORGANIZER_NAME="ZAM",
    PRETIX_EVENT_SLUG_PREFIX="area",
    PRETIX_EVENT_CURRENCY="EUR",
    PRETIX_EVENT_TIMEZONE="Europe/Berlin",
    PRETIX_EVENT_LOCALE="en",
)
class SyncPretixAreasCommandTests(TestCase):
    def setUp(self):
        ProposalArea.objects.all().delete()

    def test_creates_organizer_and_events_for_active_areas(self):
        ProposalArea.objects.create(code="metal", label="Metal")
        ProposalArea.objects.create(code="wood", label="Wood", is_active=False)

        fake_client = _FakePretixApiClient()
        stdout = StringIO()

        with patch(
            "sync_pretix.management.commands.sync_pretix_areas.Command._build_client",
            return_value=fake_client,
        ):
            call_command("sync_pretix_areas", stdout=stdout)

        self.assertEqual(fake_client.created_organizers, [{"slug": "zam", "name": "ZAM"}])
        self.assertEqual(len(fake_client.created_events), 1)
        self.assertEqual(fake_client.created_events[0]["payload"]["slug"], "area-metal")

    def test_updates_event_name_when_label_changed(self):
        ProposalArea.objects.create(code="laser", label="Laser Workshop")
        fake_client = _FakePretixApiClient(
            organizer={"slug": "zam", "name": "ZAM"},
            events=[{"slug": "area-laser", "name": {"en": "Old Name"}}],
        )

        with patch(
            "sync_pretix.management.commands.sync_pretix_areas.Command._build_client",
            return_value=fake_client,
        ):
            call_command("sync_pretix_areas")

        self.assertEqual(len(fake_client.created_events), 0)
        self.assertEqual(len(fake_client.patched_events), 1)
        self.assertEqual(fake_client.patched_events[0]["event_slug"], "area-laser")
        self.assertEqual(fake_client.patched_events[0]["payload"]["name"], {"en": "Laser Workshop"})

    def test_dry_run_does_not_mutate_remote(self):
        ProposalArea.objects.create(code="print", label="3D Print")
        fake_client = _FakePretixApiClient()

        with patch(
            "sync_pretix.management.commands.sync_pretix_areas.Command._build_client",
            return_value=fake_client,
        ):
            call_command("sync_pretix_areas", "--dry-run")

        self.assertEqual(fake_client.created_organizers, [])
        self.assertEqual(fake_client.created_events, [])
