from decimal import Decimal, InvalidOperation
from uuid import UUID

from ninja import Router

import apiv1
import sync_pretix
from apiv1.api_utils import api_permission_mandatory
from apiv1.models import Event
from apiv1.schemas import (
    CalculatedPricesOut,
    CreateCalculatedPricesIn,
    ErrorOut,
    UpdateCalculatedPricesIn,
)
from sync_pretix.models import CalculatedPrices, PretixPricingConfiguration

router = Router()


def _to_schema(instance: CalculatedPrices) -> CalculatedPricesOut:
    return CalculatedPricesOut(
        id=instance.id,
        event_id=instance.event_id,
        pricing_configuration_id=instance.pricing_configuration_id,
        member_regular_gross_eur=(
            str(instance.member_regular_gross_eur)
            if instance.member_regular_gross_eur is not None
            else None
        ),
        member_discounted_gross_eur=(
            str(instance.member_discounted_gross_eur)
            if instance.member_discounted_gross_eur is not None
            else None
        ),
        guest_regular_gross_eur=(
            str(instance.guest_regular_gross_eur)
            if instance.guest_regular_gross_eur is not None
            else None
        ),
        guest_discounted_gross_eur=(
            str(instance.guest_discounted_gross_eur)
            if instance.guest_discounted_gross_eur is not None
            else None
        ),
        business_net_eur=(
            str(instance.business_net_eur) if instance.business_net_eur is not None else None
        ),
    )


def _get_event(series_id: UUID, event_id: UUID) -> Event | None:
    return Event.objects.filter(pk=event_id, series_id=series_id).first()


def _parse_decimal_or_none(raw_value: str | None, field_name: str) -> tuple[Decimal | None, ErrorOut | None]:
    if raw_value is None:
        return None, None

    try:
        return Decimal(raw_value), None
    except (InvalidOperation, TypeError):
        return None, ErrorOut(code="prices.invalidDecimal", detail=f"Invalid decimal value for {field_name}")


@router.get(
    "/{series_id}/events/{event_id}/calculated-prices",
    response={200: CalculatedPricesOut, 401: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def get_calculated_prices(request, series_id: UUID, event_id: UUID):
    event = _get_event(series_id=series_id, event_id=event_id)
    if event is None:
        return 404, ErrorOut(code="events.notFound")

    try:
        instance = CalculatedPrices.objects.get(event=event)
    except CalculatedPrices.DoesNotExist:
        return 404, ErrorOut(code="prices.notFound")

    if not request.user.has_perm((sync_pretix, "view", CalculatedPrices), instance):
        return 401, ErrorOut(code="auth.permissionDenied")

    return 200, _to_schema(instance)


@router.post(
    "/{series_id}/events/{event_id}/calculated-prices/create",
    response={201: CalculatedPricesOut, 400: ErrorOut, 401: ErrorOut, 404: ErrorOut, 409: ErrorOut},
)
@api_permission_mandatory()
def create_calculated_prices(
    request,
    series_id: UUID,
    event_id: UUID,
    payload: CreateCalculatedPricesIn,
):
    event = _get_event(series_id=series_id, event_id=event_id)
    if event is None:
        return 404, ErrorOut(code="events.notFound")

    if not request.user.has_perm("sync_pretix.add_calculatedprices"):
        return 401, ErrorOut(code="auth.permissionDenied")

    if CalculatedPrices.objects.filter(event=event).exists():
        return 409, ErrorOut(code="prices.alreadyExists")

    instance = CalculatedPrices(event=event)
    if payload.use_default_pricing_configuration:
        instance.pricing_configuration = (
            PretixPricingConfiguration.objects.order_by("-created_at").first()
            or PretixPricingConfiguration.objects.create()
        )
    else:
        # Explicitly bypass generation so values remain empty for manual editing.
        instance._skip_price_generation = True

    instance.save()
    return 201, _to_schema(instance)


@router.put(
    "/{series_id}/events/{event_id}/calculated-prices",
    response={200: CalculatedPricesOut, 400: ErrorOut, 401: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def update_calculated_prices(
    request,
    series_id: UUID,
    event_id: UUID,
    payload: UpdateCalculatedPricesIn,
):
    event = _get_event(series_id=series_id, event_id=event_id)
    if event is None:
        return 404, ErrorOut(code="events.notFound")

    try:
        instance = CalculatedPrices.objects.get(event=event)
    except CalculatedPrices.DoesNotExist:
        return 404, ErrorOut(code="prices.notFound")

    if not request.user.has_perm((sync_pretix, "change", CalculatedPrices), instance):
        return 401, ErrorOut(code="auth.permissionDenied")

    update_data = payload.model_dump(exclude_unset=True)

    if "pricing_configuration_id" in update_data:
        pricing_configuration_id = update_data.pop("pricing_configuration_id")
        if pricing_configuration_id is None:
            instance.pricing_configuration = None
        else:
            try:
                instance.pricing_configuration = PretixPricingConfiguration.objects.get(
                    pk=pricing_configuration_id
                )
            except PretixPricingConfiguration.DoesNotExist:
                return 400, ErrorOut(code="prices.configNotFound")

    decimal_fields = (
        "member_regular_gross_eur",
        "member_discounted_gross_eur",
        "guest_regular_gross_eur",
        "guest_discounted_gross_eur",
        "business_net_eur",
    )
    for field_name in decimal_fields:
        if field_name not in update_data:
            continue
        decimal_value, parse_error = _parse_decimal_or_none(
            update_data[field_name],
            field_name,
        )
        if parse_error is not None:
            return 400, parse_error
        setattr(instance, field_name, decimal_value)

    if instance.pricing_configuration_id is None:
        # Keep manual mode stable while editing blank/custom values.
        instance._skip_price_generation = True

    instance.save()
    return 200, _to_schema(instance)


@router.delete(
    "/{series_id}/events/{event_id}/calculated-prices",
    response={204: None, 401: ErrorOut, 404: ErrorOut},
)
@api_permission_mandatory()
def delete_calculated_prices(request, series_id: UUID, event_id: UUID):
    event = _get_event(series_id=series_id, event_id=event_id)
    if event is None:
        return 404, ErrorOut(code="events.notFound")

    try:
        instance = CalculatedPrices.objects.get(event=event)
    except CalculatedPrices.DoesNotExist:
        return 404, ErrorOut(code="prices.notFound")

    if not request.user.has_perm((sync_pretix, "delete", CalculatedPrices), instance):
        return 401, ErrorOut(code="auth.permissionDenied")

    instance.delete()
    return 204, None



