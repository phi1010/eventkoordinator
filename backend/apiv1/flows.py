import logging
import textwrap
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from viewflow import fsm
from viewflow.fsm.base import Transition

import apiv1
from apiv1.models import Event, Proposal, check_proposal_required_fields
from openid_user_management.models import OpenIDUser

logger = logging.getLogger(__name__)


class ProposalTransition:
    """Data class representing an available or unavailable transition."""

    def __init__(
        self,
        action: str,
        label: str,
        target_status: str,
        enabled: bool,
        disable_reason: str | None = None,
    ):
        self.action = action
        self.label = label
        self.target_status = target_status
        self.enabled = enabled
        self.disable_reason = disable_reason

    def to_dict(self):
        return {
            "action": self.action,
            "label": self.label,
            "target_status": self.target_status,
            "enabled": self.enabled,
            "disable_reason": self.disable_reason,
        }


class ProposalFlow:
    status = fsm.State(Proposal.status, default=Proposal.Status.DRAFT)

    def has_permission(*perms):
        def permission_handler(self: object, user: Any) -> bool | None:
            if not isinstance(user, OpenIDUser):
                logger.warning(
                    f"Permission check failed: user {user!r} is not an OpenIDUser"
                )
                return False
            if not isinstance(self, ProposalFlow):
                logger.warning(
                    f"Permission check failed: object {self!r} is not a ProposalFlow instance"
                )
                return False
            proposal = self.object
            for perm in perms:
                if not user.has_perm(perm, proposal):
                    logger.debug(
                        f"Permission check failed: user {user.username!r} does not have all of the required permissions {perms} for proposal {proposal.pk}"
                    )
                    return False
            logger.debug(
                f"Permission check passed: user {user.username!r} has all of the required permissions {perms} for proposal {proposal.pk}"
            )
            return True

        return permission_handler

    def has_required_information(self: object) -> bool:
        if not isinstance(self, ProposalFlow):
            logger.warning(
                f"Condition check failed: object {self!r} is not a ProposalFlow instance"
            )
            return False
        proposal = self.object
        return all(
            (
                status["status"] == "ok"
                for status in check_proposal_required_fields(proposal).values()
            )
        )

    def __init__(self, object: Proposal):
        self.object = object

    @status.setter()
    def _set_object_status(self, value):
        logging.debug(f"Setting object status: {value}")
        self.object.status = value

    @status.getter()
    def _get_object_status(self):
        logging.debug(f"Getting object status: {self}")
        return self.object.status

    @status.transition(
        source=Proposal.Status.DRAFT,
        target=Proposal.Status.SUBMITTED,
        label="Submit proposal",
        conditions=[has_required_information],
        permission=has_permission((apiv1, "submit", Proposal)),
    )
    @status.transition(
        source=Proposal.Status.REVISE,
        target=Proposal.Status.SUBMITTED,
        label="Resubmit proposal",
        conditions=[has_required_information],
        permission=has_permission((apiv1, "submit", Proposal)),
    )
    def submit(self):
        logger.info(f"Submitting proposal: {self.object!r}")
        self.object.save()

    @status.transition(
        source=Proposal.Status.SUBMITTED,
        target=Proposal.Status.REVISE,
        label="Request revision",
        permission=has_permission((apiv1, "revise", Proposal)),
    )
    @status.transition(
        source=Proposal.Status.REJECTED,
        target=Proposal.Status.REVISE,
        label="Allow revision after rejection",
        permission=has_permission((apiv1, "revise", Proposal)),
    )
    def revise(self):
        logger.info(f"Revising proposal: {self.object}")
        try:
            send_mail(
                subject=f"Revision requested for your proposal: {self.object.title}",
                message=render_to_string(
                    "apiv1/mails/revise.txt.j2", dict(object=self.object)
                ),
                html_message=render_to_string(
                    "apiv1/mails/revise.html.j2", dict(object=self.object)
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.object.owner.email],
                fail_silently=False,
            )
        except BaseException as e:
            logger.error("Failed to send message: " + str(e), exc_info=e)
            raise
        self.object.save()

    @status.transition(
        source=Proposal.Status.SUBMITTED,
        target=Proposal.Status.ACCEPTED,
        label="Accept proposal",
        permission=has_permission((apiv1, "accept", Proposal)),
    )
    def accept(self):
        logger.info(f"Accepting proposal: {self.object}")
        self.object.save()

    @status.transition(
        source=Proposal.Status.SUBMITTED,
        target=Proposal.Status.REJECTED,
        label="Reject proposal",
        permission=has_permission((apiv1, "reject", Proposal)),
    )
    def reject(self):
        logger.info(f"Rejecting proposal: {self.object}")
        self.object.save()

    def get_available_transitions(self, user: OpenIDUser) -> list[ProposalTransition]:
        """
        Get all available transitions for this proposal and user.
        Returns a list of ProposalTransition objects with enable/disable reasons.
        Uses the FSM's transition metadata from the state machine definition.
        """
        transitions_list = []

        # Get all transition methods from the class
        transition_methods = [
            ("submit", self.submit),
            ("revise", self.revise),
            ("accept", self.accept),
            ("reject", self.reject),
        ]

        for action, method in transition_methods:
            # Get the actual transition objects from the method descriptor
            try:
                all_transitions = method.get_transitions()
                # Filter to transitions that apply from the current status
                for transition in all_transitions:
                    if transition.source == self.object.status:
                        result = self._evaluate_transition(transition, action, user)
                        transitions_list.append(result)
                        break  # Found the transition for this action from current state
            except Exception as e:
                logger.error(f"Error getting transitions for {action}: {str(e)}")

        return transitions_list

    def _evaluate_transition(
        self, transition: Transition, action: str, user: OpenIDUser
    ) -> ProposalTransition:
        """
        Evaluate a single transition to determine if it's allowed.
        Uses the FSM transition's conditions and permissions.
        """
        # Check conditions
        conditions_met = transition.conditions_met(self)
        if not conditions_met:
            if action == "submit":
                checklist = check_proposal_required_fields(self.object)
                missing_items = [
                    name for name, item in checklist.items() if item["status"] != "ok"
                ]
                missing_str = (
                    ", ".join(missing_items)
                    if missing_items
                    else "incomplete information"
                )
                return ProposalTransition(
                    action=action,
                    label=transition.label,
                    target_status=transition.target,
                    enabled=False,
                    disable_reason=f"Incomplete proposal: {missing_str}",
                )
            else:
                return ProposalTransition(
                    action=action,
                    label=transition.label,
                    target_status=transition.target,
                    enabled=False,
                    disable_reason="Conditions not met for this transition",
                )

        # Check permissions
        has_perm = transition.has_perm(self, user)
        if not has_perm:
            return ProposalTransition(
                action=action,
                label=transition.label,
                target_status=transition.target,
                enabled=False,
                disable_reason="Insufficient permissions for this action",
            )

        # All checks passed
        return ProposalTransition(
            action=action,
            label=transition.label,
            target_status=transition.target,
            enabled=True,
            disable_reason=None,
        )

    def execute_transition(self, action: str) -> bool:
        """
        Execute a transition action (submit, accept, reject, revise).
        Returns True if successful, False otherwise.
        """
        action_to_method = {
            "submit": self.submit,
            "accept": self.accept,
            "reject": self.reject,
            "revise": self.revise,
        }

        method = action_to_method.get(action)
        if not method:
            logger.error(f"Unknown transition action: {action}")
            return False

        try:
            method()
            return True
        except Exception as e:
            logger.error(f"Failed to execute transition {action}: {str(e)}")
            return False


class EventTransition:
    """Data class representing an available or unavailable event transition."""

    def __init__(
        self,
        action: str,
        label: str,
        target_status: str,
        enabled: bool,
        disable_reason: str | None = None,
    ):
        self.action = action
        self.label = label
        self.target_status = target_status
        self.enabled = enabled
        self.disable_reason = disable_reason

    def to_dict(self):
        return {
            "action": self.action,
            "label": self.label,
            "target_status": self.target_status,
            "enabled": self.enabled,
            "disable_reason": self.disable_reason,
        }


# Window within which a Published event may be confirmed (days before start_time).
CONFIRM_WINDOW_DAYS = 14


class EventFlow:
    """FSM flow for the Event lifecycle.

    State diagram:
        Draft → Proposed   : submit
        Proposed → Planned  : approve
        Proposed → Rejected : reject
        Planned → Published : publish
        Published → Confirmed : confirm  (≈1 week before event)
        Published → Canceled  : cancel
        Confirmed → Completed : complete (event date passed)
        Completed → Archived  : archive
        Canceled  → Archived  : archive
        Rejected  → Archived  : archive
    """

    status = fsm.State(Event.status, default=Event.Status.DRAFT)

    def has_permission(*perms):
        def permission_handler(self: object, user: Any) -> bool | None:
            if not isinstance(user, OpenIDUser):
                logger.warning(
                    f"Permission check failed: user {user!r} is not an OpenIDUser"
                )
                return False
            if not isinstance(self, EventFlow):
                logger.warning(
                    f"Permission check failed: object {self!r} is not an EventFlow instance"
                )
                return False
            event = self.object
            for perm in perms:
                if not user.has_perm(perm, event):
                    logger.debug(
                        f"Permission check failed: user {user.username!r} does not have all of "
                        f"the required permissions {perms} for event {event.pk}"
                    )
                    return False
            logger.debug(
                f"Permission check passed: user {user.username!r} has all of the required "
                f"permissions {perms} for event {event.pk}"
            )
            return True

        return permission_handler

    def _within_confirmation_window(self: object) -> bool:
        """Condition: event start_time is within CONFIRM_WINDOW_DAYS days from now."""
        if not isinstance(self, EventFlow):
            return False
        event = self.object
        now = timezone.now()
        return now <= event.start_time <= now + timedelta(days=CONFIRM_WINDOW_DAYS)

    def _event_has_passed(self: object) -> bool:
        """Condition: event end_time is in the past."""
        if not isinstance(self, EventFlow):
            return False
        event = self.object
        return timezone.now() >= event.end_time

    def __init__(self, object: Event):
        self.object = object

    @status.setter()
    def _set_object_status(self, value):
        logging.debug(f"Setting event status: {value}")
        self.object.status = value

    @status.getter()
    def _get_object_status(self):
        logging.debug(f"Getting event status: {self}")
        return self.object.status

    # ------------------------------------------------------------------ #
    #  Transitions                                                          #
    # ------------------------------------------------------------------ #

    @status.transition(
        source=Event.Status.DRAFT,
        target=Event.Status.PROPOSED,
        label="Submit event",
        permission=has_permission((apiv1, "submit", Event)),
    )
    def submit(self):
        logger.info(f"Submitting event: {self.object!r}")
        self.object.save()

    @status.transition(
        source=Event.Status.PROPOSED,
        target=Event.Status.PLANNED,
        label="Approve event",
        permission=has_permission((apiv1, "approve", Event)),
    )
    def approve(self):
        logger.info(f"Approving event: {self.object!r}")
        self.object.save()
        # if there are no overlapping events for the block (or any blocks, if a multiday block event that does not span full days),
        # publish automatically. This allows events that are not in conflict with others to skip the "planned" state and be published immediately.
        conflicts = self.object.find_active_conflicts()
        if conflicts:
            for conflict in conflicts:
                logger.debug(
                    "Auto-publish blocked for %r: block %s conflicts with %r (status=%s) block %s",
                    self.object,
                    conflict.my_block,
                    conflict.conflicting_event,
                    conflict.conflicting_event.status,
                    conflict.conflicting_block,
                )
            logger.info(
                "Not auto-publishing %r: %d conflict(s) found",
                self.object,
                len(conflicts),
            )
        else:
            logger.info(
                "Auto-publishing %r: no overlapping active events found",
                self.object,
            )
            self.publish()

    def _has_overlapping_events(self) -> bool:
        """Thin wrapper kept for backwards compatibility. Prefer find_active_conflicts() directly."""
        return bool(self.object.find_active_conflicts())


    @status.transition(
        source=Event.Status.PROPOSED,
        target=Event.Status.REJECTED,
        label="Reject event",
        permission=has_permission((apiv1, "reject", Event)),
    )
    def reject(self):
        logger.info(f"Rejecting event: {self.object!r}")
        self.object.save()

    @status.transition(
        source=Event.Status.PLANNED,
        target=Event.Status.PUBLISHED,
        label="Publish event",
        permission=has_permission((apiv1, "publish", Event)),
    )
    def publish(self):
        logger.info(f"Publishing event: {self.object!r}")
        self.object.save()

    @status.transition(
        source=Event.Status.PUBLISHED,
        target=Event.Status.CONFIRMED,
        label="Confirm event",
        conditions=[_within_confirmation_window],
        permission=has_permission((apiv1, "confirm", Event)),
    )
    def confirm(self):
        logger.info(f"Confirming event: {self.object!r}")
        self.object.save()

    @status.transition(
        source=Event.Status.PLANNED,
        target=Event.Status.CANCELED,
        label="Cancel event",
        permission=has_permission((apiv1, "cancel", Event)),
    )
    @status.transition(
        source=Event.Status.PUBLISHED,
        target=Event.Status.CANCELED,
        label="Cancel event",
        permission=has_permission((apiv1, "cancel", Event)),
    )
    def cancel(self):
        logger.info(f"Canceling event: {self.object!r}")
        self.object.save()

    @status.transition(
        source=Event.Status.CONFIRMED,
        target=Event.Status.COMPLETED,
        label="Complete event",
        conditions=[_event_has_passed],
        permission=has_permission((apiv1, "complete", Event)),
    )
    def complete(self):
        logger.info(f"Completing event: {self.object!r}")
        self.object.save()

    @status.transition(
        source=[Event.Status.COMPLETED, Event.Status.CANCELED, Event.Status.REJECTED],
        target=Event.Status.ARCHIVED,
        label="Archive event",
        permission=has_permission((apiv1, "archive", Event)),
    )
    def archive(self):
        logger.info(f"Archiving event: {self.object!r}")
        self.object.save()

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    def get_available_transitions(self, user: OpenIDUser) -> list[EventTransition]:
        """Return all transitions (enabled or not) applicable to the current status."""
        transitions_list = []
        transition_methods = [
            ("submit", self.submit),
            ("approve", self.approve),
            ("reject", self.reject),
            ("publish", self.publish),
            ("confirm", self.confirm),
            ("cancel", self.cancel),
            ("complete", self.complete),
            ("archive", self.archive),
        ]

        for action, method in transition_methods:
            try:
                all_transitions = method.get_transitions()
                for transition in all_transitions:
                    sources = (
                        transition.source
                        if isinstance(transition.source, list)
                        else [transition.source]
                    )
                    if self.object.status in sources:
                        result = self._evaluate_transition(transition, action, user)
                        transitions_list.append(result)
                        break
            except Exception as e:
                logger.error(f"Error getting transitions for {action}: {str(e)}")

        return transitions_list

    def _evaluate_transition(
        self, transition: Transition, action: str, user: OpenIDUser
    ) -> EventTransition:
        conditions_met = transition.conditions_met(self)
        if not conditions_met:
            if action == "confirm":
                disable_reason = (
                    f"Event must start within {CONFIRM_WINDOW_DAYS} days to be confirmed"
                )
            elif action == "complete":
                disable_reason = "Event end time has not passed yet"
            else:
                disable_reason = "Conditions not met for this transition"
            return EventTransition(
                action=action,
                label=transition.label,
                target_status=transition.target,
                enabled=False,
                disable_reason=disable_reason,
            )

        has_perm = transition.has_perm(self, user)
        if not has_perm:
            return EventTransition(
                action=action,
                label=transition.label,
                target_status=transition.target,
                enabled=False,
                disable_reason="Insufficient permissions for this action",
            )

        return EventTransition(
            action=action,
            label=transition.label,
            target_status=transition.target,
            enabled=True,
            disable_reason=None,
        )

    def execute_transition(self, action: str) -> bool:
        """Execute a named transition. Returns True on success."""
        action_to_method = {
            "submit": self.submit,
            "approve": self.approve,
            "reject": self.reject,
            "publish": self.publish,
            "confirm": self.confirm,
            "cancel": self.cancel,
            "complete": self.complete,
            "archive": self.archive,
        }

        method = action_to_method.get(action)
        if not method:
            logger.error(f"Unknown event transition action: {action}")
            return False

        try:
            method()
            return True
        except Exception as e:
            logger.error(f"Failed to execute event transition {action}: {str(e)}")
            return False

