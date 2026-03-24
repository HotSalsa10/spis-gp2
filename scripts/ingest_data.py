"""
scripts/ingest_data.py
----------------------
Generic CSV ingester — loads historical sales data from any pharmacy into
data/inventory.db.  This script is the pharmacy-agnostic alternative to
ingest_kaggle.py, which is specific to one Kaggle dataset.

Expected CSV format (long / tidy form — one row per ATC code per date):

    date,atc_code,quantity
    2023-01-01,M01AB,45.0
    2023-01-01,N02BE,23.0
    ...

Column names can be customised via --date-col / --atc-col / --qty-col.

Behaviour for unknown ATC codes
--------------------------------
- If all ATC codes in the CSV already exist in atc_categories, data loads
  immediately.
- If unknown codes are found and --register is supplied, they are
  auto-registered in atc_categories and atc_inventory (stock=0) before
  loading.
- Without --register the script exits with a clear error listing the
  unknown codes so the operator can run register_atc.py first.

Usage
-----
  # Minimal — load daily sales from a CSV:
  python scripts/ingest_data.py --csv path/to/sales.csv

  # Specify column names when they differ from the defaults:
  python scripts/ingest_data.py --csv path/to/sales.csv \\
      --date-col SaleDate --atc-col DrugCode --qty-col Units

  # Auto-register any new ATC codes found in the file:
  python scripts/ingest_data.py --csv path/to/sales.csv --register

  # Weekly granularity and a custom DB path:
  python scripts/ingest_data.py --csv path/to/sales.csv \\
      --granularity weekly --db custom/pharmacy.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Make the project root importable so we can use spis.*
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from spis.data.database import init_db  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_and_normalise(
    csv_path: Path,
    date_col: str,
    atc_col: str,
    qty_col: str,
    granularity: str,
) -> pd.DataFrame:
    """
    Read the CSV and return a normalised DataFrame with columns:
        [atc_code, sale_date, hour, granularity, quantity]
    ready for bulk-insert into the sales table.

    Raises:
        SystemExit: If required columns are missing or dates cannot be parsed.
    """
    df = pd.read_csv(csv_path)

    # Verify required columns exist
    missing_cols = {date_col, atc_col, qty_col} - set(df.columns)
    if missing_cols:
        print(f"[ingest] ERROR: The following columns are not in {csv_path.name}:")
        for col in sorted(missing_cols):
            print(f"         '{col}'")
        print(f"[ingest] Columns found: {list(df.columns)}")
        print(
            "[ingest] Use --date-col / --atc-col / --qty-col to map your column names."
        )
        sys.exit(1)

    # Parse dates
    try:
        dates = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
    except Exception as exc:
        print(f"[ingest] ERROR: Cannot parse '{date_col}' as dates: {exc}")
        sys.exit(1)

    # Clip negative quantities (with a warning)
    qty = pd.to_numeric(df[qty_col], errors="coerce").fillna(0.0)
    neg_count = (qty < 0).sum()
    if neg_count > 0:
        print(f"[ingest] WARNING: {neg_count} negative quantities clipped to 0.")
        qty = qty.clip(lower=0)

    normalised = pd.DataFrame({
        "atc_code":    df[atc_col].astype(str).str.strip(),
        "sale_date":   dates,
        "hour":        None,    # generic CSV is not hourly
        "granularity": granularity,
        "quantity":    qty,
    }).dropna(subset=["sale_date", "quantity"])

    return normalised


def _get_db_atc_codes(conn: sqlite3.Connection) -> set:
    """Return the set of ATC codes currently in atc_categories."""
    rows = conn.execute("SELECT atc_code FROM atc_categories").fetchall()
    return {row[0] for row in rows}


def _register_unknown_codes(
    unknown: set,
    conn: sqlite3.Connection,
) -> None:
    """
    Auto-register unknown ATC codes with minimal metadata.
    The operator can update the names later via an SQL UPDATE or the
    register_atc.py script.
    """
    for code in sorted(unknown):
        conn.execute(
            "INSERT OR IGNORE INTO atc_categories "
            "(atc_code, atc_name, system_name, level1_code, level2_code) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, f"Unknown ({code})", "Unknown", code[0], code[:3]),
        )
        conn.execute(
            "INSERT OR IGNORE INTO atc_inventory "
            "(atc_code, current_stock, notes) VALUES (?, 0.0, ?)",
            (code, "Auto-registered by ingest_data.py — update stock manually."),
        )
        print(f"[ingest] Registered new ATC code: {code}  (update metadata via register_atc.py)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SPIS — Generic CSV sales ingester"
    )
    parser.add_argument(
        "--csv", required=True,
        help="Path to the input CSV file.",
    )
    parser.add_argument(
        "--db", default="data/inventory.db",
        help="Path to the SQLite database (default: data/inventory.db).",
    )
    parser.add_argument(
        "--granularity", default="daily",
        choices=["hourly", "daily", "weekly", "monthly"],
        help="Sales granularity for all rows in this file (default: daily).",
    )
    parser.add_argument(
        "--date-col", default="date",
        help="CSV column containing the sale date (default: 'date').",
    )
    parser.add_argument(
        "--atc-col", default="atc_code",
        help="CSV column containing the ATC code (default: 'atc_code').",
    )
    parser.add_argument(
        "--qty-col", default="quantity",
        help="CSV column containing the quantity sold (default: 'quantity').",
    )
    parser.add_argument(
        "--register", action="store_true",
        help="Auto-register any unknown ATC codes instead of aborting.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    db_path  = Path(args.db)

    if not csv_path.exists():
        print(f"[ingest] ERROR: File not found: {csv_path}")
        sys.exit(1)

    print("=" * 60)
    print("SPIS Generic CSV Ingester")
    print("=" * 60)
    print(f"  Input CSV   : {csv_path}")
    print(f"  Database    : {db_path}")
    print(f"  Granularity : {args.granularity}")
    print()

    # Ensure DB schema exists
    init_db(db_path)
    print()

    # Load and normalise the CSV
    df = _load_and_normalise(
        csv_path,
        date_col=args.date_col,
        atc_col=args.atc_col,
        qty_col=args.qty_col,
        granularity=args.granularity,
    )

    print(f"[ingest] Loaded {len(df):,} rows from {csv_path.name}")
    found_codes = set(df["atc_code"].unique())
    print(f"[ingest] ATC codes in file: {sorted(found_codes)}")

    # Check against DB
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        known_codes = _get_db_atc_codes(conn)
        unknown = found_codes - known_codes

        if unknown:
            if args.register:
                print(
                    f"\n[ingest] Registering {len(unknown)} unknown ATC code(s) ..."
                )
                _register_unknown_codes(unknown, conn)
                conn.commit()
            else:
                print(
                    f"\n[ingest] ERROR: {len(unknown)} unknown ATC code(s) found: "
                    f"{sorted(unknown)}"
                )
                print(
                    "[ingest] Options:\n"
                    "  1. Run register_atc.py for each new code first:\n"
                    "         python scripts/register_atc.py --code <CODE> --name <NAME> ...\n"
                    "  2. Or pass --register to auto-register with placeholder metadata:\n"
                    "         python scripts/ingest_data.py --csv ... --register"
                )
                sys.exit(1)

        # Bulk-insert
        records = [
            (
                row.atc_code,
                row.sale_date,
                row.hour,
                row.granularity,
                float(row.quantity),
            )
            for row in df.itertuples(index=False)
        ]

        conn.executemany(
            "INSERT INTO sales (atc_code, sale_date, hour, granularity, quantity) "
            "VALUES (?,?,?,?,?)",
            records,
        )
        conn.commit()

    print(f"\n[ingest] Inserted {len(records):,} rows into sales table.")

    # Summary
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT granularity, COUNT(*) FROM sales GROUP BY granularity ORDER BY granularity"
        ).fetchall()
    print("\n--- Sales table summary ---")
    for granularity, count in rows:
        print(f"  {granularity:<10} : {count:>9,} rows")

    print(f"\n[ingest] Done.  Database -> {db_path}")
    print(
        "\nNext steps:\n"
        "  python scripts/run_pipeline.py   # rebuild features\n"
        "  python scripts/train_model.py    # retrain XGBoost\n"
        "  python scripts/assess_risk.py    # check risk tiers"
    )


if __name__ == "__main__":
    main()
