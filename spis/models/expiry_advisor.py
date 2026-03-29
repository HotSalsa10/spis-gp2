"""
spis/models/expiry_advisor.py
------------------------------
Phase 8.5 expiry-aware offer advisor.

Analyses inventory batches approaching their expiry date and recommends
discount tiers to recover revenue before stock becomes unsellable.

Discount tier logic (days_to_expiry):
    > 60 days : no action needed
    45-60 days: 15% off  -- "Buy More" promotion
    30-44 days: 25% off  -- "Special Offer"
    14-29 days: 40% off  -- "Clearance"
     7-13 days: 55% off  -- "Final Week"
    < 7 days  : return_to_supplier / write-off

Usage:
    from spis.models.expiry_advisor import assess_all_batches
    offers = assess_all_batches(batches, demand_by_atc)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Discount tier constants (days_to_expiry boundaries)
# ---------------------------------------------------------------------------

TIER_BUY_MORE_MAX: int = 60    # > 60d  -> no action
TIER_BUY_MORE_MIN: int = 45    # 45-60d -> 15% off
TIER_SPECIAL_MIN: int = 30     # 30-44d -> 25% off
TIER_CLEARANCE_MIN: int = 14   # 14-29d -> 40% off
TIER_FINAL_WEEK_MIN: int = 7   # 7-13d  -> 55% off
                               # < 7d   -> return/write-off

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
        suggested_discount_pct    : Discount percentage (0, 15, 25, 40, or 55)
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


def classify_discount(days_to_expiry: int) -> tuple[int, str, str]:
    """
    Map days-to-expiry to a discount tier.

    Args:
        days_to_expiry: Integer days from today to the batch expiry date.
                        Negative values mean the batch has already expired.

    Returns:
        (discount_pct, offer_label, action) tuple.
        discount_pct is one of 0, 15, 25, 40, 55.
    """
    if days_to_expiry < 0:
        return (0, "Expired", "write_off")
    if days_to_expiry < TIER_FINAL_WEEK_MIN:
        return (55, "Final Week", "return_to_supplier")
    if days_to_expiry < TIER_CLEARANCE_MIN:
        return (55, "Final Week", "promote")
    if days_to_expiry < TIER_SPECIAL_MIN:
        return (40, "Clearance", "promote")
    if days_to_expiry < TIER_BUY_MORE_MIN:
        return (25, "Special Offer", "promote")
    if days_to_expiry <= TIER_BUY_MORE_MAX:
        return (15, "Buy More", "promote")
    return (0, "OK", "none")


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
        - days_to_expiry > 60 (no action needed yet), or
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
    if days_to_expiry > TIER_BUY_MORE_MAX or days_to_expiry < 0:
        return None

    # Forecast how many units will be sold in the remaining window
    forecasted_sales = max(0.0, daily_demand * days_to_expiry)
    units_at_risk = max(0.0, float(batch["quantity"]) - forecasted_sales)

    # Skip batches with zero risk (demand covers full stock before expiry)
    if units_at_risk == 0.0:
        return None

    unit_cost = float(batch["unit_cost"])
    waste_value = units_at_risk * unit_cost
    discount_pct, offer_label, action = classify_discount(days_to_expiry)

    return ExpiryOffer(
        atc_code=batch["atc_code"],
        batch_number=batch["batch_number"],
        quantity=float(batch["quantity"]),
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
