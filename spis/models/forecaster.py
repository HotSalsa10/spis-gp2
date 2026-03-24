"""
spis/models/forecaster.py
-------------------------
Phase 3 XGBoost demand forecaster for the SPIS project.

Trains a single XGBoost regressor across all ATC codes, compares it
against naive and moving-average baselines, and saves model artifacts
for downstream use (Flask API in Phase 5).

Model input: 36 features (35 from pipeline + atc_encoded).
Baseline MAE history: naive=4.23, moving-avg=2.89, XGBoost Run3=1.58 (27 features).

Usage:
    from spis.models.forecaster import train_and_evaluate, load_model
    results = train_and_evaluate("data/processed/train.csv",
                                 "data/processed/test.csv",
                                 "models")
    model, encoder = load_model("models")
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

# Feature columns used by the model (36 total).
FEATURE_COLS = [
    "atc_encoded",
    # Calendar (12)
    "day_of_week", "day_of_month", "month", "year", "week_of_year", "is_weekend",
    "is_holiday", "season", "is_payday_window", "is_school_holiday",
    "quarter", "days_to_month_end",
    # Lags (7)
    "lag_1", "lag_2", "lag_3", "lag_7", "lag_14", "lag_28", "lag_365",
    # Rolling windows (12)
    "rolling_mean_7", "rolling_std_7", "rolling_mean_14", "rolling_mean_28",
    "rolling_std_28", "rolling_min_7", "rolling_max_7", "rolling_mean_90",
    "rolling_mean_365", "ema_7", "ema_14", "ema_28",
    # Derived (4)
    "lag_ratio_7", "trend_counter", "rolling_range_7", "ema_ratio",
]

TARGET_COL = "quantity"


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def encode_atc(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, LabelEncoder]:
    """
    Label-encode the atc_code column into atc_encoded (integer).

    The encoder is fitted on train only; test codes are transformed using
    the same mapping.

    Returns:
        (train, test, encoder) tuple.
    """
    encoder = LabelEncoder()
    train = train.copy()
    test = test.copy()

    train["atc_encoded"] = encoder.fit_transform(train["atc_code"])
    test["atc_encoded"] = encoder.transform(test["atc_code"])

    return train, test, encoder


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def baseline_naive(test: pd.DataFrame) -> np.ndarray:
    """Naive baseline: predict lag_1 (yesterday's value). NaN -> 0."""
    return test["lag_1"].fillna(0).values


def baseline_moving_avg(test: pd.DataFrame) -> np.ndarray:
    """Moving-average baseline: predict rolling_mean_7. NaN -> 0."""
    return test["rolling_mean_7"].fillna(0).values


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(y_true: np.ndarray, y_pred: np.ndarray, label: str) -> dict:
    """
    Compute MAE, RMSE, and MAPE for a set of predictions.

    MAPE uses a guard against division by zero: rows where y_true == 0
    are excluded from the percentage calculation.

    Returns:
        dict with keys: model, mae, rmse, mape.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

    # MAPE — guard against division by zero
    mask = y_true != 0
    if mask.sum() > 0:
        mape = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)
    else:
        mape = 0.0

    return {"model": label, "mae": mae, "rmse": rmse, "mape": mape}


# ---------------------------------------------------------------------------
# XGBoost training
# ---------------------------------------------------------------------------

def train_xgboost(X_train: pd.DataFrame, y_train: pd.Series) -> XGBRegressor:
    """
    Train an XGBoost regressor with GridSearchCV
    (TimeSeriesSplit, n_splits=5).

    Returns:
        The best estimator from the grid search.
    """
    param_grid = {
        "n_estimators": [200, 500],
        "max_depth": [4, 6],
        "learning_rate": [0.05, 0.1],
        "subsample": [0.8, 1.0],
        "colsample_bytree": [0.8, 1.0],
        "min_child_weight": [1, 5],
        "reg_alpha": [0, 0.1],
    }

    xgb = XGBRegressor(
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1,
    )

    tscv = TimeSeriesSplit(n_splits=5)

    grid = GridSearchCV(
        xgb,
        param_grid,
        cv=tscv,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
        verbose=0,
    )
    grid.fit(X_train, y_train)

    print(f"  Best params: {grid.best_params_}")
    print(f"  Best CV MAE: {-grid.best_score_:.4f}")

    return grid.best_estimator_


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

def get_feature_importance(
    model: XGBRegressor,
    feature_names: list[str],
) -> pd.DataFrame:
    """
    Return a DataFrame of feature importances sorted descending.

    Columns: feature, importance.
    """
    importance = model.feature_importances_
    df = pd.DataFrame({
        "feature": feature_names,
        "importance": importance,
    })
    return df.sort_values("importance", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def train_and_evaluate(
    train_path: str | Path,
    test_path: str | Path,
    output_dir: str | Path,
) -> list[dict]:
    """
    Full training pipeline:
        1. Load train/test CSVs
        2. Encode atc_code
        3. Compute baseline predictions
        4. Train XGBoost via GridSearchCV
        5. Evaluate all models
        6. Save artifacts (model, encoder, metrics)
        7. Print comparison table

    Returns:
        List of metric dicts (one per model).
    """
    train_path = Path(train_path)
    test_path = Path(test_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SPIS XGBoost Forecaster -- Phase 3")
    print("=" * 60)

    # 1. Load data
    print("\n[1/5] Loading data ...")
    train = pd.read_csv(train_path, parse_dates=["date"])
    test = pd.read_csv(test_path, parse_dates=["date"])
    print(f"  Train: {len(train):,} rows")
    print(f"  Test : {len(test):,} rows")

    # 2. Encode ATC codes
    print("\n[2/5] Encoding ATC codes ...")
    train, test, encoder = encode_atc(train, test)
    print(f"  Classes: {list(encoder.classes_)}")

    # 3. Prepare features / target — drop rows with NaN features instead
    #    of filling with 0 (which misleads the model about missing history).
    train_clean = train.dropna(subset=FEATURE_COLS)
    dropped = len(train) - len(train_clean)
    if dropped > 0:
        print(f"  Dropped {dropped:,} train rows with NaN features (incomplete history).")

    X_train = train_clean[FEATURE_COLS]
    y_train = train_clean[TARGET_COL]
    X_test = test[FEATURE_COLS].fillna(0)
    y_test = test[TARGET_COL]

    # 4. Baselines
    print("\n[3/5] Computing baselines ...")
    pred_naive = baseline_naive(test)
    pred_mavg = baseline_moving_avg(test)

    # 5. Train XGBoost
    print("\n[4/5] Training XGBoost (GridSearchCV) ...")
    model = train_xgboost(X_train, y_train)
    pred_xgb = model.predict(X_test)

    # 6. Evaluate
    print("\n[5/5] Evaluating ...")
    results = [
        evaluate(y_test.values, pred_naive, "Naive (lag_1)"),
        evaluate(y_test.values, pred_mavg, "Moving Avg (7d)"),
        evaluate(y_test.values, pred_xgb, "XGBoost"),
    ]

    # Print comparison table
    print()
    print(f"{'Model':<20} {'MAE':>10} {'RMSE':>10} {'MAPE(%)':>10}")
    print("-" * 52)
    for r in results:
        print(f"{r['model']:<20} {r['mae']:>10.2f} {r['rmse']:>10.2f} {r['mape']:>10.2f}")

    # Feature importance
    importance_df = get_feature_importance(model, FEATURE_COLS)
    print("\nTop 10 features:")
    for _, row in importance_df.head(10).iterrows():
        print(f"  {row['feature']:<25} {row['importance']:.4f}")

    # 7. Save artifacts
    print("\nSaving artifacts ...")
    joblib.dump(model, output_dir / "xgboost_forecaster.joblib")
    joblib.dump(encoder, output_dir / "label_encoder.joblib")

    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"  {output_dir / 'xgboost_forecaster.joblib'}")
    print(f"  {output_dir / 'label_encoder.joblib'}")
    print(f"  {metrics_path}")
    print("\nDone.")

    return results


# ---------------------------------------------------------------------------
# Model loading (for Phase 5 API)
# ---------------------------------------------------------------------------

def load_model(model_dir: str | Path) -> tuple[XGBRegressor, LabelEncoder]:
    """
    Load saved model and label encoder from disk.

    Args:
        model_dir: Directory containing the .joblib files.

    Returns:
        (model, encoder) tuple.
    """
    model_dir = Path(model_dir)
    model = joblib.load(model_dir / "xgboost_forecaster.joblib")
    encoder = joblib.load(model_dir / "label_encoder.joblib")
    return model, encoder
