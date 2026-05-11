
import csv
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from spis.data.database import update_stock
from spis.dashboard._shared import (
    DB_PATH,
    ROOT,
    check_required_files,
    inject_css,
    load_artifacts,
    load_atc_labels,
    run_assessment,
)

AUDIT_LOG = ROOT / "data" / "stock_audit.csv"
_AUDIT_HEADER = ["timestamp", "atc_code", "action", "batch_number", "old_stock", "new_stock", "delta"]


def _append_audit(entries: list[dict]) -> None:
    write_header = not AUDIT_LOG.exists()
    with open(AUDIT_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_AUDIT_HEADER)
        if write_header:
            writer.writeheader()
        writer.writerows(entries)


st.set_page_config(page_title="Stock Update — SPIS", layout="wide")
inject_css()
st.title("Stock Level Update")
st.caption("Enter the current physical stock count for each ATC code and click Save.")

check_required_files()


with st.spinner("Loading inventory ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

ra_by_atc  = {ra.atc_code: ra for ra in results}
atc_labels = load_atc_labels(str(DB_PATH))


TIER_BADGE = {
    "CRITICAL":  "CRITICAL",
    "LOW":       "LOW",
    "OK":        "OK",
    "OVERSTOCK": "OVERSTOCK",
}

with st.form("stock_update_form"):
    st.subheader("Current Stock Levels")
    st.caption("Enter new values — the **Change** column updates after you submit.")

    col_atc, col_input, col_prev = st.columns([2, 3, 2])
    col_atc.markdown("**ATC Code**")
    col_input.markdown("**New Stock (units)**")
    col_prev.markdown("**Previous**")

    new_values: dict[str, float] = {}
    for atc_code in sorted(inventory.keys()):
        current = inventory[atc_code]
        ra = ra_by_atc.get(atc_code)
        badge = TIER_BADGE.get(ra.risk_tier, "") if ra else ""

        label_info  = atc_labels.get(atc_code, {})
        drugs_short = label_info.get("drugs_short", atc_code)
        category    = label_info.get("category", "")

        c1, c2, c3 = st.columns([2, 3, 2])
        c1.markdown(
            "**{badge}** {drugs}  \n"
            "<small style='color:#5a7a9a'>{code} - {cat}</small>".format(
                badge=badge, drugs=drugs_short, code=atc_code, cat=category,
            ),
            unsafe_allow_html=True,
        )
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
        c3.markdown(f"{current:.1f}")

    submitted = st.form_submit_button("Save All Changes", type="primary")


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
                inventory[atc_code] = new_stock  # keep in-memory dict in sync
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{atc_code}: {exc}")

        if errors:
            st.error("Some updates failed:\n" + "\n".join(errors))
        else:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _append_audit([
                {
                    "timestamp":    now,
                    "atc_code":     code,
                    "action":       "MANUAL",
                    "batch_number": "",
                    "old_stock":    inventory[code],
                    "new_stock":    val,
                    "delta":        val - inventory[code],
                }
                for code, val in changed.items()
            ])
            st.success(
                f"Updated {len(changed)} ATC code(s): "
                + ", ".join(f"{c} -> {v:.1f}" for c, v in changed.items())
            )
            run_assessment.clear()
            st.rerun()
