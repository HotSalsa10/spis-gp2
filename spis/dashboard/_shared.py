"""
spis/dashboard/_shared.py
--------------------------
Shared constants and cached loaders used by all dashboard pages.

Import this module in every page instead of duplicating path resolution
and caching logic:

    from spis.dashboard._shared import DB_PATH, MODELS_DIR, load_artifacts, run_assessment
"""

from pathlib import Path

import streamlit as st

from spis.models.forecaster import load_model
from spis.models.risk_classifier import assess_from_features, load_atc_inventory

# ---------------------------------------------------------------------------
# Path constants (resolved relative to this file -> always correct)
# ---------------------------------------------------------------------------

ROOT         = Path(__file__).resolve().parent.parent.parent
MODELS_DIR   = ROOT / "models"
DB_PATH      = ROOT / "data" / "inventory.db"
FEATURES_CSV = ROOT / "data" / "processed" / "features_daily.csv"

REQUIRED_FILES = [
    MODELS_DIR / "xgboost_forecaster.joblib",
    MODELS_DIR / "label_encoder.joblib",
    DB_PATH,
    FEATURES_CSV,
]

# ---------------------------------------------------------------------------
# Shared cache functions (cached at process level -> shared across pages)
# ---------------------------------------------------------------------------


@st.cache_resource
def load_artifacts():
    """Load model, encoder, and inventory dict from disk (cached for process lifetime)."""
    model, encoder = load_model(MODELS_DIR)
    inventory = load_atc_inventory(DB_PATH)
    return model, encoder, inventory


@st.cache_data(ttl=300)
def run_assessment(_model, _encoder, inventory):
    """Run risk assessment (re-evaluated at most every 5 minutes)."""
    return assess_from_features(
        features_csv=FEATURES_CSV,
        inventory=inventory,
        model=_model,
        encoder=_encoder,
    )


# ---------------------------------------------------------------------------
# Guard helper
# ---------------------------------------------------------------------------


def check_required_files() -> bool:
    """
    Return True if all required files exist.
    Calls st.error + st.stop() if any are missing (no return in that case).
    """
    missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
    if missing:
        st.error(
            "Missing files — run the pipeline and train the model first:\n\n"
            + "\n".join(f"- `{p}`" for p in missing)
        )
        st.stop()
    return True
