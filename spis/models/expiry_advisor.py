"""Expiry-aware discount advisor (two-factor: days x risk_ratio)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

# day-window thresholds
TIER_NO_ACTION: int = 90     # >90d nothing
TIER_EARLY_MIN: int = 60     # 60-90d "Early Discount"
TIER_SPECIAL_MIN: int = 30   # 30-59d "Special Offer"
                              # <30d cannot dispense (GCC GDP)

# risk_ratio = units_at_risk / quantity
RISK_LOW: float = 0.33
RISK_HIGH: float = 0.66


@dataclass(frozen=True)
class ExpiryOffer:
    atc_code: str
    batch_number: str
    quantity: float
    expiry_date: str
    days_to_expiry: int
    forecasted_sales_before_expiry: float
    units_at_risk: float
    unit_cost: float
    waste_value: float
    suggested_discount_pct: int
    offer_label: str
    action: str


def classify_discount(
    days_to_expiry: int,
    risk_ratio: float = 0.5,
) -> tuple[int, str, str]:
    if days_to_expiry < 0:
        return (0, "Expired", "write_off")
    if days_to_expiry < TIER_SPECIAL_MIN:
        return (0, "Cannot Dispense", "return_to_supplier")
    if days_to_expiry < TIER_EARLY_MIN:
        # 30-59d special offer
        if risk_ratio < RISK_LOW:
            return (10, "Special Offer", "promote")
        if risk_ratio <= RISK_HIGH:
            return (20, "Special Offer", "promote")
        return (30, "Special Offer", "promote")
    if days_to_expiry <= TIER_NO_ACTION:
        # 60-90d early discount
        if risk_ratio < RISK_LOW:
            return (0, "Monitor", "none")
        if risk_ratio <= RISK_HIGH:
            return (10, "Early Discount", "promote")
        return (15, "Early Discount", "promote")
    return (0, "OK", "none")


def assess_batch(
    batch: dict,
    daily_demand: float,
    today: datetime.date | None = None,
) -> ExpiryOffer | None:
    """Return offer or None if no action needed."""
    if today is None:
        today = datetime.date.today()

    expiry = datetime.date.fromisoformat(batch["expiry_date"])
    days_to_expiry = (expiry - today).days

    if days_to_expiry > TIER_NO_ACTION or days_to_expiry < 0:
        return None

    quantity = float(batch["quantity"])
    forecasted_sales = max(0.0, daily_demand * days_to_expiry)
    units_at_risk = max(0.0, quantity - forecasted_sales)

    if units_at_risk == 0.0:
        # demand will absorb everything before it expires, skip
        return None

    unit_cost = float(batch["unit_cost"])
    waste_value = units_at_risk * unit_cost
    risk_ratio = units_at_risk / quantity if quantity > 0 else 0.0
    discount_pct, offer_label, action = classify_discount(days_to_expiry, risk_ratio)

    return ExpiryOffer(
        atc_code=batch["atc_code"],
        batch_number=batch["batch_number"],
        quantity=quantity,
        expiry_date=batch["expiry_date"],
        days_to_expiry=days_to_expiry,
        forecasted_sales_before_expiry=forecasted_sales,
        units_at_risk=units_at_risk,
        unit_cost=unit_cost,
        waste_value=waste_value,
        suggested_discount_pct=discount_pct,
        offer_label=offer_label,
        action=action,
    )


def assess_all_batches(
    batches: list[dict],
    demand_by_atc: dict[str, float],
    today: datetime.date | None = None,
) -> list[ExpiryOffer]:
    """Most urgent first."""
    if today is None:
        today = datetime.date.today()

    offers: list[ExpiryOffer] = []
    for batch in batches:
        daily_demand = demand_by_atc.get(batch["atc_code"], 0.0)
        offer = assess_batch(batch, daily_demand, today)
        if offer is not None:
            offers.append(offer)

    return sorted(offers, key=lambda o: o.days_to_expiry)
