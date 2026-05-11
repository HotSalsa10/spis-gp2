"""XGBoost demand forecaster + naive/moving-avg baselines."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

# 36 columns total: atc_encoded + 35 engineered features
FEATURE_COLS = [
    "atc_encoded",
    # calendar (12)
    "day_of_week", "day_of_month", "month", "year", "week_of_year", "is_weekend",
    "is_holiday", "season", "is_payday_window", "is_school_holiday",
    "quarter", "days_to_month_end",
    # lags (7)
    "lag_1", "lag_2", "lag_3", "lag_7", "lag_14", "lag_28", "lag_365",
    # rolling (12)
    "rolling_mean_7", "rolling_std_7", "rolling_mean_14", "rolling_mean_28",
    "rolling_std_28", "rolling_min_7", "rolling_max_7", "rolling_mean_90",
    "rolling_mean_365", "ema_7", "ema_14", "ema_28",
    # derived (4)
    "lag_ratio_7", "trend_counter", "rolling_range_7", "ema_ratio",
]

TARGET_COL = "quantity"


def encode_atc(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, LabelEncoder]:
    """Fit encoder on train, apply to both."""
    encoder = LabelEncoder()
    train = train.copy()
    test = test.copy()

    train["atc_encoded"] = encoder.fit_transform(train["atc_code"])
    test["atc_encoded"] = encoder.transform(test["atc_code"])

    return train, test, encoder


def baseline_naive(test: pd.DataFrame) -> np.ndarray:
    """Yesterday's value."""
    return test["lag_1"].fillna(0).values


def baseline_moving_avg(test: pd.DataFrame) -> np.ndarray:
    """7-day rolling mean."""
    return test["rolling_mean_7"].fillna(0).values


def evaluate(y_true: np.ndarray, y_pred: np.ndarray, label: str) -> dict:
    """MAE, RMSE, MAPE. Skips zero-actual rows for MAPE."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

    # avoid div by zero on zero-actual rows
    mask = y_true != 0
    if mask.sum() > 0:
        mape = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)
    else:
        mape = 0.0

    return {"model": label, "mae": mae, "rmse": rmse, "mape": mape}


def train_xgboost(X_train: pd.DataFrame, y_train: pd.Series) -> XGBRegressor:
    """GridSearchCV with TimeSeriesSplit (5 folds)."""
    param_grid = {
        "n_estimators":     [500, 800],
        "max_depth":        [6, 8],
        "learning_rate":    [0.03, 0.05],
        "subsample":        [0.8, 1.0],
        "colsample_bytree": [0.8, 1.0],
        "min_child_weight": [1, 5],
        "reg_alpha":        [0, 0.1],
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


def get_feature_importance(
    model: XGBRegressor,
    feature_names: list[str],
) -> pd.DataFrame:
    """Sorted descending."""
    importance = model.feature_importances_
    df = pd.DataFrame({
        "feature": feature_names,
        "importance": importance,
    })
    return df.sort_values("importance", ascending=False).reset_index(drop=True)


def train_and_evaluate(
    train_path: str | Path,
    test_path: str | Path,
    output_dir: str | Path,
) -> list[dict]:
    """Load data, train XGBoost + baselines, save artifacts."""
    train_path = Path(train_path)
    test_path = Path(test_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SPIS XGBoost Forecaster")
    print("=" * 60)

    print("\n[1/5] Loading data ...")
    train = pd.read_csv(train_path, parse_dates=["date"])
    test = pd.read_csv(test_path, parse_dates=["date"])
    print(f"  Train: {len(train):,} rows")
    print(f"  Test : {len(test):,} rows")

    print("\n[2/5] Encoding ATC codes ...")
    train, test, encoder = encode_atc(train, test)
    print(f"  Classes: {list(encoder.classes_)}")

    # drop NaN rows instead of filling with 0 (would teach model that
    # "no history" looks like a zero-sales day)
    train_clean = train.dropna(subset=FEATURE_COLS)
    dropped = len(train) - len(train_clean)
    if dropped > 0:
        print(f"  Dropped {dropped:,} train rows with NaN features (incomplete history).")

    X_train = train_clean[FEATURE_COLS]
    y_train = train_clean[TARGET_COL]
    X_test = test[FEATURE_COLS].fillna(0)
    y_test = test[TARGET_COL]

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

    fi_path = output_dir / "feature_importance.json"
    fi_records = importance_df[["feature", "importance"]].to_dict(orient="records")
    with open(fi_path, "w") as f:
        json.dump(fi_records, f, indent=2)

    print(f"  {output_dir / 'xgboost_forecaster.joblib'}")
    print(f"  {output_dir / 'label_encoder.joblib'}")
    print(f"  {metrics_path}")
    print(f"  {fi_path}")
    print("\nDone.")

    return results


def load_model(model_dir: str | Path) -> tuple[XGBRegressor, LabelEncoder]:
    model_dir = Path(model_dir)
    model = joblib.load(model_dir / "xgboost_forecaster.joblib")
    encoder = joblib.load(model_dir / "label_encoder.joblib")
    return model, encoder
