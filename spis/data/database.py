"""SQLite schema + seed data + CRUD helpers."""

import csv
import sqlite3
import warnings
from datetime import date as _date, datetime, timezone
from pathlib import Path

# ATC-4 categories from the Kaggle dataset (WHO ATC/DDD index)
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

# is_critical = 1 when stockout = direct clinical risk
# (N05B/N05C controlled substances, N02BE paracetamol, R03 inhalers)

# demo batches covering all discount tiers (dates relative to ~Mar 2026)
BATCH_SEED = [
    ("M01AE", "LOT-2026-001", 300.0, 0.50, "2026-04-15", "2025-10-01",
     "16d to expiry - cannot dispense, return"),
    ("R06",   "LOT-2026-002", 400.0, 0.35, "2026-05-10", "2025-10-01",
     "41d to expiry - special offer 25% off"),
    ("N02BA", "LOT-2026-003", 150.0, 0.20, "2026-06-15", "2025-11-01",
     "77d to expiry - early discount 15%"),
]

# stock values chosen so demo shows all 4 risk tiers
ATC_INVENTORY_SEED = [
    ("M01AB", 60.0,  "LOW"),
    ("M01AE", 500.0, "OVERSTOCK"),
    ("N02BA", 90.0,  "OK"),
    ("N02BE", 40.0,  "CRITICAL"),
    ("N05B",  100.0, "OK"),
    ("N05C",  75.0,  "OK"),
    ("R03",   25.0,  "CRITICAL"),
    ("R06",   420.0, "OVERSTOCK"),
]

# Real Saudi pharma distributors. Emails/phones are placeholders --
# replace with real contacts before sending any actual PO.
SUPPLIERS_SEED = [
    (1, "Tamer Group",
     "info@tamergroup.com",      "+966 12 000 0001", 3,
     "Jeddah pharma distributor (est. 1922) - demo contact"),
    (2, "Banaja Holdings",
     "info@banaja.com",          "+966 12 000 0002", 5,
     "Jeddah pharma distributor (est. 1948) - demo contact"),
    (3, "Cigalah Group",
     "info@cigalah.com",         "+966 12 000 0003", 7,
     "controlled-substance licensing - demo contact"),
    (4, "Jamjoom Pharma",
     "info@jamjoompharma.com",   "+966 12 000 0004", 4,
     "Saudi pharma manufacturer (est. 1988) - demo contact"),
]

# Tamer -> MSK, Banaja -> analgesics, Cigalah -> controlled, Jamjoom -> respiratory
ATC_SUPPLIER_MAP = {
    "M01AB": 1, "M01AE": 1,
    "N02BA": 2, "N02BE": 2,
    "N05B":  3, "N05C":  3,
    "R03":   4, "R06":   4,
}

DRUGS_CATALOG = [
    # (drug_name, atc_code, unit, is_critical)

    # M01AB - acetic acid NSAIDs
    ("Diclofenac",          "M01AB", "tablets",  0),
    ("Indomethacin",        "M01AB", "capsules", 0),
    ("Ketorolac",           "M01AB", "tablets",  0),
    ("Sulindac",            "M01AB", "tablets",  0),
    ("Etodolac",            "M01AB", "capsules", 0),
    ("Aceclofenac",         "M01AB", "tablets",  0),
    ("Nabumetone",          "M01AB", "tablets",  0),

    # M01AE - propionic acid NSAIDs
    ("Ibuprofen",           "M01AE", "tablets",  0),
    ("Naproxen",            "M01AE", "tablets",  0),
    ("Ketoprofen",          "M01AE", "capsules", 0),
    ("Flurbiprofen",        "M01AE", "tablets",  0),
    ("Fenoprofen",          "M01AE", "capsules", 0),
    ("Oxaprozin",           "M01AE", "tablets",  0),
    ("Loxoprofen",          "M01AE", "tablets",  0),
    ("Dexibuprofen",        "M01AE", "tablets",  0),

    # N02BA - salicylates
    ("Aspirin",             "N02BA", "tablets",  0),
    ("Diflunisal",          "N02BA", "tablets",  0),
    ("Salsalate",           "N02BA", "tablets",  0),
    ("Benorylate",          "N02BA", "tablets",  0),
    ("Carbasalate calcium", "N02BA", "sachets",  0),

    # N02BE - anilides (paracetamol family)
    ("Paracetamol",         "N02BE", "tablets",  1),
    ("Propacetamol",        "N02BE", "vials",    1),
    ("Phenacetin",          "N02BE", "tablets",  0),
    ("Bucetin",             "N02BE", "tablets",  0),
    ("Ethenzamide",         "N02BE", "tablets",  0),
    ("Acetanilide",         "N02BE", "tablets",  0),

    # N05B - anxiolytics (controlled)
    ("Diazepam",            "N05B",  "tablets",  1),
    ("Alprazolam",          "N05B",  "tablets",  1),
    ("Lorazepam",           "N05B",  "tablets",  1),
    ("Oxazepam",            "N05B",  "tablets",  1),
    ("Clonazepam",          "N05B",  "tablets",  1),
    ("Bromazepam",          "N05B",  "tablets",  1),
    ("Chlordiazepoxide",    "N05B",  "capsules", 1),
    ("Clobazam",            "N05B",  "tablets",  1),

    # N05C - hypnotics/sedatives (controlled)
    ("Zolpidem",            "N05C",  "tablets",  1),
    ("Zopiclone",           "N05C",  "tablets",  1),
    ("Temazepam",           "N05C",  "capsules", 1),
    ("Nitrazepam",          "N05C",  "tablets",  1),
    ("Triazolam",           "N05C",  "tablets",  1),
    ("Estazolam",           "N05C",  "tablets",  1),
    ("Quazepam",            "N05C",  "tablets",  1),

    # R03 - respiratory (inhalers)
    ("Salbutamol",          "R03",   "inhaler",  1),
    ("Formoterol",          "R03",   "inhaler",  1),
    ("Salmeterol",          "R03",   "inhaler",  1),
    ("Terbutaline",         "R03",   "inhaler",  1),
    ("Fenoterol",           "R03",   "inhaler",  1),
    ("Indacaterol",         "R03",   "inhaler",  1),
    ("Budesonide",          "R03",   "inhaler",  1),
    ("Fluticasone",         "R03",   "inhaler",  1),

    # R06 - antihistamines
    ("Cetirizine",          "R06",   "tablets",  0),
    ("Loratadine",          "R06",   "tablets",  0),
    ("Fexofenadine",        "R06",   "tablets",  0),
    ("Desloratadine",       "R06",   "tablets",  0),
    ("Levocetirizine",      "R06",   "tablets",  0),
    ("Azelastine",          "R06",   "spray",    0),
    ("Bilastine",           "R06",   "tablets",  0),
    ("Ebastine",            "R06",   "tablets",  0),
]

def init_db(db_path: str | Path) -> None:
    """Idempotent. Safe to re-run."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        _create_tables(conn)
        _migrate_schema(conn)
        _seed_reference_data(conn)
        conn.commit()

    print(f"[database] Initialised -> {db_path}")
    _print_summary(db_path)


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        -- ATC classification dimension
        CREATE TABLE IF NOT EXISTS atc_categories (
            atc_code    TEXT PRIMARY KEY,
            atc_name    TEXT NOT NULL,
            system_name TEXT NOT NULL,
            level1_code TEXT NOT NULL,  -- e.g. 'M', 'N', 'R'
            level2_code TEXT NOT NULL   -- e.g. 'M01', 'N02', 'N05'
        );

        -- drug catalog (reference only, sales aggregate at ATC level)
        CREATE TABLE IF NOT EXISTS drugs (
            drug_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name   TEXT    NOT NULL UNIQUE,
            atc_code    TEXT    NOT NULL REFERENCES atc_categories(atc_code),
            unit        TEXT    NOT NULL DEFAULT 'tablets',
            is_critical INTEGER NOT NULL DEFAULT 0
                        CHECK (is_critical IN (0, 1))
        );

        -- sales fact table
        CREATE TABLE IF NOT EXISTS sales (
            sale_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            atc_code    TEXT    NOT NULL REFERENCES atc_categories(atc_code),
            sale_date   TEXT    NOT NULL,  -- ISO-8601: YYYY-MM-DD
            hour        INTEGER,           -- 0–23 for hourly rows; NULL otherwise
            granularity TEXT    NOT NULL   -- 'hourly' | 'daily' | 'weekly' | 'monthly'
                        CHECK (granularity IN ('hourly', 'daily', 'weekly', 'monthly')),
            quantity    REAL    NOT NULL CHECK (quantity >= 0)
        );

        CREATE INDEX IF NOT EXISTS idx_sales_atc_date
            ON sales (atc_code, sale_date);

        CREATE INDEX IF NOT EXISTS idx_sales_granularity
            ON sales (granularity);

        -- current stock per ATC
        CREATE TABLE IF NOT EXISTS atc_inventory (
            atc_code      TEXT PRIMARY KEY REFERENCES atc_categories(atc_code),
            current_stock REAL NOT NULL CHECK (current_stock >= 0),
            last_updated  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes         TEXT
        );

        -- per-batch tracking (expiry + cost)
        CREATE TABLE IF NOT EXISTS inventory_batches (
            batch_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            atc_code          TEXT    NOT NULL REFERENCES atc_categories(atc_code),
            batch_number      TEXT    NOT NULL,
            quantity          REAL    NOT NULL CHECK (quantity >= 0),
            unit_cost         REAL    NOT NULL CHECK (unit_cost >= 0),
            expiry_date       TEXT    NOT NULL,
            received_date     TEXT    NOT NULL DEFAULT CURRENT_DATE,
            notes             TEXT,
            applied_discount  REAL,   -- NULL means use suggested
            returned          INTEGER NOT NULL DEFAULT 0 CHECK (returned IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_batches_atc_expiry
            ON inventory_batches (atc_code, expiry_date);

        -- notification alerts
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type      TEXT NOT NULL,
            atc_code        TEXT,
            batch_number    TEXT,
            severity        TEXT NOT NULL,
            message         TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TEXT
        );

        -- suppliers
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id    INTEGER PRIMARY KEY,
            name           TEXT NOT NULL UNIQUE,
            email          TEXT,
            phone          TEXT,
            lead_time_days INTEGER NOT NULL DEFAULT 7,
            notes          TEXT
        );

        -- sent PO history
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id   INTEGER REFERENCES suppliers(supplier_id),
            supplier_name TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status        TEXT NOT NULL DEFAULT 'SENT',
            total_cost    REAL NOT NULL DEFAULT 0,
            lines_json    TEXT
        );
    """)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add new columns to old DBs."""
    existing_batches = {row[1] for row in conn.execute("PRAGMA table_info(inventory_batches)")}
    if "applied_discount" not in existing_batches:
        conn.execute("ALTER TABLE inventory_batches ADD COLUMN applied_discount REAL")
    if "returned" not in existing_batches:
        conn.execute(
            "ALTER TABLE inventory_batches ADD COLUMN returned INTEGER NOT NULL DEFAULT 0"
        )
    existing_atc = {row[1] for row in conn.execute("PRAGMA table_info(atc_categories)")}
    if "supplier_id" not in existing_atc:
        conn.execute(
            "ALTER TABLE atc_categories ADD COLUMN supplier_id INTEGER"
            " REFERENCES suppliers(supplier_id)"
        )


def _seed_reference_data(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO atc_categories"
        " (atc_code, atc_name, system_name, level1_code, level2_code)"
        " VALUES (?,?,?,?,?)",
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
    conn.executemany(
        """INSERT OR IGNORE INTO suppliers
               (supplier_id, name, email, phone, lead_time_days, notes)
           VALUES (?,?,?,?,?,?)""",
        SUPPLIERS_SEED,
    )
    for atc_code, supplier_id in ATC_SUPPLIER_MAP.items():
        conn.execute(
            "UPDATE atc_categories SET supplier_id = ? WHERE atc_code = ? AND supplier_id IS NULL",
            (supplier_id, atc_code),
        )


def _print_summary(db_path: Path) -> None:
    """Print a quick row-count summary to confirm seeding worked."""
    with sqlite3.connect(db_path) as conn:
        atc_n      = conn.execute("SELECT COUNT(*) FROM atc_categories").fetchone()[0]
        drug_n     = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
        crit_n     = conn.execute("SELECT COUNT(*) FROM drugs WHERE is_critical=1").fetchone()[0]
        inv_n      = conn.execute("SELECT COUNT(*) FROM atc_inventory").fetchone()[0]
        batch_n    = conn.execute("SELECT COUNT(*) FROM inventory_batches").fetchone()[0]
        alert_n    = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        supplier_n = conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
        po_n       = conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]
    print(f"[database]   atc_categories    : {atc_n:>4}")
    print(f"[database]   drugs             : {drug_n:>4}  ({crit_n} critical)")
    print(f"[database]   atc_inventory     : {inv_n:>4}")
    print(f"[database]   inventory_batches : {batch_n:>4}")
    print(f"[database]   alerts            : {alert_n:>4}")
    print(f"[database]   suppliers         : {supplier_n:>4}")
    print(f"[database]   purchase_orders   : {po_n:>4}")
    print(f"[database]   sales             :    0 rows  (populated by ingest_kaggle.py)")


def update_stock(db_path: str | Path, atc_code: str, new_stock: float) -> None:
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
    """Insert a batch and bump atc_inventory."""
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
    """Zero the batch, set returned=1, decrement atc_inventory. Returns units recalled."""
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


def _ensure_alerts_table(conn: sqlite3.Connection) -> None:
    """Migration guard for old DBs without the alerts table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type      TEXT NOT NULL,
            atc_code        TEXT,
            batch_number    TEXT,
            severity        TEXT NOT NULL,
            message         TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TEXT
        )
    """)


def create_alert(
    db_path: str | Path,
    alert_type: str,
    atc_code: str | None,
    batch_number: str | None,
    severity: str,
    message: str,
) -> int:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        _ensure_alerts_table(conn)
        cur = conn.execute(
            """INSERT INTO alerts (alert_type, atc_code, batch_number, severity, message)
               VALUES (?, ?, ?, ?, ?)""",
            (alert_type, atc_code, batch_number, severity, message),
        )
        conn.commit()
        return cur.lastrowid


def alert_key_exists(
    db_path: str | Path,
    alert_type: str,
    atc_code: str | None,
    batch_number: str | None,
) -> bool:
    """True if there's an open alert with the same key. Used to dedupe."""
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        _ensure_alerts_table(conn)
        row = conn.execute(
            """SELECT 1 FROM alerts
               WHERE alert_type = ?
                 AND COALESCE(atc_code, '')     = COALESCE(?, '')
                 AND COALESCE(batch_number, '') = COALESCE(?, '')
                 AND acknowledged_at IS NULL
               LIMIT 1""",
            (alert_type, atc_code, batch_number),
        ).fetchone()
    return row is not None


def get_open_alerts(db_path: str | Path) -> list[dict]:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        _ensure_alerts_table(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT alert_id, alert_type, atc_code, batch_number,
                      severity, message, created_at, acknowledged_at
               FROM alerts
               WHERE acknowledged_at IS NULL
               ORDER BY created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_alerts(db_path: str | Path) -> list[dict]:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        _ensure_alerts_table(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT alert_id, alert_type, atc_code, batch_number,
                      severity, message, created_at, acknowledged_at
               FROM alerts
               ORDER BY created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def acknowledge_alert(db_path: str | Path, alert_id: int) -> None:
    db_path = Path(db_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with sqlite3.connect(db_path) as conn:
        _ensure_alerts_table(conn)
        conn.execute(
            "UPDATE alerts SET acknowledged_at = ? WHERE alert_id = ?",
            (ts, alert_id),
        )
        conn.commit()


def _ensure_purchase_orders_table(conn: sqlite3.Connection) -> None:
    """Migration guard."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id   INTEGER,
            supplier_name TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status        TEXT NOT NULL DEFAULT 'SENT',
            total_cost    REAL NOT NULL DEFAULT 0,
            lines_json    TEXT
        )
    """)


def load_suppliers(db_path: str | Path) -> list[dict]:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT supplier_id, name, email, phone, lead_time_days, notes"
            " FROM suppliers ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def add_supplier(
    db_path: str | Path,
    name: str,
    email: str = "",
    phone: str = "",
    lead_time_days: int = 7,
    notes: str = "",
) -> int:
    """Returns new supplier_id."""
    if not name or not name.strip():
        raise ValueError("Supplier name cannot be empty.")
    if lead_time_days < 0:
        raise ValueError(f"Lead time cannot be negative: {lead_time_days}")

    db_path = Path(db_path)
    name = name.strip()
    with sqlite3.connect(db_path) as conn:
        dup = conn.execute(
            "SELECT supplier_id FROM suppliers WHERE name = ?", (name,)
        ).fetchone()
        if dup:
            raise ValueError(f"Supplier already exists: {name}")
        cur = conn.execute(
            """INSERT INTO suppliers (name, email, phone, lead_time_days, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (name, email.strip(), phone.strip(), int(lead_time_days), notes.strip()),
        )
        conn.commit()
        return cur.lastrowid


def assign_supplier_to_atc(
    db_path: str | Path,
    atc_code: str,
    supplier_id: int,
) -> None:
    """Re-route an ATC to a different supplier."""
    db_path = Path(db_path)
    atc_code = atc_code.strip().upper()
    with sqlite3.connect(db_path) as conn:
        ok = conn.execute(
            "SELECT 1 FROM atc_categories WHERE atc_code = ?", (atc_code,)
        ).fetchone()
        if ok is None:
            raise ValueError(f"Unknown ATC code: {atc_code}")
        ok = conn.execute(
            "SELECT 1 FROM suppliers WHERE supplier_id = ?", (supplier_id,)
        ).fetchone()
        if ok is None:
            raise ValueError(f"Unknown supplier_id: {supplier_id}")
        conn.execute(
            "UPDATE atc_categories SET supplier_id = ? WHERE atc_code = ?",
            (int(supplier_id), atc_code),
        )
        conn.commit()


def save_purchase_order(
    db_path: str | Path,
    supplier_id: int | None,
    supplier_name: str,
    lines_json: str,
    total_cost: float,
) -> int:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        _ensure_purchase_orders_table(conn)
        cur = conn.execute(
            """INSERT INTO purchase_orders
                   (supplier_id, supplier_name, total_cost, lines_json, status)
               VALUES (?, ?, ?, ?, 'SENT')""",
            (supplier_id, supplier_name, total_cost, lines_json),
        )
        conn.commit()
        return cur.lastrowid


def load_purchase_orders(db_path: str | Path) -> list[dict]:
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        _ensure_purchase_orders_table(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT po_id, supplier_id, supplier_name, created_at, status, total_cost
               FROM purchase_orders
               ORDER BY created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def save_batch_overrides(
    db_path: str | Path,
    overrides: list[dict],
) -> None:
    """Each dict: {batch_id, applied_discount, returned}. Returned=True zeroes qty."""
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
