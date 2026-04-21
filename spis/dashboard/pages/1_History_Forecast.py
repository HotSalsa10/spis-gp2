"""
spis/dashboard/pages/1_History_Forecast.py
-------------------------------------------
Page 1 — Configurable sales history + 30-day demand forecast chart.

Displays an interactive Plotly line chart for the selected ATC code:
  - Solid line  : last N days of actual daily sales (slider-controlled)
  - Dashed line : 30-day forecast from the XGBoost model
"""

import sqlite3

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from spis.dashboard._shared import (
    DB_PATH,
    FEATURES_CSV,
    ROOT,
    check_required_files,
    inject_css,
    load_artifacts,
    load_atc_names,
    load_drugs,
    run_assessment,
)
from spis.models.forecaster import FEATURE_COLS
from spis.models.risk_classifier import forecast_30_days

TEST_CSV = ROOT / "data" / "processed" / "test.csv"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="History & Forecast — SPIS", layout="wide")
inject_css()
st.title("History & Forecast")
st.caption(
    "Actual sales history (solid line)  ·  30-day XGBoost forecast (dashed line)  ·  "
    "Forecast is projected from the end of the training dataset (Oct 2019)"
)

check_required_files()

# ---------------------------------------------------------------------------
# Load model + data
# ---------------------------------------------------------------------------

with st.spinner("Loading model ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

atc_names = load_atc_names(str(DB_PATH))
drugs_df   = load_drugs(str(DB_PATH))

# Build drug name lookup: atc_code -> sorted list of drug names
drugs_by_atc: dict[str, list[str]] = {}
for _, row in drugs_df.iterrows():
    drugs_by_atc.setdefault(row["atc_code"], []).append(row["drug_name"])

atc_codes = sorted(inventory.keys())
atc_options = [f"{code} — {atc_names.get(code, code)}" for code in atc_codes]

col_sel, col_slider = st.columns([3, 2])
with col_sel:
    selected_label = st.selectbox("Select ATC Code", atc_options)
    selected = selected_label.split(" — ")[0]
with col_slider:
    n_days = st.select_slider(
        "History window",
        options=[30, 60, 90, 180],
        value=90,
    )

drug_list = drugs_by_atc.get(selected, [])
if drug_list:
    with st.expander(f"Medications in this group ({len(drug_list)})"):
        st.write(", ".join(sorted(drug_list)))

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
# Bootstrap prediction interval (P10–P90)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def _compute_residuals(_model, _encoder, atc_code: str) -> np.ndarray:
    """Return test-set residuals (actual − predicted) for one ATC code."""
    if not TEST_CSV.exists():
        return np.array([])
    df = pd.read_csv(str(TEST_CSV))
    df = df[df["atc_code"] == atc_code].copy()
    if df.empty:
        return np.array([])
    df["atc_encoded"] = _encoder.transform(df["atc_code"])
    X = df[FEATURE_COLS].dropna()
    if X.empty:
        return np.array([])
    y_true = df.loc[X.index, "quantity"].values.astype(float)
    y_pred = _model.predict(X).astype(float)
    return y_true - y_pred


def _bootstrap_interval(
    point_forecast: list[float],
    residuals: np.ndarray,
    n_boot: int = 500,
    p_lo: float = 10.0,
    p_hi: float = 90.0,
    rng_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Bootstrap P10/P90 band by resampling test residuals onto the point forecast."""
    fc = np.array(point_forecast, dtype=float)
    if len(residuals) < 5:
        return fc, fc
    rng = np.random.default_rng(rng_seed)
    n_days = len(fc)
    sampled = rng.choice(residuals, size=(n_boot, n_days), replace=True)
    sims = np.clip(fc[None, :] + sampled, 0.0, None)
    return np.percentile(sims, p_lo, axis=0), np.percentile(sims, p_hi, axis=0)


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

history_df = _load_history(selected, n_days)
forecast_df = _load_forecast(selected)

residuals = _compute_residuals(model, encoder, selected)
lower, upper = _bootstrap_interval(
    forecast_df["quantity"].tolist() if not forecast_df.empty else [],
    residuals,
)

fig = go.Figure()

if not history_df.empty:
    fig.add_trace(go.Scatter(
        x=history_df["sale_date"],
        y=history_df["quantity"],
        mode="lines",
        name=f"Actual ({n_days}d)",
        line={"color": "#1f77b4", "width": 2},
    ))

if not forecast_df.empty:
    # Band: lower boundary (invisible) then upper with fill='tonexty'
    fig.add_trace(go.Scatter(
        x=forecast_df["date"],
        y=lower,
        mode="lines",
        line={"width": 0},
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=forecast_df["date"],
        y=upper,
        mode="lines",
        fill="tonexty",
        fillcolor="rgba(255,127,14,0.18)",
        line={"width": 0},
        name="P10–P90 interval",
        hovertemplate="Upper P90: %{y:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=forecast_df["date"],
        y=forecast_df["quantity"],
        mode="lines",
        name="Forecast (30d)",
        line={"color": "#ff7f0e", "width": 2, "dash": "dash"},
    ))

fig.update_layout(
    plot_bgcolor="#161b27",
    paper_bgcolor="#161b27",
    font={"color": "#a8c0dd"},
    xaxis_title="Date",
    yaxis_title="Units Sold / Forecast",
    xaxis={"gridcolor": "#1e2d45"},
    yaxis={"gridcolor": "#1e2d45", "zeroline": False},
    legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "bgcolor": "rgba(0,0,0,0)"},
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
