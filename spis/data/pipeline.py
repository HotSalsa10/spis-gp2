"""
spis/data/pipeline.py
---------------------
Phase 2 data pipeline: extracts daily sales from the SQLite database,
validates the data, fills missing dates, engineers time-series features,
and splits into train/test sets for XGBoost forecasting (Phase 3).

Output granularity: daily (one row per ATC code per day).

Features engineered (19 total):
    Calendar  — day_of_week, day_of_month, month, year, week_of_year, is_weekend
    Lags      — lag_1, lag_7, lag_14, lag_28, lag_365
    Rolling   — rolling_mean_7, rolling_std_7, rolling_mean_14, rolling_mean_28,
                rolling_min_7, rolling_max_7, rolling_mean_90, rolling_mean_365

Usage:
    from spis.data.pipeline import run_pipeline
    run_pipeline("data/inventory.db", "data/processed")
"""

import sqlite3
from pathlib import Path

import pandas as pd

# The 8 ATC codes present in the Kaggle pharmacy sales dataset.
EXPECTED_ATC_CODES = {"M01AB", "M01AE", "N02BA", "N02BE", "N05B", "N05C", "R03", "R06"}


# ---------------------------------------------------------------------------
# Step 1 — Extract daily sales from the database
# ---------------------------------------------------------------------------

def load_daily_sales(db_path: str | Path) -> pd.DataFrame:
    """
    Query the sales table for daily-granularity rows and return a DataFrame
    with columns: [atc_code, date, quantity].

    Args:
        db_path: Path to the SQLite database (data/inventory.db).

    Returns:
        DataFrame sorted by (atc_code, date).
    """
    query = """
        SELECT atc_code, sale_date, quantity
        FROM sales
        WHERE granularity = 'daily'
        ORDER BY atc_code, sale_date
    """
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(query, conn)

    df.rename(columns={"sale_date": "date"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Step 2 — Validate
# ---------------------------------------------------------------------------

def validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run quality checks on the raw daily sales DataFrame.

    Checks performed:
        - No null values in any column
        - No negative quantities
        - All 8 expected ATC codes are present
        - No duplicate (atc_code, date) pairs (aggregates if found)

    Args:
        df: DataFrame with columns [atc_code, date, quantity].

    Returns:
        Cleaned DataFrame (duplicates aggregated if any were found).
    """
    # --- Null check ---
    null_counts = df.isnull().sum()
    if null_counts.any():
        print(f"[pipeline] WARNING: Found null values:\n{null_counts[null_counts > 0]}")
        df = df.dropna()

    # --- Negative quantities ---
    neg_count = (df["quantity"] < 0).sum()
    if neg_count > 0:
        print(f"[pipeline] WARNING: {neg_count} negative quantities found — clipping to 0.")
        df["quantity"] = df["quantity"].clip(lower=0)

    # --- ATC code check ---
    found_codes = set(df["atc_code"].unique())
    missing = EXPECTED_ATC_CODES - found_codes
    if missing:
        print(f"[pipeline] WARNING: Missing ATC codes: {missing}")

    # --- Duplicate check ---
    dup_count = df.duplicated(subset=["atc_code", "date"]).sum()
    if dup_count > 0:
        print(f"[pipeline] WARNING: {dup_count} duplicate (atc_code, date) rows — aggregating.")
        df = df.groupby(["atc_code", "date"], as_index=False)["quantity"].sum()

    # --- Summary ---
    print(f"[pipeline] Validation passed:")
    print(f"  Rows       : {len(df):,}")
    print(f"  Date range : {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  ATC codes  : {sorted(found_codes)}")

    return df


# ---------------------------------------------------------------------------
# Step 3 — Fill missing dates
# ---------------------------------------------------------------------------

def fill_missing_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure every ATC code has a row for every day in the date range.
    Missing days are filled with quantity = 0 (no sales recorded).

    Args:
        df: Validated DataFrame with columns [atc_code, date, quantity].

    Returns:
        DataFrame with no date gaps (one row per ATC code per day).
    """
    date_min = df["date"].min()
    date_max = df["date"].max()
    full_range = pd.date_range(date_min, date_max, freq="D")

    parts = []
    for atc_code, group in df.groupby("atc_code"):
        group = group.set_index("date").reindex(full_range)
        group["atc_code"] = atc_code
        group["quantity"] = group["quantity"].fillna(0.0)
        group.index.name = "date"
        parts.append(group.reset_index())

    result = pd.concat(parts, ignore_index=True)

    filled = len(result) - len(df)
    if filled > 0:
        print(f"[pipeline] Filled {filled} missing date rows with quantity=0.")
    else:
        print(f"[pipeline] No missing dates found.")

    return result


# ---------------------------------------------------------------------------
# Step 4 — Feature engineering
# ---------------------------------------------------------------------------

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 19 time-series features to each row, computed per ATC code.

    Calendar features (6):
        day_of_week, day_of_month, month, year, week_of_year, is_weekend

    Lag features (5):
        lag_1, lag_7, lag_14, lag_28, lag_365

    Rolling window features (8):
        rolling_mean_7, rolling_std_7, rolling_mean_14, rolling_mean_28,
        rolling_min_7, rolling_max_7, rolling_mean_90, rolling_mean_365

    Args:
        df: DataFrame with columns [date, atc_code, quantity].

    Returns:
        DataFrame with all original columns plus 19 new feature columns.
    """
    df = df.sort_values(["atc_code", "date"]).copy()

    # ── Calendar features ────────────────────────────────────────────────
    df["day_of_week"]  = df["date"].dt.dayofweek       # 0=Mon, 6=Sun
    df["day_of_month"] = df["date"].dt.day
    df["month"]        = df["date"].dt.month
    df["year"]         = df["date"].dt.year
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)

    # ── Lag and rolling features (per ATC code) ──────────────────────────
    grouped = df.groupby("atc_code")["quantity"]

    # Lag features
    for lag in [1, 7, 14, 28, 365]:
        df[f"lag_{lag}"] = grouped.shift(lag)

    # Rolling window features
    df["rolling_mean_7"]   = grouped.transform(lambda x: x.rolling(7).mean())
    df["rolling_std_7"]    = grouped.transform(lambda x: x.rolling(7).std())
    df["rolling_mean_14"]  = grouped.transform(lambda x: x.rolling(14).mean())
    df["rolling_mean_28"]  = grouped.transform(lambda x: x.rolling(28).mean())
    df["rolling_min_7"]    = grouped.transform(lambda x: x.rolling(7).min())
    df["rolling_max_7"]    = grouped.transform(lambda x: x.rolling(7).max())
    df["rolling_mean_90"]  = grouped.transform(lambda x: x.rolling(90).mean())
    df["rolling_mean_365"] = grouped.transform(lambda x: x.rolling(365).mean())

    print(f"[pipeline] Engineered 19 features -> {len(df.columns)} total columns.")
    return df


# ---------------------------------------------------------------------------
# Step 5 — Train / test split
# ---------------------------------------------------------------------------

def split_train_test(
    df: pd.DataFrame,
    cutoff: str = "2019-01-01",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split the featured DataFrame into train and test sets by date.

    Rows where lag_7 is NaN (the first 7 days of data) are dropped because
    weekly lag is the most commonly used feature for demand forecasting.

    Args:
        df:     Featured DataFrame (output of engineer_features).
        cutoff: ISO date string. Train < cutoff, test >= cutoff.

    Returns:
        (train_df, test_df) tuple.
    """
    cutoff_dt = pd.Timestamp(cutoff)

    # Drop rows where lag_7 is NaN (first 7 days per ATC code)
    before = len(df)
    df = df.dropna(subset=["lag_7"])
    dropped = before - len(df)
    if dropped > 0:
        print(f"[pipeline] Dropped {dropped} rows with NaN lag_7 (first 7 days).")

    train = df[df["date"] < cutoff_dt].copy()
    test  = df[df["date"] >= cutoff_dt].copy()

    print(f"[pipeline] Train: {len(train):,} rows  ({train['date'].min().date()} to {train['date'].max().date()})")
    print(f"[pipeline] Test : {len(test):,} rows  ({test['date'].min().date()} to {test['date'].max().date()})")

    return train, test


# ---------------------------------------------------------------------------
# Step 6 — Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(db_path: str | Path, output_dir: str | Path) -> None:
    """
    Execute the full data pipeline end-to-end.

    Steps:
        1. Load daily sales from the database
        2. Validate and clean the data
        3. Fill missing dates with zero quantities
        4. Engineer 19 time-series features
        5. Split into train/test sets (cutoff: 2019-01-01)
        6. Write CSVs to the output directory

    Args:
        db_path:    Path to the SQLite database.
        output_dir: Directory where output CSVs will be saved.
    """
    db_path    = Path(db_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SPIS Data Pipeline -- Phase 2")
    print("=" * 60)

    # 1. Extract
    print("\n[1/5] Loading daily sales ...")
    df = load_daily_sales(db_path)

    # 2. Validate
    print("\n[2/5] Validating ...")
    df = validate(df)

    # 3. Fill gaps
    print("\n[3/5] Filling missing dates ...")
    df = fill_missing_dates(df)

    # 4. Feature engineering
    print("\n[4/5] Engineering features ...")
    df = engineer_features(df)

    # 5. Split
    print("\n[5/5] Splitting train / test ...")
    train, test = split_train_test(df)

    # 6. Write outputs
    print("\nWriting output files ...")
    features_path = output_dir / "features_daily.csv"
    train_path    = output_dir / "train.csv"
    test_path     = output_dir / "test.csv"

    df.to_csv(features_path, index=False)
    train.to_csv(train_path, index=False)
    test.to_csv(test_path, index=False)

    print(f"  {features_path}  ({len(df):,} rows)")
    print(f"  {train_path}  ({len(train):,} rows)")
    print(f"  {test_path}  ({len(test):,} rows)")
    print("\n[pipeline] Done.")
