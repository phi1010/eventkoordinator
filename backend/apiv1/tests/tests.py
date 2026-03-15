from pathlib import Path
from datetime import date, datetime, timezone
import time
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from sync_ical.management.commands.import_ical import parse_calendar_data
from apiv1.models import (
    Event,
    Proposal,
    ProposalArea,
    ProposalLanguage,
    Series,
    Speaker,
    SubmissionType,
)


class ProposalModelTests(TestCase):
    def setUp(self):
        self.submission_type, _ = SubmissionType.objects.get_or_create(
            code='workshop',
            defaults={'label': 'Workshop'},
        )
        self.language, _ = ProposalLanguage.objects.get_or_create(
            code='en',
            defaults={'label': 'English'},
        )
        self.area, _ = ProposalArea.objects.get_or_create(
            code='metal',
            defaults={'label': 'Metal Workshop'},
        )

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
            'duration_days': 1,
            'duration_time_per_day': '02:00',
            'max_participants': 10,
            'material_cost_eur': '3.50',
            'preferred_dates': '2026-05-10 10:00, 2026-05-24 10:00',
        }
        payload.update(overrides)
        return Proposal.objects.create(**payload)

    def test_event_ownership_and_editors_stay_auth_based(self):
        user_model = get_user_model()
        self.assertIs(Proposal._meta.get_field('owner').remote_field.model, user_model)
        self.assertIs(Proposal._meta.get_field('editors').remote_field.model, user_model)

    def test_speaker_biography_min_length_is_validated(self):
        proposal = self._create_proposal()
        speaker = Speaker(proposal=proposal, email='person@example.com', display_name='Person', biography='too short')
        with self.assertRaises(ValidationError):
            speaker.full_clean()

    def test_speaker_belongs_to_exactly_one_proposal(self):
        proposal = self._create_proposal()
        speaker = Speaker.objects.create(
            proposal=proposal,
            email='speaker@example.com',
            display_name='Test Speaker',
            biography='B' * 60,
        )
        self.assertEqual(speaker.proposal, proposal)
        self.assertIn(speaker, proposal.speakers.all())

    def test_speaker_email_can_be_empty(self):
        proposal = self._create_proposal()
        speaker = Speaker(proposal=proposal, display_name='No Email', biography='B' * 60, email='')
        speaker.full_clean()  # Should not raise
        speaker.save()
        self.assertEqual(speaker.email, '')

    def test_multiple_speakers_can_share_same_email(self):
        proposal1 = self._create_proposal()
        proposal2 = self._create_proposal(title='Second Proposal')
        Speaker.objects.create(proposal=proposal1, email='shared@example.com', display_name='Speaker 1', biography='B' * 60)
        Speaker.objects.create(proposal=proposal2, email='shared@example.com', display_name='Speaker 2', biography='B' * 60)
        # No IntegrityError expected

    def test_proposal_photo_filename_uses_uuid_and_preserves_extension(self):
        with TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                proposal = self._create_proposal(
                    photo=SimpleUploadedFile(
                        "My Summer Photo.PNG",
                        b"img",
                        content_type="image/png",
                    )
                )

        self.assertTrue(proposal.photo.name.startswith("proposal_photos/"))
        filename = Path(proposal.photo.name).name
        UUID(Path(filename).stem)
        self.assertEqual(Path(filename).suffix, ".png")

    def test_speaker_profile_picture_filename_uses_uuid_and_preserves_extension(self):
        with TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                proposal = self._create_proposal()
                speaker = Speaker.objects.create(
                    proposal=proposal,
                    email="photo-speaker@example.com",
                    display_name="Photo Speaker",
                    biography="B" * 60,
                    profile_picture=SimpleUploadedFile(
                        "avatar.JpEg",
                        b"img",
                        content_type="image/jpeg",
                    ),
                )

        self.assertTrue(speaker.profile_picture.name.startswith("speaker_profiles/"))
        filename = Path(speaker.profile_picture.name).name
        UUID(Path(filename).stem)
        self.assertEqual(Path(filename).suffix, ".jpeg")

    def test_photo_validator_allows_png_jpg_jpeg(self):
        field = Proposal._meta.get_field("photo")

        field.run_validators(SimpleUploadedFile("allowed.png", b"img", content_type="image/png"))
        field.run_validators(SimpleUploadedFile("allowed.jpg", b"img", content_type="image/jpeg"))
        field.run_validators(SimpleUploadedFile("allowed.jpeg", b"img", content_type="image/jpeg"))

    def test_photo_validator_rejects_svg(self):
        field = Proposal._meta.get_field("photo")

        with self.assertRaises(ValidationError):
            field.run_validators(
                SimpleUploadedFile(
                    "blocked.svg",
                    b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                    content_type="image/svg+xml",
                )
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

            with patch("sync_ical.management.commands.import_ical.django_timezone.now", return_value=fixed_now):
                call_command("import_ical", file=calendar_file.name)

        series = Series.objects.get(name="Recurring Import")
        imported_events = list(series.events.order_by("start_time"))

        self.assertTrue(imported_events)
        self.assertEqual(imported_events[0].start_time.date(), date(2025, 3, 10))
        self.assertEqual(imported_events[-1].start_time.date(), date(2027, 3, 10))
        self.assertTrue(all(event.tag == "community" for event in imported_events))
        self.assertEqual(series.description, "Recurring import description")


class EventApprovalPermissionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="event-owner",
            password="pw",
            email="event-owner@example.com",
        )
        self.editor = user_model.objects.create_user(
            username="event-editor",
            password="pw",
            email="event-editor@example.com",
        )
        self.other_user = user_model.objects.create_user(
            username="event-other",
            password="pw",
            email="event-other@example.com",
        )

        self.approve_perm = Permission.objects.get(codename="approve_event")
        self.reject_perm = Permission.objects.get(codename="reject_event")

        submission_type, _ = SubmissionType.objects.get_or_create(
            code="workshop",
            defaults={"label": "Workshop"},
        )
        language, _ = ProposalLanguage.objects.get_or_create(
            code="en",
            defaults={"label": "English"},
        )
        area, _ = ProposalArea.objects.get_or_create(
            code="metal",
            defaults={"label": "Metal Workshop"},
        )

        self.proposal = Proposal.objects.create(
            owner=self.owner,
            title="Linked proposal",
            submission_type=submission_type,
            language=language,
            area=area,
            abstract="A" * 50,
            description="B" * 120,
            occurrence_count=1,
            photo=SimpleUploadedFile("proposal.png", b"img", content_type="image/png"),
            duration_days=1,
            duration_time_per_day="02:00",
            max_participants=10,
            material_cost_eur="3.50",
            preferred_dates="2026-05-10 10:00, 2026-05-24 10:00",
        )
        self.proposal.editors.add(self.editor)

        self.series = Series.objects.create(name="Permission series")
        self.event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Proposal-linked event",
            start_time=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.PROPOSED,
        )

    def test_owner_needs_no_global_approve_permission(self):
        self.assertTrue(self.event.has_object_permission(self.owner, "apiv1.approve_event"))
        self.owner.user_permissions.add(self.approve_perm)
        owner = get_user_model().objects.get(pk=self.owner.pk)
        self.assertTrue(self.event.has_object_permission(owner, "apiv1.approve_event"))

    def test_editor_needs_no_global_reject_permission(self):
        self.assertTrue(self.event.has_object_permission(self.editor, "apiv1.reject_event"))
        self.editor.user_permissions.add(self.reject_perm)
        editor = get_user_model().objects.get(pk=self.editor.pk)
        self.assertTrue(self.event.has_object_permission(editor, "apiv1.reject_event"))

    def test_non_owner_non_editor_denied_even_with_global_permission(self):
        self.other_user.user_permissions.add(self.approve_perm)
        other_user = get_user_model().objects.get(pk=self.other_user.pk)
        self.assertFalse(self.event.has_object_permission(other_user, "apiv1.approve_event"))


class EventViewObjectPermissionTests(TestCase):
    """Tests for the view_event object permission on the Event model."""

    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="view-event-owner",
            password="pw",
            email="view-event-owner@example.com",
        )
        self.editor = user_model.objects.create_user(
            username="view-event-editor",
            password="pw",
            email="view-event-editor@example.com",
        )
        self.unrelated_user = user_model.objects.create_user(
            username="view-event-unrelated",
            password="pw",
            email="view-event-unrelated@example.com",
        )

        submission_type, _ = SubmissionType.objects.get_or_create(
            code="workshop",
            defaults={"label": "Workshop"},
        )
        language, _ = ProposalLanguage.objects.get_or_create(
            code="en",
            defaults={"label": "English"},
        )
        area, _ = ProposalArea.objects.get_or_create(
            code="metal",
            defaults={"label": "Metal Workshop"},
        )

        self.proposal = Proposal.objects.create(
            owner=self.owner,
            title="Linked proposal",
            submission_type=submission_type,
            language=language,
            area=area,
            abstract="A" * 50,
            description="B" * 120,
            occurrence_count=1,
            photo=SimpleUploadedFile("proposal.png", b"img", content_type="image/png"),
            duration_days=1,
            duration_time_per_day="02:00",
            max_participants=10,
            material_cost_eur="3.50",
            preferred_dates="2026-05-10 10:00",
        )
        self.proposal.editors.add(self.editor)

        self.series = Series.objects.create(name="View permission series")
        self.proposed_event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Proposed event",
            start_time=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.PROPOSED,
        )
        self.draft_event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Draft event",
            start_time=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.DRAFT,
        )
        self.unlinked_event = Event.objects.create(
            series=self.series,
            proposal=None,
            name="Unlinked event",
            start_time=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.PROPOSED,
        )

    def test_proposal_owner_can_view_non_draft_linked_event(self):
        self.assertTrue(
            self.proposed_event.has_object_permission(self.owner, "apiv1.view_event")
        )

    def test_proposal_editor_can_view_non_draft_linked_event(self):
        self.assertTrue(
            self.proposed_event.has_object_permission(self.editor, "apiv1.view_event")
        )

    def test_unrelated_user_cannot_view_non_draft_linked_event(self):
        self.assertFalse(
            self.proposed_event.has_object_permission(self.unrelated_user, "apiv1.view_event")
        )

    def test_draft_event_is_not_viewable_even_for_proposal_owner(self):
        self.assertFalse(
            self.draft_event.has_object_permission(self.owner, "apiv1.view_event")
        )

    def test_draft_event_is_not_viewable_for_proposal_editor(self):
        self.assertFalse(
            self.draft_event.has_object_permission(self.editor, "apiv1.view_event")
        )

    def test_event_without_proposal_is_not_viewable(self):
        self.assertFalse(
            self.unlinked_event.has_object_permission(self.owner, "apiv1.view_event")
        )

    def test_planned_event_is_viewable_by_owner(self):
        self.proposed_event.status = Event.Status.PLANNED
        self.proposed_event.save(update_fields=["status"])
        self.assertTrue(
            self.proposed_event.has_object_permission(self.owner, "apiv1.view_event")
        )

    def test_published_event_is_viewable_by_editor(self):
        self.proposed_event.status = Event.Status.PUBLISHED
        self.proposed_event.save(update_fields=["status"])
        self.assertTrue(
            self.proposed_event.has_object_permission(self.editor, "apiv1.view_event")
        )


class EventChangeObjectPermissionTests(TestCase):
    """Tests for the change_event object permission and update API."""

    def setUp(self):
        user_model = get_user_model()
        self.global_event_editor = user_model.objects.create_user(
            username="event-change-global-editor",
            password="pw",
            email="event-change-global-editor@example.com",
        )
        self.series_editor = user_model.objects.create_user(
            username="event-change-series-editor",
            password="pw",
            email="event-change-series-editor@example.com",
        )
        self.unprivileged_user = user_model.objects.create_user(
            username="event-change-unprivileged",
            password="pw",
            email="event-change-unprivileged@example.com",
        )

        self.global_event_editor.user_permissions.add(
            Permission.objects.get(codename="change_event")
        )
        self.series_editor.user_permissions.add(
            Permission.objects.get(codename="change_series")
        )

        self.series = Series.objects.create(name="Event change permission series")
        self.event = Event.objects.create(
            series=self.series,
            name="Editable event",
            start_time=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["oidc_id_token_expiration"] = time.time() + 3600
        session.save()

    def test_global_change_event_grants_change_event_object_permission(self):
        editor = get_user_model().objects.get(pk=self.global_event_editor.pk)
        self.assertTrue(
            self.event.has_object_permission(editor, "apiv1.change_event")
        )

    def test_change_series_grants_change_event_object_permission(self):
        editor = get_user_model().objects.get(pk=self.series_editor.pk)
        self.assertTrue(
            self.event.has_object_permission(editor, "apiv1.change_event")
        )

    def test_unprivileged_user_cannot_change_event_object(self):
        self.assertFalse(
            self.event.has_object_permission(self.unprivileged_user, "apiv1.change_event")
        )

    def test_update_event_api_allows_series_editor_without_global_change_event(self):
        self._login(self.series_editor)
        response = self.client.put(
            f"/api/v1/series/{self.series.id}/events/{self.event.id}",
            data='{"name": "Updated by series editor"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.name, "Updated by series editor")

    def test_update_event_api_denies_unprivileged_user(self):
        self._login(self.unprivileged_user)
        response = self.client.put(
            f"/api/v1/series/{self.series.id}/events/{self.event.id}",
            data='{"name": "Should fail"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class SeriesViewObjectPermissionTests(TestCase):
    """Tests for the view_series object permission on the Series model."""

    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="series-view-owner",
            password="pw",
            email="series-view-owner@example.com",
        )
        self.editor = user_model.objects.create_user(
            username="series-view-editor",
            password="pw",
            email="series-view-editor@example.com",
        )
        self.unrelated = user_model.objects.create_user(
            username="series-view-unrelated",
            password="pw",
            email="series-view-unrelated@example.com",
        )
        self.global_viewer = user_model.objects.create_user(
            username="series-view-global",
            password="pw",
            email="series-view-global@example.com",
        )
        self.global_viewer.user_permissions.add(
            Permission.objects.get(codename="view_series")
        )
        # Reload to clear permission cache
        self.global_viewer = user_model.objects.get(pk=self.global_viewer.pk)

        submission_type, _ = SubmissionType.objects.get_or_create(
            code="workshop", defaults={"label": "Workshop"}
        )
        language, _ = ProposalLanguage.objects.get_or_create(
            code="en", defaults={"label": "English"}
        )
        area, _ = ProposalArea.objects.get_or_create(
            code="metal", defaults={"label": "Metal Workshop"}
        )

        self.proposal = Proposal.objects.create(
            owner=self.owner,
            title="Test proposal",
            submission_type=submission_type,
            language=language,
            area=area,
            abstract="A" * 50,
            description="B" * 120,
            occurrence_count=1,
            photo=SimpleUploadedFile("p.png", b"img", content_type="image/png"),
            duration_days=1,
            duration_time_per_day="02:00",
            max_participants=10,
            material_cost_eur="0.00",
            preferred_dates="2026-07-01",
        )
        self.proposal.editors.add(self.editor)

        self.series = Series.objects.create(name="Permission test series")
        self.empty_series = Series.objects.create(name="Empty series")

        self.proposed_event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Proposed event",
            start_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.PROPOSED,
        )
        self.draft_event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Draft event",
            start_time=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.DRAFT,
        )

    # --- object permission unit tests ---

    def test_global_viewer_can_view_any_series(self):
        self.assertTrue(
            self.series.has_object_permission(self.global_viewer, "apiv1.view_series")
        )
        self.assertTrue(
            self.empty_series.has_object_permission(self.global_viewer, "apiv1.view_series")
        )

    def test_proposal_owner_can_view_series_with_non_draft_event(self):
        self.assertTrue(
            self.series.has_object_permission(self.owner, "apiv1.view_series")
        )

    def test_proposal_editor_can_view_series_with_non_draft_event(self):
        self.assertTrue(
            self.series.has_object_permission(self.editor, "apiv1.view_series")
        )

    def test_unrelated_user_cannot_view_series(self):
        self.assertFalse(
            self.series.has_object_permission(self.unrelated, "apiv1.view_series")
        )

    def test_owner_cannot_view_series_with_only_draft_events(self):
        # Remove the proposed event so only the draft event remains
        self.proposed_event.delete()
        self.assertFalse(
            self.series.has_object_permission(self.owner, "apiv1.view_series")
        )

    def test_owner_cannot_view_empty_series_without_global_perm(self):
        self.assertFalse(
            self.empty_series.has_object_permission(self.owner, "apiv1.view_series")
        )

    def test_change_series_delegates_to_global_permission(self):
        """change_series object permission mirrors global permission."""
        self.assertFalse(
            self.series.has_object_permission(self.owner, "apiv1.change_series")
        )
        self.owner.user_permissions.add(Permission.objects.get(codename="change_series"))
        owner = get_user_model().objects.get(pk=self.owner.pk)
        self.assertTrue(
            self.series.has_object_permission(owner, "apiv1.change_series")
        )

    # --- endpoint integration tests ---

    def _login(self, user):
        """Log in and set a valid OIDC session expiry so SessionRefresh does not redirect."""
        self.client.force_login(user)
        session = self.client.session
        session["oidc_id_token_expiration"] = time.time() + 3600
        session.save()

    def test_get_series_list_returns_series_for_proposal_owner(self):
        self._login(self.owner)
        response = self.client.get("/api/v1/series")
        self.assertEqual(response.status_code, 200)
        ids = [s["id"] for s in response.json()]
        self.assertIn(str(self.series.id), ids)
        # Empty series not visible without global perm
        self.assertNotIn(str(self.empty_series.id), ids)

    def test_get_series_list_hides_series_for_unrelated_user(self):
        self._login(self.unrelated)
        response = self.client.get("/api/v1/series")
        self.assertEqual(response.status_code, 200)
        ids = [s["id"] for s in response.json()]
        self.assertNotIn(str(self.series.id), ids)

    def test_get_series_list_requires_authentication(self):
        response = self.client.get("/api/v1/series")
        self.assertEqual(response.status_code, 401)

    def test_get_one_series_accessible_for_proposal_owner(self):
        self._login(self.owner)
        response = self.client.get(f"/api/v1/series/{self.series.id}")
        self.assertEqual(response.status_code, 200)

    def test_get_one_series_denied_for_unrelated_user(self):
        self._login(self.unrelated)
        response = self.client.get(f"/api/v1/series/{self.series.id}")
        self.assertEqual(response.status_code, 401)

    def test_get_one_series_accessible_for_global_viewer(self):
        self._login(self.global_viewer)
        response = self.client.get(f"/api/v1/series/{self.series.id}")
        self.assertEqual(response.status_code, 200)


class SeriesCreateEventPermissionTests(TestCase):
    """Tests that creating an event in a series requires the change_series object permission."""

    def setUp(self):
        user_model = get_user_model()
        self.user_with_perm = user_model.objects.create_user(
            username="create-event-perm",
            password="pw",
            email="create-event-perm@example.com",
        )
        self.user_without_series_perm = user_model.objects.create_user(
            username="create-event-noperm",
            password="pw",
            email="create-event-noperm@example.com",
        )

        self.user_with_perm.user_permissions.add(
            Permission.objects.get(codename="add_event"),
            Permission.objects.get(codename="change_series"),
        )
        self.user_without_series_perm.user_permissions.add(
            Permission.objects.get(codename="add_event"),
        )

        self.series = Series.objects.create(name="Create-event test series")

    def _create_event_payload(self):
        import json
        return json.dumps({
            "name": "New event",
            "startTime": "2026-09-01T10:00:00",
            "endTime": "2026-09-01T12:00:00",
        })

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["oidc_id_token_expiration"] = time.time() + 3600
        session.save()

    def test_user_with_change_series_can_create_event(self):
        self._login(self.user_with_perm)
        response = self.client.post(
            f"/api/v1/series/{self.series.id}/events/create",
            data=self._create_event_payload(),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

    def test_user_without_change_series_cannot_create_event(self):
        self._login(self.user_without_series_perm)
        response = self.client.post(
            f"/api/v1/series/{self.series.id}/events/create",
            data=self._create_event_payload(),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


