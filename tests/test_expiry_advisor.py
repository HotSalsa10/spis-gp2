
import datetime

import pytest

from spis.models.expiry_advisor import (
    ExpiryOffer,
    RISK_HIGH,
    RISK_LOW,
    TIER_NO_ACTION,
    assess_all_batches,
    assess_batch,
    classify_discount,
)


TODAY = datetime.date(2026, 3, 30)


def _batch(
    atc_code: str = "M01AE",
    batch_number: str = "LOT-TEST-001",
    quantity: float = 100.0,
    unit_cost: float = 1.0,
    expiry_date: str = "2026-04-15",   # 16 days out from TODAY
    notes: str = "",
) -> dict:
    return {
        "atc_code":     atc_code,
        "batch_number": batch_number,
        "quantity":     quantity,
        "unit_cost":    unit_cost,
        "expiry_date":  expiry_date,
        "notes":        notes,
    }


def test_classify_discount_no_action():
    """91+ days -> 0% OK, no action."""
    pct, label, action = classify_discount(91)
    assert pct == 0
    assert label == "OK"
    assert action == "none"


def test_classify_discount_expired():
    """Negative days -> Expired, write_off."""
    pct, label, action = classify_discount(-1)
    assert pct == 0
    assert label == "Expired"
    assert action == "write_off"


def test_classify_discount_cannot_dispense():
    """< 30 days -> Cannot Dispense regardless of risk."""
    pct, label, action = classify_discount(20)
    assert pct == 0
    assert label == "Cannot Dispense"
    assert action == "return_to_supplier"


def test_classify_discount_cannot_dispense_near_expiry():
    """3 days -> also Cannot Dispense."""
    pct, label, action = classify_discount(3)
    assert pct == 0
    assert label == "Cannot Dispense"
    assert action == "return_to_supplier"


# --- 60-90 day window ---

def test_classify_discount_early_high_risk():
    """60-90 days + high risk (>66%) -> 15% Early Discount."""
    pct, label, action = classify_discount(75, risk_ratio=0.8)
    assert pct == 15
    assert label == "Early Discount"
    assert action == "promote"


def test_classify_discount_early_medium_risk():
    """60-90 days + medium risk (33-66%) -> 10% Early Discount."""
    pct, label, action = classify_discount(75, risk_ratio=0.5)
    assert pct == 10
    assert label == "Early Discount"
    assert action == "promote"


def test_classify_discount_early_low_risk():
    """60-90 days + low risk (<33%) -> 0% Monitor, no action."""
    pct, label, action = classify_discount(75, risk_ratio=0.2)
    assert pct == 0
    assert label == "Monitor"
    assert action == "none"


def test_classify_discount_early_lower_boundary():
    """Exactly 60 days + medium risk -> Early Discount."""
    pct, label, action = classify_discount(60, risk_ratio=0.5)
    assert pct == 10
    assert label == "Early Discount"
    assert action == "promote"


def test_classify_discount_early_upper_boundary():
    """Exactly 90 days + high risk -> Early Discount (still within window)."""
    pct, label, action = classify_discount(90, risk_ratio=0.8)
    assert pct == 15
    assert label == "Early Discount"
    assert action == "promote"


# --- 30-59 day window ---

def test_classify_discount_special_high_risk():
    """30-59 days + high risk (>66%) -> 30% Special Offer."""
    pct, label, action = classify_discount(45, risk_ratio=0.8)
    assert pct == 30
    assert label == "Special Offer"
    assert action == "promote"


def test_classify_discount_special_medium_risk():
    """30-59 days + medium risk (33-66%) -> 20% Special Offer."""
    pct, label, action = classify_discount(45, risk_ratio=0.5)
    assert pct == 20
    assert label == "Special Offer"
    assert action == "promote"


def test_classify_discount_special_low_risk():
    """30-59 days + low risk (<33%) -> 10% Special Offer."""
    pct, label, action = classify_discount(45, risk_ratio=0.2)
    assert pct == 10
    assert label == "Special Offer"
    assert action == "promote"


def test_classify_discount_special_lower_boundary():
    """Exactly 30 days -> Special Offer (medium risk)."""
    pct, label, action = classify_discount(30, risk_ratio=0.5)
    assert pct == 20
    assert label == "Special Offer"
    assert action == "promote"


def test_classify_discount_risk_boundaries():
    """Tier constants RISK_LOW and RISK_HIGH must match published values."""
    assert RISK_LOW == 0.33
    assert RISK_HIGH == 0.66


def test_assess_batch_returns_none_when_too_far_out():
    """Batches > 90 days out should return None (no action needed)."""
    b = _batch(expiry_date="2026-07-05")  # 97 days from TODAY
    result = assess_batch(b, daily_demand=5.0, today=TODAY)
    assert result is None


def test_assess_batch_returns_none_when_demand_covers_stock():
    """When forecasted sales >= quantity, units_at_risk == 0 -> None."""
    b = _batch(quantity=50.0, expiry_date="2026-05-09")  # 40 days out
    # daily_demand=5.0 -> forecast = 5 * 40 = 200 > 50
    result = assess_batch(b, daily_demand=5.0, today=TODAY)
    assert result is None


def test_assess_batch_returns_none_when_already_expired():
    """Expired batches (negative days) -> None."""
    b = _batch(expiry_date="2026-03-20")  # 10 days before TODAY
    result = assess_batch(b, daily_demand=2.0, today=TODAY)
    assert result is None


def test_assess_batch_returns_offer_when_units_at_risk():
    """Batch with low demand and near expiry should yield an ExpiryOffer."""
    b = _batch(quantity=100.0, unit_cost=0.5, expiry_date="2026-04-15")  # 16 days
    result = assess_batch(b, daily_demand=2.0, today=TODAY)
    assert result is not None
    assert isinstance(result, ExpiryOffer)
    assert result.days_to_expiry == 16
    assert result.units_at_risk == pytest.approx(68.0)   # 100 - 2*16
    assert result.waste_value == pytest.approx(34.0)      # 68 * 0.5
    assert result.suggested_discount_pct == 0             # Cannot Dispense
    assert result.action == "return_to_supplier"


def test_assess_batch_waste_value_calculation():
    """waste_value = units_at_risk * unit_cost.  risk_ratio=80/200=0.4 -> 20% Special Offer."""
    b = _batch(quantity=200.0, unit_cost=0.25, expiry_date="2026-05-09")  # 40 days
    # daily_demand=3 -> forecast=120, units_at_risk=80
    result = assess_batch(b, daily_demand=3.0, today=TODAY)
    assert result is not None
    assert result.units_at_risk == pytest.approx(80.0)
    assert result.waste_value == pytest.approx(20.0)
    assert result.suggested_discount_pct == 20   # risk_ratio=0.4 (medium) -> 20%
    assert result.action == "promote"


def test_assess_all_batches_returns_sorted_by_urgency():
    """Results should be sorted ascending by days_to_expiry."""
    batches = [
        _batch(batch_number="B1", expiry_date="2026-05-09"),  # 40d
        _batch(batch_number="B2", expiry_date="2026-04-15"),  # 16d
        _batch(batch_number="B3", expiry_date="2026-04-29"),  # 30d
    ]
    demand = {"M01AE": 0.5}   # low demand -> all have units_at_risk
    offers = assess_all_batches(batches, demand, today=TODAY)
    days = [o.days_to_expiry for o in offers]
    assert days == sorted(days)


def test_assess_all_batches_skips_fully_covered_batches():
    """Batches where demand covers all stock should not appear in results."""
    batches = [
        _batch(quantity=10.0, expiry_date="2026-04-29"),   # 30d, demand=5 -> safe
    ]
    demand = {"M01AE": 5.0}   # 5 * 30 = 150 >= 10 -> no risk
    offers = assess_all_batches(batches, demand, today=TODAY)
    assert offers == []


def test_assess_all_batches_handles_missing_demand_key():
    """ATC codes not in demand_by_atc should be treated as zero demand."""
    batches = [_batch(quantity=50.0, expiry_date="2026-04-15")]
    offers = assess_all_batches(batches, demand_by_atc={}, today=TODAY)
    assert len(offers) == 1
    assert offers[0].units_at_risk == pytest.approx(50.0)
