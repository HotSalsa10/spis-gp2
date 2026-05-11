"""Pipeline: pull daily sales from DB, clean, fill gaps, engineer 35 features, split."""

import sqlite3
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

# Turkish school holidays (rough, MEB calendar) -- (m_start, d_start, m_end, d_end)
TURKEY_SCHOOL_HOLIDAYS = [
    (1, 20, 2, 3),    # winter break
    (6, 15, 9, 15),   # summer
]

# only used by tests as a sanity check; runtime reads from DB
EXPECTED_ATC_CODES = {"M01AB", "M01AE", "N02BA", "N02BE", "N05B", "N05C", "R03", "R06"}


def load_daily_sales(db_path: str | Path) -> pd.DataFrame:
    """Daily rows only -> [atc_code, date, quantity]."""
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


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Drop nulls, clip negatives, aggregate dupes."""
    null_counts = df.isnull().sum()
    if null_counts.any():
        print(f"[pipeline] WARNING: Found null values:\n{null_counts[null_counts > 0]}")
        df = df.dropna()

    neg_count = (df["quantity"] < 0).sum()
    if neg_count > 0:
        print(f"[pipeline] WARNING: {neg_count} negative quantities found — clipping to 0.")
        df["quantity"] = df["quantity"].clip(lower=0)

    dup_count = df.duplicated(subset=["atc_code", "date"]).sum()
    if dup_count > 0:
        print(f"[pipeline] WARNING: {dup_count} duplicate (atc_code, date) rows — aggregating.")
        df = df.groupby(["atc_code", "date"], as_index=False)["quantity"].sum()

    found_codes = set(df["atc_code"].unique())
    print(f"[pipeline] Validation passed:")
    print(f"  Rows       : {len(df):,}")
    print(f"  Date range : {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  ATC codes  : {sorted(found_codes)}")

    return df


def fill_missing_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Reindex every ATC to a full date range, fill missing days with 0."""
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


def _is_school_holiday(date_series: pd.Series) -> pd.Series:
    """0/1 Turkish school break flag."""
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
            # wraps around end of year
            in_range = (
                ((month > m_start) | ((month == m_start) & (day >= d_start)))
                | ((month < m_end) | ((month == m_end) & (day <= d_end)))
            )
        result = result | in_range.astype(int)

    return result


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """35 features per (atc, date). Computed group-wise so no cross-drug leakage."""
    df = df.sort_values(["atc_code", "date"]).copy()

    # calendar (12)
    df["day_of_week"]  = df["date"].dt.dayofweek       # 0=Mon
    df["day_of_month"] = df["date"].dt.day
    df["month"]        = df["date"].dt.month
    df["year"]         = df["date"].dt.year
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)

    # data is Turkish so use Turkey here (live forecast uses Saudi instead)
    tr_holidays = holidays.Turkey(years=range(
        df["date"].dt.year.min(), df["date"].dt.year.max() + 1
    ))
    df["is_holiday"]   = df["date"].dt.date.isin(tr_holidays).astype(int)

    # 1=winter..4=fall
    df["season"] = df["month"].map({
        12: 1, 1: 1, 2: 1,
        3: 2, 4: 2, 5: 2,
        6: 3, 7: 3, 8: 3,
        9: 4, 10: 4, 11: 4,
    })

    # Turkish payday cycle: 1-3 and 15-17
    dom = df["day_of_month"]
    df["is_payday_window"] = (((dom >= 1) & (dom <= 3)) | ((dom >= 15) & (dom <= 17))).astype(int)

    df["is_school_holiday"] = _is_school_holiday(df["date"])
    df["quarter"] = df["date"].dt.quarter
    df["days_to_month_end"] = df["date"].dt.days_in_month - df["day_of_month"]

    # per-ATC group ops so we don't leak across drugs
    grouped = df.groupby("atc_code")["quantity"]

    # lags (7)
    for lag in [1, 2, 3, 7, 14, 28, 365]:
        df[f"lag_{lag}"] = grouped.shift(lag)

    # rolling (12)
    df["rolling_mean_7"]   = grouped.transform(lambda x: x.rolling(7).mean())
    df["rolling_std_7"]    = grouped.transform(lambda x: x.rolling(7).std())
    df["rolling_mean_14"]  = grouped.transform(lambda x: x.rolling(14).mean())
    df["rolling_mean_28"]  = grouped.transform(lambda x: x.rolling(28).mean())
    df["rolling_std_28"]   = grouped.transform(lambda x: x.rolling(28).std())
    df["rolling_min_7"]    = grouped.transform(lambda x: x.rolling(7).min())
    df["rolling_max_7"]    = grouped.transform(lambda x: x.rolling(7).max())
    df["rolling_mean_90"]  = grouped.transform(lambda x: x.rolling(90).mean())
    df["rolling_mean_365"] = grouped.transform(lambda x: x.rolling(365).mean())
    df["ema_7"]  = grouped.transform(lambda x: x.ewm(span=7).mean())
    df["ema_14"] = grouped.transform(lambda x: x.ewm(span=14).mean())
    df["ema_28"] = grouped.transform(lambda x: x.ewm(span=28).mean())

    # derived (4)
    df["lag_ratio_7"] = df["lag_1"] / df["rolling_mean_7"].replace(0, np.nan)
    date_min = df["date"].min()
    df["trend_counter"] = (df["date"] - date_min).dt.days
    df["rolling_range_7"] = df["rolling_max_7"] - df["rolling_min_7"]
    df["ema_ratio"] = df["ema_7"] / df["ema_28"].replace(0, np.nan)

    print(f"[pipeline] Engineered 35 features -> {len(df.columns)} total columns.")
    return df


def split_train_test(
    df: pd.DataFrame,
    cutoff: str = "2019-01-01",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train < cutoff, test >= cutoff. Drops first-week rows (NaN lag_7)."""
    cutoff_dt = pd.Timestamp(cutoff)

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


def run_pipeline(db_path: str | Path, output_dir: str | Path) -> None:
    """Full pipeline: DB -> features_daily.csv + train.csv + test.csv."""
    db_path    = Path(db_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SPIS Data Pipeline")
    print("=" * 60)

    print("\n[1/5] Loading daily sales ...")
    df = load_daily_sales(db_path)

    print("\n[2/5] Validating ...")
    df = validate(df)

    print("\n[3/5] Filling missing dates ...")
    df = fill_missing_dates(df)

    print("\n[4/5] Engineering features ...")
    df = engineer_features(df)

    print("\n[5/5] Splitting train / test ...")
    train, test = split_train_test(df)

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
