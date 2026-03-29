"""
spis/dashboard/pages/1_History_Forecast.py
-------------------------------------------
Page 1 — 90-day sales history + 30-day demand forecast chart.

Displays an interactive Plotly line chart for the selected ATC code:
  - Solid line  : last 90 days of actual daily sales
  - Dashed line : 30-day forecast from the XGBoost model
"""

import sqlite3

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from spis.dashboard._shared import (
    DB_PATH,
    FEATURES_CSV,
    check_required_files,
    load_artifacts,
    run_assessment,
)
from spis.models.risk_classifier import forecast_30_days

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="History & Forecast — SPIS", layout="wide")
st.title("History & Forecast")
st.caption("90-day actual sales (solid) · 30-day XGBoost forecast (dashed)")

check_required_files()

# ---------------------------------------------------------------------------
# Load model + data
# ---------------------------------------------------------------------------

with st.spinner("Loading model ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

atc_codes = sorted(inventory.keys())
selected = st.selectbox("Select ATC Code", atc_codes)

# ---------------------------------------------------------------------------
# Fetch history from SQLite
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def _load_history(atc_code: str, n_days: int = 90) -> pd.DataFrame:
    with sqlite3.connect(str(DB_PATH)) as conn:
        df = pd.read_sql_query(
            """
            SELECT sale_date, quantity
            FROM   sales
            WHERE  atc_code = ? AND granularity = 'daily'
            ORDER  BY sale_date DESC
            LIMIT  ?
            """,
            conn,
            params=(atc_code, n_days),
        )
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    return df.sort_values("sale_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Build 30-day forecast series
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def _load_forecast(atc_code: str) -> pd.DataFrame:
    features_df = pd.read_csv(str(FEATURES_CSV), parse_dates=["date"])
    atc_rows = features_df[features_df["atc_code"] == atc_code].sort_values("date")
    if atc_rows.empty:
        return pd.DataFrame(columns=["date", "quantity"])

    seed_row = atc_rows.tail(1).reset_index(drop=True)
    start_date = atc_rows["date"].max() + pd.Timedelta(days=1)

    daily_preds = forecast_30_days(
        model, encoder, seed_row, atc_code, start_date, return_daily=True
    )
    dates = [start_date + pd.Timedelta(days=i) for i in range(len(daily_preds))]
    return pd.DataFrame({"date": dates, "quantity": daily_preds})


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

history_df = _load_history(selected)
forecast_df = _load_forecast(selected)

fig = go.Figure()

if not history_df.empty:
    fig.add_trace(go.Scatter(
        x=history_df["sale_date"],
        y=history_df["quantity"],
        mode="lines",
        name="Actual (90d)",
        line={"color": "#1f77b4", "width": 2},
    ))

if not forecast_df.empty:
    fig.add_trace(go.Scatter(
        x=forecast_df["date"],
        y=forecast_df["quantity"],
        mode="lines",
        name="Forecast (30d)",
        line={"color": "#ff7f0e", "width": 2, "dash": "dash"},
    ))

fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Units Sold / Forecast",
    legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    hovermode="x unified",
    height=450,
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Summary numbers below chart
# ---------------------------------------------------------------------------

ra_by_atc = {ra.atc_code: ra for ra in results}
ra = ra_by_atc.get(selected)
if ra:
    c1, c2, c3 = st.columns(3)
    c1.metric("30-day Forecast", f"{ra.forecast_30d:.1f} units")
    c2.metric("Daily Demand",    f"{ra.daily_demand:.1f} units/day")
    c3.metric("Days of Stock",
              "inf" if ra.days_of_stock == float("inf") else f"{ra.days_of_stock:.1f}")
