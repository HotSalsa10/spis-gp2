"""
tests/test_pipeline.py
----------------------
Unit tests for the Phase 2 data pipeline (spis.data.pipeline).

All tests use synthetic DataFrames so they run on any machine without
requiring the real Kaggle database.
"""

import pandas as pd
import pytest

from spis.data.pipeline import (
    EXPECTED_ATC_CODES,
    engineer_features,
    fill_missing_dates,
    split_train_test,
    validate,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable synthetic data
# ---------------------------------------------------------------------------

@pytest.fixture
def small_daily_df():
    """
    Create a small synthetic daily sales DataFrame for one ATC code
    spanning 400 days — enough to test lags, rolling windows, and splits.
    """
    dates = pd.date_range("2018-01-01", periods=400, freq="D")
    return pd.DataFrame({
        "atc_code": "M01AB",
        "date": dates,
        "quantity": range(400),  # 0, 1, 2, ..., 399
    })


@pytest.fixture
def multi_atc_df():
    """
    Create a synthetic DataFrame with all 8 ATC codes, each with 30 days.
    Useful for testing groupby operations.
    """
    frames = []
    for code in sorted(EXPECTED_ATC_CODES):
        dates = pd.date_range("2018-06-01", periods=30, freq="D")
        frames.append(pd.DataFrame({
            "atc_code": code,
            "date": dates,
            "quantity": 10.0,
        }))
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Test: validate
# ---------------------------------------------------------------------------

def test_validate_clean_data(multi_atc_df):
    """Clean data should pass through validate unchanged."""
    result = validate(multi_atc_df)
    assert len(result) == len(multi_atc_df)
    assert set(result.columns) == {"atc_code", "date", "quantity"}


def test_validate_catches_duplicates():
    """Duplicate (atc_code, date) rows should be aggregated by sum."""
    df = pd.DataFrame({
        "atc_code": ["M01AB", "M01AB", "M01AE"] + ["N02BA", "N02BE", "N05B", "N05C", "R03", "R06"],
        "date": pd.to_datetime(
            ["2018-01-01", "2018-01-01", "2018-01-01"]
            + ["2018-01-01"] * 6
        ),
        "quantity": [5.0, 3.0, 10.0] + [1.0] * 6,
    })
    result = validate(df)
    # M01AB duplicates should be summed: 5 + 3 = 8
    m01ab = result[result["atc_code"] == "M01AB"]
    assert len(m01ab) == 1
    assert m01ab["quantity"].iloc[0] == 8.0


# ---------------------------------------------------------------------------
# Test: fill_missing_dates
# ---------------------------------------------------------------------------

def test_fill_missing_dates():
    """A 3-day gap should be filled with quantity=0."""
    df = pd.DataFrame({
        "atc_code": ["M01AB", "M01AB", "M01AB"],
        "date": pd.to_datetime(["2018-01-01", "2018-01-02", "2018-01-06"]),
        "quantity": [10.0, 20.0, 30.0],
    })
    result = fill_missing_dates(df)

    # Should now have 6 consecutive days (Jan 1-6)
    assert len(result) == 6

    # Gap days (Jan 3, 4, 5) should have quantity = 0
    gap_rows = result[result["date"].isin(pd.to_datetime(["2018-01-03", "2018-01-04", "2018-01-05"]))]
    assert (gap_rows["quantity"] == 0.0).all()

    # Original rows should still have their values
    jan1 = result[result["date"] == pd.Timestamp("2018-01-01")]
    assert jan1["quantity"].iloc[0] == 10.0


# ---------------------------------------------------------------------------
# Test: engineer_features
# ---------------------------------------------------------------------------

def test_engineer_features_columns(small_daily_df):
    """All 19 engineered feature columns should be present after transformation."""
    result = engineer_features(small_daily_df)

    expected_features = [
        # Calendar (6)
        "day_of_week", "day_of_month", "month", "year", "week_of_year", "is_weekend",
        # Lags (5)
        "lag_1", "lag_7", "lag_14", "lag_28", "lag_365",
        # Rolling (8)
        "rolling_mean_7", "rolling_std_7", "rolling_mean_14", "rolling_mean_28",
        "rolling_min_7", "rolling_max_7", "rolling_mean_90", "rolling_mean_365",
    ]
    for feat in expected_features:
        assert feat in result.columns, f"Missing feature column: {feat}"

    # Total columns: 3 original + 19 features = 22
    assert len(result.columns) == 22


def test_engineer_features_lag_values(small_daily_df):
    """Lag_1 should equal the previous day's quantity; lag_7 should equal 7 days ago."""
    result = engineer_features(small_daily_df)

    # Row at index 1 (day 2): lag_1 should be quantity of day 1
    row_1 = result.iloc[1]
    assert row_1["lag_1"] == 0.0  # quantity of day 0

    # Row at index 7 (day 8): lag_7 should be quantity of day 1
    row_7 = result.iloc[7]
    assert row_7["lag_7"] == 0.0  # quantity of day 0

    # Row at index 10: lag_1 should be quantity at index 9
    row_10 = result.iloc[10]
    assert row_10["lag_1"] == 9.0  # quantity = index for this fixture


# ---------------------------------------------------------------------------
# Test: split_train_test
# ---------------------------------------------------------------------------

def test_split_no_leakage():
    """All train dates must be before the cutoff; all test dates at or after."""
    dates = pd.date_range("2018-01-01", periods=500, freq="D")
    df = pd.DataFrame({
        "atc_code": "M01AB",
        "date": dates,
        "quantity": range(500),
    })
    df = engineer_features(df)

    cutoff = "2018-07-01"
    train, test = split_train_test(df, cutoff=cutoff)

    cutoff_dt = pd.Timestamp(cutoff)
    assert (train["date"] < cutoff_dt).all(), "Train set has dates >= cutoff"
    assert (test["date"] >= cutoff_dt).all(), "Test set has dates < cutoff"


def test_split_no_overlap():
    """Train and test date sets should be completely disjoint."""
    dates = pd.date_range("2018-01-01", periods=500, freq="D")
    df = pd.DataFrame({
        "atc_code": "M01AB",
        "date": dates,
        "quantity": range(500),
    })
    df = engineer_features(df)

    train, test = split_train_test(df, cutoff="2018-07-01")

    train_dates = set(train["date"])
    test_dates = set(test["date"])
    overlap = train_dates & test_dates
    assert len(overlap) == 0, f"Found {len(overlap)} overlapping dates"
