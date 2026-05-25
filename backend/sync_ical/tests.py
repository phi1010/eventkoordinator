from datetime import datetime, timezone
from unittest.mock import Mock, patch

from django.test import TestCase

from apiv1.models import Event, Series
from sync_ical.models import IcalCalendarSyncTarget, IcalCalenderSyncItem
from sync_ical.tasks import sync_ical_target


class SyncIcalTargetIntegrationTests(TestCase):

    def _make_target(self, url="https://cal.example.com/feed.ics", name="Test Calendar"):
        return IcalCalendarSyncTarget.objects.create(url=url, name=name)

    def _patch_fetch(self, ics_content):
        mock_response = Mock()
        mock_response.text = ics_content
        mock_response.raise_for_status = Mock()
        return patch("sync_ical.tasks.requests.get", return_value=mock_response)

    def _patch_now(self, fixed_now):
        return patch("sync_ical.tasks.django_timezone.now", return_value=fixed_now)

    def test_creates_events_without_series(self):
        calendar_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:workshop-1@example.com
SUMMARY:Workshop Alpha
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
DESCRIPTION:First workshop description
CATEGORIES:workshop,beginner
END:VEVENT
BEGIN:VEVENT
UID:workshop-2@example.com
SUMMARY:Workshop Alpha
DTSTART;VALUE=DATE:20260308
DTEND;VALUE=DATE:20260309
CATEGORIES:workshop,beginner
END:VEVENT
BEGIN:VEVENT
UID:meeting-1@example.com
SUMMARY:Team Meeting
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
CATEGORIES:internal
END:VEVENT
END:VCALENDAR
"""
        fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        target = self._make_target()

        with self._patch_now(fixed_now), self._patch_fetch(calendar_content):
            sync_ical_target(target.pk)

        self.assertEqual(Series.objects.count(), 0)
        self.assertEqual(Event.objects.count(), 3)
        self.assertTrue(Event.objects.filter(series__isnull=True).count() == 3)

        workshop_events = list(Event.objects.filter(name="Workshop Alpha").order_by("start_time"))
        self.assertEqual(len(workshop_events), 2)
        self.assertEqual(workshop_events[0].start_time.date(), datetime(2026, 3, 1).date())
        self.assertEqual(workshop_events[1].start_time.date(), datetime(2026, 3, 8).date())
        self.assertEqual(workshop_events[0].tag, "workshop")

        meeting_event = Event.objects.get(name="Team Meeting")
        self.assertEqual(meeting_event.tag, "internal")
        self.assertIsNone(meeting_event.series)

        self.assertEqual(IcalCalenderSyncItem.objects.count(), 3)
        for item in IcalCalenderSyncItem.objects.all():
            self.assertEqual(item.sync_target, target)
            self.assertIsNotNone(item.related_event)
            self.assertIn(b"BEGIN:VEVENT", item.ical_definition.encode())

    def test_no_duplicates_on_rerun(self):
        calendar_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:recurring-workshop@example.com
SUMMARY:Recurring Workshop
DTSTART;VALUE=DATE:20260101
DTEND;VALUE=DATE:20260102
RRULE:FREQ=WEEKLY;COUNT=4
CATEGORIES:workshop
END:VEVENT
END:VCALENDAR
"""
        fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        target = self._make_target()

        with self._patch_now(fixed_now), self._patch_fetch(calendar_content):
            sync_ical_target(target.pk)

        initial_count = IcalCalenderSyncItem.objects.count()
        self.assertEqual(initial_count, 4)

        with self._patch_now(fixed_now), self._patch_fetch(calendar_content):
            sync_ical_target(target.pk)

        self.assertEqual(IcalCalenderSyncItem.objects.count(), initial_count)
        self.assertEqual(Series.objects.count(), 0)

    def test_updates_ical_definition_on_reimport(self):
        calendar_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:reimport-event@example.com
SUMMARY:Reimport Event
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
CATEGORIES:tag1
END:VEVENT
END:VCALENDAR
"""
        fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        target = self._make_target()

        with self._patch_now(fixed_now), self._patch_fetch(calendar_content):
            sync_ical_target(target.pk)

        self.assertEqual(IcalCalenderSyncItem.objects.count(), 1)

        with self._patch_now(fixed_now), self._patch_fetch(calendar_content):
            sync_ical_target(target.pk)

        self.assertEqual(IcalCalenderSyncItem.objects.count(), 1)

    def test_handles_fetch_error(self):
        from requests import RequestException

        target = self._make_target()

        with patch("sync_ical.tasks.requests.get", side_effect=RequestException("Network error")):
            with self.assertLogs("sync_ical.tasks", level="ERROR"):
                sync_ical_target(target.pk)

        self.assertEqual(Event.objects.count(), 0)

    def test_preserves_existing_data_on_fetch_error(self):
        initial_calendar = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:preserve-event@example.com
SUMMARY:Preserve Event
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
CATEGORIES:test
END:VEVENT
END:VCALENDAR
"""
        fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        target = self._make_target()

        with self._patch_now(fixed_now), self._patch_fetch(initial_calendar):
            sync_ical_target(target.pk)

        self.assertEqual(IcalCalenderSyncItem.objects.count(), 1)

        from requests import RequestException
        with patch("sync_ical.tasks.requests.get", side_effect=RequestException("Network error")):
            sync_ical_target(target.pk)

        self.assertEqual(IcalCalenderSyncItem.objects.count(), 1)

    def test_nonexistent_target_logs_error(self):
        with self.assertLogs("sync_ical.tasks", level="ERROR"):
            sync_ical_target(99999)

    def test_deletes_events_removed_from_feed(self):
        first_calendar = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:event-keep@example.com
SUMMARY:Keep Me
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
END:VEVENT
BEGIN:VEVENT
UID:event-remove@example.com
SUMMARY:Remove Me
DTSTART;VALUE=DATE:20260308
DTEND;VALUE=DATE:20260309
END:VEVENT
END:VCALENDAR
"""
        second_calendar = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:event-keep@example.com
SUMMARY:Keep Me
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
END:VEVENT
END:VCALENDAR
"""
        fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        target = self._make_target()

        with self._patch_now(fixed_now), self._patch_fetch(first_calendar):
            sync_ical_target(target.pk)

        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(IcalCalenderSyncItem.objects.count(), 2)

        with self._patch_now(fixed_now), self._patch_fetch(second_calendar):
            sync_ical_target(target.pk)

        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(IcalCalenderSyncItem.objects.count(), 1)
        self.assertEqual(Event.objects.first().name, "Keep Me")

    def test_limits_recurring_events_to_import_window(self):
        ics_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Recurring Import//EN
BEGIN:VEVENT
UID:recurring-import@example.com
SUMMARY:Recurring Import
DESCRIPTION:Recurring import description
CATEGORIES:community,calendar
DTSTART;VALUE=DATE:20250101
DTEND;VALUE=DATE:20250102
RRULE:FREQ=DAILY;COUNT=900
END:VEVENT
END:VCALENDAR
"""
        fixed_now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        target = self._make_target()

        with self._patch_now(fixed_now), self._patch_fetch(ics_content):
            sync_ical_target(target.pk)

        imported_events = list(Event.objects.filter(name="Recurring Import").order_by("start_time"))

        self.assertTrue(imported_events)
        from datetime import date
        self.assertEqual(imported_events[0].start_time.date(), date(2025, 3, 10))
        self.assertEqual(imported_events[-1].start_time.date(), date(2027, 3, 10))
