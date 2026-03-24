"""
tests/test_risk_classifier.py
------------------------------
Pytest suite for spis.models.risk_classifier (Phase 4).
Uses synthetic fixtures -- no database or CSV files required for unit tests.

Coverage:
    classify_risk          -- boundary values for all 4 tiers
    calculate_order_qty    -- normal, overstock, safety buffer, zero demand
    build_risk_assessment  -- immutability, field correctness, zero demand
    forecast_30_days       -- returns float >= 0, deterministic, unknown ATC raises
    load_atc_inventory     -- reads from SQLite, returns dict
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

from spis.models.risk_classifier import (
    TIER_CRITICAL,
    TIER_LOW,
    TIER_OK,
    RiskAssessment,
    build_risk_assessment,
    calculate_order_qty,
    classify_risk,
    forecast_30_days,
    load_atc_inventory,
)
from spis.models.forecaster import FEATURE_COLS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ATC_CODES = ["M01AB", "M01AE", "N02BA", "N02BE", "N05B", "N05C", "R03", "R06"]


@pytest.fixture
def tiny_encoder() -> LabelEncoder:
    """LabelEncoder fitted on all 8 ATC codes (deterministic ordering)."""
    enc = LabelEncoder()
    enc.fit(ATC_CODES)
    return enc


@pytest.fixture
def tiny_model(tiny_encoder: LabelEncoder) -> XGBRegressor:
    """
    Tiny XGBRegressor (n_estimators=10) trained on random data.
    Fast to fit; only needs to produce non-negative predictions.
    """
    rng = np.random.RandomState(0)
    n = 200
    X = pd.DataFrame(rng.uniform(0, 10, size=(n, len(FEATURE_COLS))), columns=FEATURE_COLS)
    y = rng.uniform(5, 15, size=n)
    model = XGBRegressor(n_estimators=10, random_state=0, n_jobs=1)
    model.fit(X, y)
    return model


@pytest.fixture
def seed_row(tiny_encoder: LabelEncoder) -> pd.DataFrame:
    """One-row DataFrame with all FEATURE_COLS for ATC code M01AB."""
    atc_encoded = int(tiny_encoder.transform(["M01AB"])[0])
    data = {col: [5.0] for col in FEATURE_COLS}
    data["atc_encoded"] = [atc_encoded]
    data["day_of_week"] = [0]
    data["day_of_month"] = [15]
    data["month"] = [6]
    data["year"] = [2020]
    data["week_of_year"] = [25]
    data["is_weekend"] = [0]
    data["is_holiday"] = [0]
    data["season"] = [3]
    data["is_payday_window"] = [1]
    data["is_school_holiday"] = [1]
    data["quarter"] = [2]
    data["days_to_month_end"] = [15]
    return pd.DataFrame(data)


@pytest.fixture
def tiny_inventory_db(tmp_path: Path) -> Path:
    """Minimal SQLite db with atc_inventory table for load_atc_inventory tests."""
    db_path = tmp_path / "test_inventory.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE atc_inventory (
                atc_code      TEXT PRIMARY KEY,
                current_stock REAL NOT NULL,
                last_updated  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                notes         TEXT
            )
        """)
        conn.executemany(
            "INSERT INTO atc_inventory (atc_code, current_stock) VALUES (?,?)",
            [("M01AB", 60.0), ("N02BE", 40.0), ("R03", 25.0)],
        )
        conn.commit()
    return db_path


# ---------------------------------------------------------------------------
# Tests -- classify_risk
# ---------------------------------------------------------------------------

def test_classify_risk_critical():
    """Days of stock below TIER_CRITICAL threshold -> CRITICAL."""
    assert classify_risk(0.0) == "CRITICAL"
    assert classify_risk(TIER_CRITICAL - 0.001) == "CRITICAL"


def test_classify_risk_low():
    """Days of stock at or above TIER_CRITICAL but below TIER_LOW -> LOW."""
    assert classify_risk(TIER_CRITICAL) == "LOW"
    assert classify_risk(TIER_LOW - 0.001) == "LOW"


def test_classify_risk_ok():
    """Days of stock at or above TIER_LOW but below TIER_OK -> OK."""
    assert classify_risk(TIER_LOW) == "OK"
    assert classify_risk(TIER_OK - 0.001) == "OK"


def test_classify_risk_overstock():
    """Days of stock at or above TIER_OK -> OVERSTOCK."""
    assert classify_risk(TIER_OK) == "OVERSTOCK"
    assert classify_risk(1000.0) == "OVERSTOCK"


def test_classify_risk_uses_constants():
    """Tier thresholds must match the published module constants."""
    assert TIER_CRITICAL == 3.0
    assert TIER_LOW == 7.0
    assert TIER_OK == 30.0


# ---------------------------------------------------------------------------
# Tests -- calculate_order_qty
# ---------------------------------------------------------------------------

def test_calculate_order_qty_basic():
    """Order qty = forecast + buffer - current_stock when positive."""
    # daily_demand=5, safety_days=3 -> buffer=15
    # forecast_30d=150, current_stock=50 -> order = 150+15-50 = 115
    result = calculate_order_qty(
        current_stock=50.0, forecast_30d=150.0, daily_demand=5.0, safety_days=3.0
    )
    assert abs(result - 115.0) < 1e-6


def test_calculate_order_qty_overstock_returns_zero():
    """When current stock exceeds forecast + buffer, order qty is 0 (not negative)."""
    result = calculate_order_qty(
        current_stock=500.0, forecast_30d=100.0, daily_demand=5.0, safety_days=3.0
    )
    assert result == 0.0


def test_calculate_order_qty_includes_safety_buffer():
    """Safety buffer = daily_demand * safety_days must be added to forecast."""
    qty_no_buffer = calculate_order_qty(
        current_stock=0.0, forecast_30d=100.0, daily_demand=5.0, safety_days=0.0
    )
    qty_with_buffer = calculate_order_qty(
        current_stock=0.0, forecast_30d=100.0, daily_demand=5.0, safety_days=3.0
    )
    assert qty_with_buffer > qty_no_buffer
    assert abs(qty_with_buffer - qty_no_buffer - 15.0) < 1e-6  # buffer = 5*3 = 15


def test_calculate_order_qty_zero_daily_demand():
    """Zero daily demand -> buffer is 0; function must not raise."""
    result = calculate_order_qty(
        current_stock=0.0, forecast_30d=100.0, daily_demand=0.0, safety_days=3.0
    )
    assert result == 100.0  # no buffer, just replenish to forecast


# ---------------------------------------------------------------------------
# Tests -- build_risk_assessment
# ---------------------------------------------------------------------------

def test_build_risk_assessment_returns_dataclass():
    """build_risk_assessment must return a RiskAssessment instance."""
    ra = build_risk_assessment(
        atc_code="M01AB", current_stock=60.0,
        forecast_30d=150.0, daily_demand=5.0,
    )
    assert isinstance(ra, RiskAssessment)


def test_build_risk_assessment_immutable():
    """RiskAssessment must be frozen (immutable)."""
    ra = build_risk_assessment(
        atc_code="M01AB", current_stock=60.0,
        forecast_30d=150.0, daily_demand=5.0,
    )
    with pytest.raises((AttributeError, TypeError)):
        ra.risk_tier = "CRITICAL"  # type: ignore[misc]


def test_build_risk_assessment_order_qty_nonnegative():
    """order_qty must never be negative."""
    ra = build_risk_assessment(
        atc_code="M01AB", current_stock=9999.0,
        forecast_30d=10.0, daily_demand=5.0,
    )
    assert ra.order_qty >= 0.0


def test_build_risk_assessment_critical_tier():
    """Low stock + high demand -> CRITICAL tier."""
    ra = build_risk_assessment(
        atc_code="N02BE", current_stock=5.0,
        forecast_30d=200.0, daily_demand=20.0,
    )
    # days_of_stock = 5 / 20 = 0.25 -> CRITICAL
    assert ra.risk_tier == "CRITICAL"
    assert ra.days_of_stock < TIER_CRITICAL


def test_build_risk_assessment_zero_demand():
    """Zero daily demand -> days_of_stock = infinity -> OVERSTOCK (no division by zero)."""
    ra = build_risk_assessment(
        atc_code="N02BA", current_stock=100.0,
        forecast_30d=0.0, daily_demand=0.0,
    )
    assert ra.risk_tier == "OVERSTOCK"
    assert ra.order_qty == 0.0


# ---------------------------------------------------------------------------
# Tests -- forecast_30_days
# ---------------------------------------------------------------------------

def test_forecast_30_days_returns_float(tiny_model, tiny_encoder, seed_row):
    """forecast_30_days must return a non-negative float."""
    start = pd.Timestamp("2020-01-01")
    result = forecast_30_days(tiny_model, tiny_encoder, seed_row, "M01AB", start)
    assert isinstance(result, float)
    assert result >= 0.0


def test_forecast_30_days_deterministic(tiny_model, tiny_encoder, seed_row):
    """Calling twice with same inputs must return the same value."""
    start = pd.Timestamp("2020-06-01")
    r1 = forecast_30_days(tiny_model, tiny_encoder, seed_row, "M01AB", start)
    r2 = forecast_30_days(tiny_model, tiny_encoder, seed_row, "M01AB", start)
    assert r1 == r2


def test_forecast_30_days_unknown_atc_raises(tiny_model, tiny_encoder, seed_row):
    """An ATC code not in the encoder must raise ValueError."""
    with pytest.raises(ValueError, match="ATC code"):
        forecast_30_days(
            tiny_model, tiny_encoder, seed_row, "UNKNOWN", pd.Timestamp("2020-01-01")
        )


# ---------------------------------------------------------------------------
# Tests -- load_atc_inventory
# ---------------------------------------------------------------------------

def test_load_atc_inventory_returns_dict(tiny_inventory_db):
    """load_atc_inventory should return a dict mapping atc_code -> stock float."""
    inv = load_atc_inventory(tiny_inventory_db)
    assert isinstance(inv, dict)
    assert inv["M01AB"] == 60.0
    assert inv["N02BE"] == 40.0
    assert inv["R03"] == 25.0


def test_load_atc_inventory_all_floats(tiny_inventory_db):
    """All values in the returned dict must be float."""
    inv = load_atc_inventory(tiny_inventory_db)
    for val in inv.values():
        assert isinstance(val, float)
