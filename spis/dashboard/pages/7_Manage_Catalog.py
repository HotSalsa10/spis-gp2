"""
spis/dashboard/pages/7_Manage_Catalog.py
-----------------------------------------
Manage Catalog page: browse ATC categories and add drugs or ATC codes.

Section A — read-only ATC overview table with drug counts.
Section B — form to add a new drug to an existing ATC category.
Section C — form to register a brand-new ATC code (with retraining warning).
"""

import streamlit as st
import pandas as pd
from pathlib import Path

from spis.dashboard._shared import DB_PATH, inject_css
from spis.data.catalog import add_atc_code, add_drug, list_atc_codes

st.set_page_config(page_title="Manage Catalog", layout="wide")
inject_css()

st.title("Manage Catalog")
st.caption("Add drugs and ATC categories without touching code.")

# ---------------------------------------------------------------------------
# Guard: DB must exist (no model artifacts required for this page)
# ---------------------------------------------------------------------------
if not DB_PATH.exists():
    st.error(
        "Database not found. Run `python scripts/ingest_kaggle.py` or "
        "`python scripts/ingest_data.py` to initialise it."
    )
    st.stop()


# ---------------------------------------------------------------------------
# Section A -- ATC categories overview
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _load_atc(db: str) -> pd.DataFrame:
    rows = list_atc_codes(Path(db))
    return pd.DataFrame(
        rows,
        columns=["atc_code", "atc_name", "system_name", "drug_count", "current_stock"],
    )


st.subheader("ATC Categories")

atc_df = _load_atc(str(DB_PATH))
if atc_df.empty:
    st.info("No ATC categories registered yet.")
else:
    st.dataframe(
        atc_df.rename(columns={
            "atc_code":      "ATC Code",
            "atc_name":      "Category Name",
            "system_name":   "Body System",
            "drug_count":    "Drugs",
            "current_stock": "Stock (units)",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ---------------------------------------------------------------------------
# Section B -- Add Drug
# ---------------------------------------------------------------------------

st.subheader("Add Drug")

atc_options = atc_df["atc_code"].tolist() if not atc_df.empty else []

if not atc_options:
    st.info("No ATC categories available. Register an ATC code first (Section C below).")
else:
    with st.form("add_drug_form", clear_on_submit=True):
        drug_name = st.text_input("Drug Name", placeholder="e.g. Naproxen 500")
        atc_sel   = st.selectbox("ATC Category", options=atc_options)
        unit      = st.selectbox(
            "Unit",
            options=["tablets", "capsules", "inhaler", "vials", "sachets", "spray", "other"],
        )
        is_crit = st.checkbox(
            "Mark as Critical",
            help="Check if a stockout poses direct clinical risk (e.g. controlled substances, bronchodilators).",
        )
        submitted_drug = st.form_submit_button("Add Drug")

    if submitted_drug:
        if not drug_name.strip():
            st.error("Drug name cannot be empty.")
        else:
            try:
                add_drug(DB_PATH, drug_name.strip(), atc_sel, unit=unit, is_critical=int(is_crit))
                _load_atc.clear()
                st.success(f"'{drug_name.strip()}' added under {atc_sel}.")
            except ValueError as exc:
                st.error(str(exc))

st.divider()

# ---------------------------------------------------------------------------
# Section C -- Add ATC Code
# ---------------------------------------------------------------------------

st.subheader("Add ATC Code")
st.warning(
    "After registering, upload sales history (`scripts/ingest_data.py`) "
    "and retrain (`scripts/train_model.py`). "
    "The forecaster cannot predict for new ATC codes until both steps are complete."
)

with st.form("add_atc_form", clear_on_submit=True):
    new_code   = st.text_input("ATC Code", placeholder="e.g. A10BA")
    new_name   = st.text_input("Category Name", placeholder="e.g. Biguanides")
    new_system = st.text_input(
        "Body System (optional)",
        placeholder="e.g. Alimentary tract and metabolism",
    )
    new_stock  = st.number_input(
        "Initial Stock (units)", min_value=0.0, value=0.0, step=1.0,
    )
    submitted_atc = st.form_submit_button("Register ATC Code")

if submitted_atc:
    if not new_code.strip():
        st.error("ATC code cannot be empty.")
    elif not new_name.strip():
        st.error("Category name cannot be empty.")
    else:
        try:
            inserted = add_atc_code(
                DB_PATH,
                code=new_code.strip(),
                name=new_name.strip(),
                system=new_system.strip(),
                initial_stock=new_stock,
            )
            _load_atc.clear()
            if inserted:
                st.success(
                    f"ATC code '{new_code.strip().upper()}' registered. "
                    "Remember to ingest sales data and retrain the model."
                )
            else:
                st.info(
                    f"'{new_code.strip().upper()}' is already registered. No changes made."
                )
        except ValueError as exc:
            st.error(str(exc))
