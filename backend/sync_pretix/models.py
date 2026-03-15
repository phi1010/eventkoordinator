from django.db import models
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import logging

from apiv1.models import SyncBaseTarget, ProposalArea
from apiv1.models.basedata import time_string_to_minutes
from apiv1.models.sync.syncbasedata import SyncBaseItem
from project.basemodels import HistoricalMetaBase
from sync_pretix.pretix_client import PretixApiClient, PretixApiError

logger = logging.getLogger(__name__)


def default_min_participants_params():
    """
    Default parameters for minimum participants calculation.
    Format: {threshold: deduction}
    Logic: max_participants - deduction where threshold <= max_participants
    Example: {0: 1, 7: 2} means deduct 1 for 1-6 participants, deduct 2 for 7+ participants
    """
    return {0: 1, 7: 2}


class PretixSyncTarget(SyncBaseTarget):
    secret_field_names = ["api_token"]

    api_token = models.CharField(
        max_length=255,
        verbose_name="Pretix API Token",
        help_text="API Token for authenticating with the Pretix API",
    )
    api_url = models.CharField(
        max_length=255, verbose_name="Pretix API URL", help_text="Pretix API URL"
    )
    organizer_slug = models.CharField(
        max_length=255, verbose_name="Organizer Slug", help_text="Organizer Slug"
    )

    def create_new_sync_item(self, event) -> "PretixSyncItem":
        """Create a PretixSyncItem for *event* using the area-to-event-slug mapping.

        Looks up the event's proposal area and finds the matching
        ``PretixSyncTargetAreaAssociation`` to determine the correct Pretix
        event slug.  The call is idempotent: if an item already exists for this
        (target, event) pair the existing item is returned unchanged.

        Raises ``ValueError`` if the event has no proposal, the proposal has no
        area, or no association is configured for that area on this target.
        """
        proposal = getattr(event, "proposal", None)
        if proposal is None:
            raise ValueError(
                f"Event {event.pk} has no proposal; cannot determine Pretix event slug."
            )
        area = getattr(proposal, "area", None)
        if area is None:
            raise ValueError(
                f"Proposal {proposal.pk} has no area; cannot determine Pretix event slug."
            )
        try:
            association = self.area_associations.get(area=area)
        except PretixSyncTargetAreaAssociation.DoesNotExist:
            raise ValueError(
                f"No Pretix event-slug configured for area {area.code!r} "
                f"on sync target {self.pk}."
            )
        item, _created = PretixSyncItem.objects.get_or_create(
            sync_target=self,
            related_event=event,
            defaults={"area_association": association, "flag_push": True},
        )
        return item


class PretixSyncTargetAreaAssociation(HistoricalMetaBase):
    sync_target = models.ForeignKey(
        PretixSyncTarget,
        on_delete=models.CASCADE,
        related_name="area_associations",
        null=True,
        blank=True,
    )
    area = models.ForeignKey(
        ProposalArea, on_delete=models.CASCADE, related_name="pretix_sync_associations"
    )
    event_slug = models.CharField(
        max_length=255, verbose_name="Event Slug", help_text="Event Slug"
    )
    ticket_product_member_regular_id = models.CharField(
        max_length=255,
        default="Regular Member Ticket",
        null=True,
        blank=True,
        verbose_name="ID or Name of Ticket Product for Members (regular)",
    )
    ticket_product_member_discounted_id = models.CharField(
        max_length=255,
        default="Discounted Member Ticket",
        null=True,
        blank=True,
        verbose_name="ID or Name of Ticket Product for Members (discounted)",
    )
    ticket_product_guest_regular_id = models.CharField(
        max_length=255,
        default="Regular Guest Ticket",
        null=True,
        blank=True,
        verbose_name="ID or Name of Ticket Product for Guests (regular)",
    )
    ticket_product_guest_discounted_id = models.CharField(
        max_length=255,
        default="Discounted Guest Ticket",
        null=True,
        blank=True,
        verbose_name="ID or Name of Ticket Product for Guests (discounted)",
    )
    ticket_product_business_id = models.CharField(
        max_length=255,
        default="Business Ticket",
        null=True,
        blank=True,
        verbose_name="ID of Ticket Product for Businesses",
    )


class PretixSyncItem(SyncBaseItem):
    """Links a Pretix subevent to an internal event via a PretixSyncTarget."""

    sync_target = models.ForeignKey(
        PretixSyncTarget,
        on_delete=models.CASCADE,
        related_name="items",
    )
    area_association = models.ForeignKey(
        "PretixSyncTargetAreaAssociation",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="sync_items",
        verbose_name="Area Association",
        help_text="The area-to-event-slug mapping used when pushing to Pretix.",
    )
    subevent_slug = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Pretix Subevent ID",
        help_text="ID of the Pretix subevent created for this event. Set on first push.",
    )

    def __str__(self):
        return f"PretixSyncItem(target={self.sync_target_id}, event={self.related_event_id})"

    def delete_remote(self) -> None:
        """Delete the linked Pretix subevent and reset the stored subevent ID."""
        if not self.subevent_slug:
            return  # Nothing to delete remotely.

        association = self.area_association
        if association is None:
            raise ValueError(
                f"PretixSyncItem {self.pk} has no area association; cannot delete remote subevent."
            )

        target = self.sync_target
        client = PretixApiClient(api_base_url=target.api_url, token=target.api_token)
        client.delete_subevent(
            organizer_slug=target.organizer_slug,
            event_slug=association.event_slug,
            subevent_id=self.subevent_slug,
        )
        logger.info(
            "Deleted Pretix subevent %s for event %s.", self.subevent_slug, self.related_event_id
        )
        self.subevent_slug = None
        self.save(update_fields=["subevent_slug", "updated_at"])

    def push_update(self) -> None:
        """Create or update the linked Pretix subevent, overriding ticket prices."""
        association = self.area_association
        if association is None:
            raise ValueError(
                f"PretixSyncItem {self.pk} has no area association; cannot push."
            )

        target = self.sync_target
        event = self.related_event
        client = PretixApiClient(api_base_url=target.api_url, token=target.api_token)

        # Determine the event locale from the proposal language; fall back to "de".
        event_locale = "de"
        proposal = getattr(event, "proposal", None)
        if proposal is not None:
            lang = getattr(proposal, "language", None)
            if lang is not None:
                event_locale = lang.code

        # Fetch the Pretix parent event to get its configured locales.
        pretix_event = client.get_event(
            organizer_slug=target.organizer_slug,
            event_slug=association.event_slug,
        )
        configured_locales = pretix_event.get("locales") or [event_locale]
        # Apply the same name to every configured locale; ensure the event's own locale is present.
        name_dict = {locale: event.name for locale in configured_locales}
        name_dict[event_locale] = event.name

        # Always fetch items — needed for both price overrides and the quota.
        items = client.list_items(
            organizer_slug=target.organizer_slug,
            event_slug=association.event_slug,
        )
        logger.debug(
            "Fetched %d item(s) from Pretix event %r: %s",
            len(items),
            association.event_slug,
            [(i.get("id"), i.get("name")) for i in items],
        )

        # Build price overrides from CalculatedPrices if available.
        item_overrides: list[dict] = []
        try:
            prices = event.calculated_prices
            item_overrides = self._build_item_overrides(association, prices, items)
            logger.debug(
                "Built %d item_override(s) for subevent: %s",
                len(item_overrides), item_overrides,
            )
            if not item_overrides:
                logger.warning(
                    "CalculatedPrices exist for event %s but produced no item overrides. "
                    "Check that prices are non-null and product names match Pretix items.",
                    event.pk,
                )
        except ObjectDoesNotExist:
            logger.warning(
                "No CalculatedPrices found for event %s; subevent will use default item prices.",
                event.pk,
            )

        payload = {
            "name": name_dict,
            "date_from": event.start_time.isoformat(),
            "date_to": event.end_time.isoformat(),
            "active": True,
            "meta_data": {},
            "item_price_overrides": item_overrides,
        }

        # Create the subevent if this is the first push.
        if not self.subevent_slug:
            result = client.create_subevent(
                organizer_slug=target.organizer_slug,
                event_slug=association.event_slug,
                payload=payload,
            )
            self.subevent_slug = str(result["id"])
            self.save(update_fields=["subevent_slug", "updated_at"])

        # Always patch to ensure item_overrides (prices) are applied.
        # Pretix may ignore item_overrides on creation, so we patch unconditionally.
        client.patch_subevent(
            organizer_slug=target.organizer_slug,
            event_slug=association.event_slug,
            subevent_id=self.subevent_slug,
            payload=payload,
        )

        # Create or update the quota so price overrides take effect.
        max_participants = getattr(proposal, "max_participants", None)
        all_item_ids = self._resolve_all_item_ids(association, items)
        if not all_item_ids:
            logger.warning(
                "No Pretix item IDs could be resolved for PretixSyncItem %s "
                "(event %r, association event_slug %r). "
                "Expected product names: %s. Fetched items: %s. "
                "Quota will be created without products.",
                self.pk,
                event.name,
                association.event_slug,
                [
                    association.ticket_product_member_regular_id,
                    association.ticket_product_member_discounted_id,
                    association.ticket_product_guest_regular_id,
                    association.ticket_product_guest_discounted_id,
                    association.ticket_product_business_id,
                ],
                [(i.get("id"), i.get("name")) for i in items],
            )
        else:
            logger.debug("Resolved %d item ID(s) for quota: %s", len(all_item_ids), all_item_ids)
        self._create_or_update_quota(
            client, target, association, self.subevent_slug,
            event.name, all_item_ids, max_participants,
        )

    def _create_or_update_quota(
        self,
        client: PretixApiClient,
        target: "PretixSyncTarget",
        association: "PretixSyncTargetAreaAssociation",
        subevent_id: str,
        quota_name: str,
        item_ids: list[int],
        max_participants: int | None,
    ) -> None:
        """Create or update the subevent quota covering all five ticket products."""
        quota_payload = {
            "name": quota_name,
            "size": max_participants,
            "items": item_ids,
            "subevent": int(subevent_id),
        }
        existing = client.list_quotas(
            organizer_slug=target.organizer_slug,
            event_slug=association.event_slug,
            subevent_id=subevent_id,
        )
        if existing:
            logger.info(
                "Updating existing quota %s for subevent %s with %d product(s), size=%s.",
                existing[0]["id"], subevent_id, len(item_ids), max_participants,
            )
            client.patch_quota(
                organizer_slug=target.organizer_slug,
                event_slug=association.event_slug,
                quota_id=str(existing[0]["id"]),
                payload=quota_payload,
            )
        else:
            logger.info(
                "Creating quota for subevent %s with %d product(s), size=%s.",
                subevent_id, len(item_ids), max_participants,
            )
            client.create_quota(
                organizer_slug=target.organizer_slug,
                event_slug=association.event_slug,
                payload=quota_payload,
            )

    @staticmethod
    def _resolve_all_item_ids(
        association: "PretixSyncTargetAreaAssociation",
        items: list[dict],
    ) -> list[int]:
        """Return resolved Pretix item IDs for all five ticket products in the association."""
        product_names_or_ids = [
            association.ticket_product_member_regular_id,
            association.ticket_product_member_discounted_id,
            association.ticket_product_guest_regular_id,
            association.ticket_product_guest_discounted_id,
            association.ticket_product_business_id,
        ]
        return [
            item_id
            for name_or_id in product_names_or_ids
            if (item_id := PretixSyncItem._resolve_item_id(items, name_or_id)) is not None
        ]

    @staticmethod
    def _resolve_item_id(items: list[dict], name_or_id: str | None) -> int | None:
        """Resolve a Pretix item ID from a numeric ID string or a localized display name.

        Name matching is case-insensitive and whitespace-stripped to tolerate
        minor differences between what the management command stored and what
        Pretix returns.
        """
        if not name_or_id:
            return None
        if name_or_id.isdigit():
            return int(name_or_id)
        needle = name_or_id.strip().lower()
        for item in items:
            names = item.get("name") or {}
            if any(v.strip().lower() == needle for v in names.values()):
                return int(item["id"])
        return None

    @staticmethod
    def _build_item_overrides(
        association: "PretixSyncTargetAreaAssociation",
        prices: "CalculatedPrices",
        items: list[dict],
    ) -> list[dict]:
        """Map each ticket product in the association to a Pretix price override entry."""
        price_mapping = [
            (association.ticket_product_member_regular_id, prices.member_regular_gross_eur),
            (association.ticket_product_member_discounted_id, prices.member_discounted_gross_eur),
            (association.ticket_product_guest_regular_id, prices.guest_regular_gross_eur),
            (association.ticket_product_guest_discounted_id, prices.guest_discounted_gross_eur),
            (association.ticket_product_business_id, prices.business_net_eur),
        ]
        overrides = []
        for name_or_id, price in price_mapping:
            item_id = PretixSyncItem._resolve_item_id(items, name_or_id)
            if item_id is not None and price is not None:
                overrides.append({"item": item_id, "price": str(price)})
        return overrides


class PretixPricingConfiguration(HistoricalMetaBase):
    """
    Global pricing configuration for course fee calculation.

    Based on Kursgebühren-Rechner (documentation/kursgebuehren_rechner_marimo(1).py).
    Contains all configurable parameters that are NOT course-specific.
    """

    # Preparation and lecturer rates
    prep_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        validators=[MinValueValidator(0)],
        verbose_name="Vorbereitungszeit (Stunden)",
        help_text="Standard-Vorbereitungszeit in Stunden",
    )

    lecturer_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=40.0,
        validators=[MinValueValidator(0)],
        verbose_name="Dozent:in Honorar pro Stunde (€)",
        help_text="Honorar für Dozent:innen pro Stunde",
    )

    # Workshop rates (different for basis courses vs regular courses)
    workshop_rate_basis = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=10.0,
        validators=[MinValueValidator(0)],
        verbose_name="Werkstatt & ZAM Satz Grundkurs (€/h)",
        help_text="Stundensatz für Werkstatt & ZAM bei Grundkursen",
    )

    workshop_rate_regular = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=20.0,
        validators=[MinValueValidator(0)],
        verbose_name="Werkstatt & ZAM Satz Regelfall (€/h)",
        help_text="Stundensatz für Werkstatt & ZAM bei regulären Kursen",
    )

    # Surcharges and discounts
    guest_surcharge = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=10.0,
        validators=[MinValueValidator(0)],
        verbose_name="Gäst:in-Aufschlag (€/h)",
        help_text="Aufschlag für Gäste pro Stunde",
    )

    discount_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.50,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        verbose_name="Ermäßigungssatz",
        help_text="Ermäßigungssatz als Dezimalzahl (z.B. 0.50 für 50%)",
    )

    business_surcharge = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.75,
        validators=[MinValueValidator(0)],
        verbose_name="Gewerbe-Aufschlag",
        help_text="Aufschlag für gewerbliche Teilnehmer als Dezimalzahl (z.B. 0.75 für 75%)",
    )

    # Tax rate
    vat_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.07,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        verbose_name="Umsatzsteuersatz",
        help_text="Umsatzsteuersatz als Dezimalzahl (z.B. 0.07 für 7%)",
    )

    # Min participants calculation parameters
    min_participants_params = models.JSONField(
        default=default_min_participants_params,
        verbose_name="Min. Teilnehmerzahl Parameter",
        help_text="Parameter für Berechnung der Mindestteilnehmerzahl im Format {threshold: deduction}. "
        "Beispiel: {0: 1, 7: 2} bedeutet: Abzug von 1 für 1-6 Teilnehmer, Abzug von 2 für 7+ Teilnehmer. "
        "Formel: max_participants - deduction (wobei threshold <= max_participants)",
    )

    class Meta:
        verbose_name = "Preiskonfiguration"
        verbose_name_plural = "Preiskonfiguration"

    def __str__(self):
        return "Pricing Configuration"

    @staticmethod
    def _to_decimal(value: int | float | Decimal | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _roundup_euro(value: Decimal) -> Decimal:
        return value.to_integral_value(rounding=ROUND_CEILING).quantize(Decimal("0.01"))

    @property
    def min_participants_thresholds(self) -> list[tuple[int, int]]:
        """Readonly normalized threshold mapping sorted ascending by threshold."""
        raw = self.min_participants_params or {}
        normalized: list[tuple[int, int]] = []
        for threshold, deduction in raw.items():
            normalized.append((int(threshold), int(deduction)))
        normalized.sort(key=lambda item: item[0])
        return normalized

    def get_min_participants(self, max_participants: int) -> int:
        """Apply documented threshold logic: max_participants - deduction."""
        mp = int(max_participants)
        deduction = 0
        for threshold, configured_deduction in self.min_participants_thresholds:
            if threshold <= mp:
                deduction = configured_deduction
            else:
                break
        return max(mp - deduction, 1)

    def get_workshop_rate(self, is_basic_course: bool) -> Decimal:
        return (
            self._to_decimal(self.workshop_rate_basis)
            if is_basic_course
            else self._to_decimal(self.workshop_rate_regular)
        )

    def get_member_regular_price(
        self,
        *,
        duration_hours: int | float | Decimal,
        material_cost: int | float | Decimal,
        max_participants: int,
        is_basic_course: bool,
    ) -> Decimal:
        duration = self._to_decimal(duration_hours)
        material = self._to_decimal(material_cost)
        workshop_rate = self.get_workshop_rate(is_basic_course)
        lecturer_rate = self._to_decimal(self.lecturer_rate)
        prep_hours = self._to_decimal(self.prep_hours)
        vat_rate = self._to_decimal(self.vat_rate)
        min_participants = self.get_min_participants(max_participants)

        value = (
            duration * (workshop_rate + lecturer_rate) + lecturer_rate * prep_hours
        ) * (Decimal("1") + vat_rate) / Decimal(min_participants) + material
        return self._roundup_euro(value)

    def get_member_discounted_price(
        self,
        *,
        duration_hours: int | float | Decimal,
        material_cost: int | float | Decimal,
        max_participants: int,
        is_basic_course: bool,
    ) -> Decimal:
        duration = self._to_decimal(duration_hours)
        material = self._to_decimal(material_cost)
        workshop_rate = self.get_workshop_rate(is_basic_course)
        lecturer_rate = self._to_decimal(self.lecturer_rate)
        prep_hours = self._to_decimal(self.prep_hours)
        vat_rate = self._to_decimal(self.vat_rate)
        discount_rate = self._to_decimal(self.discount_rate)
        min_participants = self.get_min_participants(max_participants)

        value = (
            duration * (workshop_rate * (Decimal("1") - discount_rate) + lecturer_rate)
            + lecturer_rate * prep_hours
        ) * (Decimal("1") + vat_rate) / Decimal(min_participants) + material
        return self._roundup_euro(value)

    def get_guest_regular_price(
        self,
        *,
        duration_hours: int | float | Decimal,
        material_cost: int | float | Decimal,
        max_participants: int,
        is_basic_course: bool,
    ) -> Decimal:
        duration = self._to_decimal(duration_hours)
        material = self._to_decimal(material_cost)
        workshop_rate = self.get_workshop_rate(is_basic_course)
        lecturer_rate = self._to_decimal(self.lecturer_rate)
        prep_hours = self._to_decimal(self.prep_hours)
        guest_surcharge = self._to_decimal(self.guest_surcharge)
        vat_rate = self._to_decimal(self.vat_rate)
        min_participants = self.get_min_participants(max_participants)

        value = (
            duration * (workshop_rate + guest_surcharge + lecturer_rate)
            + lecturer_rate * prep_hours
        ) * (Decimal("1") + vat_rate) / Decimal(min_participants) + material
        return self._roundup_euro(value)

    def get_guest_discounted_price(
        self,
        *,
        duration_hours: int | float | Decimal,
        material_cost: int | float | Decimal,
        max_participants: int,
        is_basic_course: bool,
    ) -> Decimal:
        # Matches the documentation sheet behavior exactly.
        return self.get_member_regular_price(
            duration_hours=duration_hours,
            material_cost=material_cost,
            max_participants=max_participants,
            is_basic_course=is_basic_course,
        )

    def get_business_net_price(
        self,
        *,
        duration_hours: int | float | Decimal,
        material_cost: int | float | Decimal,
        max_participants: int,
        is_basic_course: bool,
    ) -> Decimal:
        duration = self._to_decimal(duration_hours)
        material = self._to_decimal(material_cost)
        workshop_rate = self.get_workshop_rate(is_basic_course)
        lecturer_rate = self._to_decimal(self.lecturer_rate)
        prep_hours = self._to_decimal(self.prep_hours)
        guest_surcharge = self._to_decimal(self.guest_surcharge)
        business_surcharge = self._to_decimal(self.business_surcharge)
        min_participants = self.get_min_participants(max_participants)

        base = self._roundup_euro(
            (
                (
                    duration * (workshop_rate + guest_surcharge + lecturer_rate)
                    + lecturer_rate * prep_hours
                )
                / Decimal(min_participants)
                + material
            )
        )
        price = (Decimal(base) * (Decimal("1") + business_surcharge)).quantize(
            Decimal("0.01")
        )
        return self._roundup_euro(price)

    def get_calculated_prices(
        self,
        *,
        duration_hours: int | float | Decimal,
        material_cost: int | float | Decimal,
        max_participants: int,
        is_basic_course: bool,
    ) -> "CalculatedPriceValues":
        member_regular = self.get_member_regular_price(
            duration_hours=duration_hours,
            material_cost=material_cost,
            max_participants=max_participants,
            is_basic_course=is_basic_course,
        )
        return CalculatedPriceValues(
            member_regular_gross_eur=member_regular,
            member_discounted_gross_eur=self.get_member_discounted_price(
                duration_hours=duration_hours,
                material_cost=material_cost,
                max_participants=max_participants,
                is_basic_course=is_basic_course,
            ),
            guest_regular_gross_eur=self.get_guest_regular_price(
                duration_hours=duration_hours,
                material_cost=material_cost,
                max_participants=max_participants,
                is_basic_course=is_basic_course,
            ),
            guest_discounted_gross_eur=self.get_guest_discounted_price(
                duration_hours=duration_hours,
                material_cost=material_cost,
                max_participants=max_participants,
                is_basic_course=is_basic_course,
            ),
            business_net_eur=self.get_business_net_price(
                duration_hours=duration_hours,
                material_cost=material_cost,
                max_participants=max_participants,
                is_basic_course=is_basic_course,
            ),
        )


@dataclass(frozen=True)
class CalculatedPriceValues:
    """Readonly calculated prices derived from one course configuration."""

    member_regular_gross_eur: Decimal
    member_discounted_gross_eur: Decimal
    guest_regular_gross_eur: Decimal
    guest_discounted_gross_eur: Decimal
    business_net_eur: Decimal


class CalculatedPrices(HistoricalMetaBase):
    """Persisted event prices. Empty fields are auto-filled from proposal data."""

    event = models.OneToOneField(
        "apiv1.Event",
        on_delete=models.CASCADE,
        related_name="calculated_prices",
    )
    pricing_configuration = models.ForeignKey(
        PretixPricingConfiguration,
        on_delete=models.SET_NULL,
        related_name="calculated_prices",
        null=True,
        blank=True,
        default=None,
    )
    member_regular_gross_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )
    member_discounted_gross_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )
    guest_regular_gross_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )
    guest_discounted_gross_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )
    business_net_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )

    class Meta:
        verbose_name = "Berechnete Eventpreise"
        verbose_name_plural = "Berechnete Eventpreise"

    def __str__(self):
        return f"Calculated prices for event {self.event_id}"

    @property
    def proposal(self):
        if not self.event_id:
            return None
        return self.event.proposal

    @property
    def duration_hours(self) -> Decimal:
        proposal = self.proposal
        if proposal is None:
            return Decimal("0")
        total_minutes = time_string_to_minutes(proposal.duration_time_per_day) * int(
            proposal.duration_days
        )
        return Decimal(total_minutes) / Decimal("60")

    @property
    def max_participants(self) -> int:
        proposal = self.proposal
        return int(proposal.max_participants) if proposal is not None else 0

    @property
    def material_cost(self) -> Decimal:
        proposal = self.proposal
        return (
            Decimal(str(proposal.material_cost_eur))
            if proposal is not None
            else Decimal("0")
        )

    @property
    def is_basic_course(self) -> bool:
        proposal = self.proposal
        return bool(proposal.is_basic_course) if proposal is not None else False

    @staticmethod
    def _get_default_pricing_configuration() -> PretixPricingConfiguration:
        latest = PretixPricingConfiguration.objects.order_by("-created_at").first()
        if latest is not None:
            return latest
        return PretixPricingConfiguration.objects.create()

    def clean(self):
        super().clean()

        if not self.event_id:
            return
        if self.proposal is None:
            raise ValidationError(
                {"event": "Linked event must have a proposal to calculate prices."}
            )
        if getattr(self, "_skip_price_generation", False):
            return
        if self.pricing_configuration_id is None:
            self.pricing_configuration = self._get_default_pricing_configuration()

        calculated = self.pricing_configuration.get_calculated_prices(
            duration_hours=self.duration_hours,
            material_cost=self.material_cost,
            max_participants=self.max_participants,
            is_basic_course=self.is_basic_course,
        )

        if self.member_regular_gross_eur is None:
            self.member_regular_gross_eur = calculated.member_regular_gross_eur
        if self.member_discounted_gross_eur is None:
            self.member_discounted_gross_eur = calculated.member_discounted_gross_eur
        if self.guest_regular_gross_eur is None:
            self.guest_regular_gross_eur = calculated.guest_regular_gross_eur
        if self.guest_discounted_gross_eur is None:
            self.guest_discounted_gross_eur = calculated.guest_discounted_gross_eur
        if self.business_net_eur is None:
            self.business_net_eur = calculated.business_net_eur

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
