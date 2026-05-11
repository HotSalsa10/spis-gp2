
import streamlit as st

from spis.data.database import acknowledge_alert, get_all_alerts, load_batches
from spis.dashboard._shared import (
    DB_PATH,
    check_required_files,
    inject_css,
    load_artifacts,
    load_atc_labels,
    run_assessment,
)
from spis.models.alert_engine import refresh
from spis.models.expiry_advisor import assess_all_batches


st.set_page_config(page_title="Alerts -- SPIS", layout="wide")
inject_css()
st.title("Notification Center")
st.caption(
    "Alerts are generated automatically from low-stock risk tiers and expiry "
    "assessments. Acknowledge an alert once actioned to remove it from the open count."
)

check_required_files()


with st.spinner("Checking system state ..."):
    model, encoder, inventory = load_artifacts()
    results = run_assessment(model, encoder, inventory)

demand_by_atc = {ra.atc_code: ra.daily_demand for ra in results}

batches = load_batches(str(DB_PATH))
offers = assess_all_batches(batches, demand_by_atc)

new_count = refresh(str(DB_PATH), results, offers)
if new_count:
    st.toast(f"{new_count} new alert(s) generated.")


all_alerts = get_all_alerts(str(DB_PATH))

open_alerts   = [a for a in all_alerts if a["acknowledged_at"] is None]
critical_count = sum(1 for a in open_alerts if a["severity"] == "CRITICAL")
warning_count  = sum(1 for a in open_alerts if a["severity"] == "WARNING")


c1, c2, c3 = st.columns(3)
c1.metric("Open Alerts", len(open_alerts))
c2.metric("Critical", critical_count)
c3.metric("Warnings", warning_count)

st.divider()


with st.sidebar:
    st.header("Filters")
    show_acked = st.toggle("Show acknowledged", value=False)
    sel_severity = st.multiselect(
        "Severity",
        options=["CRITICAL", "WARNING", "INFO"],
        default=["CRITICAL", "WARNING", "INFO"],
    )
    sel_type = st.multiselect(
        "Alert type",
        options=["LOW_STOCK", "EXPIRY", "RECALL"],
        default=["LOW_STOCK", "EXPIRY", "RECALL"],
    )


filtered = list(all_alerts)
if not show_acked:
    filtered = [a for a in filtered if a["acknowledged_at"] is None]
if sel_severity:
    filtered = [a for a in filtered if a["severity"] in sel_severity]
if sel_type:
    filtered = [a for a in filtered if a["alert_type"] in sel_type]

filtered = sorted(filtered, key=lambda a: a["created_at"], reverse=True)


_BADGE_STYLE = {
    "CRITICAL": (
        "background:#ef233c;color:#fff;padding:2px 10px;"
        "border-radius:6px;font-size:0.72rem;font-weight:700;"
    ),
    "WARNING": (
        "background:#f77f00;color:#fff;padding:2px 10px;"
        "border-radius:6px;font-size:0.72rem;font-weight:700;"
    ),
    "INFO": (
        "background:#4361ee;color:#fff;padding:2px 10px;"
        "border-radius:6px;font-size:0.72rem;font-weight:700;"
    ),
}

_TYPE_LABEL = {
    "LOW_STOCK": "LOW STOCK",
    "EXPIRY":    "EXPIRY",
    "RECALL":    "RECALL",
}


def _badge(severity: str) -> str:
    style = _BADGE_STYLE.get(severity, "")
    return f'<span style="{style}">{severity}</span>'


if not filtered:
    st.info("No alerts matching the current filters.")
else:
    st.subheader(f"Alerts ({len(filtered)} shown)")

    for alert in filtered:
        alert_id   = alert["alert_id"]
        acked      = alert["acknowledged_at"] is not None
        type_label = _TYPE_LABEL.get(alert["alert_type"], alert["alert_type"])
        created_ts = alert["created_at"][:16].replace("T", "  ")

        col_info, col_btn = st.columns([9, 1])

        with col_info:
            st.markdown(
                f"{_badge(alert['severity'])}"
                f"&nbsp; <strong style='color:#a8c0dd'>{type_label}</strong>"
                f"&nbsp; <span style='color:#4e6a84;font-size:0.8rem'>{created_ts}</span>",
                unsafe_allow_html=True,
            )
            msg_color = "#6b7a8a" if acked else "#c0cfe0"
            st.markdown(
                f"<p style='margin:0.2rem 0 0.5rem 0;color:{msg_color}'>"
                f"{alert['message']}</p>",
                unsafe_allow_html=True,
            )
            if acked:
                ack_ts = alert["acknowledged_at"][:16].replace("T", "  ")
                st.caption(f"Acknowledged: {ack_ts}")

        with col_btn:
            if not acked:
                if st.button("Ack", key=f"ack_{alert_id}", help="Mark as actioned"):
                    acknowledge_alert(str(DB_PATH), alert_id)
                    st.rerun()
            else:
                st.markdown(
                    "<span style='color:#2dc653;font-size:0.8rem'>Done</span>",
                    unsafe_allow_html=True,
                )

        st.divider()
