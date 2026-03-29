"""
spis/dashboard/pages/2_Stock_Update.py
---------------------------------------
Page 2 — Interactive stock level editor.

Pharmacists can enter the current physical stock count for any ATC code
and submit the form. The database is updated immediately and the risk
assessment cache is cleared so the Overview page reflects new values.
"""

import streamlit as st

from spis.data.database import update_stock
from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    load_artifacts,
    run_assessment,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Stock Update — SPIS", layout="wide")
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
    "CRITICAL":  "🔴",
    "LOW":       "🟠",
    "OK":        "🟢",
    "OVERSTOCK": "🔵",
}

with st.form("stock_update_form"):
    st.subheader("Current Stock Levels")

    new_values: dict[str, float] = {}
    for atc_code in sorted(inventory.keys()):
        current = inventory[atc_code]
        ra = ra_by_atc.get(atc_code)
        badge = TIER_BADGE.get(ra.risk_tier, "") if ra else ""

        new_values[atc_code] = st.number_input(
            label=f"{badge} {atc_code}  (current: {current:.1f} units)",
            min_value=0.0,
            value=float(current),
            step=1.0,
            format="%.1f",
            key=f"stock_{atc_code}",
        )

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
            st.success(
                f"Updated {len(changed)} ATC code(s): "
                + ", ".join(f"{c} -> {v:.1f}" for c, v in changed.items())
            )
            # Clear cached assessment so Overview reflects new stock
            run_assessment.clear()
            st.rerun()
