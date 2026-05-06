"""
spis/models/expiry_finance.py
------------------------------
Pure financial calculations for expiry-risk analysis.
All monetary values are in SAR (Saudi Riyals).
"""
from __future__ import annotations

_IRRECOVERABLE = {"Cannot Dispense", "Expired"}


def compute_value_at_risk(offers: list) -> float:
    """Total SAR tied up in at-risk inventory (units_at_risk * unit_cost)."""
    return round(sum(o.waste_value for o in offers), 2)


def compute_recovered(offers: list, batches: list[dict]) -> float:
    """SAR recovered by selling at-risk units at their applied discount.

    Skips cannot-dispense and expired batches (those cannot generate revenue).
    Recovery = units_at_risk * unit_cost * (1 - discount/100).
    """
    discount_map = {b["batch_number"]: b["applied_discount"] for b in batches}
    total = 0.0
    for o in offers:
        if o.offer_label in _IRRECOVERABLE:
            continue
        discount_pct = discount_map.get(o.batch_number, o.suggested_discount_pct) or 0.0
        total += o.units_at_risk * o.unit_cost * (1.0 - discount_pct / 100.0)
    return round(total, 2)


def compute_waste(offers: list, batches: list[dict]) -> float:
    """SAR written off from batches that cannot be dispensed or are returned.

    These batches generate zero revenue; their full waste_value is a direct loss.
    """
    returned_set = {b["batch_number"] for b in batches if b.get("returned")}
    total = 0.0
    for o in offers:
        if o.offer_label in _IRRECOVERABLE or o.batch_number in returned_set:
            total += o.waste_value
    return round(total, 2)


def waste_by_atc(offers: list) -> dict[str, float]:
    """Aggregate waste_value by ATC code. Returns {atc_code: SAR}."""
    result: dict[str, float] = {}
    for o in offers:
        result[o.atc_code] = round(result.get(o.atc_code, 0.0) + o.waste_value, 2)
    return result
