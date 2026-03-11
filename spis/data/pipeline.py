"""
spis/data/pipeline.py
---------------------
Phase 2 data pipeline: extracts daily sales from the SQLite database,
validates the data, fills missing dates, engineers time-series features,
and splits into train/test sets for XGBoost forecasting (Phase 3).

Output granularity: daily (one row per ATC code per day).

Features engineered (26 total):
    Calendar  — day_of_week, day_of_month, month, year, week_of_year,
                is_weekend, is_holiday, season, is_payday_window,
                is_school_holiday
    Lags      — lag_1, lag_7, lag_14, lag_28, lag_365
    Rolling   — rolling_mean_7, rolling_std_7, rolling_mean_14, rolling_mean_28,
                rolling_min_7, rolling_max_7, rolling_mean_90, rolling_mean_365,
                ema_7
    Derived   — lag_ratio_7, trend_counter

Usage:
    from spis.data.pipeline import run_pipeline
    run_pipeline("data/inventory.db", "data/processed")
"""

import sqlite3
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

# Turkish school holiday periods (approximate, based on MEB calendar).
# Each tuple is (month_start, day_start, month_end, day_end).
TURKEY_SCHOOL_HOLIDAYS = [
    (1, 20, 2, 3),    # Winter / semester break (~2 weeks in late Jan)
    (6, 15, 9, 15),   # Summer break (~3 months, mid-Jun to mid-Sep)
]

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

def _is_school_holiday(date_series: pd.Series) -> pd.Series:
    """Return a 0/1 Series indicating Turkish school holiday periods."""
    month = date_series.dt.month
    day = date_series.dt.day
    result = pd.Series(0, index=date_series.index)

    for m_start, d_start, m_end, d_end in TURKEY_SCHOOL_HOLIDAYS:
        if m_start <= m_end:
            in_range = (
                ((month > m_start) | ((month == m_start) & (day >= d_start)))
                & ((month < m_end) | ((month == m_end) & (day <= d_end)))
            )
        else:
            in_range = (
                ((month > m_start) | ((month == m_start) & (day >= d_start)))
                | ((month < m_end) | ((month == m_end) & (day <= d_end)))
            )
        result = result | in_range.astype(int)

    return result


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 26 time-series features to each row, computed per ATC code.

    Calendar features (10):
        day_of_week, day_of_month, month, year, week_of_year, is_weekend,
        is_holiday, season, is_payday_window, is_school_holiday

    Lag features (5):
        lag_1, lag_7, lag_14, lag_28, lag_365

    Rolling window features (9):
        rolling_mean_7, rolling_std_7, rolling_mean_14, rolling_mean_28,
        rolling_min_7, rolling_max_7, rolling_mean_90, rolling_mean_365,
        ema_7

    Derived features (2):
        lag_ratio_7, trend_counter

    Args:
        df: DataFrame with columns [date, atc_code, quantity].

    Returns:
        DataFrame with all original columns plus 26 new feature columns.
    """
    df = df.sort_values(["atc_code", "date"]).copy()

    # ── Calendar features ────────────────────────────────────────────────
    df["day_of_week"]  = df["date"].dt.dayofweek       # 0=Mon, 6=Sun
    df["day_of_month"] = df["date"].dt.day
    df["month"]        = df["date"].dt.month
    df["year"]         = df["date"].dt.year
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)

    # Turkey public holidays (sales data is from a Turkish pharmacy)
    tr_holidays = holidays.Turkey(years=range(
        df["date"].dt.year.min(), df["date"].dt.year.max() + 1
    ))
    df["is_holiday"]   = df["date"].dt.date.isin(tr_holidays).astype(int)

    # Season: 1=Winter (Dec-Feb), 2=Spring (Mar-May), 3=Summer (Jun-Aug), 4=Fall (Sep-Nov)
    df["season"] = df["month"].map({
        12: 1, 1: 1, 2: 1,
        3: 2, 4: 2, 5: 2,
        6: 3, 7: 3, 8: 3,
        9: 4, 10: 4, 11: 4,
    })

    # Payday window: days 1-3 and 15-17 of each month (Turkish salary cycle)
    dom = df["day_of_month"]
    df["is_payday_window"] = (((dom >= 1) & (dom <= 3)) | ((dom >= 15) & (dom <= 17))).astype(int)

    # School holidays (Turkish MEB calendar)
    df["is_school_holiday"] = _is_school_holiday(df["date"])

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

    # Exponential moving average (reacts faster to recent demand changes)
    df["ema_7"] = grouped.transform(lambda x: x.ewm(span=7).mean())

    # ── Derived features ─────────────────────────────────────────────────

    # Lag ratio: how yesterday compares to the weekly average (spike detector)
    df["lag_ratio_7"] = df["lag_1"] / df["rolling_mean_7"].replace(0, np.nan)

    # Trend counter: days since the start of the dataset (captures long-term trend)
    date_min = df["date"].min()
    df["trend_counter"] = (df["date"] - date_min).dt.days

    print(f"[pipeline] Engineered 26 features -> {len(df.columns)} total columns.")
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
        4. Engineer 26 time-series features
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
