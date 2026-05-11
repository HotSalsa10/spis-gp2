
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from spis.data.database import add_batch, load_batches, recall_batch
from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    inject_css,
    load_atc_labels,
    run_assessment,
)

st.set_page_config(page_title="Receive Stock -- SPIS", layout="wide")
inject_css()
st.title("Receive Stock")
st.caption(
    "Register incoming shipments or recall faulty batches. "
    "Stock levels on the Overview page update within seconds."
)

check_required_files()

atc_info = load_atc_labels(str(DB_PATH))


@st.cache_data(ttl=300)
def _load_batches_cached(db_path: str) -> list[dict]:
    return load_batches(db_path)


def _next_batch_number() -> str:
    """Auto-suggest the next sequential LOT-YYYY-NNN batch number."""
    batches = _load_batches_cached(str(DB_PATH))
    prefix = f"LOT-{date.today().year}-"
    nums = []
    for b in batches:
        bn = b["batch_number"]
        if bn.startswith(prefix):
            try:
                nums.append(int(bn[len(prefix):]))
            except ValueError:
                pass
    nxt = max(nums) + 1 if nums else 1
    return f"{prefix}{nxt:03d}"


atc_options = sorted(atc_info.keys())
atc_display = {
    code: f"{code} -- {atc_info[code].get('drugs_short', code)}"
    for code in atc_options
}


# ============================================================
# Section 1 -- Receive new batch
# ============================================================

st.header("Receive New Batch")

with st.form("receive_batch_form"):
    col1, col2 = st.columns(2)

    with col1:
        selected_atc = st.selectbox(
            "ATC Code / Drug Category",
            options=atc_options,
            format_func=lambda c: atc_display[c],
        )
        batch_num = st.text_input(
            "Batch Number",
            value=_next_batch_number(),
            help="Auto-suggested from existing lots. Edit if the shipment uses a different code.",
        )
        quantity = st.number_input(
            "Quantity (units)", min_value=1.0, step=1.0, value=100.0, format="%.1f"
        )

    with col2:
        unit_cost = st.number_input(
            "Unit Cost (SAR)", min_value=0.0, step=0.01, value=1.00, format="%.2f"
        )
        default_expiry = date.today() + timedelta(days=548)  # ~18 months
        expiry_date = st.date_input("Expiry Date", value=default_expiry)
        notes = st.text_input("Notes (optional)", value="")

    receive_submitted = st.form_submit_button("Receive Batch", type="primary")

if receive_submitted:
    try:
        add_batch(
            str(DB_PATH),
            selected_atc,
            batch_num,
            quantity,
            unit_cost,
            str(expiry_date),
            notes,
        )
        _load_batches_cached.clear()
        run_assessment.clear()
        st.success(
            f"Received {quantity:.0f} units of {atc_display[selected_atc]}  "
            f"| Batch: **{batch_num}**  | Expires: {expiry_date}"
        )
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))


# ============================================================
# Section 2 -- Recent receipts (last 30 days)
# ============================================================

st.divider()
st.subheader("Recent Receipts (last 30 days)")

all_batches = _load_batches_cached(str(DB_PATH))
cutoff = str(date.today() - timedelta(days=30))
recent = [b for b in all_batches if (b.get("received_date") or "") >= cutoff]

if recent:
    rows = []
    for b in sorted(recent, key=lambda x: x.get("received_date", ""), reverse=True):
        info = atc_info.get(b["atc_code"], {})
        rows.append({
            "Received":    b["received_date"],
            "ATC Code":    b["atc_code"],
            "Medications": info.get("drugs_short", ""),
            "Batch":       b["batch_number"],
            "Qty":         round(b["quantity"], 1),
            "Unit Cost":   round(b["unit_cost"], 2),
            "Expiry":      b["expiry_date"],
            "Recalled":    bool(b["returned"]),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No batches received in the last 30 days.")


# ============================================================
# Section 3 -- Recall a Batch
# ============================================================

st.divider()
st.header("Recall a Batch")
st.caption(
    "Withdraw a faulty or contaminated lot. The batch quantity is zeroed and "
    "the aggregate stock level updates immediately. This action is logged in "
    "data/stock_audit.csv."
)

with st.form("recall_batch_form"):
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        recall_lot = st.text_input(
            "Batch Number to Recall", placeholder="e.g. LOT-2026-002"
        )
    with col_r2:
        recall_reason = st.text_input(
            "Recall Reason", placeholder="e.g. contamination detected, supplier defect"
        )
    recall_submitted = st.form_submit_button("Recall Batch", type="secondary")

if recall_submitted:
    if not recall_lot.strip():
        st.error("Batch number is required.")
    elif not recall_reason.strip():
        st.error("Recall reason is required.")
    else:
        try:
            units = recall_batch(str(DB_PATH), recall_lot.strip(), recall_reason.strip())
            _load_batches_cached.clear()
            run_assessment.clear()
            st.success(
                f"Batch **{recall_lot.strip()}** recalled. "
                f"{units:.0f} unit(s) withdrawn from inventory."
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
