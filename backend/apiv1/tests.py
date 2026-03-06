from datetime import date, datetime, timezone
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apiv1.management.commands.import_ical import parse_calendar_data
from apiv1.models import (
    Event,
    Proposal,
    ProposalArea,
    ProposalLanguage,
    ProposalSpeaker,
    Series,
    Speaker,
    SubmissionType,
)


class ProposalModelTests(TestCase):
    def setUp(self):
        self.submission_type = SubmissionType.objects.create(code='workshop', label='Workshop')
        self.language = ProposalLanguage.objects.create(code='en', label='English')
        self.area = ProposalArea.objects.create(code='metal', label='Metal Workshop')

    def _create_proposal(self, **overrides):
        payload = {
            'title': 'Metal Basics',
            'submission_type': self.submission_type,
            'language': self.language,
            'area': self.area,
            'abstract': 'A' * 50,
            'description': 'B' * 120,
            'occurrence_count': 1,
            'photo': SimpleUploadedFile('proposal.png', b'img', content_type='image/png'),
            'duration_minutes': 120,
            'max_participants': 10,
            'material_cost_eur': '3.50',
            'preferred_dates': '2026-05-10 10:00, 2026-05-24 10:00',
        }
        payload.update(overrides)
        return Proposal.objects.create(**payload)

    def test_event_ownership_and_editors_stay_auth_based(self):
        user_model = get_user_model()
        self.assertIs(Event._meta.get_field('owner').remote_field.model, user_model)
        self.assertIs(Proposal._meta.get_field('editors').remote_field.model, user_model)

    def test_speaker_biography_min_length_is_validated(self):
        speaker = Speaker(email='person@example.com', display_name='Person', biography='too short')
        with self.assertRaises(ValidationError):
            speaker.full_clean()

    def test_only_one_primary_speaker_per_proposal(self):
        proposal = self._create_proposal()
        primary = Speaker.objects.create(
            email='primary@example.com',
            display_name='Primary',
            biography='P' * 60,
        )
        second = Speaker.objects.create(
            email='second@example.com',
            display_name='Second',
            biography='S' * 60,
        )

        ProposalSpeaker.objects.create(
            proposal=proposal,
            speaker=primary,
            role=ProposalSpeaker.Role.PRIMARY,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProposalSpeaker.objects.create(
                    proposal=proposal,
                    speaker=second,
                    role=ProposalSpeaker.Role.PRIMARY,
                )


class ImportIcalTests(TestCase):
    def test_parse_calendar_data_expands_rrule_within_requested_window(self):
        ics_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Recurring//EN
BEGIN:VEVENT
UID:recurring-1@example.com
SUMMARY:Recurring Workshop
DTSTART;VALUE=DATE:20251230
DTEND;VALUE=DATE:20251231
RRULE:FREQ=DAILY;COUNT=10
END:VEVENT
END:VCALENDAR
"""

        events = parse_calendar_data(
            ics_content,
            window_start=date(2026, 1, 1),
            window_end=date(2026, 1, 4),
        )

        self.assertEqual(
            [event["dtstart"].date() for event in events],
            [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        )
        self.assertTrue(all(event["summary"] == "Recurring Workshop" for event in events))

    def test_import_command_limits_recurring_events_to_one_year_past_and_future(self):
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

        with NamedTemporaryFile("w", suffix=".ics", encoding="utf-8") as calendar_file:
            calendar_file.write(ics_content)
            calendar_file.flush()

            with patch("apiv1.management.commands.import_ical.django_timezone.now", return_value=fixed_now):
                call_command("import_ical", file=calendar_file.name)

        series = Series.objects.get(name="Recurring Import")
        imported_events = list(series.events.order_by("start_time"))

        self.assertTrue(imported_events)
        self.assertEqual(imported_events[0].start_time.date(), date(2025, 3, 10))
        self.assertEqual(imported_events[-1].start_time.date(), date(2027, 3, 10))
        self.assertTrue(all(event.tag == "community" for event in imported_events))
        self.assertEqual(series.description, "Recurring import description")
