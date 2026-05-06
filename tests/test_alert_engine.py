"""
tests/test_alert_engine.py
--------------------------
Unit tests for spis.models.alert_engine and the alert-related helpers
in spis.data.database.

All tests use a temporary SQLite database so they never touch data/inventory.db.
"""

import pytest

from spis.data.database import (
    acknowledge_alert,
    alert_key_exists,
    create_alert,
    get_all_alerts,
    get_open_alerts,
    init_db,
)
from spis.models.alert_engine import Alert, alerts_from_expiry, alerts_from_risk, refresh
from spis.models.expiry_advisor import ExpiryOffer
from spis.models.risk_classifier import RiskAssessment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    db = tmp_path / "test_alerts.db"
    init_db(db)
    return db


def _make_ra(atc_code: str, risk_tier: str, days_of_stock: float = 5.0) -> RiskAssessment:
    """Build a minimal RiskAssessment for testing."""
    return RiskAssessment(
        atc_code=atc_code,
        current_stock=50.0,
        forecast_30d=300.0,
        daily_demand=10.0,
        days_of_stock=days_of_stock,
        risk_tier=risk_tier,
        order_qty=max(0.0, 300.0 - 50.0),
    )


def _make_offer(
    atc_code: str,
    batch_number: str,
    action: str,
    days_to_expiry: int = 20,
) -> ExpiryOffer:
    """Build a minimal ExpiryOffer for testing."""
    return ExpiryOffer(
        atc_code=atc_code,
        batch_number=batch_number,
        quantity=100.0,
        expiry_date="2026-06-01",
        days_to_expiry=days_to_expiry,
        forecasted_sales_before_expiry=30.0,
        units_at_risk=70.0,
        unit_cost=0.50,
        waste_value=35.0,
        suggested_discount_pct=25,
        offer_label="Special Offer",
        action=action,
    )


# ---------------------------------------------------------------------------
# Tests: alerts_from_risk
# ---------------------------------------------------------------------------


def test_critical_tier_generates_critical_low_stock_alert():
    """CRITICAL risk tier must produce a LOW_STOCK alert with severity CRITICAL."""
    ra = _make_ra("N02BE", "CRITICAL", days_of_stock=2.0)
    alerts = alerts_from_risk([ra])

    assert len(alerts) == 1
    assert alerts[0].alert_type == "LOW_STOCK"
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].atc_code == "N02BE"
    assert alerts[0].batch_number is None
    assert "N02BE" in alerts[0].message


def test_low_tier_generates_warning_low_stock_alert():
    """LOW risk tier must produce a LOW_STOCK alert with severity WARNING."""
    ra = _make_ra("M01AB", "LOW", days_of_stock=9.0)
    alerts = alerts_from_risk([ra])

    assert len(alerts) == 1
    assert alerts[0].alert_type == "LOW_STOCK"
    assert alerts[0].severity == "WARNING"
    assert alerts[0].atc_code == "M01AB"


def test_ok_and_overstock_tiers_produce_no_alerts():
    """OK and OVERSTOCK tiers must not generate any LOW_STOCK alerts."""
    assessments = [
        _make_ra("N05B", "OK",        days_of_stock=30.0),
        _make_ra("M01AE", "OVERSTOCK", days_of_stock=100.0),
    ]
    alerts = alerts_from_risk(assessments)
    assert len(alerts) == 0


def test_alerts_from_risk_mixed_tiers():
    """Only CRITICAL and LOW tiers contribute; OK is skipped."""
    assessments = [
        _make_ra("N02BE", "CRITICAL"),
        _make_ra("M01AB", "LOW"),
        _make_ra("N05B",  "OK"),
    ]
    alerts = alerts_from_risk(assessments)
    assert len(alerts) == 2


# ---------------------------------------------------------------------------
# Tests: alerts_from_expiry
# ---------------------------------------------------------------------------


def test_write_off_action_generates_critical_expiry_alert():
    """action='write_off' must produce severity CRITICAL."""
    offer = _make_offer("M01AE", "LOT-TEST-001", "write_off", days_to_expiry=-1)
    alerts = alerts_from_expiry([offer])

    assert len(alerts) == 1
    assert alerts[0].alert_type == "EXPIRY"
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].batch_number == "LOT-TEST-001"


def test_return_to_supplier_action_generates_warning_expiry_alert():
    """action='return_to_supplier' must produce severity WARNING."""
    offer = _make_offer("R06", "LOT-TEST-002", "return_to_supplier", days_to_expiry=15)
    alerts = alerts_from_expiry([offer])

    assert len(alerts) == 1
    assert alerts[0].severity == "WARNING"


def test_promote_within_30d_generates_warning():
    """action='promote' with days_to_expiry <= 30 must produce severity WARNING."""
    offer = _make_offer("N02BA", "LOT-TEST-003", "promote", days_to_expiry=25)
    alerts = alerts_from_expiry([offer])

    assert alerts[0].severity == "WARNING"


def test_promote_beyond_30d_generates_info():
    """action='promote' with days_to_expiry > 30 must produce severity INFO."""
    offer = _make_offer("N02BA", "LOT-TEST-004", "promote", days_to_expiry=60)
    alerts = alerts_from_expiry([offer])

    assert alerts[0].severity == "INFO"


def test_none_action_skipped():
    """action='none' must produce no alerts."""
    offer = _make_offer("R06", "LOT-TEST-005", "none", days_to_expiry=95)
    alerts = alerts_from_expiry([offer])
    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Tests: refresh (idempotency + DB persistence)
# ---------------------------------------------------------------------------


def test_refresh_inserts_new_alerts(tmp_db):
    """refresh() must insert alerts for CRITICAL/LOW risk tiers."""
    assessments = [_make_ra("N02BE", "CRITICAL"), _make_ra("M01AB", "LOW")]
    count = refresh(tmp_db, assessments, [])

    assert count == 2
    open_alerts = get_open_alerts(tmp_db)
    assert len(open_alerts) == 2


def test_refresh_is_idempotent(tmp_db):
    """Calling refresh() twice with the same state must not duplicate alerts."""
    assessments = [_make_ra("N02BE", "CRITICAL")]

    first = refresh(tmp_db, assessments, [])
    second = refresh(tmp_db, assessments, [])

    assert first == 1
    assert second == 0
    assert len(get_open_alerts(tmp_db)) == 1


def test_refresh_after_acknowledge_creates_new_alert(tmp_db):
    """After acknowledging the open alert, refresh() may insert a fresh one."""
    assessments = [_make_ra("N02BE", "CRITICAL")]

    refresh(tmp_db, assessments, [])
    open_alerts = get_open_alerts(tmp_db)
    acknowledge_alert(tmp_db, open_alerts[0]["alert_id"])

    second = refresh(tmp_db, assessments, [])
    assert second == 1
    assert len(get_open_alerts(tmp_db)) == 1


# ---------------------------------------------------------------------------
# Tests: acknowledge_alert
# ---------------------------------------------------------------------------


def test_acknowledge_removes_from_open_count(tmp_db):
    """Acknowledging an alert must remove it from get_open_alerts()."""
    create_alert(tmp_db, "LOW_STOCK", "R03", None, "CRITICAL", "test alert")
    open_before = get_open_alerts(tmp_db)
    assert len(open_before) == 1

    acknowledge_alert(tmp_db, open_before[0]["alert_id"])

    open_after = get_open_alerts(tmp_db)
    assert len(open_after) == 0

    all_alerts = get_all_alerts(tmp_db)
    assert len(all_alerts) == 1
    assert all_alerts[0]["acknowledged_at"] is not None


def test_alert_key_exists_dedup_check(tmp_db):
    """alert_key_exists() must return True only while alert is open."""
    create_alert(tmp_db, "LOW_STOCK", "M01AB", None, "WARNING", "low stock")

    assert alert_key_exists(tmp_db, "LOW_STOCK", "M01AB", None) is True

    open_alerts = get_open_alerts(tmp_db)
    acknowledge_alert(tmp_db, open_alerts[0]["alert_id"])

    assert alert_key_exists(tmp_db, "LOW_STOCK", "M01AB", None) is False


def test_init_db_creates_alerts_table(tmp_db):
    """alerts table must exist after init_db."""
    import sqlite3
    with sqlite3.connect(tmp_db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "alerts" in tables
