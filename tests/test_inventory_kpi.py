"""
tests/test_inventory_kpi.py
----------------------------
Unit tests for spis.models.inventory_kpi.compute_turnover.

All tests use a minimal in-memory SQLite fixture (no init_db required)
so they run without the Kaggle sales data or model artifacts.
"""

import sqlite3

import pytest

from spis.models.inventory_kpi import _classify, compute_turnover

# ---------------------------------------------------------------------------
# Fixture: minimal DB with only the two tables that compute_turnover reads
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE atc_inventory (
    atc_code      TEXT PRIMARY KEY,
    current_stock REAL NOT NULL,
    last_updated  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes         TEXT
);
CREATE TABLE sales (
    sale_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    atc_code    TEXT NOT NULL,
    sale_date   TEXT NOT NULL,
    hour        INTEGER,
    granularity TEXT NOT NULL,
    quantity    REAL NOT NULL
);
"""

# A date that is always within a 365-day look-back from today (2026).
_RECENT = "2026-01-01"
# A date that is always outside even a 365-day look-back from today.
_OLD = "2024-01-01"


@pytest.fixture
def kpi_db(tmp_path):
    """Return a path to a minimal test database."""
    db = tmp_path / "kpi_test.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(_SCHEMA)
    return db


# ---------------------------------------------------------------------------
# Test 1 — turnover formula
# ---------------------------------------------------------------------------

def test_turnover_formula(kpi_db):
    """turnover = units_sold / avg_inventory; correct numeric value and label."""
    with sqlite3.connect(kpi_db) as conn:
        conn.execute(
            "INSERT INTO atc_inventory (atc_code, current_stock) VALUES ('M01AE', 10.0)"
        )
        conn.execute(
            "INSERT INTO sales (atc_code, sale_date, granularity, quantity)"
            f" VALUES ('M01AE', '{_RECENT}', 'daily', 100.0)"
        )

    result = compute_turnover(kpi_db, period_days=365)

    assert "M01AE" in result
    assert result["M01AE"]["units_sold"] == 100.0
    assert result["M01AE"]["avg_inventory"] == 10.0
    assert result["M01AE"]["turnover"] == 10.0
    assert result["M01AE"]["classification"] == "Healthy"


# ---------------------------------------------------------------------------
# Test 2 — classification thresholds
# ---------------------------------------------------------------------------

def test_classification_thresholds():
    """Every classification bucket and its boundary values are correct."""
    assert _classify(0.0) == "Slow"
    assert _classify(2.0) == "Slow"
    assert _classify(3.99) == "Slow"
    assert _classify(4.0) == "Low"
    assert _classify(5.0) == "Low"
    assert _classify(5.99) == "Low"
    assert _classify(6.0) == "Healthy"
    assert _classify(9.0) == "Healthy"
    assert _classify(12.0) == "Healthy"
    assert _classify(12.01) == "High"
    assert _classify(18.0) == "High"
    assert _classify(24.0) == "High"
    assert _classify(24.01) == "Excessive"
    assert _classify(30.0) == "Excessive"


# ---------------------------------------------------------------------------
# Test 3 — empty period handling
# ---------------------------------------------------------------------------

def test_empty_period_handling(kpi_db):
    """No sales within the look-back window -> turnover 0.0, classified Slow."""
    with sqlite3.connect(kpi_db) as conn:
        conn.execute(
            "INSERT INTO atc_inventory (atc_code, current_stock) VALUES ('R06', 50.0)"
        )
        # Sale is outside the 30-day window.
        conn.execute(
            "INSERT INTO sales (atc_code, sale_date, granularity, quantity)"
            f" VALUES ('R06', '{_OLD}', 'daily', 500.0)"
        )

    result = compute_turnover(kpi_db, period_days=30)

    assert result["R06"]["units_sold"] == 0.0
    assert result["R06"]["turnover"] == 0.0
    assert result["R06"]["classification"] == "Slow"


# ---------------------------------------------------------------------------
# Test 4 — zero inventory edge case
# ---------------------------------------------------------------------------

def test_zero_inventory_edge_case(kpi_db):
    """Zero on-hand stock -> turnover 0.0 regardless of sales volume."""
    with sqlite3.connect(kpi_db) as conn:
        conn.execute(
            "INSERT INTO atc_inventory (atc_code, current_stock) VALUES ('N05B', 0.0)"
        )
        conn.execute(
            "INSERT INTO sales (atc_code, sale_date, granularity, quantity)"
            f" VALUES ('N05B', '{_RECENT}', 'daily', 200.0)"
        )

    result = compute_turnover(kpi_db, period_days=365)

    assert result["N05B"]["avg_inventory"] == 0.0
    assert result["N05B"]["turnover"] == 0.0
    # Division by zero does not raise; result is still classifiable.
    assert result["N05B"]["classification"] == "Slow"


# ---------------------------------------------------------------------------
# Test 5 — multi-ATC aggregation
# ---------------------------------------------------------------------------

def test_multi_atc_aggregation(kpi_db):
    """Multiple ATC codes each receive independent, correctly computed turnover."""
    with sqlite3.connect(kpi_db) as conn:
        conn.executemany(
            "INSERT INTO atc_inventory (atc_code, current_stock) VALUES (?, ?)",
            [("M01AB", 20.0), ("N02BA", 100.0), ("R03", 5.0)],
        )
        conn.executemany(
            "INSERT INTO sales (atc_code, sale_date, granularity, quantity)"
            f" VALUES (?, '{_RECENT}', 'daily', ?)",
            [("M01AB", 40.0), ("N02BA", 800.0), ("R03", 10.0)],
        )

    result = compute_turnover(kpi_db, period_days=365)

    assert result["M01AB"]["turnover"] == 2.0     # 40/20  -> Slow
    assert result["N02BA"]["turnover"] == 8.0     # 800/100 -> Healthy
    assert result["R03"]["turnover"] == 2.0       # 10/5   -> Slow

    assert result["M01AB"]["classification"] == "Slow"
    assert result["N02BA"]["classification"] == "Healthy"
    assert result["R03"]["classification"] == "Slow"
