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

import sqlite3
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

# Emoji badge per tier — replaces faded background-color styling
TIER_BADGE = {
    "CRITICAL":  "🔴 CRITICAL",
    "LOW":       "🟠 LOW",
    "OK":        "🟢 OK",
    "OVERSTOCK": "🔵 OVERSTOCK",
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="SPIS Dashboard", layout="wide")
st.title("🏥 Smart Pharmacy Inventory System")
st.caption("30-day demand forecast · inventory risk · order recommendations")

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    MODELS_DIR / "xgboost_forecaster.joblib",
    MODELS_DIR / "label_encoder.joblib",
    DB_PATH,
    FEATURES_CSV,
]


@st.cache_resource
def _load_artifacts():
    model, encoder = load_model(MODELS_DIR)
    inventory = load_atc_inventory(DB_PATH)
    return model, encoder, inventory


@st.cache_data(ttl=300)
def _run_assessment(_model, _encoder, inventory):
    return assess_from_features(
        features_csv=FEATURES_CSV,
        inventory=inventory,
        model=_model,
        encoder=_encoder,
    )


@st.cache_data
def _load_drugs(db_path: str) -> pd.DataFrame:
    """Load the drugs catalog from SQLite."""
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT drug_name, atc_code, unit FROM drugs ORDER BY atc_code, drug_name",
            conn,
        )


# ---------------------------------------------------------------------------
# Guard: missing files
# ---------------------------------------------------------------------------

missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
if missing:
    st.error(
        "Missing files — run the pipeline and train the model first:\n\n"
        + "\n".join(f"- `{p}`" for p in missing)
    )
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with st.spinner("Running risk assessment ..."):
    model, encoder, inventory = _load_artifacts()
    results = _run_assessment(model, encoder, inventory)

# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

tier_counts = Counter(ra.risk_tier for ra in results)

c1, c2, c3, c4 = st.columns(4)
c1.metric("🔴 Critical",  tier_counts.get("CRITICAL",  0), help="Stock runs out in < 3 days")
c2.metric("🟠 Low",       tier_counts.get("LOW",       0), help="Stock runs out in 3–7 days")
c3.metric("🟢 OK",        tier_counts.get("OK",        0), help="7–30 days of stock remaining")
c4.metric("🔵 Overstock", tier_counts.get("OVERSTOCK", 0), help="More than 30 days of stock")

st.divider()

# ---------------------------------------------------------------------------
# Risk table
# ---------------------------------------------------------------------------

st.subheader("Inventory Risk Assessment")
st.caption("Days of Stock = current stock ÷ daily demand  |  Order Qty = units needed for the next 30 days + safety buffer")

rows = []
for ra in results:
    dos = f"{ra.days_of_stock:.1f}" if ra.days_of_stock != float("inf") else "∞"
    rows.append({
        "Drug (ATC)":     ra.atc_code,
        "In Stock":       round(ra.current_stock, 1),
        "30d Forecast":   round(ra.forecast_30d, 1),
        "Daily Demand":   round(ra.daily_demand, 1),
        "Days of Stock":  dos,
        "Risk":           TIER_BADGE[ra.risk_tier],
        "Order Qty":      round(ra.order_qty, 1),
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Order quantity bar chart
# ---------------------------------------------------------------------------

st.subheader("Recommended Order Quantities (units)")
order_df = pd.DataFrame(rows).set_index("Drug (ATC)")[["Order Qty"]]
st.bar_chart(order_df)

st.divider()

# ---------------------------------------------------------------------------
# Medications table (individual drugs, risk inherited from parent ATC code)
# ---------------------------------------------------------------------------

st.subheader("Medications by ATC Group")
st.caption("Risk tier and order quantity are inherited from the parent ATC code group")

drugs_df = _load_drugs(str(DB_PATH))

# Build atc_code → RiskAssessment lookup
ra_by_atc = {ra.atc_code: ra for ra in results}

med_rows = []
for _, drug in drugs_df.iterrows():
    ra = ra_by_atc.get(drug["atc_code"])
    if ra is None:
        continue
    med_rows.append({
        "Drug Name":  drug["drug_name"],
        "ATC Code":   drug["atc_code"],
        "Unit":       drug["unit"],
        "Risk":       TIER_BADGE[ra.risk_tier],
        "Order Qty":  round(ra.order_qty, 1),
    })

st.dataframe(pd.DataFrame(med_rows), use_container_width=True, hide_index=True)
