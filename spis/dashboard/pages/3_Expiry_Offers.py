"""
spis/dashboard/pages/3_Expiry_Offers.py
-----------------------------------------
Page 3 — Expiry-aware discount offer recommendations.

Loads all inventory batches from the database, runs the expiry advisor,
and displays a colour-coded table with suggested promotions plus a
waste recovery summary.
"""

import pandas as pd
import streamlit as st

from spis.data.database import load_batches
from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    load_artifacts,
    run_assessment,
)
from spis.models.expiry_advisor import assess_all_batches

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Expiry Offers — SPIS", layout="wide")
st.title("Expiry-Aware Discount Offers")
st.caption(
    "Batches within 60 days of expiry are surfaced here with suggested discount tiers "
    "to recover revenue before stock becomes unsellable."
)

check_required_files()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with st.spinner("Running expiry analysis ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

demand_by_atc = {ra.atc_code: ra.daily_demand for ra in results}

@st.cache_data(ttl=300)
def _load_batches_cached(db_path: str) -> list[dict]:
    return load_batches(db_path)


batches = _load_batches_cached(str(DB_PATH))
offers = assess_all_batches(batches, demand_by_atc)

# ---------------------------------------------------------------------------
# Summary card
# ---------------------------------------------------------------------------

total_waste = sum(o.waste_value for o in offers)
total_at_risk = sum(o.units_at_risk for o in offers)

c1, c2, c3 = st.columns(3)
c1.metric("Batches Needing Action", len(offers))
c2.metric("Total Units at Risk",    f"{total_at_risk:.0f}")
c3.metric("Potential Waste Value",  f"${total_waste:.2f}")

st.divider()

# ---------------------------------------------------------------------------
# Offers table
# ---------------------------------------------------------------------------

OFFER_BADGE = {
    "Buy More":      "🟡 Buy More",
    "Special Offer": "🟠 Special Offer",
    "Clearance":     "🔴 Clearance",
    "Final Week":    "🚨 Final Week",
}

if not offers:
    st.success("No batches require action in the next 60 days.")
else:
    rows = []
    for o in offers:
        rows.append({
            "ATC Code":       o.atc_code,
            "Batch":          o.batch_number,
            "Qty (units)":    round(o.quantity, 1),
            "Expiry Date":    o.expiry_date,
            "Days Left":      o.days_to_expiry,
            "Forecast Sales": round(o.forecasted_sales_before_expiry, 1),
            "At Risk":        round(o.units_at_risk, 1),
            "Waste Value":    f"${o.waste_value:.2f}",
            "Discount":       f"{o.suggested_discount_pct}% off",
            "Offer Tier":     OFFER_BADGE.get(o.offer_label, o.offer_label),
            "Action":         o.action,
        })

    st.subheader("Recommended Promotions")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Waste value bar chart
    st.divider()
    st.subheader("Waste Value by Batch")
    chart_df = pd.DataFrame({
        "Batch": [o.batch_number for o in offers],
        "Waste Value ($)": [round(o.waste_value, 2) for o in offers],
    }).set_index("Batch")
    st.bar_chart(chart_df)
