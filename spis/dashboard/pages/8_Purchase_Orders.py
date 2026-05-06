"""
spis/dashboard/pages/8_Purchase_Orders.py
------------------------------------------
Page 8 -- Purchase Orders.

Generates suggested purchase orders from the current risk assessment,
grouped by supplier.  Each PO can be downloaded as a PDF or marked as
sent (stored to purchase_orders history table).
"""

import json

import pandas as pd
import streamlit as st

from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    inject_css,
    load_artifacts,
    run_assessment,
)
from spis.data.database import load_purchase_orders, save_purchase_order
from spis.models.po_generator import build_all_pos, generate_po_pdf

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Purchase Orders -- SPIS", layout="wide")
inject_css()
st.title("Purchase Orders")
st.caption(
    "Suggested orders are derived from the current risk assessment.  "
    "CRITICAL and LOW stock ATC codes are grouped by supplier.  "
    "Download a PDF to send to the supplier or mark the order as sent."
)

check_required_files()

# ---------------------------------------------------------------------------
# Load risk assessment
# ---------------------------------------------------------------------------

with st.spinner("Running risk assessment ..."):
    model, encoder, inventory = load_artifacts()
    assessments = run_assessment(model, encoder, inventory)

pos = build_all_pos(str(DB_PATH), assessments)

# ---------------------------------------------------------------------------
# Summary strip
# ---------------------------------------------------------------------------

total_suppliers = len(pos)
total_lines     = sum(len(p["lines"]) for p in pos)
total_value     = sum(p["grand_total"] for p in pos)

m1, m2, m3 = st.columns(3)
m1.metric("Suppliers to Order From", total_suppliers)
m2.metric("Total Line Items",         total_lines)
m3.metric("Estimated Total (SAR)",    f"{total_value:,.2f}")

st.divider()

# ---------------------------------------------------------------------------
# Per-supplier PO expanders
# ---------------------------------------------------------------------------

if not pos:
    st.info(
        "No purchase orders required at this time.  "
        "All ATC codes are either OK or OVERSTOCK."
    )
else:
    st.subheader("Suggested Purchase Orders")

    for idx, po in enumerate(pos):
        supplier    = po["supplier"]
        s_name      = supplier["name"]
        grand_total = po["grand_total"]
        n_lines     = len(po["lines"])

        label = (
            f"{s_name}  --  {n_lines} item(s)  --  "
            f"SAR {grand_total:,.2f}  --  "
            f"Lead time: {supplier.get('lead_time_days', 7)} days"
        )

        with st.expander(label, expanded=(idx == 0)):
            # ── Supplier details ─────────────────────────────────────────
            col_s, col_b = st.columns([3, 1])

            with col_s:
                st.markdown(
                    f"**Supplier:** {s_name}  \n"
                    f"**Email:** {supplier.get('email') or 'N/A'}  \n"
                    f"**Phone:** {supplier.get('phone') or 'N/A'}  \n"
                    f"**Lead time:** {supplier.get('lead_time_days', 7)} days  \n"
                    f"**PO date:** {po['po_date']}"
                )

            # ── Line items table ─────────────────────────────────────────
            rows = []
            for line in po["lines"]:
                names_str = ", ".join(line["drug_names"][:3])
                if len(line["drug_names"]) > 3:
                    names_str += f" (+{len(line['drug_names']) - 3} more)"
                rows.append({
                    "ATC Code":    line["atc_code"],
                    "Category":    line["atc_name"],
                    "Drug Names":  names_str,
                    "Risk":        line["risk_tier"],
                    "Qty":         int(line["qty"]),
                    "Unit (SAR)":  f"{line['unit_cost']:.2f}",
                    "Total (SAR)": f"{line['total_cost']:.2f}",
                })

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )
            st.markdown(
                f"<div style='text-align:right;color:#a8c0dd;font-weight:700'>"
                f"Grand Total: SAR {grand_total:,.2f}</div>",
                unsafe_allow_html=True,
            )

            st.markdown("")

            # ── Action buttons ───────────────────────────────────────────
            btn_dl, btn_send, _ = st.columns([2, 2, 5])

            pdf_bytes = generate_po_pdf(po)
            filename  = f"PO_{s_name.replace(' ', '_')}_{po['po_date']}.pdf"

            with btn_dl:
                st.download_button(
                    label="Download PDF",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    key=f"dl_{idx}",
                )

            with btn_send:
                if st.button("Mark as Sent", key=f"sent_{idx}"):
                    lines_json = json.dumps(po["lines"])
                    save_purchase_order(
                        db_path=str(DB_PATH),
                        supplier_id=supplier.get("supplier_id") or 0,
                        supplier_name=s_name,
                        lines_json=lines_json,
                        total_cost=grand_total,
                    )
                    st.success(f"PO for {s_name} recorded as sent.")

# ---------------------------------------------------------------------------
# PO History
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Order History")

history = load_purchase_orders(str(DB_PATH))

if not history:
    st.caption("No purchase orders have been sent yet.")
else:
    hist_rows = []
    for h in history:
        hist_rows.append({
            "PO #":          h["po_id"],
            "Supplier":      h["supplier_name"],
            "Date":          h["created_at"][:10],
            "Status":        h["status"],
            "Total (SAR)":   f"{h['total_cost']:,.2f}",
        })
    st.dataframe(
        pd.DataFrame(hist_rows),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"{len(history)} order(s) on record.")
