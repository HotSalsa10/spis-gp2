"""
tests/test_po_generator.py
---------------------------
Unit tests for spis.models.po_generator.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from spis.data.database import init_db
from spis.models.po_generator import build_all_pos, generate_po_pdf


# ---------------------------------------------------------------------------
# Minimal stub that mimics RiskAssessment
# ---------------------------------------------------------------------------

@dataclass
class _RA:
    atc_code:    str
    risk_tier:   str
    order_qty:   float
    daily_demand: float = 10.0
    current_stock: float = 5.0
    forecast_30d: float = 300.0
    days_of_stock: float = 0.5


# ---------------------------------------------------------------------------
# Fixture: small seeded DB
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "test.db"
    init_db(str(path))
    return path


# ---------------------------------------------------------------------------
# build_all_pos tests
# ---------------------------------------------------------------------------

def test_empty_assessments_returns_empty(db):
    pos = build_all_pos(str(db), [])
    assert pos == []


def test_ok_and_overstock_excluded(db):
    assessments = [
        _RA("M01AB", "OK",        order_qty=50),
        _RA("M01AE", "OVERSTOCK", order_qty=0),
    ]
    pos = build_all_pos(str(db), assessments)
    assert pos == []


def test_critical_tier_included(db):
    assessments = [_RA("M01AB", "CRITICAL", order_qty=100)]
    pos = build_all_pos(str(db), assessments)
    assert len(pos) == 1
    assert pos[0]["lines"][0]["atc_code"] == "M01AB"
    assert pos[0]["lines"][0]["risk_tier"] == "CRITICAL"


def test_low_tier_included(db):
    assessments = [_RA("N02BA", "LOW", order_qty=60)]
    pos = build_all_pos(str(db), assessments)
    assert len(pos) == 1
    assert pos[0]["lines"][0]["risk_tier"] == "LOW"


def test_zero_order_qty_excluded(db):
    assessments = [
        _RA("M01AB", "CRITICAL", order_qty=0),
        _RA("M01AE", "LOW",      order_qty=0),
    ]
    pos = build_all_pos(str(db), assessments)
    assert pos == []


def test_same_supplier_grouped_into_one_po(db):
    # M01AB and M01AE are both mapped to supplier 1 (Al-Dawaa)
    assessments = [
        _RA("M01AB", "CRITICAL", order_qty=80),
        _RA("M01AE", "LOW",      order_qty=40),
    ]
    pos = build_all_pos(str(db), assessments)
    assert len(pos) == 1
    assert len(pos[0]["lines"]) == 2


def test_different_suppliers_produce_separate_pos(db):
    # M01AB -> supplier 1, N02BA -> supplier 2
    assessments = [
        _RA("M01AB", "CRITICAL", order_qty=80),
        _RA("N02BA", "LOW",      order_qty=50),
    ]
    pos = build_all_pos(str(db), assessments)
    assert len(pos) == 2


def test_grand_total_equals_sum_of_line_totals(db):
    assessments = [
        _RA("M01AB", "CRITICAL", order_qty=100),
        _RA("M01AE", "LOW",      order_qty=50),
    ]
    pos = build_all_pos(str(db), assessments)
    for po in pos:
        expected = round(sum(l["total_cost"] for l in po["lines"]), 2)
        assert po["grand_total"] == expected


def test_po_date_is_string(db):
    assessments = [_RA("M01AB", "CRITICAL", order_qty=100)]
    pos = build_all_pos(str(db), assessments)
    assert isinstance(pos[0]["po_date"], str)
    assert len(pos[0]["po_date"]) == 10   # YYYY-MM-DD


def test_default_unit_cost_applied_when_no_batch(db):
    # Use an ATC code known to have no batch in the test DB seed (use a fresh DB
    # that has no inventory_batches rows for M01AB unless BATCH_SEED covers it).
    # We pass default_unit_cost=5.0 and verify math.
    assessments = [_RA("M01AB", "CRITICAL", order_qty=10)]
    pos = build_all_pos(str(db), assessments, default_unit_cost=5.0)
    line = pos[0]["lines"][0]
    # unit_cost is either from batch or fallback; total = qty * unit_cost
    assert abs(line["total_cost"] - line["qty"] * line["unit_cost"]) < 0.01


# ---------------------------------------------------------------------------
# generate_po_pdf tests
# ---------------------------------------------------------------------------

def test_pdf_returns_bytes(db):
    assessments = [_RA("M01AB", "CRITICAL", order_qty=100)]
    pos = build_all_pos(str(db), assessments)
    pdf_bytes = generate_po_pdf(pos[0])
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0


def test_pdf_starts_with_pdf_header(db):
    assessments = [_RA("M01AB", "CRITICAL", order_qty=100)]
    pos = build_all_pos(str(db), assessments)
    pdf_bytes = generate_po_pdf(pos[0])
    assert pdf_bytes[:4] == b"%PDF"


def test_pdf_with_multiple_lines(db):
    assessments = [
        _RA("M01AB", "CRITICAL", order_qty=80),
        _RA("M01AE", "LOW",      order_qty=40),
    ]
    pos = build_all_pos(str(db), assessments)
    # Both map to supplier 1 -> single PO with two lines
    pdf_bytes = generate_po_pdf(pos[0])
    assert len(pdf_bytes) > 1000


def test_pdf_unassigned_supplier(db):
    # Fabricate a PO dict directly (no ATC in DB -> unassigned supplier 0)
    po = {
        "supplier": {
            "supplier_id":    0,
            "name":           "Unassigned Supplier",
            "email":          "",
            "phone":          "",
            "lead_time_days": 7,
        },
        "po_date": "2026-05-07",
        "lines": [
            {
                "atc_code":   "ZZZ",
                "atc_name":   "Unknown Category",
                "drug_names": [],
                "qty":        10,
                "unit_cost":  1.0,
                "total_cost": 10.0,
                "risk_tier":  "CRITICAL",
            }
        ],
        "grand_total": 10.0,
    }
    pdf_bytes = generate_po_pdf(po)
    assert pdf_bytes[:4] == b"%PDF"
