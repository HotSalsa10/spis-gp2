"""Page 7: browse ATC + add drugs/ATC/suppliers + assign ATC->supplier."""

import streamlit as st
import pandas as pd
from pathlib import Path

from spis.dashboard._shared import DB_PATH, inject_css
from spis.data.catalog import add_atc_code, add_drug, list_atc_codes
from spis.data.database import (
    add_supplier,
    assign_supplier_to_atc,
    load_suppliers,
)

st.set_page_config(page_title="Manage Catalog", layout="wide")
inject_css()

st.title("Manage Catalog")
st.caption("Add drugs and ATC categories without touching code.")

if not DB_PATH.exists():
    st.error(
        "Database not found. Run `python scripts/ingest_kaggle.py` or "
        "`python scripts/ingest_data.py` to initialise it."
    )
    st.stop()


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

st.divider()


st.subheader("Suppliers")
st.caption(
    "Distributors and manufacturers that fulfil purchase orders. "
    "Each ATC code is routed to one primary supplier (see Section E)."
)


@st.cache_data(ttl=30)
def _load_suppliers_cached(db: str) -> pd.DataFrame:
    rows = load_suppliers(db)
    if not rows:
        return pd.DataFrame(
            columns=["supplier_id", "name", "email", "phone", "lead_time_days", "notes"]
        )
    return pd.DataFrame(rows)


suppliers_df = _load_suppliers_cached(str(DB_PATH))
if suppliers_df.empty:
    st.info("No suppliers registered yet -- add one below.")
else:
    st.dataframe(
        suppliers_df.rename(columns={
            "supplier_id":    "ID",
            "name":           "Supplier",
            "email":          "Email",
            "phone":          "Phone",
            "lead_time_days": "Lead Time (days)",
            "notes":          "Notes",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("**Add Supplier**")

with st.form("add_supplier_form", clear_on_submit=True):
    sup_name  = st.text_input("Supplier Name",   placeholder="e.g. Tamer Group")
    sup_email = st.text_input("Contact Email",   placeholder="e.g. info@tamergroup.com")
    sup_phone = st.text_input("Contact Phone",   placeholder="e.g. +966 12 000 0001")
    sup_lead  = st.number_input(
        "Lead Time (days)", min_value=0, max_value=60, value=7, step=1,
    )
    sup_notes = st.text_input("Notes (optional)", placeholder="Speciality or any free text")
    submitted_sup = st.form_submit_button("Add Supplier")

if submitted_sup:
    if not sup_name.strip():
        st.error("Supplier name cannot be empty.")
    else:
        try:
            new_id = add_supplier(
                DB_PATH,
                name=sup_name.strip(),
                email=sup_email.strip(),
                phone=sup_phone.strip(),
                lead_time_days=int(sup_lead),
                notes=sup_notes.strip(),
            )
            _load_suppliers_cached.clear()
            st.success(f"Supplier '{sup_name.strip()}' added (ID {new_id}).")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

st.divider()


st.subheader("Assign ATC Code to Supplier")
st.caption(
    "Choose which supplier should receive purchase orders for each ATC code. "
    "Changes take effect on the next render of the Purchase Orders page."
)

suppliers_for_assign = load_suppliers(str(DB_PATH))
atc_for_assign = atc_df["atc_code"].tolist() if not atc_df.empty else []

if not suppliers_for_assign or not atc_for_assign:
    st.info("Register at least one supplier and one ATC code before assigning.")
else:
    with st.form("assign_supplier_form", clear_on_submit=False):
        sel_atc = st.selectbox("ATC Code", options=atc_for_assign, key="assign_atc")
        sup_options = {s["supplier_id"]: s["name"] for s in suppliers_for_assign}
        sel_sup_id = st.selectbox(
            "Supplier",
            options=list(sup_options.keys()),
            format_func=lambda sid: f"{sup_options[sid]} (ID {sid})",
            key="assign_sup",
        )
        submitted_assign = st.form_submit_button("Assign")

    if submitted_assign:
        try:
            assign_supplier_to_atc(DB_PATH, sel_atc, sel_sup_id)
            _load_atc.clear()
            st.success(
                f"{sel_atc} is now routed to '{sup_options[sel_sup_id]}'."
            )
        except ValueError as exc:
            st.error(str(exc))
