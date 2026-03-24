"""
spis/api/routes.py
------------------
Flask Blueprint with all SPIS REST API endpoints (Phase 5).

Endpoints:
    GET /health                     -- Liveness check
    GET /api/v1/risk                -- Full risk assessment for all ATC codes
    GET /api/v1/forecast/<atc_code> -- 30-day demand forecast for one ATC code
"""

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
    """Attach the API blueprint to the Flask application."""
    app.register_blueprint(bp)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ra_to_dict(ra) -> dict:
    """
    Convert a RiskAssessment dataclass to a JSON-serialisable dict.
    Replaces float('inf') days_of_stock with None (JSON cannot encode infinity).
    """
    d = dataclasses.asdict(ra)
    if d.get("days_of_stock") == float("inf"):
        d["days_of_stock"] = None
    return d


def _model_loaded() -> bool:
    """Return True if model artifacts were successfully loaded at startup."""
    return (
        current_app.config.get("_MODEL") is not None
        and current_app.config.get("_ENCODER") is not None
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@bp.get("/health")
def health():
    """Liveness check -- always HTTP 200 if the server is running."""
    return jsonify({"status": "ok", "version": VERSION})


# ---------------------------------------------------------------------------
# GET /api/v1/risk
# ---------------------------------------------------------------------------

@bp.get("/api/v1/risk")
def risk_assessment():
    """
    Run a full risk assessment for every ATC code in the inventory.

    Returns a JSON object with:
        assessed_at  : ISO-8601 UTC timestamp
        safety_days  : safety buffer used in order-qty calculation
        results      : list of per-ATC-code risk records
    """
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
        output_csv=None,        # No CSV written via the API
    )

    return jsonify({
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "safety_days": safety_days,
        "results": [_ra_to_dict(ra) for ra in results],
    })


# ---------------------------------------------------------------------------
# GET /api/v1/forecast/<atc_code>
# ---------------------------------------------------------------------------

@bp.get("/api/v1/forecast/<atc_code>")
def forecast(atc_code: str):
    """
    Return a 30-day demand forecast for a single ATC code.

    Path parameter:
        atc_code : ATC-4 code (e.g. M01AB).

    Returns:
        200 -- JSON with atc_code, forecast_30d, daily_demand, forecast_start.
        404 -- Unknown ATC code.
        503 -- Model artifacts not loaded.
    """
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
