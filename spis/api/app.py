"""
spis/api/app.py
---------------
Flask application factory for the SPIS REST API (Phase 5).

Creates and configures the Flask app, loads model artifacts at startup,
and registers all API routes via Blueprint.

Usage:
    from spis.api.app import create_app
    app = create_app()
    app.run()
"""

from pathlib import Path

from flask import Flask

from spis.api.routes import register_routes
from spis.models.forecaster import load_model

# ---------------------------------------------------------------------------
# Default configuration (overridable via create_app(config={...}))
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "DB_PATH":       "data/inventory.db",
    "FEATURES_PATH": "data/processed/features_daily.csv",
    "MODELS_DIR":    "models",
    "SAFETY_DAYS":   3.0,
}


def create_app(config: dict | None = None) -> Flask:
    """
    Application factory -- creates a configured Flask instance.

    Loads XGBoost model and LabelEncoder from MODELS_DIR at startup.
    If artifacts are absent, the app starts without a model; affected
    endpoints will return HTTP 503 until artifacts are available.

    Args:
        config: Optional dict of config overrides (used in tests).

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)

    # Apply defaults then any caller overrides
    app.config.update(_DEFAULTS)
    if config:
        app.config.update(config)

    # Eagerly load model artifacts (fast startup failure is better than
    # a slow failure on the first request)
    models_dir = Path(app.config["MODELS_DIR"])
    model_file  = models_dir / "xgboost_forecaster.joblib"
    encoder_file = models_dir / "label_encoder.joblib"

    if model_file.exists() and encoder_file.exists():
        model, encoder = load_model(models_dir)
        app.config["_MODEL"]   = model
        app.config["_ENCODER"] = encoder
    else:
        app.config["_MODEL"]   = None
        app.config["_ENCODER"] = None

    register_routes(app)
    return app
