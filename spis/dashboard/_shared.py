"""Shared constants, cached loaders, and CSS used by every dashboard page."""

from pathlib import Path

import streamlit as st

import sqlite3

from spis.models.forecaster import load_model
from spis.models.risk_classifier import assess_from_features, load_atc_inventory

_CSS = """
<style>
/* ── Hide Streamlit chrome ───────────────────────────────────────────── */
#MainMenu {visibility: hidden;}
footer    {visibility: hidden;}
header    {visibility: hidden;}

/* ── App background ─────────────────────────────────────────────────── */
.stApp { background-color: #0e1117; color: #e0e6f0; }
.main .block-container {
    padding-top: 1.8rem;
    padding-bottom: 2rem;
    max-width: 1280px;
}

/* ── Sidebar ─────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #161b27;
    border-right: 1px solid #1e2535;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] li {
    color: #8fa8cc !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #1e2535 !important;
}

/* ── Metric cards ────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #161b27;
    border: 1px solid #1e2d45;
    border-radius: 14px;
    padding: 1.1rem 1.3rem 1rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.75rem !important;
    color: #5a7a9a !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
[data-testid="stMetricValue"] > div {
    font-size: 2.1rem !important;
    font-weight: 800 !important;
    color: #e0e6f0 !important;
}

/* ── Section headings ────────────────────────────────────────────────── */
h1 { color: #e0e6f0 !important; font-weight: 800 !important; letter-spacing: -0.02em; }
h2 { color: #a8c0dd !important; font-weight: 700 !important; font-size: 1.3rem !important; }
h3 { color: #a8c0dd !important; font-weight: 600 !important; }
p, li, span { color: #c0cfe0; }

/* ── Captions ────────────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] p {
    color: #4e6a84 !important;
    font-size: 0.82rem !important;
}

/* ── DataFrames ──────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] > div {
    border-radius: 12px;
    border: 1px solid #1e2d45;
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(0,0,0,0.35);
}

/* ── Primary button ──────────────────────────────────────────────────── */
button[kind="primary"],
.stButton > button[kind="primary"] {
    background: #1a6fa8 !important;
    border: none !important;
    border-radius: 9px !important;
    font-weight: 600 !important;
    color: #ffffff !important;
}
button[kind="primary"]:hover {
    background: #155a8a !important;
}

/* ── Secondary button ────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 9px !important;
    font-weight: 600 !important;
    background: #161b27 !important;
    border: 1px solid #1e2d45 !important;
    color: #a8c0dd !important;
}

/* ── Alerts ──────────────────────────────────────────────────────────── */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* ── Selectbox / number input ────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input {
    background: #161b27 !important;
    border: 1px solid #1e2d45 !important;
    border-radius: 8px !important;
    color: #e0e6f0 !important;
}

/* ── Divider ─────────────────────────────────────────────────────────── */
hr { border-color: #1e2535 !important; margin: 1.4rem 0 !important; }

/* ── Spinner ─────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div { color: #1a6fa8 !important; }

/* ── App subtitle ────────────────────────────────────────────────────── */
.spis-subtitle { color: #647a90; font-size: 0.85rem; margin: 0; }

/* ── KPI Cards ───────────────────────────────────────────────────────── */
.kpi-card {
    background: #161b27;
    border: 1px solid #1e2d45;
    border-radius: 14px;
    padding: 1.3rem 1.5rem 1.2rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
}
.kpi-critical::before  { background: #ef233c; }
.kpi-low::before       { background: #f77f00; }
.kpi-ok::before        { background: #2dc653; }
.kpi-overstock::before { background: #4361ee; }
.kpi-label {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #5a7a9a;
    margin-bottom: 0.5rem;
}
.kpi-value {
    font-size: 2.8rem;
    font-weight: 900;
    line-height: 1;
    margin-bottom: 0.45rem;
}
.kpi-critical  .kpi-value { color: #ef233c; }
.kpi-low       .kpi-value { color: #f77f00; }
.kpi-ok        .kpi-value { color: #2dc653; }
.kpi-overstock .kpi-value { color: #4361ee; }
.kpi-hint { font-size: 0.74rem; color: #4e6a84; }

/* ── Critical alert banner ───────────────────────────────────────────── */
.alert-critical {
    background: rgba(239,35,60,0.10);
    border: 1px solid rgba(239,35,60,0.35);
    border-left: 4px solid #ef233c;
    border-radius: 10px;
    padding: 0.9rem 1.2rem;
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 1.2rem;
}
.alert-dot {
    width: 26px; height: 26px;
    background: #ef233c;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 900; font-size: 0.9rem; color: #fff;
    flex-shrink: 0; line-height: 26px; text-align: center;
}
.alert-title { font-weight: 700; color: #ef233c; margin-bottom: 0.2rem; font-size: 0.95rem; }
.alert-body  { color: #c0cfe0; font-size: 0.85rem; }

/* ── Form container ──────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: #161b27;
    border: 1px solid #1e2d45 !important;
    border-radius: 14px;
    padding: 1.2rem 1.5rem !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.35);
}
</style>
"""


def inject_css() -> None:
    """Call once after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


ROOT         = Path(__file__).resolve().parent.parent.parent
MODELS_DIR   = ROOT / "models"
DB_PATH      = ROOT / "data" / "inventory.db"
FEATURES_CSV = ROOT / "data" / "processed" / "features_daily.csv"

REQUIRED_FILES = [
    MODELS_DIR / "xgboost_forecaster.joblib",
    MODELS_DIR / "label_encoder.joblib",
    DB_PATH,
    FEATURES_CSV,
]


@st.cache_resource
def load_artifacts():
    """Loaded once per process."""
    model, encoder = load_model(MODELS_DIR)
    inventory = load_atc_inventory(DB_PATH)
    return model, encoder, inventory


@st.cache_data(ttl=300)
def run_assessment(_model, _encoder, _inventory):
    """Re-runs every 5 min (or when cache is cleared)."""
    return assess_from_features(
        features_csv=FEATURES_CSV,
        inventory=_inventory,
        model=_model,
        encoder=_encoder,
    )


@st.cache_data
def load_atc_names(db_path: str) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT atc_code, atc_name FROM atc_categories"
        ).fetchall()
    return {code: name for code, name in rows}


@st.cache_data
def load_drugs(db_path: str) -> "pd.DataFrame":
    import pandas as pd
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT drug_name, atc_code, unit FROM drugs ORDER BY atc_code, drug_name",
            conn,
        )


@st.cache_data
def load_atc_labels(db_path: str) -> dict:
    """atc_code -> {category, drugs_short, drugs_full}."""
    with sqlite3.connect(db_path) as conn:
        cats = conn.execute(
            "SELECT atc_code, atc_name FROM atc_categories"
        ).fetchall()
        drug_rows = conn.execute(
            "SELECT atc_code, drug_name FROM drugs ORDER BY atc_code, drug_name"
        ).fetchall()

    drug_map: dict = {}
    for code, name in drug_rows:
        drug_map.setdefault(code, []).append(name)

    result = {}
    for code, cat_name in cats:
        names = drug_map.get(code, [])
        result[code] = {
            "category":    cat_name,
            "drugs_short": " / ".join(names[:3]),
            "drugs_full":  ", ".join(names),
        }
    return result


def check_required_files() -> bool:
    """Stop the page if model/db/features are missing."""
    missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
    if missing:
        st.error(
            "Missing files — run the pipeline and train the model first:\n\n"
            + "\n".join(f"- `{p}`" for p in missing)
        )
        st.stop()
    return True
