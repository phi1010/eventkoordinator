from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from simple_history.models import HistoricalRecords
from solo.models import SingletonModel

from project.basemodels import HistoricalMetaBase


def default_min_participants_params():
    """
    Default parameters for minimum participants calculation.
    Format: {threshold: deduction}
    Logic: max_participants - deduction where threshold <= max_participants
    Example: {0: 1, 7: 2} means deduct 1 for 1-6 participants, deduct 2 for 7+ participants
    """
    return {
        0: 1,
        7: 2
    }


class PricingConfiguration(SingletonModel):
    """
    Global pricing configuration for course fee calculation.

    Based on Kursgebühren-Rechner (documentation/kursgebuehren_rechner_marimo(1).py).
    Contains all configurable parameters that are NOT course-specific.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(inherit=True)

    # Preparation and lecturer rates
    prep_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        validators=[MinValueValidator(0)],
        verbose_name="Vorbereitungszeit (Stunden)",
        help_text="Standard-Vorbereitungszeit in Stunden"
    )

    lecturer_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=40.0,
        validators=[MinValueValidator(0)],
        verbose_name="Dozent:in Honorar pro Stunde (€)",
        help_text="Honorar für Dozent:innen pro Stunde"
    )

    # Workshop rates (different for basis courses vs regular courses)
    workshop_rate_basis = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=10.0,
        validators=[MinValueValidator(0)],
        verbose_name="Werkstatt & ZAM Satz Grundkurs (€/h)",
        help_text="Stundensatz für Werkstatt & ZAM bei Grundkursen"
    )

    workshop_rate_regular = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=20.0,
        validators=[MinValueValidator(0)],
        verbose_name="Werkstatt & ZAM Satz Regelfall (€/h)",
        help_text="Stundensatz für Werkstatt & ZAM bei regulären Kursen"
    )

    # Surcharges and discounts
    guest_surcharge = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=10.0,
        validators=[MinValueValidator(0)],
        verbose_name="Gäst:in-Aufschlag (€/h)",
        help_text="Aufschlag für Gäste pro Stunde"
    )

    discount_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.50,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        verbose_name="Ermäßigungssatz",
        help_text="Ermäßigungssatz als Dezimalzahl (z.B. 0.50 für 50%)"
    )

    business_surcharge = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.75,
        validators=[MinValueValidator(0)],
        verbose_name="Gewerbe-Aufschlag",
        help_text="Aufschlag für gewerbliche Teilnehmer als Dezimalzahl (z.B. 0.75 für 75%)"
    )

    # Tax rate
    vat_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.07,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        verbose_name="Umsatzsteuersatz",
        help_text="Umsatzsteuersatz als Dezimalzahl (z.B. 0.07 für 7%)"
    )

    # Min participants calculation parameters
    min_participants_params = models.JSONField(
        default=default_min_participants_params,
        verbose_name="Min. Teilnehmerzahl Parameter",
        help_text="Parameter für Berechnung der Mindestteilnehmerzahl im Format {threshold: deduction}. "
                  "Beispiel: {0: 1, 7: 2} bedeutet: Abzug von 1 für 1-6 Teilnehmer, Abzug von 2 für 7+ Teilnehmer. "
                  "Formel: max_participants - deduction (wobei threshold <= max_participants)"
    )

    class Meta:
        verbose_name = "Preiskonfiguration"
        verbose_name_plural = "Preiskonfiguration"

    def __str__(self):
        return "Pricing Configuration"