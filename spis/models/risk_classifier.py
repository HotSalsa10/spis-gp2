"""
spis/models/risk_classifier.py
-------------------------------
Phase 4 risk classification and order-quantity recommendation.

For each ATC code the module answers two questions:
    1. What is the current risk tier (CRITICAL / LOW / OK / OVERSTOCK)?
    2. How many units should be ordered to cover the next 30 days?

Risk tiers are defined by Days-of-Stock (DoS = current_stock / daily_demand):
    CRITICAL  : DoS < 3   -- likely stockout within 3 days
    LOW       : 3 <= DoS < 7
    OK        : 7 <= DoS < 30
    OVERSTOCK : DoS >= 30

Order quantity formula:
    order_qty = max(0, forecast_30d + safety_buffer - current_stock)
    safety_buffer = daily_demand * safety_days

Usage:
    from spis.models.risk_classifier import assess_from_features
    results = assess_from_features(
        features_csv="data/processed/features_daily.csv",
        inventory={"M01AB": 60.0, ...},
        model=model,
        encoder=encoder,
    )
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import holidays
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

from spis.models.forecaster import FEATURE_COLS

# ---------------------------------------------------------------------------
# Risk tier thresholds (Days of Stock)
# ---------------------------------------------------------------------------

TIER_CRITICAL: float = 3.0   # DoS < 3  -> CRITICAL
TIER_LOW: float = 7.0         # DoS < 7  -> LOW
TIER_OK: float = 30.0         # DoS < 30 -> OK  (else OVERSTOCK)


# ---------------------------------------------------------------------------
# RiskAssessment result object (immutable)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RiskAssessment:
    """
    Immutable result record for a single ATC code's risk evaluation.

    Attributes:
        atc_code      : ATC-4 code (e.g. "M01AB")
        current_stock : Stock on hand at assessment time (units)
        forecast_30d  : Predicted demand over the next 30 days (units)
        daily_demand  : Average daily demand derived from forecast_30d / 30
        days_of_stock : current_stock / daily_demand (inf if demand is 0)
        risk_tier     : One of CRITICAL | LOW | OK | OVERSTOCK
        order_qty     : Recommended order quantity (units, >= 0)
    """

    atc_code: str
    current_stock: float
    forecast_30d: float
    daily_demand: float
    days_of_stock: float
    risk_tier: str
    order_qty: float


# ---------------------------------------------------------------------------
# Pure functions (all stateless; easy to unit-test)
# ---------------------------------------------------------------------------

def classify_risk(days_of_stock: float) -> str:
    """
    Map Days-of-Stock to a risk tier string.

    Args:
        days_of_stock: current_stock / daily_demand (use float('inf') for zero demand)

    Returns:
        One of "CRITICAL", "LOW", "OK", "OVERSTOCK".
    """
    if days_of_stock < TIER_CRITICAL:
        return "CRITICAL"
    if days_of_stock < TIER_LOW:
        return "LOW"
    if days_of_stock < TIER_OK:
        return "OK"
    return "OVERSTOCK"


def calculate_order_qty(
    current_stock: float,
    forecast_30d: float,
    daily_demand: float,
    safety_days: float = 3.0,
) -> float:
    """
    Recommended order quantity to cover the next 30 days plus a safety buffer.

    Formula:
        safety_buffer = daily_demand * safety_days
        order_qty     = max(0, forecast_30d + safety_buffer - current_stock)

    Args:
        current_stock : Units currently in stock.
        forecast_30d  : Predicted demand over 30 days.
        daily_demand  : Average daily demand (used only to size the safety buffer).
        safety_days   : Number of extra days of buffer stock to maintain.

    Returns:
        Recommended order quantity (always >= 0).
    """
    safety_buffer = daily_demand * safety_days
    raw = forecast_30d + safety_buffer - current_stock
    return float(max(0.0, raw))


def build_risk_assessment(
    atc_code: str,
    current_stock: float,
    forecast_30d: float,
    daily_demand: float,
    safety_days: float = 3.0,
) -> RiskAssessment:
    """
    Compute all risk fields and return an immutable RiskAssessment record.

    Args:
        atc_code      : ATC-4 code.
        current_stock : Units on hand.
        forecast_30d  : 30-day demand forecast.
        daily_demand  : Average daily demand (forecast_30d / 30 typically).
        safety_days   : Buffer days for order quantity calculation.

    Returns:
        RiskAssessment dataclass (frozen).
    """
    if daily_demand > 0:
        days_of_stock = current_stock / daily_demand
    else:
        days_of_stock = float("inf")

    risk_tier = classify_risk(days_of_stock)
    order_qty = calculate_order_qty(current_stock, forecast_30d, daily_demand, safety_days)

    return RiskAssessment(
        atc_code=atc_code,
        current_stock=current_stock,
        forecast_30d=forecast_30d,
        daily_demand=daily_demand,
        days_of_stock=days_of_stock,
        risk_tier=risk_tier,
        order_qty=order_qty,
    )


# ---------------------------------------------------------------------------
# 30-day demand forecasting (iterative, using trained XGBoost)
# ---------------------------------------------------------------------------

# Season lookup: month -> season (1=Winter, 2=Spring, 3=Summer, 4=Fall)
_SEASON_MAP = {
    12: 1, 1: 1, 2: 1,
    3: 2,  4: 2, 5: 2,
    6: 3,  7: 3, 8: 3,
    9: 4, 10: 4, 11: 4,
}


def forecast_30_days(
    model: XGBRegressor,
    encoder: LabelEncoder,
    seed_row: pd.DataFrame,
    atc_code: str,
    start_date: pd.Timestamp,
    days: int = 30,
) -> float:
    """
    Forecast total demand over `days` days starting from `start_date`.

    Strategy:
        - Calendar features (day_of_week, month, etc.) are computed from actual
          future dates, capturing real seasonal / holiday effects.
        - Lag and rolling features are held constant from the seed_row (last
          known feature values). This is a conservative assumption: no feedback
          loop, but it avoids leaking future information.
        - Predictions are clipped to >= 0 before summing.

    Args:
        model      : Trained XGBRegressor (from Phase 3).
        encoder    : LabelEncoder fitted on ATC codes.
        seed_row   : One-row DataFrame with all FEATURE_COLS for `atc_code`.
                     (The last row of features_daily.csv for that code.)
        atc_code   : ATC-4 code to forecast.
        start_date : First date of the 30-day forecast window.
        days       : Number of days to forecast (default 30).

    Returns:
        Total predicted demand (float, >= 0).

    Raises:
        ValueError: If `atc_code` is not in the encoder's known classes.
    """
    if atc_code not in encoder.classes_:
        raise ValueError(
            f"ATC code '{atc_code}' not found in encoder. "
            f"Known codes: {list(encoder.classes_)}"
        )

    atc_encoded = int(encoder.transform([atc_code])[0])

    # Pre-load Turkish public holidays for the forecast window
    tr_holidays = holidays.Turkey(
        years=range(start_date.year, start_date.year + 2)
    )

    # Extract static (lag/rolling/EMA) values from the seed row
    seed = seed_row.iloc[0]

    total = 0.0
    for i in range(days):
        d = start_date + pd.Timedelta(days=i)
        month = d.month
        dom = d.day

        # Calendar features computed from the actual future date
        calendar_vals = {
            "atc_encoded":       atc_encoded,
            "day_of_week":       d.dayofweek,
            "day_of_month":      dom,
            "month":             month,
            "year":              d.year,
            "week_of_year":      int(d.isocalendar()[1]),
            "is_weekend":        int(d.dayofweek >= 5),
            "is_holiday":        int(d.date() in tr_holidays),
            "season":            _SEASON_MAP[month],
            "is_payday_window":  int((1 <= dom <= 3) or (15 <= dom <= 17)),
            "is_school_holiday": int(
                (6 <= month <= 8)
                or (month == 1 and dom >= 20)
                or (month == 2 and dom <= 3)
            ),
            "quarter":           (month - 1) // 3 + 1,
            "days_to_month_end": int(
                pd.Timestamp(d.year, month, 1).days_in_month - dom
            ),
        }

        # Build feature row: seed values for lag/rolling, calendar from above
        row_vals = {col: float(seed[col]) if col in seed.index else 0.0
                    for col in FEATURE_COLS}
        row_vals.update(calendar_vals)

        X = pd.DataFrame([row_vals])[FEATURE_COLS]
        pred = float(model.predict(X)[0])
        total += max(0.0, pred)

    return total


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

def load_atc_inventory(db_path: str | Path) -> dict[str, float]:
    """
    Load current stock levels from the atc_inventory table.

    Args:
        db_path: Path to the SQLite inventory database.

    Returns:
        Dict mapping atc_code -> current_stock (float).
    """
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT atc_code, current_stock FROM atc_inventory"
        ).fetchall()
    return {atc_code: float(stock) for atc_code, stock in rows}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def assess_from_features(
    features_csv: str | Path,
    inventory: dict[str, float],
    model: XGBRegressor,
    encoder: LabelEncoder,
    start_date: pd.Timestamp | None = None,
    safety_days: float = 3.0,
    output_csv: str | Path | None = None,
) -> list[RiskAssessment]:
    """
    Run Phase 4 risk assessment for all ATC codes.

    For each ATC code:
        1. Use the last known feature row from features_daily.csv as the seed.
        2. Forecast 30 days of demand with the trained XGBoost model.
        3. Compute DoS, risk tier, and order quantity.

    Args:
        features_csv : Path to features_daily.csv (output of Phase 2 pipeline).
        inventory    : Dict of atc_code -> current_stock (from load_atc_inventory).
        model        : Trained XGBRegressor.
        encoder      : LabelEncoder fitted on ATC codes.
        start_date   : First date of the 30-day window (default: day after last data).
        safety_days  : Safety buffer days for order qty calculation.
        output_csv   : Optional path to write the results CSV.

    Returns:
        List of RiskAssessment records, one per ATC code.
    """
    features_csv = Path(features_csv)
    df = pd.read_csv(features_csv, parse_dates=["date"])

    # Default start date: the day after the last date in the features file
    if start_date is None:
        start_date = df["date"].max() + pd.Timedelta(days=1)

    print(f"[risk] Assessment start date : {start_date.date()}")
    print(f"[risk] ATC codes to assess   : {sorted(inventory.keys())}")
    print()

    results: list[RiskAssessment] = []

    for atc_code, current_stock in sorted(inventory.items()):
        # Get the last feature row for this ATC code (the seed)
        atc_rows = df[df["atc_code"] == atc_code].sort_values("date")
        if atc_rows.empty:
            print(f"  [WARN] No feature rows found for {atc_code} -- skipping.")
            continue

        seed_row = atc_rows.tail(1).reset_index(drop=True)

        # Forecast 30-day demand
        forecast_30d = forecast_30_days(
            model, encoder, seed_row, atc_code, start_date
        )
        daily_demand = forecast_30d / 30.0

        # Build assessment
        ra = build_risk_assessment(
            atc_code=atc_code,
            current_stock=current_stock,
            forecast_30d=forecast_30d,
            daily_demand=daily_demand,
            safety_days=safety_days,
        )
        results.append(ra)

        print(
            f"  {atc_code:<8}  stock={current_stock:>7.1f}  "
            f"forecast30d={forecast_30d:>8.1f}  "
            f"DoS={ra.days_of_stock:>6.1f}  "
            f"tier={ra.risk_tier:<10}  order={ra.order_qty:>8.1f}"
        )

    print()
    _print_summary(results)

    # Optionally persist to CSV
    if output_csv is not None:
        output_csv = Path(output_csv)
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "atc_code":      ra.atc_code,
                "current_stock": ra.current_stock,
                "forecast_30d":  ra.forecast_30d,
                "daily_demand":  ra.daily_demand,
                "days_of_stock": ra.days_of_stock,
                "risk_tier":     ra.risk_tier,
                "order_qty":     ra.order_qty,
            }
            for ra in results
        ]
        pd.DataFrame(rows).to_csv(output_csv, index=False)
        print(f"[risk] Results saved -> {output_csv}")

    return results


def _print_summary(results: list[RiskAssessment]) -> None:
    """Print a tier-count summary table."""
    from collections import Counter
    counts = Counter(ra.risk_tier for ra in results)
    print("[risk] Risk Tier Summary")
    print("-" * 30)
    for tier in ("CRITICAL", "LOW", "OK", "OVERSTOCK"):
        n = counts.get(tier, 0)
        bar = "#" * n
        print(f"  {tier:<12} {n:>2}  {bar}")
    print()
    critical = [ra for ra in results if ra.risk_tier == "CRITICAL"]
    if critical:
        print("[risk] *** ACTION REQUIRED -- Critical items: ***")
        for ra in critical:
            print(f"  {ra.atc_code}  stock={ra.current_stock:.0f}  "
                  f"order={ra.order_qty:.0f} units")
        print()
