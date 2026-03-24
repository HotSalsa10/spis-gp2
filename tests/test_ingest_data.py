"""
tests/test_ingest_data.py
--------------------------
Unit tests for helper functions in scripts/ingest_data.py.

Tests cover CSV normalisation, DB code lookup, and unknown-code registration.
The main() entrypoint is a CLI wrapper and is not tested here.
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make scripts/ importable without installing it as a package.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from ingest_data import (  # noqa: E402
    _get_db_atc_codes,
    _load_and_normalise,
    _register_unknown_codes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_csv(tmp_path):
    """Write a minimal valid CSV and return its Path."""
    csv_file = tmp_path / "sales.csv"
    csv_file.write_text(
        "date,atc_code,quantity\n"
        "2023-01-01,M01AB,45.0\n"
        "2023-01-02,M01AB,30.0\n"
        "2023-01-01,N02BE,12.0\n"
    )
    return csv_file


@pytest.fixture
def empty_db(tmp_path):
    """SQLite connection with only the atc_categories and atc_inventory tables."""
    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE atc_categories "
            "(atc_code TEXT PRIMARY KEY, atc_name TEXT, system_name TEXT, "
            "level1_code TEXT, level2_code TEXT)"
        )
        conn.execute(
            "CREATE TABLE atc_inventory "
            "(atc_code TEXT PRIMARY KEY, current_stock REAL, notes TEXT)"
        )
        conn.commit()
    return db_path


# ---------------------------------------------------------------------------
# Tests: _load_and_normalise
# ---------------------------------------------------------------------------

def test_load_normalise_returns_expected_columns(sample_csv):
    """Output DataFrame must have exactly the 5 expected columns."""
    df = _load_and_normalise(sample_csv, "date", "atc_code", "quantity", "daily")
    assert set(df.columns) == {"atc_code", "sale_date", "hour", "granularity", "quantity"}


def test_load_normalise_row_count(sample_csv):
    """All 3 valid rows should be present in the output."""
    df = _load_and_normalise(sample_csv, "date", "atc_code", "quantity", "daily")
    assert len(df) == 3


def test_load_normalise_granularity_propagated(sample_csv):
    """The granularity argument must appear in every row."""
    df = _load_and_normalise(sample_csv, "date", "atc_code", "quantity", "weekly")
    assert (df["granularity"] == "weekly").all()


def test_load_normalise_clips_negative_quantities(tmp_path):
    """Negative quantities must be clipped to 0."""
    csv_file = tmp_path / "neg.csv"
    csv_file.write_text("date,atc_code,quantity\n2023-01-01,M01AB,-5.0\n")
    df = _load_and_normalise(csv_file, "date", "atc_code", "quantity", "daily")
    assert df["quantity"].iloc[0] == 0.0


def test_load_normalise_custom_column_names(tmp_path):
    """Custom column-name mapping (--date-col / --atc-col / --qty-col) must work."""
    csv_file = tmp_path / "custom.csv"
    csv_file.write_text("SaleDate,DrugCode,Units\n2023-05-01,R06,9.0\n")
    df = _load_and_normalise(csv_file, "SaleDate", "DrugCode", "Units", "daily")
    assert len(df) == 1
    assert df["atc_code"].iloc[0] == "R06"


def test_load_normalise_missing_column_exits(sample_csv):
    """Passing a wrong column name must trigger SystemExit."""
    with pytest.raises(SystemExit):
        _load_and_normalise(sample_csv, "date", "wrong_col", "quantity", "daily")


# ---------------------------------------------------------------------------
# Tests: _get_db_atc_codes
# ---------------------------------------------------------------------------

def test_get_db_atc_codes_empty_db(empty_db):
    """A freshly created DB with no rows should return an empty set."""
    with sqlite3.connect(empty_db) as conn:
        codes = _get_db_atc_codes(conn)
    assert codes == set()


def test_get_db_atc_codes_returns_known_codes(empty_db):
    """After inserting two ATC codes the function should return exactly those two."""
    with sqlite3.connect(empty_db) as conn:
        conn.execute(
            "INSERT INTO atc_categories (atc_code, atc_name, system_name, level1_code, level2_code) "
            "VALUES ('M01AB', 'Anti-inflammatory', 'Musculoskeletal', 'M', 'M01')"
        )
        conn.execute(
            "INSERT INTO atc_categories (atc_code, atc_name, system_name, level1_code, level2_code) "
            "VALUES ('N02BE', 'Pain relief', 'Nervous system', 'N', 'N02')"
        )
        conn.commit()
        codes = _get_db_atc_codes(conn)
    assert codes == {"M01AB", "N02BE"}


# ---------------------------------------------------------------------------
# Tests: _register_unknown_codes
# ---------------------------------------------------------------------------

def test_register_unknown_codes_inserts_atc_categories(empty_db):
    """Unknown codes must appear in atc_categories after registration."""
    with sqlite3.connect(empty_db) as conn:
        _register_unknown_codes({"A10BA"}, conn)
        conn.commit()
        row = conn.execute(
            "SELECT atc_code FROM atc_categories WHERE atc_code = 'A10BA'"
        ).fetchone()
    assert row is not None


def test_register_unknown_codes_inserts_inventory(empty_db):
    """Unknown codes must also get a row in atc_inventory with stock=0."""
    with sqlite3.connect(empty_db) as conn:
        _register_unknown_codes({"A10BA"}, conn)
        conn.commit()
        row = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code = 'A10BA'"
        ).fetchone()
    assert row is not None
    assert row[0] == 0.0


def test_register_unknown_codes_idempotent(empty_db):
    """Calling _register_unknown_codes twice for the same code must not raise."""
    with sqlite3.connect(empty_db) as conn:
        _register_unknown_codes({"A10BA"}, conn)
        conn.commit()
        # Second call — INSERT OR IGNORE means no error, no duplicate
        _register_unknown_codes({"A10BA"}, conn)
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM atc_categories WHERE atc_code = 'A10BA'"
        ).fetchone()[0]
    assert count == 1
