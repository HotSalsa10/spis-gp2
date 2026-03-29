"""
tests/test_expiry_advisor.py
-----------------------------
Unit tests for spis.models.expiry_advisor.

All tests are pure-logic (no database, no model artifacts required).
"""

import datetime

import pytest

from spis.models.expiry_advisor import (
    ExpiryOffer,
    TIER_BUY_MORE_MAX,
    assess_all_batches,
    assess_batch,
    classify_discount,
)

# ---------------------------------------------------------------------------
# Reference date used across all tests
# ---------------------------------------------------------------------------

TODAY = datetime.date(2026, 3, 29)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _batch(
    atc_code: str = "M01AE",
    batch_number: str = "LOT-TEST-001",
    quantity: float = 100.0,
    unit_cost: float = 1.0,
    expiry_date: str = "2026-04-08",   # 10 days out from TODAY
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


# ---------------------------------------------------------------------------
# Tests: classify_discount
# ---------------------------------------------------------------------------


def test_classify_discount_buy_more():
    """45-60 days -> 15% Buy More."""
    pct, label, action = classify_discount(50)
    assert pct == 15
    assert label == "Buy More"
    assert action == "promote"


def test_classify_discount_special_offer():
    """30-44 days -> 25% Special Offer."""
    pct, label, action = classify_discount(35)
    assert pct == 25
    assert label == "Special Offer"
    assert action == "promote"


def test_classify_discount_clearance():
    """14-29 days -> 40% Clearance."""
    pct, label, action = classify_discount(20)
    assert pct == 40
    assert label == "Clearance"
    assert action == "promote"


def test_classify_discount_final_week():
    """7-13 days -> 55% Final Week."""
    pct, label, action = classify_discount(10)
    assert pct == 55
    assert label == "Final Week"
    assert action == "promote"


def test_classify_discount_return_to_supplier():
    """< 7 days -> 55% Final Week, return_to_supplier action."""
    pct, label, action = classify_discount(3)
    assert pct == 55
    assert label == "Final Week"
    assert action == "return_to_supplier"


def test_classify_discount_no_action():
    """61+ days -> 0% OK, no action."""
    pct, label, action = classify_discount(61)
    assert pct == 0
    assert label == "OK"
    assert action == "none"


def test_classify_discount_expired():
    """Negative days -> Expired, write_off."""
    pct, label, action = classify_discount(-1)
    assert pct == 0
    assert label == "Expired"
    assert action == "write_off"


# ---------------------------------------------------------------------------
# Tests: assess_batch
# ---------------------------------------------------------------------------


def test_assess_batch_returns_none_when_too_far_out():
    """Batches > 60 days out should return None (no action needed)."""
    b = _batch(expiry_date="2026-06-28")  # ~91 days from TODAY
    result = assess_batch(b, daily_demand=5.0, today=TODAY)
    assert result is None


def test_assess_batch_returns_none_when_demand_covers_stock():
    """When forecasted sales >= quantity, units_at_risk == 0 -> None."""
    b = _batch(quantity=50.0, expiry_date="2026-04-28")  # 30 days out
    # daily_demand=5.0 -> forecast = 5 * 30 = 150 > 50
    result = assess_batch(b, daily_demand=5.0, today=TODAY)
    assert result is None


def test_assess_batch_returns_none_when_already_expired():
    """Expired batches (negative days) -> None."""
    b = _batch(expiry_date="2026-03-20")  # 9 days before TODAY
    result = assess_batch(b, daily_demand=2.0, today=TODAY)
    assert result is None


def test_assess_batch_returns_offer_when_units_at_risk():
    """Batch with low demand and near expiry should yield an ExpiryOffer."""
    b = _batch(quantity=100.0, unit_cost=0.5, expiry_date="2026-04-08")  # 10 days
    result = assess_batch(b, daily_demand=2.0, today=TODAY)
    assert result is not None
    assert isinstance(result, ExpiryOffer)
    assert result.days_to_expiry == 10
    assert result.units_at_risk == pytest.approx(80.0)   # 100 - 2*10
    assert result.waste_value == pytest.approx(40.0)      # 80 * 0.5
    assert result.suggested_discount_pct == 55


def test_assess_batch_waste_value_calculation():
    """waste_value = units_at_risk * unit_cost."""
    b = _batch(quantity=200.0, unit_cost=0.25, expiry_date="2026-04-23")  # 25 days
    # daily_demand=3 -> forecast=75, units_at_risk=125
    result = assess_batch(b, daily_demand=3.0, today=TODAY)
    assert result is not None
    assert result.units_at_risk == pytest.approx(125.0)
    assert result.waste_value == pytest.approx(31.25)


# ---------------------------------------------------------------------------
# Tests: assess_all_batches
# ---------------------------------------------------------------------------


def test_assess_all_batches_returns_sorted_by_urgency():
    """Results should be sorted ascending by days_to_expiry."""
    batches = [
        _batch(batch_number="B1", expiry_date="2026-04-28"),  # 30d
        _batch(batch_number="B2", expiry_date="2026-04-08"),  # 10d
        _batch(batch_number="B3", expiry_date="2026-04-18"),  # 20d
    ]
    demand = {"M01AE": 0.5}   # low demand -> all have units_at_risk
    offers = assess_all_batches(batches, demand, today=TODAY)
    days = [o.days_to_expiry for o in offers]
    assert days == sorted(days)


def test_assess_all_batches_skips_fully_covered_batches():
    """Batches where demand covers all stock should not appear in results."""
    batches = [
        _batch(quantity=10.0, expiry_date="2026-04-08"),   # 10d, demand=5 -> safe
    ]
    demand = {"M01AE": 5.0}   # 5 * 10 = 50 >= 10 -> no risk
    offers = assess_all_batches(batches, demand, today=TODAY)
    assert offers == []


def test_assess_all_batches_handles_missing_demand_key():
    """ATC codes not in demand_by_atc should be treated as zero demand."""
    batches = [_batch(quantity=50.0, expiry_date="2026-04-08")]
    offers = assess_all_batches(batches, demand_by_atc={}, today=TODAY)
    assert len(offers) == 1
    assert offers[0].units_at_risk == pytest.approx(50.0)
