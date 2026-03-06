import logging
import textwrap
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from viewflow import fsm
from viewflow.fsm.base import Transition

import apiv1
from apiv1.models import Proposal, check_proposal_required_fields
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
