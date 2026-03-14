"""
Speakers router.

Handles endpoints for managing proposal speakers.
"""

import logging
import uuid
from typing import cast

from django.core.exceptions import ValidationError
from django.db import models
from ninja import File, Router, UploadedFile

import apiv1
from apiv1.api_utils import api_permission_mandatory
from apiv1.models import Proposal as ProposalModel, Speaker
from apiv1.schemas import ProposalSpeakerOut, SpeakerOut, SpeakerIn, ErrorOut

router = Router()
logger = logging.getLogger(__name__)


def _speaker_to_schema(speaker: Speaker) -> SpeakerOut:
    return SpeakerOut(
        id=speaker.id,
        email=speaker.email,
        display_name=speaker.display_name,
        biography=speaker.biography,
        profile_picture=speaker.profile_picture.url if speaker.profile_picture else None,
        use_gravatar=speaker.use_gravatar,
    )


def _speaker_to_proposal_speaker_out(speaker: Speaker) -> ProposalSpeakerOut:
    return ProposalSpeakerOut(
        id=speaker.id,
        speaker=_speaker_to_schema(speaker),
        role=speaker.role,
        sort_order=speaker.sort_order,
    )


@router.post(
    "/{proposal_id}/speakers",
    response={201: ProposalSpeakerOut, 400: ErrorOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def add_speaker_to_proposal(
    request, proposal_id: uuid.UUID, payload: SpeakerIn
) -> tuple[int, ProposalSpeakerOut] | tuple[int, ErrorOut]:
    """Add a new speaker to a proposal"""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
        if not request.user.has_perm((apiv1, "change", ProposalModel), proposal):
            return 401, ErrorOut(error="Permission denied")
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "change", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")

    try:
        sort_order = proposal.speakers.count()
        speaker = Speaker(
            proposal=proposal,
            email=payload.email or "",
            display_name=payload.display_name or "",
            biography=payload.biography or "",
            use_gravatar=payload.use_gravatar or False,
            sort_order=sort_order,
        )
        speaker.save()
        return 201, _speaker_to_proposal_speaker_out(speaker)
    except Exception as e:
        logger.error(f"Failed to add speaker: {str(e)}")
        return 400, ErrorOut(error="Failed to add speaker")


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

    speakers = proposal.speakers.order_by("sort_order")

    return 200, [_speaker_to_proposal_speaker_out(s) for s in speakers]


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
        speaker = Speaker.objects.get(id=speaker_id, proposal=proposal)
        speaker.delete()
        return 200, {"success": True, "message": "Speaker removed from proposal"}
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "change", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")
    except Speaker.DoesNotExist:
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
        speaker = Speaker.objects.get(id=speaker_id, proposal=proposal)
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "change", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")
    except Speaker.DoesNotExist:
        return 404, ErrorOut(error="Speaker not found in proposal")
    except Exception as e:
        logger.error(f"Failed to retrieve speaker: {str(e)}")
        return 404, ErrorOut(error="Speaker not found in proposal")

    try:
        if payload.email is not None:
            speaker.email = payload.email

        if payload.display_name is not None:
            speaker.display_name = payload.display_name

        if payload.biography is not None:
            speaker.biography = payload.biography

        if payload.use_gravatar is not None:
            speaker.use_gravatar = payload.use_gravatar

        speaker.save()
        return 200, _speaker_to_proposal_speaker_out(speaker)
    except Exception as e:
        logger.error(f"Failed to update speaker: {str(e)}")
        return 400, ErrorOut(error="Failed to update speaker")


@router.post(
    "/{proposal_id}/speakers/{speaker_id}/profile-picture",
    response={200: ProposalSpeakerOut, 400: ErrorOut, 404: ErrorOut, 401: ErrorOut, 403: ErrorOut},
)
@api_permission_mandatory()
def upload_speaker_profile_picture(
    request, proposal_id: uuid.UUID, speaker_id: uuid.UUID, file: UploadedFile = File(...)
) -> tuple[int, ProposalSpeakerOut] | tuple[int, ErrorOut]:
    """Upload or replace a speaker profile image within a proposal."""
    try:
        proposal = ProposalModel.objects.get(pk=proposal_id)
        if not request.user.has_perm((apiv1, "change", ProposalModel), proposal):
            return 401, ErrorOut(error="Permission denied")
        speaker = Speaker.objects.get(id=speaker_id, proposal=proposal)
    except ProposalModel.DoesNotExist:
        if not request.user.has_perm((apiv1, "change", ProposalModel), None):
            return 401, ErrorOut(error="Permission denied")
        return 404, ErrorOut(error="Proposal not found")
    except Speaker.DoesNotExist:
        return 404, ErrorOut(error="Speaker not found in proposal")

    profile_picture_field = cast(
        models.FileField, speaker._meta.get_field("profile_picture")
    )
    try:
        profile_picture_field.clean(file, speaker)
    except ValidationError as exc:
        return 400, ErrorOut(
            error="Invalid speaker image",
            detail=" ".join(exc.messages),
        )

    previous_picture_name = speaker.profile_picture.name if speaker.profile_picture else None
    speaker.profile_picture = file
    speaker.save(update_fields=["profile_picture"])

    if previous_picture_name and previous_picture_name != speaker.profile_picture.name:
        profile_picture_field.storage.delete(previous_picture_name)

    return 200, _speaker_to_proposal_speaker_out(speaker)
