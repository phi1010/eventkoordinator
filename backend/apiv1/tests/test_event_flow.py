"""Unit tests for EventFlow.approve() auto-publish behaviour.

The approve() transition moves an event from PROPOSED → PLANNED and then
immediately publishes it (PLANNED → PUBLISHED) when no active events overlap
any of its time blocks.  These tests verify that logic for:
  - single-day events with and without conflicts
  - full-day (use_full_days=True) events
  - multi-day non-full-day events (per-day blocks)
  - events that share only adjacent (touching) time slots (no overlap)
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.test import TestCase

from apiv1.flows import EventFlow
from apiv1.models import Event, Series


class EventFlowApproveAutoPublishTest(TestCase):
    """EventFlow.approve() auto-publishes iff no active events overlap."""

    def setUp(self) -> None:
        self.series = Series.objects.create(name="Flow Test Series")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_event(
        self,
        start: datetime,
        end: datetime,
        *,
        status: str = Event.Status.PROPOSED,
        use_full_days: bool = False,
        name: str = "Test Event",
    ) -> Event:
        return Event.objects.create(
            series=self.series,
            name=name,
            start_time=start,
            end_time=end,
            status=status,
            use_full_days=use_full_days,
        )

    # ------------------------------------------------------------------
    # single-day events
    # ------------------------------------------------------------------

    def test_approve_no_conflicts_auto_publishes(self) -> None:
        """Single-day event with no other active events is auto-published."""
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_approve_with_overlapping_published_event_stays_planned(self) -> None:
        """Overlapping published event prevents auto-publish; stays PLANNED."""
        self._make_event(
            start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc),
            status=Event.Status.PUBLISHED,
            name="Blocker",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PLANNED)

    def test_approve_with_overlapping_confirmed_event_stays_planned(self) -> None:
        """Overlapping confirmed event prevents auto-publish; stays PLANNED."""
        self._make_event(
            start=datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc),
            status=Event.Status.CONFIRMED,
            name="Confirmed Blocker",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PLANNED)

    def test_approve_with_overlapping_planned_event_stays_planned(self) -> None:
        """Overlapping planned event prevents auto-publish; stays PLANNED."""
        self._make_event(
            start=datetime(2026, 6, 1, 10, 30, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc),
            status=Event.Status.PLANNED,
            name="Planned Blocker",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PLANNED)

    def test_approve_with_non_overlapping_event_auto_publishes(self) -> None:
        """Published event on a different day does not block auto-publish."""
        self._make_event(
            start=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.PUBLISHED,
            name="Other Day",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_approve_touching_events_are_not_considered_overlapping(self) -> None:
        """An event ending exactly when the new one starts does not block it."""
        self._make_event(
            start=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            status=Event.Status.PUBLISHED,
            name="Earlier",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_approve_archived_or_canceled_events_do_not_block(self) -> None:
        """Events in non-active statuses (canceled, archived) do not block publish."""
        self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.CANCELED,
            name="Canceled",
        )
        self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.ARCHIVED,
            name="Archived",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    # ------------------------------------------------------------------
    # full-day (use_full_days=True) events
    # ------------------------------------------------------------------

    def test_approve_full_day_event_no_conflict_auto_publishes(self) -> None:
        """Full-day event with no conflicts is auto-published."""
        event = self._make_event(
            start=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc),
            use_full_days=True,
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_approve_full_day_event_with_conflict_stays_planned(self) -> None:
        """Full-day event overlapping an active event stays PLANNED."""
        self._make_event(
            start=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc),
            status=Event.Status.PUBLISHED,
            name="Blocker inside full-day span",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc),
            use_full_days=True,
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PLANNED)

    # ------------------------------------------------------------------
    # multi-day non-full-day events (per-day blocks)
    # ------------------------------------------------------------------

    def test_approve_multiday_event_no_conflict_auto_publishes(self) -> None:
        """Multi-day non-full-day event with no per-day block conflicts auto-publishes."""
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 3, 18, 0, tzinfo=timezone.utc),
            use_full_days=False,
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_approve_multiday_event_conflict_on_middle_day_stays_planned(self) -> None:
        """Conflict on the second day of a multi-day block event keeps it PLANNED."""
        # This event overlaps day 2's block (2026-06-02 10:00–18:00)
        self._make_event(
            start=datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
            status=Event.Status.PUBLISHED,
            name="Day-2 blocker",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 3, 18, 0, tzinfo=timezone.utc),
            use_full_days=False,
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PLANNED)

    def test_approve_multiday_event_conflict_outside_blocks_auto_publishes(self) -> None:
        """Conflict outside the daily block windows does not block auto-publish.

        The multi-day event has daily blocks 10:00–18:00.  A conflict at 20:00–22:00
        (outside the blocks) must NOT prevent auto-publish.
        """
        self._make_event(
            start=datetime(2026, 6, 2, 20, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc),
            status=Event.Status.PUBLISHED,
            name="Night event (outside blocks)",
        )
        event = self._make_event(
            start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 3, 18, 0, tzinfo=timezone.utc),
            use_full_days=False,
        )
        EventFlow(event).approve()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

