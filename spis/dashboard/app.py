"""
spis/dashboard/app.py
---------------------
Phase 8.5 Streamlit dashboard for SPIS — Overview page.

Displays inventory risk tiers, 30-day demand forecasts, and order
recommendations for all ATC codes.  Additional pages (History & Forecast,
Stock Update, Expiry Offers, Analytics) are in spis/dashboard/pages/.

Run:
    streamlit run spis/dashboard/app.py
    # or via the convenience script:
    python scripts/run_dashboard.py
"""

import sqlite3
from collections import Counter

import pandas as pd
import streamlit as st

from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    load_artifacts,
    run_assessment,
)

# Emoji badge per tier
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
# Guard: missing files
# ---------------------------------------------------------------------------

check_required_files()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with st.spinner("Running risk assessment ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)


@st.cache_data
def _load_drugs(db_path: str) -> pd.DataFrame:
    """Load the drugs catalog from SQLite."""
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT drug_name, atc_code, unit FROM drugs ORDER BY atc_code, drug_name",
            conn,
        )


# ---------------------------------------------------------------------------
# Critical alerts banner
# ---------------------------------------------------------------------------

critical_items = [ra for ra in results if ra.risk_tier == "CRITICAL"]
if critical_items:
    names = "  |  ".join(
        f"{ra.atc_code} (order {ra.order_qty:.0f} units)" for ra in critical_items
    )
    st.error(f"**ACTION REQUIRED** — {len(critical_items)} critical item(s) need reordering:  {names}")

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
