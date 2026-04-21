"""
spis/dashboard/pages/4_Analytics.py
--------------------------------------
Page 4 — Analytics: feature importance + ABC demand analysis.

Panels:
  1. XGBoost feature importance (horizontal bar chart)
  2. ABC / Pareto analysis of ATC codes by 30-day forecasted demand
"""

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ABC classification cutoffs (cumulative demand %)
ABC_A_CUTOFF = 80
ABC_B_CUTOFF = 95

from spis.dashboard._shared import (
    FEATURES_CSV,
    MODELS_DIR,
    check_required_files,
    inject_css,
    load_artifacts,
    run_assessment,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Analytics — SPIS", layout="wide")
inject_css()
st.title("Analytics")
st.caption("XGBoost feature importance  ·  ABC demand analysis")

check_required_files()

# ---------------------------------------------------------------------------
# Panel 1 — Feature importance
# ---------------------------------------------------------------------------

st.subheader("Model Accuracy")

metrics_path = MODELS_DIR / "metrics.json"
if metrics_path.exists():
    with open(metrics_path) as f:
        metrics = json.load(f)

    m_naive = next((m for m in metrics if "Naive" in m["model"]), None)
    m_mavg  = next((m for m in metrics if "Moving" in m["model"]), None)
    m_xgb   = next((m for m in metrics if "XGBoost" in m["model"]), None)

    if m_xgb:
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric(
            "XGBoost MAE",
            f"{m_xgb['mae']:.2f} units",
            delta=f"{m_mavg['mae'] - m_xgb['mae']:.2f} vs moving avg" if m_mavg else None,
        )
        mc2.metric(
            "XGBoost RMSE",
            f"{m_xgb['rmse']:.2f} units",
        )
        mc3.metric(
            "XGBoost MAPE",
            f"{m_xgb['mape']:.1f}%",
        )
        mc4.metric(
            "vs Naive Baseline",
            f"{m_xgb['mae']:.2f}",
            delta=f"{m_naive['mae'] - m_xgb['mae']:.2f} better" if m_naive else None,
        )

        with st.expander("Full baseline comparison"):
            st.dataframe(
                pd.DataFrame(metrics).rename(columns={
                    "model": "Model", "mae": "MAE", "rmse": "RMSE", "mape": "MAPE (%)"
                }).round(2),
                hide_index=True,
                use_container_width=True,
            )

st.divider()

st.subheader("XGBoost Feature Importance")

fi_path = MODELS_DIR / "feature_importance.json"
if not fi_path.exists():
    st.warning(
        "`models/feature_importance.json` not found. "
        "Re-run `scripts/train_model.py` to generate it."
    )
else:
    with open(fi_path) as f:
        fi_data = json.load(f)

    fi_df = pd.DataFrame(fi_data).head(20)   # top 20 features

    fig = px.bar(
        fi_df.sort_values("importance"),
        x="importance",
        y="feature",
        orientation="h",
        labels={"importance": "Importance Score", "feature": "Feature"},
        color="importance",
        color_continuous_scale="Blues",
        height=550,
    )
    fig.update_layout(
        coloraxis_showscale=False,
        yaxis_title="",
        plot_bgcolor="#161b27",
        paper_bgcolor="#161b27",
        font={"color": "#a8c0dd"},
        xaxis={"gridcolor": "#1e2d45"},
        yaxis={"gridcolor": "#1e2d45"},
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Panel 2 — ABC / Pareto demand analysis
# ---------------------------------------------------------------------------

st.subheader("ABC Demand Analysis")
st.caption(
    f"A = codes driving the first {ABC_A_CUTOFF}% of demand  ·  "
    f"B = up to {ABC_B_CUTOFF}%  ·  "
    "C = remaining  ·  "
    "Based on 30-day XGBoost forecasts (refreshed every 5 min)"
)

with st.spinner("Loading risk assessment ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

abc_df = pd.DataFrame([
    {"ATC Code": ra.atc_code, "30d Forecast": ra.forecast_30d}
    for ra in results
]).sort_values("30d Forecast", ascending=False).reset_index(drop=True)

total_demand = abc_df["30d Forecast"].sum()
abc_df["Cumulative %"] = abc_df["30d Forecast"].cumsum() / total_demand * 100
abc_df["Share %"] = abc_df["30d Forecast"] / total_demand * 100


def _abc_class(cum_pct: float) -> str:
    if cum_pct <= ABC_A_CUTOFF:
        return "A"
    if cum_pct <= ABC_B_CUTOFF:
        return "B"
    return "C"


abc_df["Class"] = abc_df["Cumulative %"].apply(_abc_class)

color_map = {"A": "#d62728", "B": "#ff7f0e", "C": "#1f77b4"}

fig2 = px.bar(
    abc_df,
    x="ATC Code",
    y="30d Forecast",
    color="Class",
    color_discrete_map=color_map,
    text="Class",
    labels={"30d Forecast": "30-day Forecasted Demand (units)"},
    height=400,
)
fig2.update_traces(textposition="outside")
fig2.update_layout(
    plot_bgcolor="#161b27",
    paper_bgcolor="#161b27",
    font={"color": "#a8c0dd"},
    xaxis={"gridcolor": "#1e2d45"},
    yaxis={"gridcolor": "#1e2d45"},
)
st.plotly_chart(fig2, use_container_width=True)

st.dataframe(
    abc_df[["ATC Code", "30d Forecast", "Share %", "Cumulative %", "Class"]]
    .rename(columns={"30d Forecast": "30d Forecast (units)",
                     "Share %": "Share (%)",
                     "Cumulative %": "Cumulative (%)"}),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ---------------------------------------------------------------------------
# Panel 3 — 12-month rolling demand trend
# ---------------------------------------------------------------------------

st.subheader("12-Month Rolling Demand Trend")
st.caption("90-day rolling average of daily sales per ATC code — shows whether demand is growing or shrinking")

if FEATURES_CSV.exists():
    @st.cache_data(ttl=600)
    def _load_trend() -> pd.DataFrame:
        df = pd.read_csv(str(FEATURES_CSV), parse_dates=["date"])
        df = df[["date", "atc_code", "quantity"]].copy()
        last_date = df["date"].max()
        cutoff = last_date - pd.Timedelta(days=365)
        df = df[df["date"] >= cutoff]
        df = df.sort_values("date")
        df["rolling_90"] = (
            df.groupby("atc_code")["quantity"]
            .transform(lambda s: s.rolling(90, min_periods=14).mean())
        )
        return df.dropna(subset=["rolling_90"])

    trend_df = _load_trend()
    atc_codes_trend = sorted(trend_df["atc_code"].unique())

    selected_atcs = st.multiselect(
        "ATC Codes to display",
        atc_codes_trend,
        default=atc_codes_trend,
    )

    fig_trend = go.Figure()
    for code in selected_atcs:
        sub = trend_df[trend_df["atc_code"] == code]
        fig_trend.add_trace(go.Scatter(
            x=sub["date"],
            y=sub["rolling_90"].round(2),
            mode="lines",
            name=code,
            hovertemplate=f"{code}<br>%{{x|%Y-%m-%d}}<br>Avg: %{{y:.1f}} units<extra></extra>",
        ))

    fig_trend.update_layout(
        plot_bgcolor="#161b27",
        paper_bgcolor="#161b27",
        font={"color": "#a8c0dd"},
        xaxis={"title": "Date", "gridcolor": "#1e2d45"},
        yaxis={"title": "90-day Rolling Avg (units/day)", "gridcolor": "#1e2d45", "zeroline": False},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "bgcolor": "rgba(0,0,0,0)"},
        hovermode="x unified",
        height=420,
        margin={"t": 30, "b": 10},
    )
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.warning("Features CSV not found — run `scripts/run_pipeline.py` to generate it.")
