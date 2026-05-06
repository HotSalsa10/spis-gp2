"""
tests/test_database.py
----------------------
Unit tests for spis.data.database — schema creation and seed data.

All tests use a temporary SQLite file so they never touch data/inventory.db.
"""

import sqlite3

import pytest

from spis.data.database import (
    ATC_CATEGORIES,
    ATC_INVENTORY_SEED,
    BATCH_SEED,
    DRUGS_CATALOG,
    add_batch,
    init_db,
    recall_batch,
    update_stock,
)


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


# ---------------------------------------------------------------------------
# Tests: Phase 8.5 — inventory_batches table and update_stock
# ---------------------------------------------------------------------------


def test_init_db_creates_inventory_batches_table(tmp_db):
    """inventory_batches table must exist after init_db."""
    init_db(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert "inventory_batches" in tables


def test_init_db_seeds_batches(tmp_db):
    """inventory_batches should have exactly len(BATCH_SEED) rows after seeding."""
    init_db(tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM inventory_batches").fetchone()[0]

    assert count == len(BATCH_SEED)


def test_update_stock_changes_value(tmp_db):
    """update_stock must update current_stock for the given ATC code."""
    init_db(tmp_db)

    update_stock(tmp_db, "M01AB", 999.0)

    with sqlite3.connect(tmp_db) as conn:
        stock = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code='M01AB'"
        ).fetchone()[0]

    assert stock == pytest.approx(999.0)


def test_update_stock_raises_on_negative(tmp_db):
    """update_stock must raise ValueError for negative stock values."""
    init_db(tmp_db)

    with pytest.raises(ValueError):
        update_stock(tmp_db, "M01AB", -1.0)


# ---------------------------------------------------------------------------
# Tests: Phase 9 Item 4 -- add_batch
# ---------------------------------------------------------------------------


def test_add_batch_happy_path(tmp_db):
    """add_batch inserts a row and recomputes atc_inventory.current_stock."""
    init_db(tmp_db)

    import sqlite3
    with sqlite3.connect(tmp_db) as conn:
        old_stock = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code='N02BE'"
        ).fetchone()[0]

    add_batch(tmp_db, "N02BE", "LOT-TEST-001", 200.0, 0.50, "2027-12-31", "test batch")

    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute(
            "SELECT quantity FROM inventory_batches WHERE batch_number='LOT-TEST-001'"
        ).fetchone()
        new_stock = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code='N02BE'"
        ).fetchone()[0]

    assert row is not None
    assert row[0] == pytest.approx(200.0)
    assert new_stock == pytest.approx(old_stock + 200.0)


def test_add_batch_recomputes_stock_from_all_batches(tmp_db):
    """current_stock equals the sum of all non-returned batches for that ATC code."""
    init_db(tmp_db)

    add_batch(tmp_db, "N05B", "LOT-A-001", 100.0, 1.0, "2027-06-01")
    add_batch(tmp_db, "N05B", "LOT-A-002",  50.0, 1.0, "2027-09-01")

    import sqlite3
    with sqlite3.connect(tmp_db) as conn:
        # Seed stock for N05B is 100.0; two batches add 150 more.
        stock = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code='N05B'"
        ).fetchone()[0]
        seed_val = next(s for (c, s, _) in ATC_INVENTORY_SEED if c == "N05B")

    assert stock == pytest.approx(seed_val + 150.0)


def test_add_batch_duplicate_rejected(tmp_db):
    """add_batch must raise ValueError when batch_number already exists."""
    init_db(tmp_db)

    add_batch(tmp_db, "R03", "LOT-DUP-001", 50.0, 0.80, "2027-01-01")
    with pytest.raises(ValueError, match="already exists"):
        add_batch(tmp_db, "R03", "LOT-DUP-001", 30.0, 0.80, "2027-03-01")


def test_add_batch_negative_quantity_rejected(tmp_db):
    """add_batch must raise ValueError for quantity <= 0."""
    init_db(tmp_db)

    with pytest.raises(ValueError, match="positive"):
        add_batch(tmp_db, "M01AB", "LOT-NEG-001", -10.0, 1.0, "2027-01-01")


def test_add_batch_zero_quantity_rejected(tmp_db):
    """add_batch must reject zero quantity."""
    init_db(tmp_db)

    with pytest.raises(ValueError, match="positive"):
        add_batch(tmp_db, "M01AB", "LOT-ZERO-001", 0.0, 1.0, "2027-01-01")


def test_add_batch_invalid_date_rejected(tmp_db):
    """add_batch must raise ValueError for malformed expiry dates."""
    init_db(tmp_db)

    with pytest.raises(ValueError, match="expiry date"):
        add_batch(tmp_db, "M01AB", "LOT-BAD-001", 50.0, 1.0, "not-a-date")


def test_add_batch_past_expiry_warns(tmp_db):
    """add_batch must emit a UserWarning when expiry date is in the past."""
    init_db(tmp_db)

    with pytest.warns(UserWarning, match="past"):
        add_batch(tmp_db, "M01AB", "LOT-PAST-001", 10.0, 0.50, "2020-01-01")


# ---------------------------------------------------------------------------
# Tests: Phase 9 Item 5 -- recall_batch
# ---------------------------------------------------------------------------


def test_recall_batch_happy_path(tmp_db):
    """recall_batch zeros quantity, sets returned=1, and reduces aggregate stock."""
    init_db(tmp_db)

    import sqlite3
    add_batch(tmp_db, "R06", "LOT-RECALL-001", 300.0, 0.35, "2027-06-01")

    with sqlite3.connect(tmp_db) as conn:
        stock_before = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code='R06'"
        ).fetchone()[0]

    units = recall_batch(tmp_db, "LOT-RECALL-001", "contamination test")

    with sqlite3.connect(tmp_db) as conn:
        batch = conn.execute(
            "SELECT quantity, returned, notes FROM inventory_batches WHERE batch_number='LOT-RECALL-001'"
        ).fetchone()
        stock_after = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code='R06'"
        ).fetchone()[0]

    assert units == pytest.approx(300.0)
    assert batch[0] == pytest.approx(0.0)
    assert batch[1] == 1
    assert "RECALLED" in batch[2]
    assert stock_after == pytest.approx(stock_before - 300.0)


def test_recall_batch_unknown_rejected(tmp_db):
    """recall_batch must raise ValueError for an unknown batch number."""
    init_db(tmp_db)

    with pytest.raises(ValueError, match="Unknown batch"):
        recall_batch(tmp_db, "LOT-NONEXISTENT-999", "test")


def test_recall_batch_idempotent(tmp_db):
    """Recalling an already-recalled batch does not raise and returns 0."""
    init_db(tmp_db)

    add_batch(tmp_db, "N02BA", "LOT-IDEM-001", 80.0, 0.20, "2027-04-01")
    recall_batch(tmp_db, "LOT-IDEM-001", "first recall")
    # Second recall should succeed and report 0 units (already zeroed)
    units_second = recall_batch(tmp_db, "LOT-IDEM-001", "duplicate recall check")

    assert units_second == pytest.approx(0.0)
