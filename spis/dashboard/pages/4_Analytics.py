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
import streamlit as st

from spis.dashboard._shared import (
    MODELS_DIR,
    check_required_files,
    load_artifacts,
    run_assessment,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Analytics — SPIS", layout="wide")
st.title("Analytics")
st.caption("Feature importance · ABC demand analysis")

check_required_files()

# ---------------------------------------------------------------------------
# Panel 1 — Feature importance
# ---------------------------------------------------------------------------

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
    fig.update_layout(coloraxis_showscale=False, yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Panel 2 — ABC / Pareto demand analysis
# ---------------------------------------------------------------------------

st.subheader("ABC Demand Analysis")
st.caption(
    "A = top 20% of codes driving ~80% of demand  "
    "B = next 30%  "
    "C = remaining 50%"
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
    if cum_pct <= 80:
        return "A"
    if cum_pct <= 95:
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
st.plotly_chart(fig2, use_container_width=True)

st.dataframe(
    abc_df[["ATC Code", "30d Forecast", "Share %", "Cumulative %", "Class"]]
    .rename(columns={"30d Forecast": "30d Forecast (units)",
                     "Share %": "Share (%)",
                     "Cumulative %": "Cumulative (%)"}),
    use_container_width=True,
    hide_index=True,
)
