"""
tests/test_database.py
----------------------
Unit tests for spis.data.database — schema creation and seed data.

All tests use a temporary SQLite file so they never touch data/inventory.db.
"""

import sqlite3

import pytest

from spis.data.database import ATC_CATEGORIES, DRUGS_CATALOG, ATC_INVENTORY_SEED, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Path to a temporary SQLite database that is deleted after each test."""
    return tmp_path / "test_inventory.db"


# ---------------------------------------------------------------------------
# Tests: schema
# ---------------------------------------------------------------------------

def test_init_db_creates_all_tables(tmp_db):
    """All four expected tables must exist after init_db."""
    init_db(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert {"atc_categories", "drugs", "sales", "atc_inventory"} <= tables


def test_init_db_is_idempotent(tmp_db):
    """Calling init_db twice must not raise an error or duplicate rows."""
    init_db(tmp_db)
    init_db(tmp_db)  # second call should be a no-op

    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM atc_categories").fetchone()[0]

    assert count == len(ATC_CATEGORIES)


# ---------------------------------------------------------------------------
# Tests: seed data
# ---------------------------------------------------------------------------

def test_init_db_seeds_atc_categories(tmp_db):
    """atc_categories should have exactly 8 rows after seeding."""
    init_db(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM atc_categories").fetchone()[0]

    assert count == len(ATC_CATEGORIES)


def test_init_db_seeds_drugs(tmp_db):
    """drugs table should have exactly 57 rows, 25 of them critical."""
    init_db(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        total    = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
        critical = conn.execute(
            "SELECT COUNT(*) FROM drugs WHERE is_critical = 1"
        ).fetchone()[0]

    assert total    == len(DRUGS_CATALOG)
    assert critical == sum(1 for _, _, _, crit in DRUGS_CATALOG if crit == 1)


def test_init_db_seeds_inventory(tmp_db):
    """atc_inventory should have one row per ATC code after seeding."""
    init_db(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM atc_inventory").fetchone()[0]

    assert count == len(ATC_INVENTORY_SEED)


def test_init_db_sales_starts_empty(tmp_db):
    """sales table should be empty immediately after init (no rows seeded)."""
    init_db(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]

    assert count == 0
