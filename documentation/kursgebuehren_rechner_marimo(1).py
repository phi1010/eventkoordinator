import marimo

__generated_with = "0.19.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import math
    import pandas as pd
    import marimo as mo
    return math, mo, pd


@app.cell
def _(mo):
    mo.md(r"""
    # Kursgebühren-Rechner

    Interaktive Marimo-Version der bereitgestellten Kalkulation.

    Die Formeln wurden **möglichst nah am Tabellenblatt** umgesetzt, inklusive Rundungen und der Beispielrechnungen.
    """)
    return


@app.cell
def _(basis_course, max_participants, mo):
    min_participants = mo.ui.number(value=max_participants.value - (1 if max_participants.value <= 6 else 2), start=1, step=1, label="Min. Teilnehmerzahl", disabled=True)
    prep_hours = mo.ui.number(value=0.0, start=0, step=0.25, label="Vorbereitung (Stunden)", disabled=True)
    lecturer_rate = mo.ui.number(value=40.0, start=0, step=1.0, label="Dozent:in Honorar pro Stunde (€)", disabled=True)
    workshop_rate = mo.ui.number(value=10.0 if basis_course.value else 20.0, start=0, step=1.0, label="Werkstatt & ZAM pro Stunde (€)", disabled=True)
    guest_surcharge = mo.ui.number(value=10.0, start=0, step=1.0, label="Gäst:in-Aufschlag pro Stunde (€)", disabled=True)
    discount_rate = mo.ui.number(value=0.50, start=0, step=0.05, label="Ermäßigungssatz", disabled=True)
    business_surcharge = mo.ui.number(value=0.75, start=0, step=0.05, label="Gewerbe-Aufschlag", disabled=True)
    vat_rate = mo.ui.number(value=0.07, start=0, step=0.01, label="USt.", disabled=True)
    return (
        business_surcharge,
        discount_rate,
        guest_surcharge,
        lecturer_rate,
        min_participants,
        prep_hours,
        vat_rate,
        workshop_rate,
    )


@app.cell
def _(mo):
    duration_hours = mo.ui.number(value=1.5, start=0, step=0.25, label="**Kursdauer (Stunden)**")
    material_cost = mo.ui.number(value=3.0, start=0, step=0.5, label="**Materialkosten pro Person (€)**")
    max_participants = mo.ui.number(value=8, start=1, step=1, label="**Max. Teilnehmerzahl**")
    basis_course = mo.ui.checkbox(value=True, label="**Ist Grundkurs** (Grundkurs: 10 EUR; Regelfall: 20 EUR)")
    return basis_course, duration_hours, material_cost, max_participants


@app.cell
def _(
    basis_course,
    business_surcharge,
    discount_rate,
    duration_hours,
    guest_surcharge,
    lecturer_rate,
    material_cost,
    max_participants,
    min_participants,
    mo,
    prep_hours,
    vat_rate,
    workshop_rate,
):
    mo.vstack(
        [
            mo.md("## Eingaben"),
            mo.vstack([min_participants, max_participants]),
            mo.vstack([duration_hours, material_cost, prep_hours]),
            mo.vstack([lecturer_rate, basis_course, workshop_rate, guest_surcharge]),
            mo.vstack([discount_rate, business_surcharge, vat_rate]),
        ]
    )
    return


@app.cell
def _(math):
    # Spreadsheet-like rounding up to full euros
    def roundup_euro(value: float) -> int:
        return math.ceil(value)

    def lecturer_honorarium(duration_hours: float, lecturer_rate: float) -> float:
        return duration_hours * lecturer_rate

    def member_fee_regular(
        duration_hours: float,
        workshop_rate: float,
        lecturer_rate: float,
        prep_hours: float,
        vat_rate: float,
        min_participants: int,
        material_cost: float,
    ) -> int:
        return roundup_euro(
            (
                duration_hours * (workshop_rate + lecturer_rate)
                + lecturer_rate * prep_hours
            )
            * (1 + vat_rate)
            / min_participants
            + material_cost
        )

    def member_fee_discounted(
        duration_hours: float,
        workshop_rate: float,
        lecturer_rate: float,
        prep_hours: float,
        vat_rate: float,
        min_participants: int,
        material_cost: float,
        discount_rate: float,
    ) -> int:
        return roundup_euro(
            (
                duration_hours * (workshop_rate * (1 - discount_rate) + lecturer_rate)
                + lecturer_rate * prep_hours
            )
            * (1 + vat_rate)
            / min_participants
            + material_cost
        )

    def guest_fee_regular(
        duration_hours: float,
        workshop_rate: float,
        guest_surcharge: float,
        lecturer_rate: float,
        prep_hours: float,
        vat_rate: float,
        min_participants: int,
        material_cost: float,
    ) -> int:
        return roundup_euro(
            (
                duration_hours * (workshop_rate + guest_surcharge + lecturer_rate)
                + lecturer_rate * prep_hours
            )
            * (1 + vat_rate)
            / min_participants
            + material_cost
        )

    def guest_fee_discounted_like_sheet(member_regular_fee: int) -> int:
        # The original sheet references =B19 here.
        # This preserves the spreadsheet logic exactly as provided.
        return member_regular_fee

    def business_fee_net(
        duration_hours: float,
        workshop_rate: float,
        guest_surcharge: float,
        lecturer_rate: float,
        prep_hours: float,
        min_participants: int,
        material_cost: float,
        business_surcharge: float,
    ) -> int:
        return roundup_euro(
            (
                (
                    duration_hours
                    * (workshop_rate + guest_surcharge + lecturer_rate)
                    + lecturer_rate * prep_hours
                )
                / min_participants
                + material_cost
            )
        ) * (1 + business_surcharge)

    def example_row(
        label: str,
        participants: int,
        price_per_person: float,
        duration_hours: float,
        lecturer_rate: float,
        prep_hours: float,
        material_cost: float,
        vat_rate: float,
    ) -> dict:
        costs = duration_hours * (lecturer_rate + prep_hours) + material_cost * participants
        revenue = participants * price_per_person
        workshop_net = (revenue / (1 + vat_rate) - costs) / 2
        zam_net = workshop_net
        lecturer_gross = lecturer_honorarium(duration_hours, lecturer_rate)
        material_gross = participants * material_cost
        return {
            "Beispiel": label,
            "Kosten": round(costs, 2),
            "Einnahmen": round(revenue, 2),
            "Werkstatt (netto)": round(workshop_net, 2),
            "ZAM (netto)": round(zam_net, 2),
            "Dozent:in (brutto)": round(lecturer_gross, 2),
            "Material (brutto)": round(material_gross, 2),
        }
    return (
        business_fee_net,
        example_row,
        guest_fee_discounted_like_sheet,
        guest_fee_regular,
        lecturer_honorarium,
        member_fee_discounted,
        member_fee_regular,
    )


@app.cell
def _(
    business_fee_net,
    business_surcharge,
    discount_rate,
    duration_hours,
    example_row,
    guest_fee_discounted_like_sheet,
    guest_fee_regular,
    guest_surcharge,
    lecturer_honorarium,
    lecturer_rate,
    material_cost,
    max_participants,
    member_fee_discounted,
    member_fee_regular,
    min_participants,
    mo,
    pd,
    prep_hours,
    vat_rate,
    workshop_rate,
):
    min_p = int(min_participants.value)
    max_p = int(max_participants.value)
    duration = float(duration_hours.value)
    material = float(material_cost.value)
    prep = float(prep_hours.value)
    lecturer = float(lecturer_rate.value)
    workshop = float(workshop_rate.value)
    guest_extra = float(guest_surcharge.value)
    discount = float(discount_rate.value)
    business_extra = float(business_surcharge.value)
    vat = float(vat_rate.value)

    honorarium = lecturer_honorarium(duration, lecturer)
    fee_member_regular = member_fee_regular(
        duration, workshop, lecturer, prep, vat, min_p, material
    )
    fee_member_discounted = member_fee_discounted(
        duration, workshop, lecturer, prep, vat, min_p, material, discount
    )
    fee_guest_regular = guest_fee_regular(
        duration, workshop, guest_extra, lecturer, prep, vat, min_p, material
    )
    fee_guest_discounted = guest_fee_discounted_like_sheet(fee_member_regular)
    fee_business_net = business_fee_net(
        duration, workshop, guest_extra, lecturer, prep, min_p, material, business_extra
    )

    fee_table = pd.DataFrame(
        [
            {
                "Kategorie": "Mitglied",
                "regulär": fee_member_regular,
                "ermäßigt": fee_member_discounted,
                "Art": "brutto",
                "p.P. pro Stunde regulär": round(fee_member_regular / duration, 2),
                "p.P. pro Stunde ermäßigt": round(fee_member_discounted / duration, 2),
            },
            {
                "Kategorie": "Gäst:in",
                "regulär": fee_guest_regular,
                "ermäßigt": fee_guest_discounted,
                "Art": "brutto",
                "p.P. pro Stunde regulär": round(fee_guest_regular / duration, 2),
                "p.P. pro Stunde ermäßigt": round(fee_guest_discounted / duration, 2),
            },
            {
                "Kategorie": "Gewerbe",
                "regulär": round(fee_business_net, 2),
                "ermäßigt": None,
                "Art": "netto",
                "p.P. pro Stunde regulär": round(fee_business_net / duration, 2),
                "p.P. pro Stunde ermäßigt": None,
            },
        ]
    )

    examples = pd.DataFrame(
        [
            example_row(
                f"bei {min_p} Mitgliedern mit Ermäßigung",
                min_p,
                fee_member_discounted,
                duration,
                lecturer,
                prep,
                material,
                vat,
            ),
            example_row(
                f"bei {min_p} Mitgliedern",
                min_p,
                fee_member_regular,
                duration,
                lecturer,
                prep,
                material,
                vat,
            ),
            example_row(
                f"bei {max_p} Gäst:innen",
                max_p,
                fee_guest_regular,
                duration,
                lecturer,
                prep,
                material,
                vat,
            ),
        ]
    )

    acceptance_note = (
        f"Ausfallregel laut Notiz: max-1 bei ≤ 6 TN, sonst max-2. "
        f"Bei aktueller Mindestteilnehmerzahl {min_p} entspräche das "
        f"{max(min_p - 1, 0)} bestätigten Zusagen als praktische Untergrenze."
        if min_p <= 6
        else f"Ausfallregel laut Notiz: max-1 bei ≤ 6 TN, sonst max-2. "
             f"Bei aktueller Mindestteilnehmerzahl {min_p} entspräche das "
             f"{max(min_p - 2, 0)} bestätigten Zusagen als praktische Untergrenze."
    )

    mo.vstack(
        [
            mo.md("## Kernergebnisse"),
            mo.md(
                f"""
                - **Honorar an Dozent:in :** {honorarium:.2f} €
                - **USt.:** {vat:.0%}
                - **Hinweis:** {acceptance_note}
                """
            ),
            mo.md("## Teilnahmegebühren"),
            fee_table,
            mo.md("## Beispielrechnungen"),
            examples,
        ]
    )
    return (
        fee_business_net,
        fee_guest_discounted,
        fee_guest_regular,
        fee_member_discounted,
        fee_member_regular,
        max_p,
        min_p,
    )


@app.cell
def _(
    fee_business_net,
    fee_guest_discounted,
    fee_guest_regular,
    fee_member_discounted,
    fee_member_regular,
    max_p,
    min_p,
    mo,
):
    participant_count = mo.ui.slider(
        start=1, stop=max(max_p, 1), step=1, value=min_p, label="Teilnehmerzahl"
    )
    participant_type = mo.ui.dropdown(
        options={
            "Mitglied regulär": "member_regular",
            "Mitglied ermäßigt": "member_discounted",
            "Gäst:in regulär": "guest_regular",
            "Gäst:in ermäßigt (wie Tabellenblatt)": "guest_discounted",
            "Gewerbe": "business",
        },
        value="Mitglied regulär",
        label="Tarif",
    )

    fees = {
        "member_regular": fee_member_regular,
        "member_discounted": fee_member_discounted,
        "guest_regular": fee_guest_regular,
        "guest_discounted": fee_guest_discounted,
        "business": fee_business_net,
    }

    labels = {
        "member_regular": "Mitglied regulär",
        "member_discounted": "Mitglied ermäßigt",
        "guest_regular": "Gäst:in regulär",
        "guest_discounted": "Gäst:in ermäßigt (wie Tabellenblatt)",
        "business": "Gewerbe",
    }
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Organisatorische Hinweise

    - **Zusage/Absage:** 5 Tage vor Termin
    - **Rücktrittregel:** Rückerstattung bis 5 Tage vor Termin möglich (Kulanz)
    - Danach nur, wenn jemand einspringt, z. B. aus der Warteliste

    ## Anmerkungen

    - VHS + JuKS: 40 €/h, Vorbereitung wird nicht vergütet (eigentlich 60 €/90 min)
    - Stadtmuseum: 30 €/h + 250–500 € für Konzeption
    """)
    return


if __name__ == "__main__":
    app.run()
