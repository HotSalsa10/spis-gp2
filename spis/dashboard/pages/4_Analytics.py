"""
spis/dashboard/pages/4_Analytics.py
--------------------------------------
Page 4 — Analytics: feature importance + ABC demand analysis.

Panels:
  1. XGBoost feature importance (horizontal bar chart)
  2. ABC / Pareto analysis of ATC codes by 30-day forecasted demand
"""

import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from spis.models.decomposition import decompose
from spis.models.inventory_kpi import compute_turnover

# ABC classification cutoffs (cumulative demand %)
ABC_A_CUTOFF = 80
ABC_B_CUTOFF = 95

from spis.dashboard._shared import (
    DB_PATH,
    FEATURES_CSV,
    MODELS_DIR,
    check_required_files,
    inject_css,
    load_artifacts,
    load_atc_labels,
    run_assessment,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Analytics — SPIS", layout="wide")
inject_css()
st.title("Analytics")
st.caption(
    "XGBoost feature importance  ·  ABC demand analysis  ·  "
    "All forecasts based on sales data through Oct 2019"
)

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

st.subheader("Fast / Medium / Slow Movers (ABC Pareto)")
st.caption(
    "A-class drugs (top 80% of demand) need tight stock control; "
    "C-class can be ordered less frequently.  "
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
        return "Fast"
    if cum_pct <= ABC_B_CUTOFF:
        return "Medium"
    return "Slow"


abc_df["Class"] = abc_df["Cumulative %"].apply(_abc_class)

atc_labels = load_atc_labels(str(DB_PATH))
abc_df["Medications"] = abc_df["ATC Code"].map(
    lambda code: atc_labels.get(code, {}).get("drugs_short", "")
)

color_map = {"Fast": "#d62728", "Medium": "#ff7f0e", "Slow": "#1f77b4"}

fig2 = px.bar(
    abc_df,
    x="ATC Code",
    y="30d Forecast",
    color="Class",
    color_discrete_map=color_map,
    text="Class",
    hover_data={"Medications": True, "Class": False},
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
    abc_df[["ATC Code", "Medications", "30d Forecast", "Share %", "Cumulative %", "Class"]]
    .rename(columns={"30d Forecast": "30d Forecast (units)",
                     "Share %": "Share (%)",
                     "Cumulative %": "Cumulative (%)"}),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ---------------------------------------------------------------------------
# Panel 3 — Seasonal decomposition
# ---------------------------------------------------------------------------

st.subheader("Seasonal Decomposition")
st.caption(
    "Trend = long-term direction; Seasonal = repeating pattern; "
    "Residual = unexplained noise. Low residual means the model captures the signal well."
)

if FEATURES_CSV.exists():
    @st.cache_data(ttl=600)
    def _load_features() -> pd.DataFrame:
        df = pd.read_csv(str(FEATURES_CSV), parse_dates=["date"])
        return df[["date", "atc_code", "quantity"]].copy()

    feat_df = _load_features()
    atc_codes_all = sorted(feat_df["atc_code"].unique())

    sel_atc = st.selectbox("ATC Code", atc_codes_all, key="decomp_atc")

    atc_qty = (
        feat_df[feat_df["atc_code"] == sel_atc]
        .sort_values("date")
        .reset_index(drop=True)
    )
    dates = atc_qty["date"]
    qty_arr = atc_qty["quantity"].to_numpy(dtype=float)

    decomp = decompose(qty_arr, period=365)

    _DECOMP_TRACES = [
        ("trend",    "#4cc9f0", "Trend (units/day)"),
        ("seasonal", "#7bed9f", "Seasonal component"),
        ("residual", "#ff6b6b", "Residual"),
    ]

    fig_decomp = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        subplot_titles=[t[2] for t in _DECOMP_TRACES],
        vertical_spacing=0.09,
    )

    for row, (key, color, label) in enumerate(_DECOMP_TRACES, start=1):
        fig_decomp.add_trace(
            go.Scatter(
                x=dates, y=decomp[key].round(3),
                mode="lines", name=label,
                line={"color": color, "width": 1.2},
                showlegend=False,
            ),
            row=row, col=1,
        )

    fig_decomp.update_layout(
        height=540,
        plot_bgcolor="#161b27",
        paper_bgcolor="#161b27",
        font={"color": "#a8c0dd"},
        margin={"t": 50, "b": 10},
    )
    fig_decomp.update_xaxes(gridcolor="#1e2d45")
    fig_decomp.update_yaxes(gridcolor="#1e2d45", zeroline=False)

    st.plotly_chart(fig_decomp, use_container_width=True)
else:
    st.warning("Features CSV not found -- run `scripts/run_pipeline.py` to generate it.")

st.divider()

# ---------------------------------------------------------------------------
# Panel 4 — Year-over-Year demand growth
# ---------------------------------------------------------------------------

st.subheader("Year-over-Year Demand Growth (%)")
st.caption(
    "Compares the most recent 365-day period against the prior 365-day period. "
    "Green = growing demand; red = declining demand."
)

if FEATURES_CSV.exists():
    @st.cache_data(ttl=600)
    def _load_yoy() -> pd.DataFrame:
        df = pd.read_csv(str(FEATURES_CSV), parse_dates=["date"])
        df = df[["date", "atc_code", "quantity"]].copy()
        last_date = df["date"].max()
        this_start = last_date - pd.Timedelta(days=364)
        last_start = last_date - pd.Timedelta(days=729)
        last_end   = last_date - pd.Timedelta(days=365)

        this_yr = (
            df[df["date"] >= this_start]
            .groupby("atc_code")["quantity"].sum()
            .rename("this_year")
        )
        last_yr = (
            df[(df["date"] >= last_start) & (df["date"] <= last_end)]
            .groupby("atc_code")["quantity"].sum()
            .rename("last_year")
        )
        yoy = pd.concat([this_yr, last_yr], axis=1).dropna()
        yoy["yoy_pct"] = (yoy["this_year"] - yoy["last_year"]) / yoy["last_year"] * 100
        return yoy.reset_index().rename(
            columns={"atc_code": "ATC Code", "yoy_pct": "YoY Growth (%)"}
        )

    yoy_df = _load_yoy()
    yoy_df["Direction"] = np.where(yoy_df["YoY Growth (%)"] >= 0, "Growing", "Declining")
    yoy_df["Label"] = yoy_df["YoY Growth (%)"].apply(lambda x: f"{x:+.1f}%")

    fig_yoy = px.bar(
        yoy_df.sort_values("YoY Growth (%)"),
        x="ATC Code",
        y="YoY Growth (%)",
        color="Direction",
        color_discrete_map={"Growing": "#2dc653", "Declining": "#ef233c"},
        text="Label",
        height=380,
    )
    fig_yoy.update_traces(textposition="outside")
    fig_yoy.update_layout(
        showlegend=False,
        plot_bgcolor="#161b27",
        paper_bgcolor="#161b27",
        font={"color": "#a8c0dd"},
        xaxis={"gridcolor": "#1e2d45"},
        yaxis={
            "gridcolor": "#1e2d45",
            "zeroline": True,
            "zerolinecolor": "#4e6a84",
            "zerolinewidth": 1,
        },
    )
    st.plotly_chart(fig_yoy, use_container_width=True)
else:
    st.warning("Features CSV not found -- run `scripts/run_pipeline.py` to generate it.")

st.divider()

# ---------------------------------------------------------------------------
# Panel 5 — 12-month rolling demand trend
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

st.divider()

# ---------------------------------------------------------------------------
# Panel 6 — Inventory turnover KPI strip
# ---------------------------------------------------------------------------

st.subheader("Inventory Turnover Ratio")
st.caption(
    "Turnover = annual units sold / current on-hand stock.  "
    "Thresholds: Slow <4x | Low 4-6x | Healthy 6-12x | High 12-24x | Excessive >24x"
)

turnover_data = compute_turnover(str(DB_PATH))
if turnover_data:
    turnover_vals = [v["turnover"] for v in turnover_data.values()]
    avg_t = sum(turnover_vals) / len(turnover_vals)
    min_t = min(turnover_vals)
    max_t = max(turnover_vals)

    tk1, tk2, tk3 = st.columns(3)
    tk1.metric("Avg Turnover", f"{avg_t:.1f}x")
    tk2.metric("Min Turnover", f"{min_t:.1f}x")
    tk3.metric("Max Turnover", f"{max_t:.1f}x")

    t_rows = [
        {
            "ATC Code":      code,
            "Units Sold (yr)": v["units_sold"],
            "Avg Inventory": v["avg_inventory"],
            "Turnover (x)":  v["turnover"],
            "Class":         v["classification"],
        }
        for code, v in sorted(turnover_data.items())
    ]
    st.dataframe(
        pd.DataFrame(t_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Units Sold (yr)": st.column_config.NumberColumn("Units Sold (yr)", format="%.0f"),
            "Avg Inventory":   st.column_config.NumberColumn("Avg Inventory",   format="%.1f"),
            "Turnover (x)":    st.column_config.NumberColumn("Turnover (x)",    format="%.2f"),
        },
    )
else:
    st.info("No inventory data available. Run `scripts/ingest_kaggle.py` to populate sales.")
