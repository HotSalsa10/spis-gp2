"""
tests/test_forecaster.py
------------------------
Pytest suite for spis.models.forecaster (Phase 3).
Uses synthetic data fixtures — no database or CSV files required.
"""

import json

import numpy as np
import pandas as pd
import pytest
from xgboost import XGBRegressor

from spis.models.forecaster import (
    baseline_moving_avg,
    baseline_naive,
    encode_atc,
    evaluate,
    load_model,
    train_and_evaluate,
    train_xgboost,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_train_test():
    """Create small synthetic train/test DataFrames with required columns."""
    rng = np.random.RandomState(42)
    n = 200
    codes = ["M01AB", "N02BE"]

    rows = []
    for code in codes:
        for i in range(n):
            rows.append({
                "atc_code": code,
                "date": pd.Timestamp("2018-01-01") + pd.Timedelta(days=i),
                "quantity": float(rng.poisson(10)),
                "day_of_week": i % 7,
                "day_of_month": (i % 28) + 1,
                "month": ((i // 30) % 12) + 1,
                "year": 2018,
                "week_of_year": (i // 7) + 1,
                "is_weekend": int(i % 7 >= 5),
                "is_holiday": int(i % 30 == 0),
                "season": ((((i // 30) % 12) + 1) // 3 % 4) + 1,
                "is_payday_window": int(((i % 28) + 1) <= 3 or 15 <= ((i % 28) + 1) <= 17),
                "is_school_holiday": int(6 <= (((i // 30) % 12) + 1) <= 8),
                "quarter": ((((i // 30) % 12) + 1) - 1) // 3 + 1,
                "days_to_month_end": 30 - ((i % 28) + 1),
                "lag_1": float(rng.poisson(10)),
                "lag_2": float(rng.poisson(10)),
                "lag_3": float(rng.poisson(10)),
                "lag_7": float(rng.poisson(10)),
                "lag_14": float(rng.poisson(10)),
                "lag_28": float(rng.poisson(10)),
                "lag_365": float(rng.poisson(10)),
                "rolling_mean_7": float(rng.uniform(5, 15)),
                "rolling_std_7": float(rng.uniform(1, 5)),
                "rolling_mean_14": float(rng.uniform(5, 15)),
                "rolling_mean_28": float(rng.uniform(5, 15)),
                "rolling_std_28": float(rng.uniform(1, 5)),
                "rolling_min_7": float(rng.poisson(5)),
                "rolling_max_7": float(rng.poisson(15)),
                "rolling_mean_90": float(rng.uniform(5, 15)),
                "rolling_mean_365": float(rng.uniform(5, 15)),
                "ema_7": float(rng.uniform(5, 15)),
                "ema_14": float(rng.uniform(5, 15)),
                "ema_28": float(rng.uniform(5, 15)),
                "lag_ratio_7": float(rng.uniform(0.5, 2.0)),
                "trend_counter": i,
                "rolling_range_7": float(rng.uniform(1, 10)),
                "ema_ratio": float(rng.uniform(0.8, 1.2)),
            })

    df = pd.DataFrame(rows)
    train = df[df["date"] < "2018-06-01"].copy()
    test = df[df["date"] >= "2018-06-01"].copy()
    return train, test


# ---------------------------------------------------------------------------
# Tests — encode_atc
# ---------------------------------------------------------------------------

def test_encode_atc_creates_column(synthetic_train_test):
    """encode_atc should add an atc_encoded integer column."""
    train, test = synthetic_train_test
    train_enc, test_enc, encoder = encode_atc(train, test)

    assert "atc_encoded" in train_enc.columns
    assert "atc_encoded" in test_enc.columns
    assert train_enc["atc_encoded"].dtype in (np.int32, np.int64, int)


def test_encode_atc_consistent(synthetic_train_test):
    """Same atc_code should map to the same integer in train and test."""
    train, test = synthetic_train_test
    train_enc, test_enc, encoder = encode_atc(train, test)

    train_mapping = dict(zip(train_enc["atc_code"], train_enc["atc_encoded"]))
    test_mapping = dict(zip(test_enc["atc_code"], test_enc["atc_encoded"]))

    for code in train_mapping:
        if code in test_mapping:
            assert train_mapping[code] == test_mapping[code]


# ---------------------------------------------------------------------------
# Tests — baselines
# ---------------------------------------------------------------------------

def test_baseline_naive_uses_lag1(synthetic_train_test):
    """Naive baseline should return lag_1 values."""
    _, test = synthetic_train_test
    pred = baseline_naive(test)
    expected = test["lag_1"].fillna(0).values
    np.testing.assert_array_equal(pred, expected)


def test_baseline_moving_avg_uses_rolling7(synthetic_train_test):
    """Moving-average baseline should return rolling_mean_7 values."""
    _, test = synthetic_train_test
    pred = baseline_moving_avg(test)
    expected = test["rolling_mean_7"].fillna(0).values
    np.testing.assert_array_equal(pred, expected)


# ---------------------------------------------------------------------------
# Tests — evaluate
# ---------------------------------------------------------------------------

def test_evaluate_perfect_predictions():
    """Perfect predictions should give zero error across all metrics."""
    y = np.array([10.0, 20.0, 30.0])
    result = evaluate(y, y, "perfect")
    assert result["mae"] == 0.0
    assert result["rmse"] == 0.0
    assert result["mape"] == 0.0


def test_evaluate_known_error():
    """Check MAE/RMSE for a known error vector."""
    y_true = np.array([10.0, 20.0, 30.0])
    y_pred = np.array([12.0, 18.0, 33.0])

    result = evaluate(y_true, y_pred, "known")

    # MAE = mean(|2, 2, 3|) = 7/3
    assert abs(result["mae"] - 7 / 3) < 1e-6

    # RMSE = sqrt(mean(4, 4, 9)) = sqrt(17/3)
    expected_rmse = np.sqrt(17 / 3)
    assert abs(result["rmse"] - expected_rmse) < 1e-6

    # MAPE = mean(|2/10, 2/20, 3/30|) * 100 = mean(0.2, 0.1, 0.1) * 100 = 13.333...
    assert abs(result["mape"] - 100 * np.mean([0.2, 0.1, 0.1])) < 1e-4


# ---------------------------------------------------------------------------
# Tests — train_xgboost
# ---------------------------------------------------------------------------

def test_train_xgboost_returns_model(synthetic_train_test):
    """train_xgboost should return a fitted XGBRegressor."""
    train, _ = synthetic_train_test
    train_enc, _, _ = encode_atc(train, train)

    from spis.models.forecaster import FEATURE_COLS, TARGET_COL
    X = train_enc[FEATURE_COLS].fillna(0)
    y = train_enc[TARGET_COL]

    model = train_xgboost(X, y)
    assert isinstance(model, XGBRegressor)
    assert hasattr(model, "predict")


# ---------------------------------------------------------------------------
# Tests — save / load roundtrip
# ---------------------------------------------------------------------------

def test_load_model_roundtrip(tmp_path, synthetic_train_test):
    """Saving and loading model artifacts should produce identical predictions."""
    train, test = synthetic_train_test
    train_enc, test_enc, encoder = encode_atc(train, test)

    from spis.models.forecaster import FEATURE_COLS, TARGET_COL
    X_train = train_enc[FEATURE_COLS].fillna(0)
    y_train = train_enc[TARGET_COL]
    X_test = test_enc[FEATURE_COLS].fillna(0)

    model = train_xgboost(X_train, y_train)
    pred_before = model.predict(X_test)

    # Save
    import joblib
    joblib.dump(model, tmp_path / "xgboost_forecaster.joblib")
    joblib.dump(encoder, tmp_path / "label_encoder.joblib")

    # Load
    loaded_model, loaded_encoder = load_model(tmp_path)
    pred_after = loaded_model.predict(X_test)

    np.testing.assert_array_almost_equal(pred_before, pred_after)
    np.testing.assert_array_equal(encoder.classes_, loaded_encoder.classes_)
