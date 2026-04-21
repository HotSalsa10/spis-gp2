"""
scripts/ingest_kaggle.py
------------------------
One-time ETL script: downloads the Pharma Sales Dataset from Kaggle,
copies the raw CSVs to data/raw/, and loads them into data/inventory.db.

Dataset : milanzdravkovic/pharma-sales-data (2014–2019)
Files   : saleshourly.csv, salesdaily.csv, salesweekly.csv, salesmonthly.csv

Prerequisites
-------------
  A Kaggle API token is required.
  1. Go to https://www.kaggle.com/settings  ->  API  ->  "Create New Token"
  2. Move the downloaded kaggle.json to  C:\\Users\\<you>\\.kaggle\\kaggle.json
  3. Run:  python scripts/ingest_kaggle.py

Usage
-----
  # From the project root, with the venv active:
  python scripts/ingest_kaggle.py
"""

import datetime
import shutil
import sqlite3
import sys
from pathlib import Path

import kagglehub
import pandas as pd

# ---------------------------------------------------------------------------
# Make the project root importable so we can use spis.*
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from spis.data.database import init_db  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATASET_SLUG  = "milanzdravkovic/pharma-sales-data"
RAW_DIR       = PROJECT_ROOT / "data" / "raw"
DB_PATH       = PROJECT_ROOT / "data" / "inventory.db"

# The 8 ATC-category column names present in each CSV.
ATC_CODES = {"M01AB", "M01AE", "N02BA", "N02BE", "N05B", "N05C", "R03", "R06"}

# Maps each expected filename to its time granularity label.
GRANULARITY_MAP = {
    "saleshourly.csv":  "hourly",
    "salesdaily.csv":   "daily",
    "salesweekly.csv":  "weekly",
    "salesmonthly.csv": "monthly",
}


# ---------------------------------------------------------------------------
# Step 1 — Download
# ---------------------------------------------------------------------------
def download_dataset() -> Path:
    """
    Download the Kaggle dataset to the local cache and return the directory path.
    kagglehub skips the download if the dataset is already cached.
    """
    print(f"\n[ingest] Downloading '{DATASET_SLUG}' from Kaggle ...")
    try:
        cache_path = Path(kagglehub.dataset_download(DATASET_SLUG))
    except Exception as exc:
        print(f"\n[ingest] ERROR: {exc}")
        print(
            "\nHint: Make sure your Kaggle API token exists at:\n"
            "  C:\\Users\\<you>\\.kaggle\\kaggle.json\n"
            "Generate one at: https://www.kaggle.com/settings -> API -> Create New Token"
        )
        sys.exit(1)

    print(f"[ingest] Cached at: {cache_path}")
    return cache_path


# ---------------------------------------------------------------------------
# Step 2 — Copy raw CSVs
# ---------------------------------------------------------------------------
def copy_to_raw(source_dir: Path) -> None:
    """
    Copy all CSVs from the Kaggle cache into data/raw/.
    Keeping raw files untouched is good data-science practice —
    the database can always be rebuilt from them.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for csv_file in source_dir.rglob("*.csv"):
        dest = RAW_DIR / csv_file.name
        shutil.copy2(csv_file, dest)
        print(f"[ingest] Copied -> {dest.relative_to(PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# Step 3 — Parse helpers
# ---------------------------------------------------------------------------
def _resolve_date_column(df: pd.DataFrame, granularity: str) -> pd.Series:
    """
    Return a Series of ISO-8601 date strings (YYYY-MM-DD) for every row.

    The four CSVs use slightly different date representations:
      • hourly / daily  ->  'datum' column  (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
      • weekly          ->  'Year' + 'Week' columns  (ISO week number)
      • monthly         ->  'Year' + 'Month' columns
    """
    # Try straightforward date columns first
    for col in ("datum", "Datum", "date", "Date"):
        if col in df.columns:
            return pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d")

    # Weekly: convert ISO year + week -> Monday of that week
    if {"Year", "Week"}.issubset(df.columns):
        return df.apply(
            lambda r: datetime.date.fromisocalendar(
                int(r["Year"]), int(r["Week"]), 1
            ).isoformat(),
            axis=1,
        )

    # Monthly: Year + Month -> first day of month
    if {"Year", "Month"}.issubset(df.columns):
        return pd.to_datetime(
            df[["Year", "Month"]].assign(Day=1).rename(
                columns={"Year": "year", "Month": "month", "Day": "day"}
            )
        ).dt.strftime("%Y-%m-%d")

    raise ValueError(
        f"Cannot find a date column in the DataFrame. "
        f"Columns present: {list(df.columns)}"
    )


def _resolve_hour_column(df: pd.DataFrame, granularity: str) -> pd.Series:
    """Return a Series of hour integers (0–23) for hourly data, or None for other granularities."""
    if granularity != "hourly":
        return pd.Series([None] * len(df), dtype=object)

    for col in ("Hour", "hour", "h"):
        if col in df.columns:
            return df[col].astype("Int64")  # nullable integer

    # If no hour column found in an hourly file, default to 0
    print("[ingest] WARNING: hourly file has no Hour column — defaulting to hour=0.")
    return pd.Series([0] * len(df), dtype="Int64")


# ---------------------------------------------------------------------------
# Step 4 — Load one CSV into the sales table
# ---------------------------------------------------------------------------
def load_csv_to_db(csv_path: Path, granularity: str, conn: sqlite3.Connection) -> int:
    """
    Read one CSV, melt from wide to long format, and bulk-insert into sales.

    Wide format (one column per drug):
        datum       | M01AB | M01AE | ...
        2014-01-01  |  47.0 |  82.0 | ...

    Long format (one row per drug per time point — what the DB stores):
        atc_code | sale_date  | hour | granularity | quantity
        M01AB    | 2014-01-01 | NULL | daily       | 47.0
        M01AE    | 2014-01-01 | NULL | daily       | 82.0

    Returns:
        Number of rows inserted.
    """
    df = pd.read_csv(csv_path)

    # Only keep ATC columns that actually exist in this file
    present_atc = [col for col in df.columns if col in ATC_CODES]
    if not present_atc:
        print(f"[ingest] WARNING: No ATC columns found in {csv_path.name} — skipping.")
        return 0

    # Attach normalised date and hour columns.
    # Note: avoid leading underscores — itertuples() silently drops them.
    df["sale_date"] = _resolve_date_column(df, granularity)
    df["hour_val"]  = _resolve_hour_column(df, granularity)

    # Melt: wide -> long, drop rows where quantity is NaN
    melted = (
        df[["sale_date", "hour_val"] + present_atc]
        .melt(id_vars=["sale_date", "hour_val"], var_name="atc_code", value_name="quantity")
        .dropna(subset=["quantity"])
    )
    melted["granularity"] = granularity

    # Build a list of plain Python tuples for sqlite3 (handles pd.NA -> None)
    records = [
        (
            row.atc_code,
            row.sale_date,
            None if pd.isna(row.hour_val) else int(row.hour_val),
            row.granularity,
            float(row.quantity),
        )
        for row in melted.itertuples(index=False)
    ]

    conn.executemany(
        "INSERT INTO sales (atc_code, sale_date, hour, granularity, quantity) VALUES (?,?,?,?,?)",
        records,
    )
    return len(records)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-raw",
        action="store_true",
        help="Skip Kaggle download and use the CSVs already in data/raw/",
    )
    args = parser.parse_args()

    if args.from_raw:
        missing = [f for f in GRANULARITY_MAP if not (RAW_DIR / f).exists()]
        if missing:
            print(f"[ingest] ERROR: Missing files in data/raw/: {missing}")
            sys.exit(1)
        print("[ingest] --from-raw: skipping Kaggle download, using data/raw/ directly.")
    else:
        # 1. Download from Kaggle
        cache_dir = download_dataset()
        # 2. Copy raw CSVs into data/raw/
        copy_to_raw(cache_dir)

    # 3. Initialise schema + seed ATC / drug reference data
    print()
    init_db(DB_PATH)

    # 4. Load each CSV granularity into the sales table
    print()
    total_rows = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")  # faster bulk inserts

        for filename, granularity in GRANULARITY_MAP.items():
            csv_path = RAW_DIR / filename
            if not csv_path.exists():
                print(f"[ingest] WARNING: {filename} not found — skipping.")
                continue

            n = load_csv_to_db(csv_path, granularity, conn)
            conn.commit()
            print(f"[ingest] {filename:<24}  ->  {n:>8,} rows  ({granularity})")
            total_rows += n

    # 5. Print final summary
    print("\n--- Sales table summary ---")
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT granularity, COUNT(*) FROM sales GROUP BY granularity ORDER BY granularity"
        ).fetchall()
    for granularity, count in rows:
        print(f"  {granularity:<10} : {count:>9,} rows")
    print(f"  {'TOTAL':<10} : {total_rows:>9,} rows")
    print(f"\n[ingest] Done.  Database -> {DB_PATH.relative_to(PROJECT_ROOT)}\n")


if __name__ == "__main__":
    main()
