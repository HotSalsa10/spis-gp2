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

from collections import Counter

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    inject_css,
    load_artifacts,
    load_atc_labels,
    load_atc_names,
    load_drugs,
    run_assessment,
)

TIER_COLOR = {
    "CRITICAL":  "#ef233c",
    "LOW":       "#f77f00",
    "OK":        "#2dc653",
    "OVERSTOCK": "#4361ee",
}

# ---------------------------------------------------------------------------
# Page config + styling
# ---------------------------------------------------------------------------

st.set_page_config(page_title="SPIS Dashboard", layout="wide")
inject_css()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="display:flex; align-items:center; gap:14px; margin-bottom:0.2rem;">
        <div>
            <h1 style="margin:0; font-size:1.9rem;">Smart Pharmacy Inventory System</h1>
            <p class="spis-subtitle">
                30-day demand forecast &nbsp;·&nbsp; inventory risk &nbsp;·&nbsp; order recommendations
            </p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.divider()

check_required_files()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with st.spinner("Running risk assessment …"):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

st.caption(
    "Forecasts are based on historical sales data through **Oct 2019**  ·  "
    "Risk assessment refreshed every 5 min"
)

tier_counts = Counter(ra.risk_tier for ra in results)
atc_names   = load_atc_names(str(DB_PATH))
atc_labels  = load_atc_labels(str(DB_PATH))

# ---------------------------------------------------------------------------
# Critical alert banner
# ---------------------------------------------------------------------------

critical_items = [ra for ra in results if ra.risk_tier == "CRITICAL"]
if critical_items:
    items_html = " &nbsp;·&nbsp; ".join(
        "<strong>{drugs}</strong> ({code}) &mdash; order {qty:.0f} units".format(
            drugs=atc_labels.get(ra.atc_code, {}).get("drugs_short", ra.atc_code),
            code=ra.atc_code,
            qty=ra.order_qty,
        )
        for ra in critical_items
    )
    st.markdown(
        f"""
        <div class="alert-critical">
          <div class="alert-dot">!</div>
          <div>
            <div class="alert-title">
              ACTION REQUIRED &mdash; {len(critical_items)} item(s) need reordering
            </div>
            <div class="alert-body">{items_html}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

kpi_items = [
    ("CRITICAL",  "Critical",   "Reorder immediately",     "kpi-critical"),
    ("LOW",       "Low Stock",  "Reorder within 14 days",  "kpi-low"),
    ("OK",        "Adequate",   "14 – 90 days of stock",   "kpi-ok"),
    ("OVERSTOCK", "Overstock",  "More than 90 days",       "kpi-overstock"),
]

cols = st.columns(4)
for col, (tier, label, hint, cls) in zip(cols, kpi_items):
    n = tier_counts.get(tier, 0)
    col.markdown(
        f"""
        <div class="kpi-card {cls}">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{n}</div>
          <div class="kpi-hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-top:1.5rem'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Donut chart + Order bar chart — side by side
# ---------------------------------------------------------------------------

left_col, right_col = st.columns([2, 3])

with left_col:
    st.subheader("Risk Distribution")

    labels = [t for t in TIER_COLOR if tier_counts.get(t, 0) > 0]
    values = [tier_counts[t] for t in labels]
    colors = [TIER_COLOR[t] for t in labels]

    fig_donut = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.65,
        marker={"colors": colors, "line": {"color": "#0e1117", "width": 2}},
        textinfo="label+percent",
        textfont={"size": 12, "color": "#a8c0dd"},
        hovertemplate="%{label}: %{value} SKU(s)<extra></extra>",
    ))
    fig_donut.add_annotation(
        text=f"<b>{len(results)}</b><br><span style='font-size:11px'>ATC Codes</span>",
        x=0.5, y=0.5,
        font={"size": 20, "color": "#e0e6f0"},
        showarrow=False,
    )
    fig_donut.update_layout(
        plot_bgcolor="#161b27",
        paper_bgcolor="#161b27",
        font={"color": "#a8c0dd"},
        showlegend=False,
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        height=290,
    )
    st.plotly_chart(fig_donut, use_container_width=True)

with right_col:
    st.subheader("Recommended Order Quantities (units)")

    chart_rows = sorted(results, key=lambda r: r.order_qty, reverse=True)
    fig_bar = go.Figure(go.Bar(
        x=[r.atc_code for r in chart_rows],
        y=[round(r.order_qty, 1) for r in chart_rows],
        marker_color=[TIER_COLOR[r.risk_tier] for r in chart_rows],
        marker_line_width=0,
        text=[f"{r.order_qty:.0f}" for r in chart_rows],
        textposition="outside",
        textfont={"size": 12},
        hovertemplate="%{x}<br>Order Qty: %{y:.1f} units<extra></extra>",
    ))
    fig_bar.update_layout(
        plot_bgcolor="#161b27",
        paper_bgcolor="#161b27",
        font={"color": "#a8c0dd"},
        xaxis={"title": "", "tickfont": {"size": 13}, "gridcolor": "#1e2d45"},
        yaxis={"title": "Units", "gridcolor": "#1e2d45", "zeroline": False},
        margin={"t": 30, "b": 10, "l": 10, "r": 10},
        height=290,
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Risk table
# ---------------------------------------------------------------------------

st.subheader("Inventory Risk Assessment")
st.caption(
    "Days of Stock = current stock ÷ daily demand  "
    "·  Order Qty = 30-day forecast + safety buffer"
)

rows = []
for ra in results:
    dos_val = min(ra.days_of_stock, 365) if ra.days_of_stock != float("inf") else 365
    rows.append({
        "ATC Code":      ra.atc_code,
        "Drug Category": atc_names.get(ra.atc_code, ra.atc_code),
        "Medications":   atc_labels.get(ra.atc_code, {}).get("drugs_short", ""),
        "In Stock":      round(ra.current_stock, 1),
        "30d Forecast":  round(ra.forecast_30d, 1),
        "Daily Demand":  round(ra.daily_demand, 1),
        "Days of Stock": dos_val,
        "Risk":          ra.risk_tier,
        "Order Qty":     round(ra.order_qty, 1),
    })

risk_df = pd.DataFrame(rows)
st.dataframe(
    risk_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "In Stock":      st.column_config.NumberColumn("In Stock",      format="%.1f"),
        "30d Forecast":  st.column_config.NumberColumn("30d Forecast",  format="%.1f"),
        "Daily Demand":  st.column_config.NumberColumn("Daily Demand",  format="%.1f"),
        "Order Qty":     st.column_config.NumberColumn("Order Qty",     format="%.1f"),
        "Days of Stock": st.column_config.ProgressColumn(
            "Days of Stock",
            min_value=0,
            max_value=365,
            format="%.0f d",
        ),
    },
)

st.divider()

# ---------------------------------------------------------------------------
# Medications table
# ---------------------------------------------------------------------------

st.subheader("Medications by ATC Group")
st.caption("Risk tier and order quantity are inherited from the parent ATC code group")

drugs_df  = load_drugs(str(DB_PATH))
ra_by_atc = {ra.atc_code: ra for ra in results}

med_rows = []
for _, drug in drugs_df.iterrows():
    ra = ra_by_atc.get(drug["atc_code"])
    if ra is None:
        continue
    med_rows.append({
        "Drug Name": drug["drug_name"],
        "ATC Code":  drug["atc_code"],
        "Unit":      drug["unit"],
        "Risk":      ra.risk_tier,
        "Order Qty": round(ra.order_qty, 1),
    })

st.dataframe(
    pd.DataFrame(med_rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Order Qty": st.column_config.NumberColumn("Order Qty", format="%.1f"),
    },
)
