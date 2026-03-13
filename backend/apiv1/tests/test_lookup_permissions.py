from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apiv1.auth_groups import AUTHENTICATED_USERS_GROUP_NAME
from apiv1.models import ProposalArea, ProposalLanguage, SubmissionType


@override_settings(AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"])
class LookupPermissionsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="lookup-user",
            email="lookup-user@example.com",
            password="test-password",
        )

        SubmissionType.objects.get_or_create(
            code="workshop", defaults={"label": "Workshop"}
        )
        ProposalLanguage.objects.get_or_create(
            code="de", defaults={"label": "German"}
        )
        ProposalArea.objects.get_or_create(
            code="wood", defaults={"label": "Wood"}
        )

    def test_new_user_gets_authenticated_users_group(self):
        self.assertTrue(
            self.user.groups.filter(name=AUTHENTICATED_USERS_GROUP_NAME).exists()
        )

    def test_lookup_endpoints_are_accessible_for_authenticated_user(self):
        self.client.force_login(self.user)

        for path in (
            "/api/v1/submission_types",
            "/api/v1/proposal_languages",
            "/api/v1/proposal_areas",
        ):
            response = self.client.get(path)
            self.assertEqual(200, response.status_code, path)
            self.assertGreater(len(response.json()), 0, path)

    def test_lookup_endpoints_require_authentication(self):
        response = self.client.get("/api/v1/submission_types")
        self.assertEqual(401, response.status_code)


