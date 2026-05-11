"""Flask app factory."""

from pathlib import Path

from flask import Flask

from spis.api.routes import register_routes
from spis.models.forecaster import load_model

_DEFAULTS: dict = {
    "DB_PATH":       "data/inventory.db",
    "FEATURES_PATH": "data/processed/features_daily.csv",
    "MODELS_DIR":    "models",
    "SAFETY_DAYS":   3.0,
}


def create_app(config: dict | None = None) -> Flask:
    """Load model at startup -- fail fast if it's missing."""
    app = Flask(__name__)

    app.config.update(_DEFAULTS)
    if config:
        app.config.update(config)

    # eager load so we 503 at startup instead of timing out later
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
