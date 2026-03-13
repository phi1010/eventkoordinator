from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from apiv1.models import Event as EventModel


class SeriesApiTest(TestCase):
    def setUp(self) -> None:
        self.username = "series-api-user"
        self.password = "series-api-pass-123"

        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username=self.username,
            password=self.password,
            email=f"{self.username}@example.com",
        )
        self.user.user_permissions.add(
            Permission.objects.get(codename="add_series")
        )

    def test_create_series_does_not_create_initial_event(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            "/api/v1/series/create",
            data=json.dumps({"name": "API Created Series", "description": "desc"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        payload = response.json()
        self.assertIn("id", payload)
        self.assertEqual(payload.get("events"), [])

        self.assertEqual(
            EventModel.objects.filter(series_id=payload["id"]).count(),
            0,
            "Series creation should not create an implicit event.",
        )

