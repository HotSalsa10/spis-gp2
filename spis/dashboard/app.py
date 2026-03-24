"""
spis/dashboard/app.py
---------------------
Phase 6 Streamlit dashboard for SPIS.

Displays inventory risk tiers, 30-day demand forecasts, and order
recommendations for all ATC codes — loaded directly from model artifacts
(no running API required).

Run:
    streamlit run spis/dashboard/app.py
    # or via the convenience script:
    python scripts/run_dashboard.py
"""

from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

from spis.models.forecaster import load_model
from spis.models.risk_classifier import assess_from_features, load_atc_inventory

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file → always correct regardless of cwd)
# ---------------------------------------------------------------------------

ROOT         = Path(__file__).resolve().parent.parent.parent
MODELS_DIR   = ROOT / "models"
DB_PATH      = ROOT / "data" / "inventory.db"
FEATURES_CSV = ROOT / "data" / "processed" / "features_daily.csv"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="SPIS Dashboard", layout="wide")
st.title("Smart Pharmacy Inventory System")
st.caption("Inventory risk assessment and 30-day demand forecast")

# ---------------------------------------------------------------------------
# Data loading (cached so the model is not reloaded on every rerun)
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    MODELS_DIR / "xgboost_forecaster.joblib",
    MODELS_DIR / "label_encoder.joblib",
    DB_PATH,
    FEATURES_CSV,
]


@st.cache_resource
def _load_artifacts():
    """Load model and inventory once; reuse across reruns."""
    model, encoder = load_model(MODELS_DIR)
    inventory = load_atc_inventory(DB_PATH)
    return model, encoder, inventory


@st.cache_data(ttl=300)
def _run_assessment(_model, _encoder, inventory):
    """Run risk assessment (cached for 5 minutes)."""
    return assess_from_features(
        features_csv=FEATURES_CSV,
        inventory=inventory,
        model=_model,
        encoder=_encoder,
    )


# ---------------------------------------------------------------------------
# Guard: check required files exist before running
# ---------------------------------------------------------------------------

missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
if missing:
    st.error(
        "Missing files — run the pipeline and train the model first:\n\n"
        + "\n".join(f"- `{p}`" for p in missing)
    )
    st.stop()

# ---------------------------------------------------------------------------
# Run assessment
# ---------------------------------------------------------------------------

with st.spinner("Running risk assessment ..."):
    model, encoder, inventory = _load_artifacts()
    results = _run_assessment(model, encoder, inventory)

# ---------------------------------------------------------------------------
# Summary metrics (one card per tier)
# ---------------------------------------------------------------------------

tier_counts = Counter(ra.risk_tier for ra in results)

cols = st.columns(4)
tier_labels = {"CRITICAL": "🔴 Critical", "LOW": "🟠 Low", "OK": "🟢 OK", "OVERSTOCK": "🔵 Overstock"}
for col, tier in zip(cols, ["CRITICAL", "LOW", "OK", "OVERSTOCK"]):
    col.metric(tier_labels[tier], tier_counts.get(tier, 0))

st.divider()

# ---------------------------------------------------------------------------
# Risk table
# ---------------------------------------------------------------------------

st.subheader("Inventory Risk Assessment")

TIER_BG = {
    "CRITICAL":  "background-color: #ffe0e0",
    "LOW":       "background-color: #fff3cd",
    "OK":        "background-color: #d4edda",
    "OVERSTOCK": "background-color: #cce5ff",
}

rows = []
for ra in results:
    dos = round(ra.days_of_stock, 1) if ra.days_of_stock != float("inf") else "∞"
    rows.append({
        "ATC Code":      ra.atc_code,
        "Stock (units)": round(ra.current_stock, 1),
        "Forecast 30d":  round(ra.forecast_30d, 1),
        "Daily Demand":  round(ra.daily_demand, 1),
        "Days of Stock": dos,
        "Risk Tier":     ra.risk_tier,
        "Order Qty":     round(ra.order_qty, 1),
    })

df = pd.DataFrame(rows)


def _row_style(row):
    css = TIER_BG.get(row["Risk Tier"], "")
    return [css] * len(row)


styled = df.style.apply(_row_style, axis=1)
st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Order quantity bar chart
# ---------------------------------------------------------------------------

st.subheader("Recommended Order Quantities (units)")
order_df = df.set_index("ATC Code")[["Order Qty"]]
st.bar_chart(order_df)
