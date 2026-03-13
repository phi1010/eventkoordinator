from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apiv1.models import Proposal, ProposalArea, ProposalLanguage, SubmissionType

AUTHENTICATED_USERS_GROUP_NAME = "Authenticated Users"


def ensure_authenticated_users_group() -> Group:
    """Create the default authenticated-users group and required permissions."""
    group, _ = Group.objects.get_or_create(name=AUTHENTICATED_USERS_GROUP_NAME)

    permission_definitions = [
        ("add_proposal", "Can add proposal", Proposal),
        ("browse_proposal", "Can browse proposal list", Proposal),
        ("view_submissiontype", "Can view submission type", SubmissionType),
        ("view_proposallanguage", "Can view proposal language", ProposalLanguage),
        ("view_proposalarea", "Can view proposal area", ProposalArea),
    ]

    for codename, name, model in permission_definitions:
        permission, _ = Permission.objects.get_or_create(
            codename=codename,
            content_type=ContentType.objects.get_for_model(model),
            defaults={"name": name},
        )
        group.permissions.add(permission)

    return group


def assign_authenticated_group_to_all_users() -> None:
    """Ensure all users belong to the default authenticated-users group."""
    group = ensure_authenticated_users_group()
    user_model = get_user_model()
    for user in user_model.objects.all():
        user.groups.add(group)

