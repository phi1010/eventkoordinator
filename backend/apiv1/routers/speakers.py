"""
Speakers router.

Handles endpoints for managing proposal speakers.
"""

import logging
import uuid
from ninja import Router

import apiv1
from apiv1.api_utils import api_permission_mandatory
from apiv1.models import Proposal as ProposalModel, ProposalSpeaker, Speaker
from apiv1.schemas import ProposalSpeakerOut, SpeakerOut, SpeakerIn, ErrorOut

router = Router()
logger = logging.getLogger(__name__)


@router.post(
    "/{proposal_id}/speakers",
    response={201: ProposalSpeakerOut, 400: ErrorOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def add_speaker_to_proposal(
    request, proposal_id: uuid.UUID, payload: SpeakerIn
) -> tuple[int, ProposalSpeakerOut] | tuple[int, ErrorOut]:
    """Add a speaker to a proposal or create new speaker if doesn't exist"""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
        if not request.user.has_perm((apiv1, "change", ProposalModel), proposal):
            return 401, ErrorOut(error="Permission denied")
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "change", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")

    try:
        # Try to get existing speaker by email
        if payload.email:
            speaker, created = Speaker.objects.get_or_create(
                email=payload.email,
                defaults={
                    "display_name": payload.display_name or payload.email.split("@")[0],
                    "biography": payload.biography or "",
                    "use_gravatar": payload.use_gravatar or False,
                },
            )
            # Update speaker if it already existed
            if not created:
                if payload.display_name is not None:
                    speaker.display_name = payload.display_name
                if payload.biography is not None:
                    speaker.biography = payload.biography
                if payload.use_gravatar is not None:
                    speaker.use_gravatar = payload.use_gravatar
                speaker.save()
        else:
            return 400, ErrorOut(error="Speaker email is required")

        # Add speaker to proposal
        sort_order = proposal.proposal_speakers.count()
        proposal_speaker, created = ProposalSpeaker.objects.get_or_create(
            proposal=proposal, speaker=speaker, defaults={"sort_order": sort_order}
        )

        return 201, ProposalSpeakerOut(
            id=proposal_speaker.id,
            speaker=SpeakerOut(
                id=speaker.id,
                email=speaker.email,
                display_name=speaker.display_name,
                biography=speaker.biography,
                profile_picture=speaker.profile_picture.url
                if speaker.profile_picture
                else None,
                use_gravatar=speaker.use_gravatar,
            ),
            role=proposal_speaker.role,
            sort_order=proposal_speaker.sort_order,
        )
    except Exception as e:
        logger.error(f"Failed to add speaker: {str(e)}")
        return 400, ErrorOut(error=f"Failed to add speaker")


@router.get(
    "/{proposal_id}/speakers",
    response={200: list[ProposalSpeakerOut], 404: ErrorOut, 401: ErrorOut, 403: ErrorOut}
)
@api_permission_mandatory()
def list_proposal_speakers(
    request, proposal_id: uuid.UUID
) -> tuple[int, list[ProposalSpeakerOut]] | tuple[int, ErrorOut]:
    """List all speakers for a proposal"""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
        if not request.user.has_perm((apiv1, "view", ProposalModel), proposal):
            return 401, ErrorOut(error="Permission denied")
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "view", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")

    speakers = (
        ProposalSpeaker.objects.select_related("speaker")
        .filter(proposal=proposal)
        .order_by("sort_order")
    )

    return 200, [
        ProposalSpeakerOut(
            id=ps.id,
            speaker=SpeakerOut(
                id=ps.speaker.id,
                email=ps.speaker.email,
                display_name=ps.speaker.display_name,
                biography=ps.speaker.biography,
                profile_picture=ps.speaker.profile_picture.url
                if ps.speaker.profile_picture
                else None,
                use_gravatar=ps.speaker.use_gravatar,
            ),
            role=ps.role,
            sort_order=ps.sort_order,
        )
        for ps in speakers
    ]


@router.delete(
    "/{proposal_id}/speakers/{speaker_id}",
    response={200: dict, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut}
)
@api_permission_mandatory()
def remove_speaker_from_proposal(
    request, proposal_id: uuid.UUID, speaker_id: uuid.UUID
) -> tuple[int, dict] | tuple[int, ErrorOut]:
    """Remove a speaker from a proposal"""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
        if not request.user.has_perm((apiv1, "change", ProposalModel), proposal):
            return 401, ErrorOut(error="Permission denied")
        proposal_speaker = ProposalSpeaker.objects.get(id=speaker_id, proposal=proposal)
        proposal_speaker.delete()

        return 200, {"success": True, "message": "Speaker removed from proposal"}
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "change", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")
    except ProposalSpeaker.DoesNotExist:
        return 404, ErrorOut(error="Speaker not found in proposal")
    except Exception as e:
        logger.error(f"Failed to remove speaker: {str(e)}")
        return 404, ErrorOut(error="Speaker not found")


@router.put(
    "/{proposal_id}/speakers/{speaker_id}",
    response={200: ProposalSpeakerOut, 400: ErrorOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def update_speaker_in_proposal(
    request, proposal_id: uuid.UUID, speaker_id: uuid.UUID, payload: SpeakerIn
) -> tuple[int, ProposalSpeakerOut] | tuple[int, ErrorOut]:
    """Update speaker information in a proposal"""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
        if not request.user.has_perm((apiv1, "change", ProposalModel), proposal):
            return 401, ErrorOut(error="Permission denied")
        proposal_speaker = ProposalSpeaker.objects.select_related("speaker").get(
            id=speaker_id, proposal=proposal
        )
        speaker = proposal_speaker.speaker
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "change", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")
    except ProposalSpeaker.DoesNotExist:
        return 404, ErrorOut(error="Speaker not found in proposal")
    except Exception as e:
        logger.error(f"Failed to retrieve speaker: {str(e)}")
        return 404, ErrorOut(error="Speaker not found in proposal")

    try:
        # Update speaker fields
        if payload.email is not None and payload.email != speaker.email:
            # Check if email is already in use
            if (
                Speaker.objects.filter(email=payload.email)
                .exclude(id=speaker.id)
                .exists()
            ):
                return 400, ErrorOut(error="Email already in use by another speaker")
            speaker.email = payload.email

        if payload.display_name is not None:
            speaker.display_name = payload.display_name

        if payload.biography is not None:
            speaker.biography = payload.biography

        if payload.use_gravatar is not None:
            speaker.use_gravatar = payload.use_gravatar

        speaker.save()

        return 200, ProposalSpeakerOut(
            id=proposal_speaker.id,
            speaker=SpeakerOut(
                id=speaker.id,
                email=speaker.email,
                display_name=speaker.display_name,
                biography=speaker.biography,
                profile_picture=speaker.profile_picture.url
                if speaker.profile_picture
                else None,
                use_gravatar=speaker.use_gravatar,
            ),
            role=proposal_speaker.role,
            sort_order=proposal_speaker.sort_order,
        )
    except Exception as e:
        logger.error(f"Failed to update speaker: {str(e)}")
        return 400, ErrorOut(error=f"Failed to update speaker")
