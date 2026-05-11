import pytest
from spis.models.expiry_advisor import ExpiryOffer
from spis.models.expiry_finance import (
    compute_value_at_risk,
    compute_recovered,
    compute_waste,
    waste_by_atc,
)


def _offer(**kwargs) -> ExpiryOffer:
    defaults = {
        "atc_code": "M01AB",
        "batch_number": "LOT-001",
        "quantity": 100.0,
        "expiry_date": "2026-09-01",
        "days_to_expiry": 60,
        "forecasted_sales_before_expiry": 40.0,
        "units_at_risk": 60.0,
        "unit_cost": 10.0,
        "waste_value": 600.0,
        "suggested_discount_pct": 15,
        "offer_label": "Early Discount",
        "action": "promote",
    }
    defaults.update(kwargs)
    return ExpiryOffer(**defaults)


def _batch(batch_number="LOT-001", applied_discount=None, returned=False) -> dict:
    return {"batch_number": batch_number, "applied_discount": applied_discount, "returned": returned}


def test_value_at_risk_single():
    assert compute_value_at_risk([_offer(waste_value=600.0)]) == 600.0


def test_value_at_risk_sum():
    offers = [_offer(waste_value=600.0), _offer(batch_number="LOT-002", waste_value=400.0)]
    assert compute_value_at_risk(offers) == 1000.0


def test_value_at_risk_empty():
    assert compute_value_at_risk([]) == 0.0


def test_recovered_with_15pct_discount():
    # 60 units * SAR10 * (1 - 0.15) = SAR 510.0
    assert compute_recovered([_offer()], [_batch(applied_discount=15)]) == 510.0


def test_recovered_zero_discount():
    # no discount -> full unit cost recovered
    assert compute_recovered([_offer(suggested_discount_pct=0)], [_batch(applied_discount=0)]) == 600.0


def test_recovered_skips_cannot_dispense():
    offer = _offer(offer_label="Cannot Dispense")
    assert compute_recovered([offer], [_batch()]) == 0.0


def test_recovered_skips_expired():
    offer = _offer(offer_label="Expired")
    assert compute_recovered([offer], [_batch()]) == 0.0


def test_recovered_falls_back_to_suggested():
    # applied_discount not in batches list -> use suggested_discount_pct=15
    offer = _offer(suggested_discount_pct=15)
    assert compute_recovered([offer], [_batch(batch_number="OTHER", applied_discount=0)]) == 510.0


def test_waste_cannot_dispense():
    offer = _offer(offer_label="Cannot Dispense", waste_value=600.0)
    assert compute_waste([offer], [_batch(returned=False)]) == 600.0


def test_waste_returned_batch():
    offer = _offer(offer_label="Early Discount", waste_value=600.0)
    assert compute_waste([offer], [_batch(returned=True)]) == 600.0


def test_waste_zero_for_normal_offer():
    offer = _offer(offer_label="Early Discount", waste_value=600.0)
    assert compute_waste([offer], [_batch(returned=False)]) == 0.0


def test_waste_by_atc_groups():
    offers = [
        _offer(atc_code="M01AB", waste_value=300.0),
        _offer(atc_code="M01AB", batch_number="LOT-002", waste_value=200.0),
        _offer(atc_code="N02BE", batch_number="LOT-003", waste_value=150.0),
    ]
    result = waste_by_atc(offers)
    assert result["M01AB"] == 500.0
    assert result["N02BE"] == 150.0


def test_waste_by_atc_empty():
    assert waste_by_atc([]) == {}
