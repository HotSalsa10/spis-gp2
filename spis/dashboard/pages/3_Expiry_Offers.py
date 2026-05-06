"""
spis/dashboard/pages/3_Expiry_Offers.py
-----------------------------------------
Page 3 — Expiry-aware discount offer recommendations.

Loads all inventory batches from the database, runs the expiry advisor,
and displays a colour-coded table with suggested promotions plus a
waste recovery summary.
"""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from spis.data.database import load_batches, save_batch_overrides
from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    inject_css,
    load_artifacts,
    load_atc_labels,
    run_assessment,
)
from spis.models.expiry_advisor import assess_all_batches

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Expiry Offers — SPIS", layout="wide")
inject_css()
st.title("Expiry-Aware Discount Offers")
st.caption(
    "Batches within 90 days of expiry are surfaced here  ·  "
    "Demand forecasts are based on sales data through Oct 2019  ·  "
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


batches  = _load_batches_cached(str(DB_PATH))
offers   = assess_all_batches(batches, demand_by_atc)
atc_info = load_atc_labels(str(DB_PATH))

# ---------------------------------------------------------------------------
# Summary card
# ---------------------------------------------------------------------------

total_waste = sum(o.waste_value for o in offers)
total_at_risk = sum(o.units_at_risk for o in offers)

def _projected_recovery(offers_list, batches_list) -> float:
    """Revenue recovered by selling at-risk units at a discounted price.
    Recovery = units_at_risk * unit_cost * (1 - discount/100).
    Without a discount a unit at risk becomes waste; any sale price > 0 is recovery.
    """
    discount_map = {b["batch_number"]: b["applied_discount"] for b in batches_list}
    total = 0.0
    for o in offers_list:
        discount_pct = discount_map.get(o.batch_number, o.suggested_discount_pct) or 0.0
        total += o.units_at_risk * o.unit_cost * (1.0 - discount_pct / 100.0)
    return total

proj_recovery = _projected_recovery(offers, batches)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Batches Needing Action", len(offers))
c2.metric("Total Units at Risk",    f"{total_at_risk:.0f}")
c3.metric("Potential Waste Value",  f"SAR {total_waste:.2f}")
c4.metric("Projected Recovery",     f"SAR {proj_recovery:.2f}")

st.divider()

# ---------------------------------------------------------------------------
# Offers table
# ---------------------------------------------------------------------------

OFFER_BADGE = {
    "Monitor":          "Monitor (no discount yet)",
    "Early Discount":   "Early Discount",
    "Special Offer":    "Special Offer",
    "Cannot Dispense":  "Cannot Dispense — Return to Supplier",
    "Expired":          "Expired — Write Off",
}

URGENCY_COLOR = {
    "Cannot Dispense": "#e63946",
    "Expired":         "#6c1e2e",
    "Special Offer":   "#f77f00",
    "Early Discount":  "#fcbf49",
    "Monitor":         "#4895ef",
}


def _gantt_chart(filtered_offers):
    today = date.today()
    fig = go.Figure()
    for o in filtered_offers:
        color = URGENCY_COLOR.get(o.offer_label, "#7f8fa6")
        try:
            expiry = date.fromisoformat(str(o.expiry_date))
        except (ValueError, TypeError):
            continue
        days_left = max(0, (expiry - today).days)
        fig.add_trace(go.Bar(
            orientation="h",
            x=[days_left],
            y=[o.batch_number],
            base=[0],
            marker_color=color,
            text=f"{o.days_to_expiry}d — SAR {o.waste_value:.0f} at risk",
            textposition="inside",
            insidetextanchor="start",
            hovertemplate=(
                f"<b>{o.batch_number}</b><br>"
                f"ATC: {o.atc_code}<br>"
                f"Expiry: {o.expiry_date}<br>"
                f"Days left: {o.days_to_expiry}<br>"
                f"Waste value: SAR {o.waste_value:.2f}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="#161b27",
        paper_bgcolor="#161b27",
        font={"color": "#a8c0dd"},
        xaxis={
            "title": "Days until expiry (from today)",
            "gridcolor": "#1e2d45",
            "zeroline": True,
            "zerolinecolor": "#e63946",
        },
        yaxis={"gridcolor": "#1e2d45", "autorange": "reversed"},
        margin={"t": 24, "b": 10, "l": 10, "r": 10},
        height=max(180, 60 + len(filtered_offers) * 38),
    )
    # Legend swatches
    for label, color in URGENCY_COLOR.items():
        fig.add_trace(go.Bar(
            x=[None], y=[None],
            orientation="h",
            marker_color=color,
            name=label,
            showlegend=True,
        ))
    fig.update_layout(
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


def _render_offers_section(filtered_offers, tab_key: str):
    batch_id_map = {b["batch_number"]: b["batch_id"] for b in batches}
    rows = []
    for o in filtered_offers:
        info = atc_info.get(o.atc_code, {})
        saved_discount = next(
            (b["applied_discount"] for b in batches if b["batch_number"] == o.batch_number),
            None,
        )
        is_returned = next(
            (bool(b["returned"]) for b in batches if b["batch_number"] == o.batch_number),
            False,
        )
        rows.append({
            "_batch_id":            batch_id_map.get(o.batch_number, -1),
            "ATC Code":             o.atc_code,
            "Drug Category":        info.get("category", o.atc_code),
            "Medications":          info.get("drugs_full", ""),
            "Batch":                o.batch_number,
            "Qty (units)":          round(o.quantity, 1),
            "Expiry Date":          o.expiry_date,
            "Days Left":            o.days_to_expiry,
            "Forecast Sales":       round(o.forecasted_sales_before_expiry, 1),
            "At Risk":              round(o.units_at_risk, 1),
            "Waste Value (SAR)":    round(o.waste_value, 2),
            "Status":               OFFER_BADGE.get(o.offer_label, o.offer_label),
            "Suggested Discount %": o.suggested_discount_pct,
            "Applied Discount %":   saved_discount if saved_discount is not None else o.suggested_discount_pct,
            "Return to Supplier":   is_returned,
            "Action":               o.action,
        })

    st.subheader("Recommended Promotions")
    st.caption(
        "The **Suggested Discount %** is calculated automatically. "
        "Edit **Applied Discount %** or tick **Return to Supplier**, then click **Confirm & Print Labels**."
    )

    edited_df = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        key=f"editor_{tab_key}",
        disabled=[
            "ATC Code", "Drug Category", "Medications", "Batch",
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
            "Return to Supplier": st.column_config.CheckboxColumn(
                "Return to Supplier",
                help="Tick to mark this batch for supplier return — quantity will be zeroed.",
            ),
            "_batch_id": None,
        },
    )

    if st.button("Confirm & Print Labels", type="primary", key=f"confirm_{tab_key}"):
        overrides = [
            {
                "batch_id":         row["_batch_id"],
                "applied_discount": row["Applied Discount %"],
                "returned":         row["Return to Supplier"],
            }
            for _, row in edited_df.iterrows()
            if row["_batch_id"] != -1
        ]
        try:
            save_batch_overrides(str(DB_PATH), overrides)
            _load_batches_cached.clear()
            returned_batches = [r for r in overrides if r["returned"]]
            msg = f"Saved overrides for {len(overrides)} batch(es)."
            if returned_batches:
                msg += f" {len(returned_batches)} batch(es) marked for supplier return."
            st.success(msg)
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to save overrides: {exc}")

    st.divider()
    st.subheader("Expiry Timeline")
    st.caption("Each bar spans from today to the batch expiry date. Colour indicates urgency tier.")
    st.plotly_chart(_gantt_chart(filtered_offers), use_container_width=True)


if not offers:
    st.success("No batches require action in the next 90 days.")
else:
    filter_opt = st.radio(
        "Show",
        ["All", "Urgent  (<30 days)", "Upcoming  (30–90 days)"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if filter_opt == "Urgent  (<30 days)":
        filtered_offers = [o for o in offers if o.days_to_expiry < 30]
        if not filtered_offers:
            st.info("No batches expiring within 30 days.")
    elif filter_opt == "Upcoming  (30–90 days)":
        filtered_offers = [o for o in offers if 30 <= o.days_to_expiry <= 90]
        if not filtered_offers:
            st.info("No batches in the 30–90 day window.")
    else:
        filtered_offers = offers

    if filtered_offers:
        _render_offers_section(filtered_offers, "main")
