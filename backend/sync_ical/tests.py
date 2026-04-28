from datetime import datetime, timezone
from io import StringIO
from unittest.mock import Mock, patch

from django.test import TestCase

from apiv1.models import Event, Series
from sync_ical.models import IcalCalendarSyncTarget, IcalCalenderSyncItem
from sync_ical.tasks import import_ical_task


class ImportIcalTaskIntegrationTests(TestCase):
    """Integration tests for the Celery import_ical_task."""

    def test_import_ical_task_creates_series_and_events(self):
        """Test that the task creates series, events, and sync items from a calendar."""
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

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = calendar_content
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                output = StringIO()
                with patch("sys.stdout", output):
                    import_ical_task()

        self.assertEqual(Series.objects.count(), 2)

        workshop_series = Series.objects.get(name="Workshop Alpha")
        self.assertEqual(workshop_series.events.count(), 2)
        workshop_events = list(workshop_series.events.order_by("start_time"))
        self.assertEqual(workshop_events[0].start_time.date(), datetime(2026, 3, 1).date())
        self.assertEqual(workshop_events[1].start_time.date(), datetime(2026, 3, 8).date())
        self.assertEqual(workshop_events[0].tag, "workshop")

        meeting_series = Series.objects.get(name="Team Meeting")
        self.assertEqual(meeting_series.events.count(), 1)
        self.assertEqual(meeting_series.events.first().tag, "internal")

        self.assertEqual(IcalCalendarSyncTarget.objects.count(), 1)
        sync_target = IcalCalendarSyncTarget.objects.get()
        self.assertEqual(sync_target.url, "https://www.zam.haus/?mec-ical-feed=1")
        self.assertEqual(sync_target.name, "https://www.zam.haus/?mec-ical-feed=1")

        self.assertEqual(IcalCalenderSyncItem.objects.count(), 3)
        for item in IcalCalenderSyncItem.objects.all():
            self.assertEqual(item.sync_target, sync_target)
            self.assertIsNotNone(item.related_event)
            self.assertIn(b"BEGIN:VEVENT", item.ical_definition.encode())
            self.assertIn(item.related_event.series.name, item.ical_definition)

    def test_import_ical_task_no_duplicates_on_rerun(self):
        """Test that running the task again doesn't create duplicate events."""
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

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = calendar_content
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                import_ical_task()

        initial_count = IcalCalenderSyncItem.objects.count()
        self.assertEqual(initial_count, 4)

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = calendar_content
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                import_ical_task()

        self.assertEqual(IcalCalenderSyncItem.objects.count(), initial_count)

    def test_import_ical_task_updates_sync_items_on_reimport(self):
        """Test that re-importing the same event updates the sync item."""
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

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = calendar_content
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                import_ical_task()

        sync_items_count = IcalCalenderSyncItem.objects.count()
        self.assertEqual(sync_items_count, 1)

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = calendar_content
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                import_ical_task()

        self.assertEqual(IcalCalenderSyncItem.objects.count(), sync_items_count)

    def test_import_ical_task_handles_fetch_error(self):
        """Test that the task handles HTTP errors gracefully."""
        from requests import RequestException

        with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
            mock_get.side_effect = RequestException("Network error")

            with self.assertLogs("sync_ical.tasks", level="INFO"):
                import_ical_task()

            self.assertEqual(Event.objects.count(), 0)
            self.assertEqual(Series.objects.count(), 0)

    def test_import_ical_task_preserves_sync_items_on_error(self):
        """Test that existing sync items are preserved when calendar fetch fails."""
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

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = initial_calendar
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                import_ical_task()

        initial_sync_count = IcalCalenderSyncItem.objects.count()
        self.assertEqual(initial_sync_count, 1)

        from requests import RequestException
        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_get.side_effect = RequestException("Network error")

                import_ical_task()

        self.assertEqual(IcalCalenderSyncItem.objects.count(), initial_sync_count)

    def test_command_clear_flag_clears_data_before_import(self):
        """Test that --clear flag removes all existing data before importing."""
        initial_calendar = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:initial-event@example.com
SUMMARY:Initial Event
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
END:VEVENT
END:VCALENDAR
"""

        new_calendar = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:new-event@example.com
SUMMARY:New Event
DTSTART;VALUE=DATE:20260401
DTEND;VALUE=DATE:20260402
END:VEVENT
END:VCALENDAR
"""

        fixed_now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

        # First import without clear
        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = initial_calendar
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                from django.core.management import call_command
                call_command("import_ical", clear=False)

        self.assertEqual(Series.objects.count(), 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(IcalCalendarSyncTarget.objects.count(), 1)
        initial_series_id = Series.objects.first().id

        # Import with clear - should delete old data and create new
        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = new_calendar
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                from django.core.management import call_command
                call_command("import_ical", clear=True)

        self.assertEqual(Series.objects.count(), 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(IcalCalenderSyncItem.objects.count(), 1)
        self.assertNotEqual(Series.objects.first().id, initial_series_id)
        self.assertEqual(Series.objects.first().name, "New Event")

    def test_command_clear_flag_emits_warning(self):
        """Test that --clear flag shows clearing warning message."""
        calendar_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:warning-test@example.com
SUMMARY:Warning Test
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
END:VEVENT
END:VCALENDAR
"""

        fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = calendar_content
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                from django.core.management import call_command
                output = StringIO()
                with patch("sys.stdout", output):
                    call_command("import_ical", clear=True)

                output_str = output.getvalue()
                self.assertIn("Clearing existing series and events", output_str)
                self.assertIn("Cleared", output_str)

    def test_command_rollback_on_error_in_transaction(self):
        """Test that database rolls back cleanly on error within transaction."""
        valid_calendar = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:valid-event@example.com
SUMMARY:Valid Event
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260302
END:VEVENT
END:VCALENDAR
"""

        fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

        with patch(
            "sync_ical.management.commands.import_ical.django_timezone.now",
            return_value=fixed_now
        ):
            with patch("sync_ical.management.commands.import_ical.requests.get") as mock_get:
                mock_response = Mock()
                mock_response.text = valid_calendar
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                import sys
                from io import StringIO
                output = StringIO()
                
                with patch("sys.stdout", output):
                    from django.core.management import call_command
                    call_command("import_ical", clear=True)

                self.assertEqual(Series.objects.count(), 1)
                self.assertEqual(Event.objects.count(), 1)
