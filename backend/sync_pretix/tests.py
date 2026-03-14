from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apiv1.models.basedata import Event, Proposal, Series
from sync_pretix.models import CalculatedPrices, PretixPricingConfiguration


class PretixPricingConfigurationTests(TestCase):
	def setUp(self):
		self.config = PretixPricingConfiguration.objects.create()

	def test_min_participants_thresholds_are_sorted_and_normalized(self):
		self.config.min_participants_params = {"7": "2", "0": "1"}
		self.config.save(update_fields=["min_participants_params"])

		self.assertEqual(self.config.min_participants_thresholds, [(0, 1), (7, 2)])

	def test_calculated_prices_match_documentation_example(self):
		prices = self.config.get_calculated_prices(
			duration_hours=1.5,
			material_cost=3.0,
			max_participants=8,
			is_basic_course=True,
		)

		self.assertEqual(prices.member_regular_gross_eur, Decimal("17.00"))
		self.assertEqual(prices.member_discounted_gross_eur, Decimal("16.00"))
		self.assertEqual(prices.guest_regular_gross_eur, Decimal("20.00"))
		self.assertEqual(prices.guest_discounted_gross_eur, Decimal("17.00"))
		self.assertEqual(prices.business_net_eur, Decimal("32.00"))
		self.assertIsInstance(prices.member_regular_gross_eur, Decimal)
		self.assertIsInstance(prices.member_discounted_gross_eur, Decimal)
		self.assertIsInstance(prices.guest_regular_gross_eur, Decimal)
		self.assertIsInstance(prices.guest_discounted_gross_eur, Decimal)

	def test_guest_discounted_matches_sheet_logic(self):
		self.assertEqual(
			self.config.get_guest_discounted_price(
				duration_hours=2,
				material_cost=5,
				max_participants=10,
				is_basic_course=False,
			),
			self.config.get_member_regular_price(
				duration_hours=2,
				material_cost=5,
				max_participants=10,
				is_basic_course=False,
			),
		)


class CalculatedPricesTests(TestCase):
	def setUp(self):
		self.config = PretixPricingConfiguration.objects.create()
		self.series = Series.objects.create(name="Series")
		self.proposal = Proposal.objects.create(
			title="Workshop",
			abstract="a" * 50,
			description="d" * 50,
			material_cost_eur=Decimal("3.00"),
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
			name="Event",
			start_time=now,
			end_time=now,
		)

	def test_save_populates_empty_price_fields_from_linked_event_proposal(self):
		prices = CalculatedPrices.objects.create(event=self.event)
		self.assertEqual(prices.duration_hours, Decimal("3"))
		self.assertEqual(prices.pricing_configuration, self.config)

		expected = self.config.get_calculated_prices(
			duration_hours=Decimal("3"),
			material_cost=Decimal("3.00"),
			max_participants=8,
			is_basic_course=True,
		)
		self.assertEqual(prices.member_regular_gross_eur, expected.member_regular_gross_eur)
		self.assertEqual(prices.member_discounted_gross_eur, expected.member_discounted_gross_eur)
		self.assertEqual(prices.guest_regular_gross_eur, expected.guest_regular_gross_eur)
		self.assertEqual(prices.guest_discounted_gross_eur, expected.guest_discounted_gross_eur)
		self.assertEqual(prices.business_net_eur, expected.business_net_eur)

	def test_save_uses_explicit_pricing_configuration(self):
		custom = PretixPricingConfiguration.objects.create(lecturer_rate=200)
		prices = CalculatedPrices.objects.create(
			event=self.event,
			pricing_configuration=custom,
		)
		self.assertEqual(prices.pricing_configuration, custom)

		expected = custom.get_calculated_prices(
			duration_hours=Decimal("3"),
			material_cost=Decimal("3.00"),
			max_participants=8,
			is_basic_course=True,
		)
		self.assertEqual(prices.member_regular_gross_eur, expected.member_regular_gross_eur)

	def test_save_uses_newest_pricing_configuration_when_not_specified(self):
		newer = PretixPricingConfiguration.objects.create(lecturer_rate=120)
		prices = CalculatedPrices.objects.create(event=self.event)

		self.assertEqual(prices.pricing_configuration, newer)

	def test_save_creates_pricing_configuration_when_none_exist(self):
		PretixPricingConfiguration.objects.all().delete()
		prices = CalculatedPrices.objects.create(event=self.event)

		self.assertIsNotNone(prices.pricing_configuration)
		self.assertEqual(PretixPricingConfiguration.objects.count(), 1)

	def test_save_keeps_manually_provided_fields(self):
		prices = CalculatedPrices.objects.create(
			event=self.event,
			member_regular_gross_eur=Decimal("999.00"),
		)
		self.assertEqual(prices.member_regular_gross_eur, Decimal("999.00"))
		self.assertIsInstance(prices.member_regular_gross_eur, Decimal)
		self.assertIsNotNone(prices.member_discounted_gross_eur)
		self.assertIsNotNone(prices.guest_regular_gross_eur)
		self.assertIsNotNone(prices.guest_discounted_gross_eur)
		self.assertIsNotNone(prices.business_net_eur)

	def test_event_without_proposal_raises_validation_error(self):
		now = timezone.now()
		event = Event.objects.create(
			series=self.series,
			proposal=None,
			name="No Proposal",
			start_time=now,
			end_time=now,
		)
		prices = CalculatedPrices(event=event)

		with self.assertRaises(ValidationError):
			prices.save()
