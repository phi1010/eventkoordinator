from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from apiv1.models.basedata import Event, Proposal, Series
from sync_pretix.models import CalculatedPrices


class CalculatedPricesApiTest(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="calculated-prices-api-user",
            password="pw-123",
            email="calculated-prices-api-user@example.com",
        )

        required_permissions = Permission.objects.filter(
            codename__in=[
                "add_calculatedprices",
                "view_calculatedprices",
                "change_calculatedprices",
                "delete_calculatedprices",
            ]
        )
        self.user.user_permissions.add(*required_permissions)

        self.series = Series.objects.create(name="Pricing API Series")
        self.proposal = Proposal.objects.create(
            title="Pricing Workshop",
            abstract="A" * 60,
            description="B" * 120,
            material_cost_eur=Decimal("4.50"),
            preferred_dates="Any",
            duration_days=2,
            duration_time_per_day="01:30",
            max_participants=8,
            is_basic_course=True,
        )
        now = timezone.now()
        self.event = Event.objects.create(
            series=self.series,
            proposal=self.proposal,
            name="Pricing API Event",
            start_time=now,
            end_time=now,
        )

    def _url(self, suffix: str = "") -> str:
        base = f"/api/v1/pricing/{self.series.id}/events/{self.event.id}/calculated-prices"
        return f"{base}{suffix}"

    def test_create_with_default_configuration_generates_values(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            self._url("/create"),
            data=json.dumps({"use_default_pricing_configuration": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIsNotNone(payload["pricing_configuration_id"])
        self.assertIsNotNone(payload["member_regular_gross_eur"])
        self.assertIsNotNone(payload["business_net_eur"])

    def test_create_with_none_configuration_leaves_values_blank(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            self._url("/create"),
            data=json.dumps({"use_default_pricing_configuration": False}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIsNone(payload["pricing_configuration_id"])
        self.assertIsNone(payload["member_regular_gross_eur"])
        self.assertIsNone(payload["member_discounted_gross_eur"])
        self.assertIsNone(payload["guest_regular_gross_eur"])
        self.assertIsNone(payload["guest_discounted_gross_eur"])
        self.assertIsNone(payload["business_net_eur"])

    def test_update_manual_values_after_none_configuration(self) -> None:
        self.client.force_login(self.user)
        self.client.post(
            self._url("/create"),
            data=json.dumps({"use_default_pricing_configuration": False}),
            content_type="application/json",
        )

        update_response = self.client.put(
            self._url(),
            data=json.dumps(
                {
                    "member_regular_gross_eur": "19.50",
                    "member_discounted_gross_eur": "17.00",
                    "guest_regular_gross_eur": "22.00",
                    "guest_discounted_gross_eur": "19.50",
                    "business_net_eur": "34.99",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(update_response.status_code, 200)
        payload = update_response.json()
        self.assertEqual(payload["member_regular_gross_eur"], "19.50")
        self.assertEqual(payload["business_net_eur"], "34.99")

        instance = CalculatedPrices.objects.get(event=self.event)
        self.assertEqual(instance.member_regular_gross_eur, Decimal("19.50"))
        self.assertEqual(instance.business_net_eur, Decimal("34.99"))

    def test_create_rejects_manual_value_override_payload(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            self._url("/create"),
            data=json.dumps(
                {
                    "use_default_pricing_configuration": True,
                    "member_regular_gross_eur": "99.00",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 422)

    def test_create_requires_add_permission(self) -> None:
        self.user.user_permissions.remove(
            Permission.objects.get(codename="add_calculatedprices")
        )
        self.client.force_login(self.user)

        response = self.client.post(
            self._url("/create"),
            data=json.dumps({"use_default_pricing_configuration": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)


