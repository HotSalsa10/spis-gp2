"""
spis/models/expiry_advisor.py
------------------------------
Phase 8.5 expiry-aware offer advisor.

Analyses inventory batches approaching their expiry date and recommends
discount tiers to recover revenue before stock becomes unsellable.

Discount tier logic — 2-factor (days_to_expiry × risk_ratio):
    risk_ratio = units_at_risk / quantity  (how much of the batch won't sell)

    > 90 days  : no action needed
    60-90 days :
        low  risk (<0.33) -> Monitor        (no discount, watch closely)
        med  risk (0.33-0.66) -> 10% off    "Early Discount"
        high risk (>0.66) -> 15% off        "Early Discount"
    30-59 days :
        low  risk (<0.33) -> 10% off        "Special Offer"
        med  risk (0.33-0.66) -> 20% off    "Special Offer"
        high risk (>0.66) -> 30% off        "Special Offer"
    < 30 days  : return_to_supplier         "Cannot Dispense"
                 (< 30 days remaining shelf life: unsafe to dispense to patients
                  per GCC/international GDP best practice)
    expired    : write_off

Usage:
    from spis.models.expiry_advisor import assess_all_batches
    offers = assess_all_batches(batches, demand_by_atc)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Discount tier constants
# ---------------------------------------------------------------------------

TIER_NO_ACTION: int = 90    # > 90d  -> no action
TIER_EARLY_MIN: int = 60    # 60-90d -> "Early Discount" (10% or 15% based on risk)
TIER_SPECIAL_MIN: int = 30  # 30-59d -> "Special Offer"  (10%, 20%, or 30%)
                             # < 30d  -> return_to_supplier "Cannot Dispense"

# Risk ratio thresholds (units_at_risk / quantity)
RISK_LOW: float = 0.33      # < 0.33  -> low risk
RISK_HIGH: float = 0.66     # > 0.66  -> high risk (between = medium)

# ---------------------------------------------------------------------------
# ExpiryOffer result object (immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpiryOffer:
    """
    Immutable result record for a single batch expiry recommendation.

    Attributes:
        atc_code                  : ATC-4 code (e.g. "M01AE")
        batch_number              : Batch identifier (e.g. "LOT-2026-001")
        quantity                  : Units in this batch
        expiry_date               : Expiry date (ISO string "YYYY-MM-DD")
        days_to_expiry            : Calendar days from today to expiry_date
        forecasted_sales_before_expiry : Expected units sold before expiry date
        units_at_risk             : max(0, quantity - forecasted_sales_before_expiry)
        unit_cost                 : Cost per unit (for waste value calculation)
        waste_value               : units_at_risk * unit_cost
        suggested_discount_pct    : Discount percentage (0, 10, 15, 20, or 30)
        offer_label               : Human-readable tier label
        action                    : Short action string (e.g. "promote", "return")
    """

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


# ---------------------------------------------------------------------------
# Pure classification function
# ---------------------------------------------------------------------------


def classify_discount(
    days_to_expiry: int,
    risk_ratio: float = 0.5,
) -> tuple[int, str, str]:
    """
    Map days-to-expiry + risk_ratio to a discount tier.

    Args:
        days_to_expiry: Integer days from today to the batch expiry date.
                        Negative values mean the batch has already expired.
        risk_ratio:     Fraction of the batch that demand won't cover before
                        expiry (units_at_risk / quantity).  Range [0, 1].
                        Default 0.5 (medium risk).

    Returns:
        (discount_pct, offer_label, action) tuple.
        discount_pct is one of 0, 10, 15, 20, or 30.
    """
    if days_to_expiry < 0:
        return (0, "Expired", "write_off")
    if days_to_expiry < TIER_SPECIAL_MIN:        # < 30 days
        return (0, "Cannot Dispense", "return_to_supplier")
    if days_to_expiry < TIER_EARLY_MIN:           # 30-59 days  "Special Offer"
        if risk_ratio < RISK_LOW:
            return (10, "Special Offer", "promote")
        if risk_ratio <= RISK_HIGH:
            return (20, "Special Offer", "promote")
        return (30, "Special Offer", "promote")
    if days_to_expiry <= TIER_NO_ACTION:          # 60-90 days  "Early Discount"
        if risk_ratio < RISK_LOW:
            return (0, "Monitor", "none")
        if risk_ratio <= RISK_HIGH:
            return (10, "Early Discount", "promote")
        return (15, "Early Discount", "promote")
    return (0, "OK", "none")                      # > 90 days


# ---------------------------------------------------------------------------
# Per-batch assessment
# ---------------------------------------------------------------------------


def assess_batch(
    batch: dict,
    daily_demand: float,
    today: datetime.date | None = None,
) -> ExpiryOffer | None:
    """
    Assess a single inventory batch and return an ExpiryOffer if action needed.

    Returns None when:
        - days_to_expiry > 90 (no action needed yet), or
        - units_at_risk == 0 (all stock will be sold before expiry), or
        - days_to_expiry < 0 (already expired — caller decides handling).

    Args:
        batch        : Dict with keys: atc_code, batch_number, quantity,
                       unit_cost, expiry_date (ISO string), notes.
        daily_demand : Average daily demand for this ATC code (units/day).
        today        : Reference date (default: datetime.date.today()).

    Returns:
        ExpiryOffer or None.
    """
    if today is None:
        today = datetime.date.today()

    expiry = datetime.date.fromisoformat(batch["expiry_date"])
    days_to_expiry = (expiry - today).days

    # No action needed: too far out or already expired
    if days_to_expiry > TIER_NO_ACTION or days_to_expiry < 0:
        return None

    # Forecast how many units will be sold in the remaining window
    quantity = float(batch["quantity"])
    forecasted_sales = max(0.0, daily_demand * days_to_expiry)
    units_at_risk = max(0.0, quantity - forecasted_sales)

    # Skip batches with zero risk (demand covers full stock before expiry)
    if units_at_risk == 0.0:
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


# ---------------------------------------------------------------------------
# Batch orchestrator
# ---------------------------------------------------------------------------


def assess_all_batches(
    batches: list[dict],
    demand_by_atc: dict[str, float],
    today: datetime.date | None = None,
) -> list[ExpiryOffer]:
    """
    Assess all inventory batches and return actionable ExpiryOffer records.

    Args:
        batches       : List of batch dicts (from load_batches()).
        demand_by_atc : Dict mapping atc_code -> daily_demand (units/day).
                        Codes missing from this dict are treated as 0 demand.
        today         : Reference date (default: datetime.date.today()).

    Returns:
        List of ExpiryOffer records sorted by days_to_expiry ascending
        (most urgent first).
    """
    if today is None:
        today = datetime.date.today()

    offers: list[ExpiryOffer] = []
    for batch in batches:
        daily_demand = demand_by_atc.get(batch["atc_code"], 0.0)
        offer = assess_batch(batch, daily_demand, today)
        if offer is not None:
            offers.append(offer)

    return sorted(offers, key=lambda o: o.days_to_expiry)
