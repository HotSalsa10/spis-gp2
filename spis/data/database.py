"""
spis/data/database.py
---------------------
Initialises the SPIS SQLite database schema and seeds the ATC / drug reference data.

Schema (4 tables):
    atc_categories  — ATC-4 classification reference (8 rows)
    drugs           — Clinical drug catalog (57 rows)
    sales           — Time-series fact table (rows inserted by ingest_kaggle.py)
    atc_inventory   — Current stock level per ATC code (Phase 4)

Usage:
    from spis.data.database import init_db
    init_db("data/inventory.db")
"""

import csv
import sqlite3
import warnings
from datetime import date as _date, datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Reference Data — ATC Classification
# ---------------------------------------------------------------------------
# The Kaggle dataset contains sales aggregated at ATC-4 level for 8 categories.
# Source: WHO ATC/DDD Index (https://www.whocc.no/atc_ddd_index/)

ATC_CATEGORIES = [
    # (atc_code, atc_name, system_name, level1_code, level2_code)
    ("M01AB", "Acetic acid derivatives",           "Musculoskeletal system", "M", "M01"),
    ("M01AE", "Propionic acid derivatives",         "Musculoskeletal system", "M", "M01"),
    ("N02BA", "Salicylic acid and derivatives",     "Nervous system",         "N", "N02"),
    ("N02BE", "Anilides",                           "Nervous system",         "N", "N02"),
    ("N05B",  "Anxiolytics",                        "Nervous system",         "N", "N05"),
    ("N05C",  "Hypnotics and sedatives",            "Nervous system",         "N", "N05"),
    ("R03",   "Drugs for obstructive airway dis.",  "Respiratory system",     "R", "R03"),
    ("R06",   "Antihistamines for systemic use",    "Respiratory system",     "R", "R06"),
]

# ---------------------------------------------------------------------------
# Reference Data — Drug Catalog (57 drugs across 8 ATC categories)
# ---------------------------------------------------------------------------
# is_critical = 1 when a stockout poses direct clinical harm:
#   • N05B/N05C — controlled substances; abrupt withdrawal -> seizures / crisis
#   • N02BE      — first-line analgesic (Paracetamol); mass-demand essential
#   • R03        — bronchodilators / ICS; life-critical for asthma / COPD patients

# ---------------------------------------------------------------------------
# Reference Data — Inventory Batches (Phase 8.5 expiry seed data)
# ---------------------------------------------------------------------------
# Mock batches chosen to demonstrate all discount tiers in the demo.
# Dates are relative to the project demo date (March 30, 2026):
#   LOT-2026-001 : expires Apr 15 2026 ( 16 days) -> Cannot Dispense (< 30d) -- return to supplier
#   LOT-2026-002 : expires May 10 2026 ( 41 days) -> Special Offer 25% off   (30-59d)
#   LOT-2026-003 : expires Jun 15 2026 ( 77 days) -> Early Discount 15% off  (60-90d)

BATCH_SEED = [
    # (atc_code, batch_number, quantity, unit_cost, expiry_date, received_date, notes)
    ("M01AE", "LOT-2026-001", 300.0, 0.50, "2026-04-15", "2025-10-01",
     "16 days to expiry -- Cannot Dispense, return to supplier"),
    ("R06",   "LOT-2026-002", 400.0, 0.35, "2026-05-10", "2025-10-01",
     "41 days to expiry -- Special Offer 25% off"),
    ("N02BA", "LOT-2026-003", 150.0, 0.20, "2026-06-15", "2025-11-01",
     "77 days to expiry -- Early Discount 15% off"),
]

# ---------------------------------------------------------------------------
# Reference Data — ATC Inventory (Phase 4 seed stock levels)
# ---------------------------------------------------------------------------
# Mock stock values chosen to demonstrate all 4 risk tiers in the demo:
#   CRITICAL (DoS < 3)  : N02BE (~2 days), R03 (~2 days)
#   LOW      (3 <= < 7) : M01AB (~6 days)
#   OK       (7 <= < 30): N02BA (~15 days), N05B (~20 days), N05C (~25 days)
#   OVERSTOCK (>= 30)   : M01AE (~40 days), R06 (~40 days)

ATC_INVENTORY_SEED = [
    # (atc_code, current_stock, notes)
    ("M01AB", 60.0,  "~6 days of stock (LOW risk)"),
    ("M01AE", 500.0, "~40 days of stock (OVERSTOCK)"),
    ("N02BA", 90.0,  "~15 days of stock (OK)"),
    ("N02BE", 40.0,  "~2 days of stock (CRITICAL)"),
    ("N05B",  100.0, "~20 days of stock (OK)"),
    ("N05C",  75.0,  "~25 days of stock (OK)"),
    ("R03",   25.0,  "~2 days of stock (CRITICAL)"),
    ("R06",   420.0, "~40 days of stock (OVERSTOCK)"),
]

DRUGS_CATALOG = [
    # (drug_name, atc_code, unit, is_critical)

    # ── M01AB — Anti-inflammatory, acetic acid derivatives ────────────────
    ("Diclofenac",          "M01AB", "tablets",  0),
    ("Indomethacin",        "M01AB", "capsules", 0),
    ("Ketorolac",           "M01AB", "tablets",  0),
    ("Sulindac",            "M01AB", "tablets",  0),
    ("Etodolac",            "M01AB", "capsules", 0),
    ("Aceclofenac",         "M01AB", "tablets",  0),
    ("Nabumetone",          "M01AB", "tablets",  0),

    # ── M01AE — Propionic acid derivatives ───────────────────────────────
    ("Ibuprofen",           "M01AE", "tablets",  0),
    ("Naproxen",            "M01AE", "tablets",  0),
    ("Ketoprofen",          "M01AE", "capsules", 0),
    ("Flurbiprofen",        "M01AE", "tablets",  0),
    ("Fenoprofen",          "M01AE", "capsules", 0),
    ("Oxaprozin",           "M01AE", "tablets",  0),
    ("Loxoprofen",          "M01AE", "tablets",  0),
    ("Dexibuprofen",        "M01AE", "tablets",  0),

    # ── N02BA — Salicylic acid and derivatives ────────────────────────────
    ("Aspirin",             "N02BA", "tablets",  0),
    ("Diflunisal",          "N02BA", "tablets",  0),
    ("Salsalate",           "N02BA", "tablets",  0),
    ("Benorylate",          "N02BA", "tablets",  0),
    ("Carbasalate calcium", "N02BA", "sachets",  0),

    # ── N02BE — Anilides ──────────────────────────────────────────────────
    ("Paracetamol",         "N02BE", "tablets",  1),  # first-line analgesic
    ("Propacetamol",        "N02BE", "vials",    1),
    ("Phenacetin",          "N02BE", "tablets",  0),
    ("Bucetin",             "N02BE", "tablets",  0),
    ("Ethenzamide",         "N02BE", "tablets",  0),
    ("Acetanilide",         "N02BE", "tablets",  0),

    # ── N05B — Anxiolytics (controlled substances) ────────────────────────
    ("Diazepam",            "N05B",  "tablets",  1),
    ("Alprazolam",          "N05B",  "tablets",  1),
    ("Lorazepam",           "N05B",  "tablets",  1),
    ("Oxazepam",            "N05B",  "tablets",  1),
    ("Clonazepam",          "N05B",  "tablets",  1),
    ("Bromazepam",          "N05B",  "tablets",  1),
    ("Chlordiazepoxide",    "N05B",  "capsules", 1),
    ("Clobazam",            "N05B",  "tablets",  1),

    # ── N05C — Hypnotics and sedatives (controlled substances) ────────────
    ("Zolpidem",            "N05C",  "tablets",  1),
    ("Zopiclone",           "N05C",  "tablets",  1),
    ("Temazepam",           "N05C",  "capsules", 1),
    ("Nitrazepam",          "N05C",  "tablets",  1),
    ("Triazolam",           "N05C",  "tablets",  1),
    ("Estazolam",           "N05C",  "tablets",  1),
    ("Quazepam",            "N05C",  "tablets",  1),

    # ── R03 — Drugs for obstructive airway diseases ───────────────────────
    ("Salbutamol",          "R03",   "inhaler",  1),  # life-critical for asthma
    ("Formoterol",          "R03",   "inhaler",  1),
    ("Salmeterol",          "R03",   "inhaler",  1),
    ("Terbutaline",         "R03",   "inhaler",  1),
    ("Fenoterol",           "R03",   "inhaler",  1),
    ("Indacaterol",         "R03",   "inhaler",  1),
    ("Budesonide",          "R03",   "inhaler",  1),
    ("Fluticasone",         "R03",   "inhaler",  1),

    # ── R06 — Antihistamines for systemic use ────────────────────────────
    ("Cetirizine",          "R06",   "tablets",  0),
    ("Loratadine",          "R06",   "tablets",  0),
    ("Fexofenadine",        "R06",   "tablets",  0),
    ("Desloratadine",       "R06",   "tablets",  0),
    ("Levocetirizine",      "R06",   "tablets",  0),
    ("Azelastine",          "R06",   "spray",    0),
    ("Bilastine",           "R06",   "tablets",  0),
    ("Ebastine",            "R06",   "tablets",  0),
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path) -> None:
    """
    Create (or verify) the inventory.db schema and seed all reference data.

    Safe to call on an existing database — uses IF NOT EXISTS / INSERT OR IGNORE
    so re-running never corrupts data.

    Args:
        db_path: File path for the SQLite database (parent dirs created if needed).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        _create_tables(conn)
        _migrate_batches_columns(conn)
        _seed_reference_data(conn)
        conn.commit()

    print(f"[database] Initialised -> {db_path}")
    _print_summary(db_path)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _create_tables(conn: sqlite3.Connection) -> None:
    """Define all DDL. Uses IF NOT EXISTS so this is idempotent."""
    conn.executescript("""
        -- ATC classification dimension
        CREATE TABLE IF NOT EXISTS atc_categories (
            atc_code    TEXT PRIMARY KEY,
            atc_name    TEXT NOT NULL,
            system_name TEXT NOT NULL,
            level1_code TEXT NOT NULL,  -- e.g. 'M', 'N', 'R'
            level2_code TEXT NOT NULL   -- e.g. 'M01', 'N02', 'N05'
        );

        -- Clinical drug catalog (reference; NOT the unit of sales aggregation)
        CREATE TABLE IF NOT EXISTS drugs (
            drug_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name   TEXT    NOT NULL UNIQUE,
            atc_code    TEXT    NOT NULL REFERENCES atc_categories(atc_code),
            unit        TEXT    NOT NULL DEFAULT 'tablets',
            is_critical INTEGER NOT NULL DEFAULT 0
                        CHECK (is_critical IN (0, 1))
        );

        -- Sales fact table — one row per (atc_code, date, granularity)
        CREATE TABLE IF NOT EXISTS sales (
            sale_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            atc_code    TEXT    NOT NULL REFERENCES atc_categories(atc_code),
            sale_date   TEXT    NOT NULL,  -- ISO-8601: YYYY-MM-DD
            hour        INTEGER,           -- 0–23 for hourly rows; NULL otherwise
            granularity TEXT    NOT NULL   -- 'hourly' | 'daily' | 'weekly' | 'monthly'
                        CHECK (granularity IN ('hourly', 'daily', 'weekly', 'monthly')),
            quantity    REAL    NOT NULL CHECK (quantity >= 0)
        );

        -- Indexes that speed up the two main query patterns:
        --   1. Fetch time series for a single drug  ->  idx_sales_atc_date
        --   2. Filter by granularity for modelling  ->  idx_sales_granularity
        CREATE INDEX IF NOT EXISTS idx_sales_atc_date
            ON sales (atc_code, sale_date);

        CREATE INDEX IF NOT EXISTS idx_sales_granularity
            ON sales (granularity);

        -- Current stock level per ATC code (Phase 4 risk classification)
        CREATE TABLE IF NOT EXISTS atc_inventory (
            atc_code      TEXT PRIMARY KEY REFERENCES atc_categories(atc_code),
            current_stock REAL NOT NULL CHECK (current_stock >= 0),
            last_updated  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes         TEXT
        );

        -- Per-batch stock with expiry date and unit cost (Phase 8.5)
        CREATE TABLE IF NOT EXISTS inventory_batches (
            batch_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            atc_code          TEXT    NOT NULL REFERENCES atc_categories(atc_code),
            batch_number      TEXT    NOT NULL,
            quantity          REAL    NOT NULL CHECK (quantity >= 0),
            unit_cost         REAL    NOT NULL CHECK (unit_cost >= 0),
            expiry_date       TEXT    NOT NULL,
            received_date     TEXT    NOT NULL DEFAULT CURRENT_DATE,
            notes             TEXT,
            applied_discount  REAL,   -- pharmacist override; NULL means use suggested
            returned          INTEGER NOT NULL DEFAULT 0 CHECK (returned IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_batches_atc_expiry
            ON inventory_batches (atc_code, expiry_date);
    """)


def _migrate_batches_columns(conn: sqlite3.Connection) -> None:
    """Add columns introduced after initial schema deployment (idempotent)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(inventory_batches)")}
    if "applied_discount" not in existing:
        conn.execute("ALTER TABLE inventory_batches ADD COLUMN applied_discount REAL")
    if "returned" not in existing:
        conn.execute(
            "ALTER TABLE inventory_batches ADD COLUMN returned INTEGER NOT NULL DEFAULT 0"
        )


def _seed_reference_data(conn: sqlite3.Connection) -> None:
    """Insert ATC categories, drug catalog, and inventory rows (skips duplicates)."""
    conn.executemany(
        "INSERT OR IGNORE INTO atc_categories VALUES (?,?,?,?,?)",
        ATC_CATEGORIES,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO drugs (drug_name, atc_code, unit, is_critical) VALUES (?,?,?,?)",
        DRUGS_CATALOG,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO atc_inventory (atc_code, current_stock, notes) VALUES (?,?,?)",
        ATC_INVENTORY_SEED,
    )
    conn.executemany(
        """INSERT OR IGNORE INTO inventory_batches
               (atc_code, batch_number, quantity, unit_cost, expiry_date, received_date, notes)
           VALUES (?,?,?,?,?,?,?)""",
        BATCH_SEED,
    )


def _print_summary(db_path: Path) -> None:
    """Print a quick row-count summary to confirm seeding worked."""
    with sqlite3.connect(db_path) as conn:
        atc_n    = conn.execute("SELECT COUNT(*) FROM atc_categories").fetchone()[0]
        drug_n   = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
        crit_n   = conn.execute("SELECT COUNT(*) FROM drugs WHERE is_critical=1").fetchone()[0]
        inv_n    = conn.execute("SELECT COUNT(*) FROM atc_inventory").fetchone()[0]
        batch_n  = conn.execute("SELECT COUNT(*) FROM inventory_batches").fetchone()[0]
    print(f"[database]   atc_categories    : {atc_n:>4} rows")
    print(f"[database]   drugs             : {drug_n:>4} rows  ({crit_n} critical)")
    print(f"[database]   atc_inventory     : {inv_n:>4} rows  (Phase 4 stock levels)")
    print(f"[database]   inventory_batches : {batch_n:>4} rows  (Phase 8.5 expiry tracking)")
    print(f"[database]   sales             :    0 rows  (populated by ingest_kaggle.py)")


# ---------------------------------------------------------------------------
# Public helpers — stock management (Phase 8.5)
# ---------------------------------------------------------------------------

def update_stock(db_path: str | Path, atc_code: str, new_stock: float) -> None:
    """
    Update the current stock level for one ATC code in atc_inventory.

    Args:
        db_path  : Path to the SQLite database.
        atc_code : ATC-4 code to update.
        new_stock: New stock level (must be >= 0).

    Raises:
        ValueError: If new_stock is negative.
    """
    if new_stock < 0:
        raise ValueError(f"Stock cannot be negative: {new_stock}")
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE atc_inventory SET current_stock=?, last_updated=CURRENT_TIMESTAMP "
            "WHERE atc_code=?",
            (new_stock, atc_code),
        )
        conn.commit()


def load_batches(db_path: str | Path) -> list[dict]:
    """
    Load all inventory batches from the inventory_batches table.

    Returns:
        List of dicts with keys: batch_id, atc_code, batch_number, quantity,
        unit_cost, expiry_date (ISO string), received_date, notes,
        applied_discount (float|None), returned (int 0/1).
    """
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT batch_id, atc_code, batch_number, quantity,
                      unit_cost, expiry_date, received_date, notes,
                      applied_discount, returned
               FROM inventory_batches
               ORDER BY expiry_date"""
        ).fetchall()
    return [dict(row) for row in rows]


def add_batch(
    db_path: str | Path,
    atc_code: str,
    batch_number: str,
    quantity: float,
    unit_cost: float,
    expiry_date: str,
    notes: str = "",
) -> None:
    """
    Insert a new received batch and recompute aggregate stock for that ATC code.

    Args:
        db_path     : Path to the SQLite database.
        atc_code    : ATC-4 code the batch belongs to.
        batch_number: Unique lot identifier (e.g. LOT-2026-099).
        quantity    : Number of units received (must be > 0).
        unit_cost   : Cost per unit in SAR (must be >= 0).
        expiry_date : Expiry date string in YYYY-MM-DD format.
        notes       : Optional free-text notes.

    Raises:
        ValueError: quantity <= 0, unit_cost < 0, invalid date, duplicate batch_number.
    """
    if quantity <= 0:
        raise ValueError(f"Quantity must be positive: {quantity}")
    if unit_cost < 0:
        raise ValueError(f"Unit cost cannot be negative: {unit_cost}")
    try:
        parsed_expiry = _date.fromisoformat(str(expiry_date))
    except ValueError:
        raise ValueError(f"Invalid expiry date (expected YYYY-MM-DD): {expiry_date}")
    if parsed_expiry < _date.today():
        warnings.warn(
            f"Expiry date {expiry_date} is in the past. "
            "Batch will be immediately eligible for write-off.",
            UserWarning,
            stacklevel=2,
        )

    db_path = Path(db_path)
    old_stock = 0.0
    new_stock = quantity

    with sqlite3.connect(db_path) as conn:
        dup = conn.execute(
            "SELECT batch_id FROM inventory_batches WHERE batch_number=?",
            (batch_number,),
        ).fetchone()
        if dup:
            raise ValueError(f"Batch number already exists: {batch_number}")

        old_row = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code=?",
            (atc_code,),
        ).fetchone()
        old_stock = old_row[0] if old_row else 0.0

        conn.execute(
            """INSERT INTO inventory_batches
                   (atc_code, batch_number, quantity, unit_cost, expiry_date, received_date, notes)
               VALUES (?, ?, ?, ?, ?, CURRENT_DATE, ?)""",
            (atc_code, batch_number, quantity, unit_cost, str(expiry_date), notes),
        )
        conn.execute(
            """UPDATE atc_inventory
               SET current_stock = current_stock + ?,
                   last_updated = CURRENT_TIMESTAMP
               WHERE atc_code = ?""",
            (quantity, atc_code),
        )
        new_row = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code=?",
            (atc_code,),
        ).fetchone()
        new_stock = new_row[0] if new_row else (old_stock + quantity)
        conn.commit()

    _append_batch_audit(db_path, atc_code, "RECEIVE", batch_number, old_stock, new_stock, quantity)


def recall_batch(db_path: str | Path, batch_number: str, reason: str) -> float:
    """
    Withdraw a faulty batch: zero its quantity, mark returned=1, recompute stock.

    Args:
        db_path     : Path to the SQLite database.
        batch_number: Lot identifier to recall.
        reason      : Human-readable recall reason appended to batch notes.

    Returns:
        Number of units that were recalled (0.0 if already recalled).

    Raises:
        ValueError: batch_number not found.
    """
    db_path = Path(db_path)
    old_stock = 0.0
    new_stock = 0.0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT atc_code, quantity, notes FROM inventory_batches WHERE batch_number=?",
            (batch_number,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown batch number: {batch_number}")

        atc_code, qty, old_notes = row

        old_row = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code=?",
            (atc_code,),
        ).fetchone()
        old_stock = old_row[0] if old_row else 0.0

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        suffix = f"RECALLED {ts}: {reason}"
        new_notes = ((old_notes or "").rstrip("; ") + "; " + suffix).lstrip("; ")

        conn.execute(
            """UPDATE inventory_batches
               SET quantity = 0, returned = 1, notes = ?
               WHERE batch_number = ?""",
            (new_notes, batch_number),
        )
        conn.execute(
            """UPDATE atc_inventory
               SET current_stock = MAX(0, current_stock - ?),
                   last_updated = CURRENT_TIMESTAMP
               WHERE atc_code = ?""",
            (qty, atc_code),
        )
        new_row = conn.execute(
            "SELECT current_stock FROM atc_inventory WHERE atc_code=?",
            (atc_code,),
        ).fetchone()
        new_stock = new_row[0] if new_row else 0.0
        conn.commit()

    _append_batch_audit(db_path, atc_code, "RECALL", batch_number, old_stock, new_stock, -qty)
    return qty


_BATCH_AUDIT_HEADER = [
    "timestamp", "atc_code", "action", "batch_number", "old_stock", "new_stock", "delta",
]


def _append_batch_audit(
    db_path: Path,
    atc_code: str,
    action: str,
    batch_number: str,
    old_stock: float,
    new_stock: float,
    delta: float,
) -> None:
    audit_path = db_path.parent / "stock_audit.csv"
    write_header = not audit_path.exists()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(audit_path, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(_BATCH_AUDIT_HEADER)
        writer.writerow([ts, atc_code, action, batch_number, old_stock, new_stock, delta])


def save_batch_overrides(
    db_path: str | Path,
    overrides: list[dict],
) -> None:
    """
    Persist pharmacist overrides for one or more batches.

    Each dict in *overrides* must have:
        batch_id         (int)
        applied_discount (float|None)
        returned         (bool/int)  — if True, quantity is zeroed out

    Args:
        db_path  : Path to the SQLite database.
        overrides: List of override dicts (one per edited batch).
    """
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        for ov in overrides:
            conn.execute(
                """UPDATE inventory_batches
                   SET applied_discount = ?,
                       returned         = ?,
                       quantity         = CASE WHEN ? THEN 0 ELSE quantity END
                   WHERE batch_id = ?""",
                (
                    ov.get("applied_discount"),
                    1 if ov.get("returned") else 0,
                    1 if ov.get("returned") else 0,
                    ov["batch_id"],
                ),
            )
        conn.commit()
