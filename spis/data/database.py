"""
spis/data/database.py
---------------------
Initialises the SPIS SQLite database schema and seeds the ATC / drug reference data.

Schema (3 tables):
    atc_categories  — ATC-4 classification reference (8 rows)
    drugs           — Clinical drug catalog (57 rows)
    sales           — Time-series fact table (rows inserted by ingest_kaggle.py)

Usage:
    from spis.data.database import init_db
    init_db("data/inventory.db")
"""

import sqlite3
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
    """)


def _seed_reference_data(conn: sqlite3.Connection) -> None:
    """Insert ATC categories and drug catalog rows (skips duplicates)."""
    conn.executemany(
        "INSERT OR IGNORE INTO atc_categories VALUES (?,?,?,?,?)",
        ATC_CATEGORIES,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO drugs (drug_name, atc_code, unit, is_critical) VALUES (?,?,?,?)",
        DRUGS_CATALOG,
    )


def _print_summary(db_path: Path) -> None:
    """Print a quick row-count summary to confirm seeding worked."""
    with sqlite3.connect(db_path) as conn:
        atc_n   = conn.execute("SELECT COUNT(*) FROM atc_categories").fetchone()[0]
        drug_n  = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
        crit_n  = conn.execute("SELECT COUNT(*) FROM drugs WHERE is_critical=1").fetchone()[0]
    print(f"[database]   atc_categories : {atc_n:>4} rows")
    print(f"[database]   drugs          : {drug_n:>4} rows  ({crit_n} critical)")
    print(f"[database]   sales          :    0 rows  (populated by ingest_kaggle.py)")
