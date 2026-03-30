"""
spis/dashboard/pages/3_Expiry_Offers.py
-----------------------------------------
Page 3 — Expiry-aware discount offer recommendations.

Loads all inventory batches from the database, runs the expiry advisor,
and displays a colour-coded table with suggested promotions plus a
waste recovery summary.
"""

import sqlite3

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


@st.cache_data
def _load_atc_drug_info(db_path: str) -> dict[str, dict]:
    """Return dict: atc_code -> {name, drugs (comma-separated top 4)}."""
    with sqlite3.connect(db_path) as conn:
        cats = conn.execute(
            "SELECT atc_code, atc_name FROM atc_categories"
        ).fetchall()
        drugs = conn.execute(
            "SELECT atc_code, drug_name FROM drugs ORDER BY atc_code, drug_name"
        ).fetchall()

    drug_map: dict[str, list] = {}
    for code, name in drugs:
        drug_map.setdefault(code, []).append(name)

    return {
        code: {
            "name": cat_name,
            "drugs": ", ".join(drug_map.get(code, [])[:4]),
        }
        for code, cat_name in cats
    }

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Expiry Offers — SPIS", layout="wide")
st.title("Expiry-Aware Discount Offers")
st.caption(
    "Batches within 90 days of expiry are surfaced here. "
    "Batches under 30 days must be returned to supplier — they cannot be dispensed to patients."
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
atc_info = _load_atc_drug_info(str(DB_PATH))

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
    "Monitor":          "🔵 Monitor (no discount yet)",
    "Early Discount":   "🟡 Early Discount",
    "Special Offer":    "🟠 Special Offer",
    "Cannot Dispense":  "🚨 Cannot Dispense — Return to Supplier",
    "Expired":          "❌ Expired — Write Off",
}

if not offers:
    st.success("No batches require action in the next 90 days.")
else:
    rows = []
    for o in offers:
        info = atc_info.get(o.atc_code, {})
        rows.append({
            "ATC Code":            o.atc_code,
            "Drug Category":       info.get("name", o.atc_code),
            "Example Drugs":       info.get("drugs", ""),
            "Batch":               o.batch_number,
            "Qty (units)":         round(o.quantity, 1),
            "Expiry Date":         o.expiry_date,
            "Days Left":           o.days_to_expiry,
            "Forecast Sales":      round(o.forecasted_sales_before_expiry, 1),
            "At Risk":             round(o.units_at_risk, 1),
            "Waste Value (SAR)":   round(o.waste_value, 2),
            "Status":              OFFER_BADGE.get(o.offer_label, o.offer_label),
            "Suggested Discount %": o.suggested_discount_pct,
            "Applied Discount %":  o.suggested_discount_pct,   # pharmacist can override
            "Action":              o.action,
        })

    st.subheader("Recommended Promotions")
    st.caption(
        "The **Suggested Discount %** is calculated automatically. "
        "Edit **Applied Discount %** to override for any batch before printing labels."
    )

    edited_df = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        disabled=[
            "ATC Code", "Drug Category", "Example Drugs", "Batch",
            "Qty (units)", "Expiry Date", "Days Left", "Forecast Sales",
            "At Risk", "Waste Value (SAR)", "Status",
            "Suggested Discount %", "Action",
        ],
        column_config={
            "Applied Discount %": st.column_config.NumberColumn(
                "Applied Discount %",
                min_value=0,
                max_value=100,
                step=5,
                help="Override the suggested discount. Must be 0-100.",
            ),
            "Waste Value (SAR)": st.column_config.NumberColumn(
                "Waste Value (SAR)", format="SAR %.2f"
            ),
        },
    )

    # Waste value bar chart (uses model values, not overrides)
    st.divider()
    st.subheader("Waste Value by Batch")
    chart_df = pd.DataFrame({
        "Batch": [o.batch_number for o in offers],
        "Waste Value (SAR)": [round(o.waste_value, 2) for o in offers],
    }).set_index("Batch")
    st.bar_chart(chart_df)
