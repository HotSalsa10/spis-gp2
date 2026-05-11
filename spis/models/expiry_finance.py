"""SAR aggregates over the offer list."""
from __future__ import annotations

_IRRECOVERABLE = {"Cannot Dispense", "Expired"}


def compute_value_at_risk(offers: list) -> float:
    return round(sum(o.waste_value for o in offers), 2)


def compute_recovered(offers: list, batches: list[dict]) -> float:
    """Revenue we can still recover via discounts."""
    discount_map = {b["batch_number"]: b["applied_discount"] for b in batches}
    total = 0.0
    for o in offers:
        if o.offer_label in _IRRECOVERABLE:
            continue  # nothing to recover
        discount_pct = discount_map.get(o.batch_number, o.suggested_discount_pct) or 0.0
        total += o.units_at_risk * o.unit_cost * (1.0 - discount_pct / 100.0)
    return round(total, 2)


def compute_waste(offers: list, batches: list[dict]) -> float:
    """Money we just lose (write-offs + returns)."""
    returned_set = {b["batch_number"] for b in batches if b.get("returned")}
    total = 0.0
    for o in offers:
        if o.offer_label in _IRRECOVERABLE or o.batch_number in returned_set:
            total += o.waste_value
    return round(total, 2)


def waste_by_atc(offers: list) -> dict[str, float]:
    result: dict[str, float] = {}
    for o in offers:
        result[o.atc_code] = round(result.get(o.atc_code, 0.0) + o.waste_value, 2)
    return result
