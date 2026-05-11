
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

from spis.api.app import create_app
from spis.models.forecaster import FEATURE_COLS


ATC_CODES = ["M01AB", "M01AE", "N02BA", "N02BE", "N05B", "N05C", "R03", "R06"]


@pytest.fixture(scope="session")
def tiny_encoder() -> LabelEncoder:
    """LabelEncoder fitted on all 8 ATC codes (deterministic ordering)."""
    enc = LabelEncoder()
    enc.fit(ATC_CODES)
    return enc


@pytest.fixture(scope="session")
def tiny_model(tiny_encoder: LabelEncoder) -> XGBRegressor:
    """Tiny XGBRegressor trained on random data -- fast, not accurate."""
    rng = np.random.RandomState(0)
    n = 200
    X = pd.DataFrame(rng.uniform(0, 10, size=(n, len(FEATURE_COLS))), columns=FEATURE_COLS)
    y = rng.uniform(5, 15, size=n)
    model = XGBRegressor(n_estimators=10, random_state=0, n_jobs=1)
    model.fit(X, y)
    return model


@pytest.fixture
def artifact_dir(tmp_path, tiny_model, tiny_encoder) -> Path:
    """Save model + encoder to a temporary directory; return the directory path."""
    joblib.dump(tiny_model, tmp_path / "xgboost_forecaster.joblib")
    joblib.dump(tiny_encoder, tmp_path / "label_encoder.joblib")
    return tmp_path


@pytest.fixture
def features_csv(tmp_path, tiny_encoder) -> Path:
    """Minimal features_daily.csv -- one row per ATC code, all FEATURE_COLS present."""
    rng = np.random.RandomState(1)
    rows = []
    for code in ATC_CODES:
        atc_enc = int(tiny_encoder.transform([code])[0])
        row: dict = {col: float(rng.uniform(0, 10)) for col in FEATURE_COLS}
        # Overwrite with realistic calendar values so downstream logic doesn't break
        row.update({
            "atc_encoded":       atc_enc,
            "day_of_week":       1,
            "day_of_month":      8,
            "month":             10,
            "year":              2019,
            "week_of_year":      41,
            "is_weekend":        0,
            "is_holiday":        0,
            "season":            4,
            "is_payday_window":  0,
            "is_school_holiday": 0,
            "quarter":           4,
            "days_to_month_end": 23,
        })
        row["atc_code"] = code
        row["date"] = "2019-10-08"
        rows.append(row)

    csv_path = tmp_path / "features_daily.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def inventory_db(tmp_path) -> Path:
    """Minimal SQLite database with atc_inventory table (100 units per code)."""
    db_path = tmp_path / "inventory.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE atc_inventory (
                atc_code      TEXT PRIMARY KEY,
                current_stock REAL NOT NULL,
                last_updated  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                notes         TEXT
            )
        """)
        conn.executemany(
            "INSERT INTO atc_inventory (atc_code, current_stock) VALUES (?, ?)",
            [(code, 100.0) for code in ATC_CODES],
        )
        conn.commit()
    return db_path


@pytest.fixture
def app(artifact_dir, features_csv, inventory_db):
    """Flask test application configured with temporary artifact paths."""
    flask_app = create_app({
        "TESTING":       True,
        "DB_PATH":       str(inventory_db),
        "FEATURES_PATH": str(features_csv),
        "MODELS_DIR":    str(artifact_dir),
        "SAFETY_DAYS":   3.0,
    })
    return flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def app_no_model(tmp_path, features_csv, inventory_db):
    """Flask app with an empty models dir (no artifacts) to test 503 responses."""
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir()
    flask_app = create_app({
        "TESTING":       True,
        "DB_PATH":       str(inventory_db),
        "FEATURES_PATH": str(features_csv),
        "MODELS_DIR":    str(empty_dir),
        "SAFETY_DAYS":   3.0,
    })
    return flask_app


@pytest.fixture
def client_no_model(app_no_model):
    return app_no_model.test_client()


def test_health_returns_200(client):
    """Health endpoint must return HTTP 200."""
    assert client.get("/health").status_code == 200


def test_health_status_ok(client):
    """Health JSON body must have status='ok'."""
    data = client.get("/health").get_json()
    assert data["status"] == "ok"


def test_health_includes_version(client):
    """Health response must include a non-empty version string."""
    data = client.get("/health").get_json()
    assert "version" in data
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_risk_returns_200(client):
    """Risk endpoint must return HTTP 200."""
    assert client.get("/api/v1/risk").status_code == 200


def test_risk_contains_results_key(client):
    """Risk JSON body must have a 'results' list."""
    data = client.get("/api/v1/risk").get_json()
    assert "results" in data
    assert isinstance(data["results"], list)


def test_risk_returns_all_atc_codes(client):
    """Risk results must contain one entry per ATC code in the inventory."""
    data = client.get("/api/v1/risk").get_json()
    returned = {r["atc_code"] for r in data["results"]}
    assert returned == set(ATC_CODES)


def test_risk_result_required_fields(client):
    """Each risk result must contain all required fields."""
    required = {"atc_code", "current_stock", "forecast_30d",
                "daily_demand", "days_of_stock", "risk_tier", "order_qty"}
    data = client.get("/api/v1/risk").get_json()
    for result in data["results"]:
        assert required <= result.keys(), f"Missing fields in result: {result}"


def test_risk_tier_values_valid(client):
    """risk_tier must be one of the four valid tier strings."""
    valid_tiers = {"CRITICAL", "LOW", "OK", "OVERSTOCK"}
    data = client.get("/api/v1/risk").get_json()
    for result in data["results"]:
        assert result["risk_tier"] in valid_tiers


def test_risk_order_qty_nonnegative(client):
    """order_qty must never be negative."""
    data = client.get("/api/v1/risk").get_json()
    for result in data["results"]:
        assert result["order_qty"] >= 0.0


def test_risk_includes_metadata(client):
    """Risk response must include assessed_at and safety_days metadata."""
    data = client.get("/api/v1/risk").get_json()
    assert "assessed_at" in data
    assert "safety_days" in data


def test_risk_no_model_returns_503(client_no_model):
    """Risk endpoint must return HTTP 503 when model artifacts are absent."""
    assert client_no_model.get("/api/v1/risk").status_code == 503


def test_forecast_known_code_returns_200(client):
    """Forecast endpoint must return 200 for a known ATC code."""
    assert client.get("/api/v1/forecast/M01AB").status_code == 200


def test_forecast_required_fields(client):
    """Forecast response must include atc_code, forecast_30d, daily_demand, forecast_start."""
    data = client.get("/api/v1/forecast/M01AB").get_json()
    required = {"atc_code", "forecast_30d", "daily_demand", "forecast_start"}
    assert required <= data.keys()


def test_forecast_values_nonnegative(client):
    """forecast_30d and daily_demand must be >= 0."""
    data = client.get("/api/v1/forecast/M01AB").get_json()
    assert data["forecast_30d"] >= 0.0
    assert data["daily_demand"] >= 0.0


def test_forecast_atc_code_echoed(client):
    """atc_code field in response must match the requested code."""
    data = client.get("/api/v1/forecast/N02BE").get_json()
    assert data["atc_code"] == "N02BE"


def test_forecast_unknown_returns_404(client):
    """Unknown ATC code must return HTTP 404."""
    assert client.get("/api/v1/forecast/UNKNOWN").status_code == 404


def test_forecast_unknown_error_message(client):
    """404 response for an unknown ATC code must include an 'error' field."""
    data = client.get("/api/v1/forecast/UNKNOWN").get_json()
    assert "error" in data


def test_forecast_no_model_returns_503(client_no_model):
    """Forecast endpoint must return HTTP 503 when model artifacts are absent."""
    assert client_no_model.get("/api/v1/forecast/M01AB").status_code == 503
