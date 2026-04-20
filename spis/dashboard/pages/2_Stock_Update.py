"""
spis/dashboard/pages/2_Stock_Update.py
---------------------------------------
Page 2 — Interactive stock level editor.

Pharmacists can enter the current physical stock count for any ATC code
and submit the form. The database is updated immediately and the risk
assessment cache is cleared so the Overview page reflects new values.
All changes are appended to data/stock_audit.csv for traceability.
"""

import csv
from datetime import datetime
from pathlib import Path

import streamlit as st

from spis.data.database import update_stock
from spis.dashboard._shared import (
    DB_PATH,
    ROOT,
    check_required_files,
    inject_css,
    load_artifacts,
    run_assessment,
)

AUDIT_LOG = ROOT / "data" / "stock_audit.csv"
_AUDIT_HEADER = ["timestamp", "atc_code", "old_stock", "new_stock", "delta"]


def _append_audit(entries: list[dict]) -> None:
    write_header = not AUDIT_LOG.exists()
    with open(AUDIT_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_AUDIT_HEADER)
        if write_header:
            writer.writeheader()
        writer.writerows(entries)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Stock Update — SPIS", layout="wide")
inject_css()
st.title("Stock Level Update")
st.caption("Enter the current physical stock count for each ATC code and click Save.")

check_required_files()

# ---------------------------------------------------------------------------
# Load current stock levels
# ---------------------------------------------------------------------------

with st.spinner("Loading inventory ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

ra_by_atc = {ra.atc_code: ra for ra in results}

# ---------------------------------------------------------------------------
# Build form with one number_input per ATC code
# ---------------------------------------------------------------------------

TIER_BADGE = {
    "CRITICAL":  "CRITICAL",
    "LOW":       "LOW",
    "OK":        "OK",
    "OVERSTOCK": "OVERSTOCK",
}

with st.form("stock_update_form"):
    st.subheader("Current Stock Levels")
    st.caption("Enter new values — the **Change** column updates after you submit.")

    col_atc, col_input, col_delta = st.columns([2, 3, 2])
    col_atc.markdown("**ATC Code**")
    col_input.markdown("**New Stock (units)**")
    col_delta.markdown("**Change**")

    new_values: dict[str, float] = {}
    for atc_code in sorted(inventory.keys()):
        current = inventory[atc_code]
        ra = ra_by_atc.get(atc_code)
        badge = TIER_BADGE.get(ra.risk_tier, "") if ra else ""

        c1, c2, c3 = st.columns([2, 3, 2])
        c1.markdown(f"**{badge}** {atc_code}")
        new_val = c2.number_input(
            label=f"stock_{atc_code}",
            label_visibility="collapsed",
            min_value=0.0,
            value=float(current),
            step=1.0,
            format="%.1f",
            key=f"stock_{atc_code}",
        )
        new_values[atc_code] = new_val
        delta = new_val - current
        if abs(delta) > 0.001:
            sign = "+" if delta > 0 else ""
            c3.markdown(f"**{sign}{delta:.1f}**")
        else:
            c3.markdown("—")

    submitted = st.form_submit_button("Save All Changes", type="primary")

# ---------------------------------------------------------------------------
# Handle submission
# ---------------------------------------------------------------------------

if submitted:
    changed = {
        code: val
        for code, val in new_values.items()
        if abs(val - inventory[code]) > 0.001
    }

    if not changed:
        st.info("No changes detected.")
    else:
        errors: list[str] = []
        for atc_code, new_stock in changed.items():
            try:
                update_stock(DB_PATH, atc_code, new_stock)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{atc_code}: {exc}")

        if errors:
            st.error("Some updates failed:\n" + "\n".join(errors))
        else:
            now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            _append_audit([
                {
                    "timestamp": now,
                    "atc_code": code,
                    "old_stock": inventory[code],
                    "new_stock": val,
                    "delta": val - inventory[code],
                }
                for code, val in changed.items()
            ])
            st.success(
                f"Updated {len(changed)} ATC code(s): "
                + ", ".join(f"{c} -> {v:.1f}" for c, v in changed.items())
            )
            run_assessment.clear()
            st.rerun()
