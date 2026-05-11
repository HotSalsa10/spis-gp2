"""Three endpoints: /health, /api/v1/risk, /api/v1/forecast/<atc>."""

import dataclasses
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import Blueprint, current_app, jsonify

from spis.models.risk_classifier import (
    assess_from_features,
    forecast_30_days,
    load_atc_inventory,
)

VERSION = "0.1.0"

bp = Blueprint("api", __name__)


def register_routes(app) -> None:
    app.register_blueprint(bp)


def _ra_to_dict(ra) -> dict:
    """JSON can't encode inf, so swap to None."""
    d = dataclasses.asdict(ra)
    if d.get("days_of_stock") == float("inf"):
        d["days_of_stock"] = None
    return d


def _model_loaded() -> bool:
    return (
        current_app.config.get("_MODEL") is not None
        and current_app.config.get("_ENCODER") is not None
    )


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "version": VERSION})


@bp.get("/api/v1/risk")
def risk_assessment():
    """Full risk assessment for every ATC code."""
    if not _model_loaded():
        return jsonify({
            "error": "Model artifacts not loaded. Run scripts/train_model.py first."
        }), 503

    model = current_app.config["_MODEL"]
    encoder = current_app.config["_ENCODER"]
    db_path = Path(current_app.config["DB_PATH"])
    features_path = Path(current_app.config["FEATURES_PATH"])
    safety_days = float(current_app.config["SAFETY_DAYS"])

    inventory = load_atc_inventory(db_path)
    results = assess_from_features(
        features_csv=features_path,
        inventory=inventory,
        model=model,
        encoder=encoder,
        safety_days=safety_days,
        output_csv=None,
    )

    return jsonify({
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "safety_days": safety_days,
        "results": [_ra_to_dict(ra) for ra in results],
    })


@bp.get("/api/v1/forecast/<atc_code>")
def forecast(atc_code: str):
    """30-day forecast for one ATC code. 404 if unknown, 503 if no model."""
    if not _model_loaded():
        return jsonify({
            "error": "Model artifacts not loaded. Run scripts/train_model.py first."
        }), 503

    model = current_app.config["_MODEL"]
    encoder = current_app.config["_ENCODER"]

    if atc_code not in encoder.classes_:
        return jsonify({"error": f"Unknown ATC code: {atc_code}"}), 404

    features_path = Path(current_app.config["FEATURES_PATH"])
    df = pd.read_csv(features_path, parse_dates=["date"])

    atc_rows = df[df["atc_code"] == atc_code].sort_values("date")
    if atc_rows.empty:
        return jsonify({"error": f"No feature data found for {atc_code}"}), 404

    seed_row = atc_rows.tail(1).reset_index(drop=True)
    start_date = df["date"].max() + pd.Timedelta(days=1)

    forecast_30d = forecast_30_days(model, encoder, seed_row, atc_code, start_date)
    daily_demand = forecast_30d / 30.0

    return jsonify({
        "atc_code":       atc_code,
        "forecast_30d":   round(forecast_30d, 4),
        "daily_demand":   round(daily_demand, 4),
        "forecast_start": start_date.date().isoformat(),
    })
