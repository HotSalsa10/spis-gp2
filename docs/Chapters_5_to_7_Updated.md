# Chapters 5 – 7 (Updated)

_Smart Pharmacy Inventory System (SPIS) — Graduation Project 2_
_Revision date: 2026-05-11_

This document replaces the previous drafts of Chapters 5, 6, and 7. The content
was verified against the source tree at HEAD: every code snippet, tier
threshold, schema description, and test count below was read directly out of
the repository rather than carried over from the older drafts. Stale numbers,
plan-only features, and outdated tier logic from earlier revisions have been
removed.

---

# Chapter 5: Implementation

## 5.1 Development Environment

SPIS is built and run under Windows 11 in a Python 3.11.9 virtual environment.
Python 3.11 was chosen deliberately because `scispacy 0.6.x` is not yet
compatible with Python 3.14 (which is installed on the same machine). Cross-team
reproducibility is provided by:

- `requirements.txt` with `>=` pins on every dependency
- A single SQLite database file (`data/inventory.db`) so no external DB engine is
  required
- All artifacts (model, encoder, processed CSVs) rebuildable from `scripts/`

Key dependencies (resolved versions used during defense):

| Package | Version | Role |
|--------|--------|------|
| `pandas` | 2.3.3 | Tabular data, feature engineering |
| `numpy` | 1.26.4 | Numerical ops |
| `scikit-learn` | 1.8.0 | `LabelEncoder`, `TimeSeriesSplit`, `GridSearchCV` |
| `xgboost` | 3.2.0 | Demand forecasting model |
| `statsmodels` | latest | `seasonal_decompose` on the Analytics page |
| `holidays` | 0.35 | Public-holiday calendars |
| `joblib` | 1.3.2 | Model serialisation |
| `flask` | 3.1.3 | REST API |
| `streamlit` | 1.54.0 | Multi-page dashboard |
| `plotly` | 5.x | Interactive charts (Plotly Express + graph_objects) |
| `fpdf2` | 2.7+ | PDF generation for purchase orders and committee handout |
| `pytest` | 9.0.2 | Test runner |

The virtual environment is activated with `.\venv\Scripts\activate`
(PowerShell) or `source venv/Scripts/activate` (bash). VS Code is the team's
editor.

## 5.2 Repository Layout

The repository is one Python package (`spis/`) plus thin launcher scripts. Each
domain (data, models, API, dashboard) is its own subpackage so imports stay
explicit and unit tests can target a single concern.

```
spis-gp2/
  spis/
    data/        catalog.py  database.py  pipeline.py
    models/      forecaster.py  risk_classifier.py  expiry_advisor.py
                 expiry_finance.py  alert_engine.py  decomposition.py
                 inventory_kpi.py  po_generator.py
    api/         app.py  routes.py
    dashboard/   app.py  _shared.py  pages/1..8_*.py
  scripts/       ingest_kaggle.py  ingest_data.py  register_atc.py
                 run_pipeline.py   train_model.py  assess_risk.py
                 run_api.py        run_dashboard.py
                 export_committee_pdf.py  run_public.py
  data/          inventory.db (git-ignored, rebuilt by scripts/ingest_kaggle.py)
                 stock_audit.csv (local audit log, written by add_batch/recall_batch/Page 2)
                 processed/   features_daily.csv  train.csv  test.csv (git-ignored)
  models/        xgboost_forecaster.joblib  label_encoder.joblib
                 metrics.json  feature_importance.json (git-ignored)
  tests/         14 test_*.py files
  docs/          chapter1..7 + this file
```

## 5.3 Data Layer

### 5.3.1 SQLite Schema

`spis/data/database.py` owns the schema. `init_db()` is idempotent and is
called by every CLI before reads, so a fresh checkout can be brought to a
runnable state with a single command. The schema is **eight tables**:

| Table | Purpose |
|-------|---------|
| `atc_categories` | ATC-4 classification reference. Carries `level1_code` and `level2_code` and (after migration) a nullable `supplier_id` FK. |
| `drugs` | Per-SKU catalog: `drug_name` (unique), `atc_code`, `unit`, `is_critical`. 57 drugs seeded across 8 categories. |
| `sales` | Time-series fact table: `atc_code`, `sale_date`, `hour`, `granularity`, `quantity`. Indexed on `(atc_code, sale_date)` and on `granularity`. |
| `atc_inventory` | One row per ATC code: `current_stock`, `last_updated`. The single source of truth for the risk assessor. |
| `inventory_batches` | Per-batch stock with `batch_number`, `quantity`, `unit_cost`, `expiry_date`, `received_date`, plus `applied_discount` and `returned` (added by Phase 9 migration). |
| `alerts` | Notification log: `alert_type` (LOW_STOCK / EXPIRY / RECALL), severity, atc_code, batch_number, `created_at`, `acknowledged_at`. |
| `suppliers` | Directory of distributors with `lead_time_days`. Seeded with four real Saudi-market suppliers — Tamer Group (est. 1922), Banaja Holdings (est. 1948), Cigalah Group, and Jamjoom Pharma (est. 1988) — each routed to the ATC codes that match its known specialty. Contact-detail fields (`email`, `phone`) carry clearly-placeholder values in the seed and are intended to be overridden via the Manage Catalog page before any live order is placed. |
| `purchase_orders` | Sent-PO history: supplier, `total_cost`, `lines_json`, `status`. |

`_migrate_schema()` runs inside `init_db()` and adds the late-Phase columns
(`applied_discount`, `returned`, `atc_categories.supplier_id`) when they are
missing, so older databases keep working after pulling Phase 9.

Two append-only audit trails sit alongside the database. `data/stock_audit.csv`
captures every stock movement (manual edits, batch receipts, recalls) with
`timestamp / atc_code / action / batch_number / old_stock / new_stock / delta`.
The CSV is the only place a non-SQL viewer can read the change history, which
is intentionally separate from the live tables.

### 5.3.2 Database Public Helpers

`database.py` exposes a small, opinionated public surface so neither the
dashboard nor the API needs to write SQL directly:

| Function | Action |
|----------|--------|
| `init_db(path)` | Create / migrate the schema, seed reference data. Idempotent. |
| `update_stock(path, atc, qty)` | Set `atc_inventory.current_stock`; raises on negative input. |
| `load_batches(path)` | Return all batches as dicts (ordered by `expiry_date`). |
| `add_batch(...)` | Insert a new lot, increment `atc_inventory.current_stock`, append a `RECEIVE` row to `stock_audit.csv`. |
| `recall_batch(path, lot, reason)` | Zero a batch's quantity, set `returned=1`, decrement aggregate stock, append a `RECALL` row to the audit log. |
| `save_batch_overrides(path, [{batch_id, applied_discount, returned}])` | Persist pharmacist overrides set in the Expiry Offers data editor. |
| `create_alert / alert_key_exists / acknowledge_alert / get_open_alerts / get_all_alerts` | Alert lifecycle, used by the notification engine. |
| `load_suppliers / add_supplier / assign_supplier_to_atc` | Supplier directory CRUD: list, insert (auto-assigned `supplier_id`, rejects empty / duplicate names and negative lead times), and re-route an ATC code to a different supplier. |
| `save_purchase_order / load_purchase_orders` | PO history persistence. |
| `add_atc_code / add_drug / list_atc_codes / list_drugs` (in `catalog.py`) | Shared between the CLI (`scripts/register_atc.py`) and the Manage Catalog page. |

### 5.3.3 Ingestion Paths

Two paths exist for getting sales data into the database:

1. **`scripts/ingest_kaggle.py`** — bootstrap path. Loads the Kaggle pharmacy
   dataset (four granularities), rebuilds the `sales` fact table, and ensures
   the 8 reference ATC codes are seeded.
2. **`scripts/ingest_data.py`** — pharmacy-agnostic path. Accepts any
   long-format CSV (`date, atc_code, quantity`), normalises columns to
   uppercase / ISO date, clips negatives to zero, aggregates duplicates per
   `(atc_code, date)`, and with `--register` inserts any unseen ATC code into
   `atc_categories` + `atc_inventory`.

```python
# spis/data/pipeline.py — validate()
df["quantity"] = df["quantity"].clip(lower=0)       # negatives become 0
df = df.groupby(["atc_code", "date"], as_index=False)["quantity"].sum()  # dedup
```

## 5.4 Modelling Layer

### 5.4.1 Feature Engineering

`spis/data/pipeline.py::engineer_features()` derives **35 time-series features**
per `(atc_code, date)` row. Lag, rolling, and EMA features are computed
group-wise (`grouped = df.groupby("atc_code")["quantity"]`) so no future
information leaks across ATC codes.

- **12 calendar features**: `day_of_week`, `day_of_month`, `month`, `year`,
  `week_of_year`, `is_weekend`, `is_holiday` (Turkish — the training data is
  the Kaggle Turkish-pharmacy dataset), `season` (1 = Winter … 4 = Fall),
  `is_payday_window` (days 1–3 and 15–17), `is_school_holiday` (Turkish MEB
  calendar), `quarter`, `days_to_month_end`.
- **7 lag features**: `lag_{1, 2, 3, 7, 14, 28, 365}`.
- **12 rolling / EMA features**: `rolling_mean_{7,14,28,90,365}`,
  `rolling_std_{7,28}`, `rolling_{min,max}_7`, `ema_{7,14,28}`.
- **4 derived features**: `lag_ratio_7` (= `lag_1` / `rolling_mean_7`),
  `trend_counter` (days since dataset start), `rolling_range_7`,
  `ema_ratio` (= `ema_7` / `ema_28`).

After the ATC code is encoded with `LabelEncoder` into `atc_encoded`, the
model input matrix is **36 columns** (35 + 1). The `FEATURE_COLS` list in
`spis/models/forecaster.py` is the single source of truth for ordering — both
the pipeline outputs and the live forecaster use the same list.

### 5.4.2 XGBoost Forecaster

`spis/models/forecaster.py` trains a single `XGBRegressor` for all 8 ATC codes
(the `atc_encoded` feature lets one model learn category-specific behaviour
while sharing calendar/lag signal). `train_and_evaluate()` runs `GridSearchCV`
with `TimeSeriesSplit(n_splits=5)` so cross-validation never sees future data.

```python
# spis/models/forecaster.py — actual production grid
param_grid = {
    "n_estimators":     [500, 800],
    "max_depth":        [6, 8],
    "learning_rate":    [0.03, 0.05],
    "subsample":        [0.8, 1.0],
    "colsample_bytree": [0.8, 1.0],
    "min_child_weight": [1, 5],
    "reg_alpha":        [0, 0.1],
}
```

NaN-bearing rows (the first year of history per ATC, where `lag_365` is null)
are **dropped** before training rather than zero-filled — zero-filling would
teach the model that "no recorded sales" looks identical to an actual zero-sales
day. The held-out test set (cutoff 2019-01-01) reports MAE ≈ 1.06, RMSE ≈ 2.29,
soundly beating the naive (`lag_1`) and moving-average (`rolling_mean_7`)
baselines.

Three artifacts are written to `models/`: `xgboost_forecaster.joblib`,
`label_encoder.joblib`, `metrics.json`, and `feature_importance.json`. The
Analytics dashboard page reads both JSON files directly so the team never has
to rebuild charts after a retrain.

### 5.4.3 30-Day Forecast Loop (Recursive)

`risk_classifier.forecast_30_days()` is the live forecasting path. It is
**recursive** by design: each predicted value is appended to a rolling history
buffer (length 365), and the next iteration recomputes lag, rolling, and EMA
features from that buffer. EMAs are updated in place with the textbook
incremental formula:

```
α₇  = 2 / (7  + 1)
α₁₄ = 2 / (14 + 1)
α₂₈ = 2 / (28 + 1)
ema₇  = ema₇  + α₇  · (pred − ema₇)
ema₁₄ = ema₁₄ + α₁₄ · (pred − ema₁₄)
ema₂₈ = ema₂₈ + α₂₈ · (pred − ema₂₈)
```

Every prediction is clipped to `≥ 0` before being appended to the buffer.
`return_daily=True` returns the per-day list (used by Page 1 of the dashboard);
the default `return_daily=False` returns the 30-day sum (used by the risk
classifier).

Holiday context shifts deliberately between training and serving. The
training pipeline tags rows with **Turkish** holidays (because the Kaggle
dataset is Turkish), but `forecast_30_days` tags future dates with
**`holidays.SaudiArabia(...)`** to align with the operational context of the
pilot pharmacy. This is documented inline in the source and is the intended
behaviour.

```python
# spis/models/risk_classifier.py — header of the forecast loop
if atc_code not in encoder.classes_:
    raise ValueError(f"ATC code '{atc_code}' not found in encoder. ...")
tr_holidays = holidays.SaudiArabia(
    years=range(start_date.year, start_date.year + 2)
)
```

### 5.4.4 Risk Classification

`RiskAssessment` is a frozen dataclass — immutable by design so an assessment
captured for one render of the dashboard cannot be mutated by another:

```python
@dataclass(frozen=True)
class RiskAssessment:
    atc_code: str
    current_stock: float
    forecast_30d: float
    daily_demand: float
    days_of_stock: float       # float('inf') when daily_demand == 0
    risk_tier: str             # "CRITICAL" | "LOW" | "OK" | "OVERSTOCK"
    order_qty: float
```

The tier thresholds were calibrated for community-pharmacy lead times (3–7 days
to receive a shipment) — they sit higher than the original Phase 4 sketch and
are now codified as constants:

```python
# spis/models/risk_classifier.py
TIER_CRITICAL = 7.0    # DoS < 7   -> CRITICAL  (stockout within a week)
TIER_LOW      = 14.0   # DoS < 14  -> LOW       (stockout within two weeks)
TIER_OK       = 90.0   # DoS < 90  -> OK        (≤ 3 months of stock)
                        # DoS >= 90 -> OVERSTOCK (more than 3 months)

def classify_risk(days_of_stock):
    if days_of_stock < TIER_CRITICAL: return "CRITICAL"
    if days_of_stock < TIER_LOW:      return "LOW"
    if days_of_stock < TIER_OK:       return "OK"
    return "OVERSTOCK"

def calculate_order_qty(current_stock, forecast_30d, daily_demand, safety_days=3.0):
    safety_buffer = daily_demand * safety_days
    return float(max(0.0, forecast_30d + safety_buffer - current_stock))
```

Zero daily demand is handled by setting `days_of_stock = float('inf')` and
returning `OVERSTOCK` instead of raising — see
`build_risk_assessment()`.

### 5.4.5 Expiry-Aware Discount Advisor

`spis/models/expiry_advisor.py` decides what to do with each batch. The
decision is **two-factor**: time-to-expiry plus the share of the batch that
demand will *not* cover before expiry (`risk_ratio = units_at_risk /
quantity`).

| Days to expiry | Low risk (<0.33) | Medium risk (0.33–0.66) | High risk (>0.66) | Action |
|----------------|------------------|--------------------------|--------------------|--------|
| `> 90`         | — | — | — | `none` (filtered out before reaching the dashboard) |
| `60..90`       | Monitor (0%) | Early Discount 10% | Early Discount 15% | `promote` (or `none` for Monitor) |
| `30..59`       | Special Offer 10% | Special Offer 20% | Special Offer 30% | `promote` |
| `< 30`         | Cannot Dispense (0%) | Cannot Dispense (0%) | Cannot Dispense (0%) | `return_to_supplier` |
| `< 0`          | Expired (0%) | Expired (0%) | Expired (0%) | `write_off` |

The under-30-day "Cannot Dispense" rule is conservative on purpose: GCC/GDP
guidance discourages dispensing stock with less than a month of shelf life
remaining, so anything in that window goes back to the supplier rather than
being clearance-priced. The discount tier function is pure:

```python
def classify_discount(days_to_expiry, risk_ratio=0.5):
    if days_to_expiry < 0:        return (0, "Expired", "write_off")
    if days_to_expiry < 30:       return (0, "Cannot Dispense", "return_to_supplier")
    if days_to_expiry < 60:                                  # Special Offer
        if risk_ratio < 0.33:     return (10, "Special Offer", "promote")
        if risk_ratio <= 0.66:    return (20, "Special Offer", "promote")
        return                       (30, "Special Offer", "promote")
    if days_to_expiry <= 90:                                  # Early Discount
        if risk_ratio < 0.33:     return (0,  "Monitor",        "none")
        if risk_ratio <= 0.66:    return (10, "Early Discount", "promote")
        return                       (15, "Early Discount", "promote")
    return (0, "OK", "none")
```

`assess_batch()` returns `None` for batches more than 90 days from expiry (no
action needed) or with zero units at risk (demand will absorb them before they
expire). `assess_all_batches()` sorts the actionable offers by
`days_to_expiry` ascending so the most urgent appear at the top of the
dashboard table.

### 5.4.6 Financial Aggregations

`spis/models/expiry_finance.py` exposes the four pure functions used by Page 3
to render its KPI strip. All values are in **SAR (Saudi Riyal)**:

| Function | Formula |
|----------|---------|
| `compute_value_at_risk(offers)` | Σ `units_at_risk × unit_cost` over every offer. |
| `compute_recovered(offers, batches)` | Σ `units_at_risk × unit_cost × (1 − discount/100)` over offers that are **not** "Cannot Dispense" or "Expired". Uses the pharmacist's `applied_discount` from `inventory_batches` if it overrides the suggested value. |
| `compute_waste(offers, batches)` | Σ `waste_value` over offers that are irrecoverable (Cannot Dispense / Expired) **or** whose batch is marked `returned=1`. |
| `waste_by_atc(offers)` | Per-ATC waste totals for the red bar chart. |

### 5.4.7 Phase 9 Domain Modules

Each Phase 9 module is pure-Python, unit tested, and consumed by exactly one
dashboard page so the layering stays clean:

| Module | Purpose | Consumer |
|--------|---------|----------|
| `expiry_advisor.py` | Per-batch two-factor discount tier + units-at-risk math. | Page 3 |
| `expiry_finance.py` | SAR aggregations on top of the offer list. | Page 3 |
| `alert_engine.py` | Maps `RiskAssessment` + `ExpiryOffer` to `Alert` rows; idempotent persistence. | Page 6 |
| `decomposition.py` | Wrapper over `statsmodels.seasonal_decompose` (period = 365, additive). Edge NaNs in the trend component are extrapolated, remaining NaNs zeroed. | Page 4 |
| `inventory_kpi.py` | Annual turnover ratio (Slow < 4 ≤ Low < 6 ≤ Healthy ≤ 12 < High ≤ 24 < Excessive). | Overview + Page 4 |
| `po_generator.py` | Builds supplier-grouped POs from CRITICAL/LOW assessments, renders the PDF via `fpdf2`. | Page 8 |

The alert engine has the only mutating call. `refresh()` builds candidate
alerts from the current risk + expiry results and skips inserting any whose
`(alert_type, atc_code, batch_number)` triple already has an open record. The
notification feed therefore stays idempotent across dashboard refreshes:

```python
def refresh(db_path, assessments, offers):
    candidates = alerts_from_risk(assessments) + alerts_from_expiry(offers)
    inserted = 0
    for a in candidates:
        if not alert_key_exists(db_path, a.alert_type, a.atc_code, a.batch_number):
            create_alert(db_path, a.alert_type, a.atc_code,
                         a.batch_number, a.severity, a.message)
            inserted += 1
    return inserted
```

Risk → alert mapping uses `CRITICAL` (LOW_STOCK / CRITICAL severity) and
`LOW` (LOW_STOCK / WARNING) tiers; OK and OVERSTOCK are skipped. Expiry →
alert mapping treats `write_off` as CRITICAL, `return_to_supplier` as
WARNING, and `promote` as WARNING if `days_to_expiry ≤ 30` else INFO.

## 5.5 Streamlit Dashboard

The dashboard is the team's primary user surface. It is **not** a thin client
over the Flask API — it loads the model artifacts and SQLite database directly
from disk via `spis/dashboard/_shared.py`, which keeps every page sub-second
without any network hop. The Flask API (Section 5.6) is a separate, sample
external surface.

### 5.5.1 Page Layout

Streamlit's multi-page convention is used: `app.py` is the entry point and any
file in `spis/dashboard/pages/` shows up automatically in the sidebar in
filename order.

```
spis/dashboard/
  app.py                          Overview — KPI cards, donut, order bar,
                                  risk table, medications table with turnover
  _shared.py                      Path constants, cached loaders, CSS,
                                  missing-artifact guard
  pages/
    1_History_Forecast.py         Plotly history + 30-day forecast + P10–P90
                                  bootstrap band per ATC code
    2_Stock_Update.py             st.form to edit current_stock; writes audit row
    3_Expiry_Offers.py            Financial KPI strip, data_editor for discount
                                  overrides, Gantt-style timeline, waste bar
    4_Analytics.py                Six panels (see 5.5.3 below)
    5_Receive_Stock.py            Receive a new lot OR recall a faulty one;
                                  recent-receipts table; both flows audited
    6_Alerts.py                   Auto-refresh notification feed with ack button
                                  and sidebar severity/type filters
    7_Manage_Catalog.py           ATC overview + add-drug + register-ATC forms,
                                  supplier directory + add-supplier form,
                                  ATC-to-supplier reassignment form
    8_Purchase_Orders.py          Per-supplier expanders, PDF download,
                                  Mark-as-Sent, order history
```

### 5.5.2 How the Frontend Talks to the Models

Every page imports the same helpers from `_shared.py`, which encapsulate the
"how do I get a current view of the system" pattern:

```python
# spis/dashboard/_shared.py (excerpt)
@st.cache_resource
def load_artifacts():
    model, encoder = load_model(MODELS_DIR)
    inventory      = load_atc_inventory(DB_PATH)
    return model, encoder, inventory

@st.cache_data(ttl=300)
def run_assessment(_model, _encoder, _inventory):
    return assess_from_features(
        features_csv=FEATURES_CSV,
        inventory=_inventory,
        model=_model,
        encoder=_encoder,
    )
```

Two caches are used deliberately:

- `@st.cache_resource` is process-lifetime. The XGBoost model and the
  `LabelEncoder` are loaded exactly once per Streamlit process. Because the
  model is read-only after training, sharing it across pages and sessions is
  safe.
- `@st.cache_data(ttl=300)` is value-keyed. The full assessment is recomputed
  at most every five minutes, or immediately when a page calls
  `run_assessment.clear()` (Pages 2 and 5 do this after a stock edit / batch
  receipt so the new numbers appear on the next rerun).

Page 1 (`1_History_Forecast.py`) is the most direct demonstration of how the
frontend consumes the forecaster:

1. User picks an ATC code in a `st.selectbox` and chooses a history window
   (30/60/90/180 days) via `st.select_slider`.
2. The page reads the last N days of history straight from the SQLite `sales`
   table (`pd.read_sql_query`).
3. The cached `model` and `encoder` are passed into
   `forecast_30_days(..., return_daily=True)` to get a 30-element list of
   per-day predictions.
4. Test-set residuals are bootstrapped 500× to produce a **P10–P90 prediction
   band** around the point forecast. This is the only place the dashboard
   shows forecast uncertainty.
5. A Plotly `go.Figure` overlays history (solid blue), the P10–P90 ribbon
   (translucent orange), and the forecast line (dashed orange).

```python
# Page 1 — bootstrap interval
sampled = rng.choice(residuals, size=(n_boot, n_days), replace=True)
sims    = np.clip(forecast[None, :] + sampled, 0.0, None)
lower, upper = np.percentile(sims, 10, axis=0), np.percentile(sims, 90, axis=0)
```

Page 2 (`2_Stock_Update.py`) shows the inverse direction — the frontend
writing back into the SQLite layer:

```python
with st.form("stock_update_form"):
    new_values = { atc: st.number_input(...) for atc in inventory }
    submitted = st.form_submit_button("Save All Changes", type="primary")

if submitted:
    for atc, val in changed.items():
        update_stock(DB_PATH, atc, val)
    _append_audit([...])             # data/stock_audit.csv
    run_assessment.clear()           # so the Overview reflects new values
    st.rerun()
```

Page 6 (`6_Alerts.py`) wires the alert engine into the same loop:

```python
model, encoder, inventory = load_artifacts()
assessments = run_assessment(model, encoder, inventory)
offers      = assess_all_batches(load_batches(DB_PATH),
                                 {ra.atc_code: ra.daily_demand for ra in assessments})
new_count   = refresh(DB_PATH, assessments, offers)  # idempotent insert
if new_count:
    st.toast(f"{new_count} new alert(s) generated.")
```

### 5.5.3 Analytics Page Panels

Page 4 packs six analytical views into one screen:

1. **Model Accuracy** — MAE / RMSE / MAPE metric cards read from
   `models/metrics.json`, with an expandable baseline-comparison table.
2. **XGBoost Feature Importance** — top 20 features as a Plotly Express
   horizontal bar, coloured by importance score. Reads
   `models/feature_importance.json`.
3. **Fast / Medium / Slow Movers (ABC Pareto)** — sorts ATC codes by 30-day
   forecasted demand and computes cumulative share. Cutoffs are 80 %
   ("Fast") and 95 % ("Medium"); everything beyond is "Slow". The class
   labels are intentionally pharmacy-friendly rather than the textbook
   A/B/C letters.
4. **Seasonal Decomposition** — `statsmodels.seasonal_decompose` with
   `period=365` rendered as three stacked subplots (trend / seasonal /
   residual) for the selected ATC code.
5. **Year-over-Year Demand Growth** — bar chart comparing the most recent
   365-day total against the prior 365-day total, green for growing demand,
   red for declining.
6. **12-Month Rolling Demand Trend** — a 90-day rolling mean per ATC across
   the last year, plotted on one shared axis with a multi-select.

The page also closes with the **Inventory Turnover Ratio** strip and table
fed by `inventory_kpi.compute_turnover()`.

### 5.5.4 Expiry Offers Page Mechanics

Page 3 is the most stateful page after the alert centre. The user gets:

- A four-metric SAR KPI strip (Value at Risk, Projected Recovery, Written
  Off, Waste Rate).
- A red bar chart of waste-by-ATC sorted descending.
- A radio filter (`All` / `Urgent <30 days` / `Upcoming 30–90 days`).
- A `st.data_editor` with editable **Applied Discount %** and **Return to
  Supplier** columns. On confirm, edits go through `save_batch_overrides()`
  in `database.py`, which updates `applied_discount`, sets `returned`, and
  zeros the batch quantity when the return flag is on.
- A Gantt-style horizontal bar timeline coloured by urgency tier.

### 5.5.5 Receive Stock and Recall

Page 5 has two forms:

- **Receive New Batch** — calls `database.add_batch(...)`, which inserts the
  row, increments `atc_inventory.current_stock`, and appends a `RECEIVE`
  audit line. A helper auto-suggests the next `LOT-YYYY-NNN` number.
- **Recall a Batch** — calls `database.recall_batch(...)`, which zeros the
  batch quantity, sets `returned=1`, decrements stock with a `MAX(0, ...)`
  guard, and appends a `RECALL` audit line. The original notes string is
  preserved with a `RECALLED <ISO-timestamp>: <reason>` suffix.

Both flows invalidate the relevant caches (`run_assessment.clear()` and the
local `_load_batches_cached.clear()`) so other pages see the new state on
their next render.

### 5.5.6 Manage Catalog — Drugs, ATC Codes, and Suppliers

Page 7 (`7_Manage_Catalog.py`) is the only page that does not require model
artifacts — it operates purely against the SQLite database. It is laid out
as five vertically-stacked sections:

- **A. ATC Categories** — read-only table with drug counts and current
  stock per ATC code.
- **B. Add Drug** — form that calls `catalog.add_drug()`. Rejects empty
  names and unknown ATC codes via `ValueError` raised by the helper.
- **C. Add ATC Code** — form that calls `catalog.add_atc_code()`. Warns
  that sales history and a retrain are still required before the
  forecaster can serve the new code.
- **D. Suppliers** — read-only directory table plus an **Add Supplier**
  form bound to `database.add_supplier()`. The supplier_id is
  auto-assigned by SQLite, names are unique, and negative lead times are
  rejected. Tamer Group / Banaja Holdings / Cigalah Group / Jamjoom
  Pharma are visible here on a fresh install and are themselves editable
  data (no code change needed to add a fifth supplier or rename one of
  the seeds).
- **E. Assign ATC Code to Supplier** — selectbox-driven form bound to
  `database.assign_supplier_to_atc()`. The pharmacist picks an ATC code
  and a supplier; the change takes effect on the next render of Page 8.

This means the entire supplier directory and routing logic is operator-
editable through the dashboard — no Python edits, no SQL, no
redeployment.

### 5.5.7 Missing-Artifact Guard

Every page calls `check_required_files()` after `inject_css()`. If any of
`xgboost_forecaster.joblib`, `label_encoder.joblib`, `inventory.db`, or
`features_daily.csv` are absent, the page prints a clear error and calls
`st.stop()` instead of throwing a stack trace at the user. Page 7 (Manage
Catalog) only requires the database, so it relaxes the guard accordingly.

## 5.6 REST API (Sample External Interface)

The dashboard reads model artifacts directly, but a separate Flask app
(`spis/api/`) is provided as the sample interface for any non-Streamlit
consumer (a future POS integration, a mobile front-end, or a curl test from
the committee). It is intentionally minimal — three endpoints, no auth,
in-memory model — so the surface area stays small enough to test exhaustively.

```python
# spis/api/app.py
def create_app(config=None):
    app = Flask(__name__)
    app.config.update(_DEFAULTS)
    if config: app.config.update(config)

    models_dir = Path(app.config["MODELS_DIR"])
    if (models_dir / "xgboost_forecaster.joblib").exists() and \
       (models_dir / "label_encoder.joblib").exists():
        model, encoder = load_model(models_dir)
        app.config["_MODEL"]   = model
        app.config["_ENCODER"] = encoder
    else:
        app.config["_MODEL"] = app.config["_ENCODER"] = None
    register_routes(app)
    return app
```

The factory pattern enables tests to spin up an isolated app with a
`tmp_path`-backed `MODELS_DIR`, and the eager load means a misconfigured
deployment fails at startup rather than on the first inbound request.

| Method | Path | Behaviour |
|--------|------|-----------|
| `GET` | `/health` | Liveness; always `200` with `{status, version}`. |
| `GET` | `/api/v1/risk` | Full risk assessment for every ATC code in the inventory. `503` if model not loaded. `days_of_stock == inf` is serialised as JSON `null` via `_ra_to_dict`. |
| `GET` | `/api/v1/forecast/<atc_code>` | 30-day forecast for one code; `404` if `atc_code` is not in `encoder.classes_`; `503` if model not loaded. |

```python
# spis/api/routes.py — null-safe serialisation
def _ra_to_dict(ra):
    d = dataclasses.asdict(ra)
    if d.get("days_of_stock") == float("inf"):
        d["days_of_stock"] = None
    return d
```

`scripts/run_api.py` is the launcher; it accepts `--host`, `--port`,
`--debug`, `--db`, `--features`, `--models`, and `--safety-days` flags and
prints a startup warning when the model artifacts are missing.

## 5.7 CLI Scripts

Every long-running operation has a one-line launcher in `scripts/` so neither
the team nor the committee needs to remember module paths.

| Script | Purpose |
|--------|---------|
| `ingest_kaggle.py` | Rebuild the database from the original Kaggle dataset. |
| `ingest_data.py` | Append a new pharmacy's CSV (long format). |
| `register_atc.py` | Manually register an ATC code (or `--list` all). |
| `run_pipeline.py` | Produce `features_daily.csv`, `train.csv`, `test.csv`. |
| `train_model.py` | Run GridSearchCV and persist model + encoder + metrics + feature importance. |
| `assess_risk.py` | One-shot CLI risk assessment → CSV. |
| `run_api.py` | Start the Flask REST server. |
| `run_dashboard.py` | Start Streamlit on a chosen port. |
| `export_committee_pdf.py` | Render the committee one-pager via fpdf2. |
| `run_public.py` | Launch dashboard bound to `0.0.0.0` for the lab demo. |

The intended onboarding sequence for a new pharmacy is:

```
register_atc.py  →  ingest_data.py  →  run_pipeline.py  →  train_model.py
```

---

# Chapter 6: Testing

## 6.1 Testing Strategy

The team applies a three-layer strategy across every phase:

- **Unit tests** exercise pure functions in isolation with synthetic fixtures —
  tier classification, order-quantity arithmetic, expiry-discount mapping,
  feature counts, ATC-level inference.
- **Integration tests** exercise multi-module flows against temporary SQLite
  databases and the Flask test client. The pipeline ingest, the API endpoints,
  the alert engine's idempotency, and the PO generator's PDF output are all
  validated this way.
- **Manual UI testing** is performed locally with `python scripts/run_dashboard.py`.
  The team verifies tier colours, cache invalidation after a stock edit, batch
  receipts, recalls, and alert acknowledgement on every page before each
  milestone.

The runner is **pytest 9.0.2**. Fixtures live next to their test files (no
global `conftest.py`), so test ownership is local and the dependency graph
between tests is obvious. Slow fixtures (a tiny `XGBRegressor` with
`n_estimators=10`) are widened to session scope where it is safe to do so.
Every test is deterministic — random seeds are fixed, dates are pinned, and
SQLite paths are created in `tmp_path` so no test sees another test's data.

## 6.2 Test Suite

The Phase 9 enhancements grew the suite to **182 tests across 14 files**
(counted by AST over all `test_*.py` modules). All pass on the current
codebase (`venv/Scripts/python -m pytest -q` → `182 passed`). The
breakdown is:

| Module / Feature | Test file | Tests | Focus |
|------------------|-----------|-------|-------|
| Data pipeline | `test_pipeline.py` | 7 | Feature count, lag/rolling math, validate / dedupe / clip, train/test cutoff |
| Forecaster | `test_forecaster.py` | 8 | Baselines, ATC encoding, GridSearchCV, model save/load, evaluate metrics |
| Risk classifier | `test_risk_classifier.py` | 19 | DoS formula, all four tier boundaries, order qty, recursive 30-day loop, unknown-ATC raises, `load_atc_inventory` |
| Expiry advisor | `test_expiry_advisor.py` | 22 | Two-factor discount mapping (every quadrant), `units_at_risk`, `assess_batch` None-return paths, ordering |
| Expiry finance | `test_expiry_finance.py` | 13 | Value-at-risk, recovered revenue with overrides, write-off totals, per-ATC waste aggregation |
| Alert engine | `test_alert_engine.py` | 15 | Risk → alert mapping, expiry → alert mapping, severity assignment, idempotent refresh, acknowledge / get_all |
| Decomposition | `test_decomposition.py` | 5 | Output shape, NaN handling, short-series guard, period validation |
| Inventory KPI | `test_inventory_kpi.py` | 5 | Turnover formula, classification thresholds, zero-inventory guard |
| PO generator | `test_po_generator.py` | 14 | Supplier grouping, line totals, default-cost fallback, PDF bytes header, empty-input case |
| Database schema | `test_database.py` | 29 | Schema creation, seed row counts, idempotency, `inventory_batches` seed, `update_stock`, `add_batch` (7 paths including past-expiry warn), `recall_batch` (happy / unknown / idempotent), suppliers seed and ATC→supplier link, `add_supplier` (happy / empty / duplicate / negative-lead-time), `assign_supplier_to_atc` (happy / unknown-ATC / unknown-supplier) |
| Catalog helpers | `test_catalog.py` | 10 | `add_drug`, `add_atc_code`, duplicate / empty / unknown-FK guards |
| Flask API | `test_api.py` | 18 | All endpoints + 200 / 404 / 503 paths |
| Data ingestion | `test_ingest_data.py` | 11 | CSV normalisation, negative clipping, dedup, custom columns, auto-register |
| ATC registration | `test_register_atc.py` | 6 | Level inference, hierarchical validation |
| **Total** | | **182** | |

Coverage target is **80% on critical paths**. The forecaster, risk classifier,
expiry advisor, alert engine, and API routes each measure above 90 % line
coverage when running `pytest --cov=spis`. Uncovered lines are logging /
print statements and exception branches reached only on file-I/O failures.

## 6.3 Representative Unit Tests

### 6.3.1 Tier Boundaries

The four tier thresholds are tested at and immediately below their boundary
values. The current `TIER_CRITICAL / TIER_LOW / TIER_OK` constants are
asserted explicitly so that any future tuning forces a deliberate test
update:

```python
# tests/test_risk_classifier.py
def test_classify_risk_uses_constants():
    assert TIER_CRITICAL == 7.0
    assert TIER_LOW      == 14.0
    assert TIER_OK       == 90.0

def test_classify_risk_critical():
    assert classify_risk(0.0) == "CRITICAL"
    assert classify_risk(TIER_CRITICAL - 0.001) == "CRITICAL"

def test_classify_risk_low():
    assert classify_risk(TIER_CRITICAL)        == "LOW"
    assert classify_risk(TIER_LOW - 0.001)     == "LOW"

def test_classify_risk_ok():
    assert classify_risk(TIER_LOW)             == "OK"
    assert classify_risk(TIER_OK - 0.001)      == "OK"

def test_classify_risk_overstock():
    assert classify_risk(TIER_OK)              == "OVERSTOCK"
    assert classify_risk(1000.0)               == "OVERSTOCK"
```

### 6.3.2 Order Quantity Includes Safety Buffer

```python
def test_calculate_order_qty_includes_safety_buffer():
    no_buf   = calculate_order_qty(0.0, 100.0, 5.0, safety_days=0.0)
    with_buf = calculate_order_qty(0.0, 100.0, 5.0, safety_days=3.0)
    assert with_buf - no_buf == 15.0   # 5 units/day × 3 days
```

### 6.3.3 Expiry Discount Mapping

`test_expiry_advisor.py` covers every quadrant of the two-factor
(days × risk) matrix. Excerpts:

```python
def test_classify_discount_expired():
    pct, label, action = classify_discount(-1)
    assert (pct, label, action) == (0, "Expired", "write_off")

def test_classify_discount_cannot_dispense():
    pct, label, action = classify_discount(20)            # <30 days
    assert (pct, label, action) == (0, "Cannot Dispense", "return_to_supplier")

def test_classify_discount_no_action():
    pct, label, action = classify_discount(91)            # >90 days
    assert (pct, label, action) == (0, "OK", "none")
```

### 6.3.4 Feature Count Invariant

The pipeline must produce exactly 35 engineered features (plus the 3 original
columns). A test for this number means a future contributor adding a feature
cannot silently drift the model input matrix:

```python
def test_engineer_features_columns(small_daily_df):
    out = engineer_features(small_daily_df)
    assert len(out.columns) == 38     # 3 original + 35 features
    for f in ["ema_14", "lag_365", "season", "ema_ratio"]:
        assert f in out.columns
```

## 6.4 Integration Tests

### 6.4.1 Flask API via Test Client

`test_api.py` uses Flask's in-process test client; no socket is opened, so the
suite stays fast and CI-friendly. Each test runs against a fresh
`tmp_path`-rooted artifact directory built from a tiny in-memory XGBoost model
(`n_estimators=10`):

```python
def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json["status"] == "ok"

def test_risk_assessment_no_model(client_no_model):
    r = client_no_model.get("/api/v1/risk")
    assert r.status_code == 503
    assert "Model artifacts not loaded" in r.json["error"]

def test_forecast_unknown_atc(client):
    r = client.get("/api/v1/forecast/UNKNOWN")
    assert r.status_code == 404
```

### 6.4.2 Pipeline Train/Test Isolation

```python
def test_split_no_leakage():
    df = load_and_engineer(cutoff="2018-07-01")
    train, test = split_train_test(df, cutoff="2018-07-01")
    cutoff_dt = pd.Timestamp("2018-07-01")
    assert (train["date"] <  cutoff_dt).all()
    assert (test["date"]  >= cutoff_dt).all()
```

### 6.4.3 Alert Engine Idempotency

The alert engine has the subtlest integration behaviour because it writes to
disk. The corresponding test seeds CRITICAL/LOW assessments and expiry
offers, runs `refresh` once to populate the table, then asserts a second
call inserts zero new rows:

```python
def test_refresh_is_idempotent(tmp_db):
    inserted_first  = refresh(tmp_db, assessments=[critical_ra], offers=[])
    inserted_second = refresh(tmp_db, assessments=[critical_ra], offers=[])
    assert inserted_first  > 0
    assert inserted_second == 0
```

`alert_key_exists` is the underlying guard — same triple
`(alert_type, atc_code, batch_number)` with `acknowledged_at IS NULL`
counts as a duplicate.

### 6.4.4 Database Write Paths

`test_database.py` covers the three mutating helpers end-to-end against a
`tmp_path` SQLite database:

- `update_stock` — rejects negatives, updates `current_stock`, bumps
  `last_updated`.
- `add_batch` — inserts row, raises on duplicate `batch_number`, raises on
  invalid date / negative quantity, warns on past expiry, increments
  `atc_inventory.current_stock`.
- `recall_batch` — zeros the batch, sets `returned=1`, decrements aggregate
  stock with the `MAX(0, ...)` floor, appends a recall suffix to the
  `notes` column.

## 6.5 Error-Handling Tests

| ID | Scenario | Expected Behaviour |
|----|----------|--------------------|
| EH-001 | Negative quantity in ingest CSV | Clipped to 0.0 |
| EH-002 | Duplicate `(atc_code, date)` | Aggregated by `groupby().sum()` |
| EH-003 | Forecast for unknown ATC | API returns 404; `forecast_30_days` raises `ValueError` |
| EH-004 | Model artifacts missing | API returns 503 on `/risk` and `/forecast` |
| EH-005 | Zero daily demand | `days_of_stock == inf` → tier `OVERSTOCK`, `order_qty == 0` |
| EH-006 | First 7 days of an ATC's history (NaN `lag_7`) | Dropped in `split_train_test` |
| EH-007 | `forecast_30_days` on unknown ATC | `ValueError` with message |
| EH-008 | XGBoost returns small negative float | Clipped to 0.0 before being appended to the rolling history |
| EH-009 | Duplicate alert re-emitted | `alert_engine.refresh` skips it (idempotent) |
| EH-010 | Recall on unknown batch | `recall_batch` raises `ValueError` |
| EH-011 | `add_batch` with duplicate lot | Raises `ValueError("Batch number already exists: ...")` |
| EH-012 | Inventory turnover with zero current_stock | Reports `turnover == 0.0`, classification "Slow" |

## 6.6 Defects Found During Development

Selected defects, all fixed before the corresponding phase closed. Every fix
is accompanied by a regression test:

| Defect | Module | Fix |
|--------|--------|-----|
| `days_of_stock = inf` serialised as `"Infinity"` and broke JSON parsers | `api/routes.py` | `_ra_to_dict` replaces with `None` |
| Forecast loop held lag/rolling features constant, producing flat 30-day predictions | `risk_classifier.py` | Switched to recursive: append each prediction to a 365-day history buffer, recompute lag/rolling/EMA before the next step |
| Negative quantities in raw CSV reached the model | `pipeline.py` | `.clip(lower=0)` + EH-001 test |
| First 7 days of each ATC had NaN `lag_7`, crashed the train split | `pipeline.py` | `dropna(subset=["lag_7"])` in `split_train_test` |
| Tiny negative XGBoost predictions polluted the rolling history | `risk_classifier.py` | `max(0.0, pred)` per day before appending |
| Alerts duplicated on every dashboard refresh | `alert_engine.py` | `alert_key_exists` check + EH-009 test |
| `inventory_batches` lacked pharmacist-override columns; Page 3 edits had nowhere to land | `database.py` | `_migrate_schema` adds `applied_discount` and `returned` if missing |
| PO PDF crashed on non-Latin characters (e.g. supplier names with accents) | `po_generator.py` | `_safe()` encodes to latin-1 with `errors="replace"` before every `pdf.cell` call |
| Forecasting used Turkish holidays at serve time even though the pilot pharmacy is in Saudi | `risk_classifier.py` | Switched the live forecast loop to `holidays.SaudiArabia(...)`; training pipeline kept on `holidays.Turkey(...)` because the dataset itself is Turkish |

## 6.7 Test Infrastructure

- Fixtures live next to their test files; no global `conftest.py` so test
  ownership is local and the dependency graph between tests is obvious.
- The Flask API tests use a fresh `tmp_path` per test and never reuse the
  on-disk database used by the dashboard.
- A small `tiny_model` fixture (`n_estimators=10`) keeps the forecaster tests
  under a second total — anything larger lives in `scripts/train_model.py`,
  which is invoked manually.

Running the full suite locally:

```
py -3.11 -m pytest -q
```

Typical wall-clock time on a developer laptop is ~15 s. There are no
intermittent failures across the three independent runs performed for the
committee dossier.

---

# Chapter 7: Conclusion and Future Work

## 7.1 Summary

SPIS started as an empty repository in early Phase 1 and is, at the end of
Phase 9, a complete inventory-intelligence application:

- A reproducible SQLite database with eight tables, seeded from a real Kaggle
  pharmacy dataset (424,080 sales transactions over six years across eight
  ATC categories) and extended with batch-level expiry tracking, a directory
  of four real Saudi-market suppliers (Tamer Group, Banaja Holdings,
  Cigalah Group, Jamjoom Pharma) routable per-ATC, purchase-order history,
  and a notification log.
- A 35-feature time-series pipeline that splits cleanly along a 2019-01-01
  cutoff into 14,544 train rows and 2,248 test rows.
- A single XGBoost regressor — tuned with `TimeSeriesSplit` cross-validation
  across the production grid — that beats the moving-average baseline by ~3×
  on MAE (≈ 1.06 vs ≈ 2.89) and the naive baseline by ~4×.
- A four-tier risk classifier (`CRITICAL < 7d`, `LOW < 14d`, `OK < 90d`,
  `OVERSTOCK ≥ 90d`) calibrated for community-pharmacy lead times, with a
  deterministic order-quantity formula and a configurable safety buffer.
- A multi-page Streamlit dashboard (Overview plus eight pages) that reads
  model artifacts directly and ships with interactive history+forecast
  charts with P10–P90 bootstrap bands, in-app stock editing, batch receipt
  and recall, two-factor expiry-aware discount suggestions in SAR, a
  notification feed with sidebar filters, catalog management, an Analytics
  page with six panels (model accuracy, feature importance, ABC Pareto,
  seasonal decomposition, YoY growth, rolling trend) and a turnover KPI
  strip, and one-click supplier PO PDFs.
- A separate, well-tested Flask API as a sample external integration surface.
- A test suite of **182 tests** across 14 files, all passing, with 80%+
  coverage on every critical path.
- An IEEE-referenced graduation report (this document plus chapters 1–4).

## 7.2 Evaluation Against Objectives

| Objective (Chapter 1) | Implementation | Outcome |
|-----------------------|----------------|---------|
| Reproducible pharmacy database | `spis/data/database.py` with idempotent `init_db()` + `_migrate_schema()` | Achieved |
| End-to-end feature pipeline | `spis/data/pipeline.py`; 35 features, group-wise no-leak | Achieved |
| Demand forecaster | `spis/models/forecaster.py`; MAE ≈ 1.06, RMSE ≈ 2.29 | Achieved |
| Risk classification | `spis/models/risk_classifier.py`; four tiers (7 / 14 / 90 day boundaries) + order qty | Achieved |
| REST surface | `spis/api/`; 3 endpoints, 18 tests | Achieved |
| Interactive dashboard | `spis/dashboard/`; Overview + 8 pages incl. supplier management on Page 7 | Achieved |
| Expiry-aware discount system | `expiry_advisor.py`, `expiry_finance.py`, Page 3 | Achieved |
| Notifications | `alert_engine.py`, `alerts` table, Page 6 | Achieved |
| Operational PO output | `po_generator.py`, Page 8, fpdf2 PDFs in SAR | Achieved |
| Batch receipt & recall | `database.add_batch / recall_batch`, Page 5, stock_audit.csv | Achieved |
| Generalisable ingestion | `scripts/ingest_data.py`, `scripts/register_atc.py`, `catalog.py` | Achieved |
| Coverage ≥ 80% on critical paths | pytest + coverage gate | Achieved |

## 7.3 Evaluation Against Requirements

Every functional requirement (FR-1 … FR-6 in Chapter 3) is exercised by at
least one automated test, and the Phase 9 enhancements introduced four
additional behavioural requirements (expiry handling, alert idempotency,
turnover classification, supplier PO export) each backed by a dedicated test
file.

Non-functional requirements:

- **NFR-1 Performance**: full pipeline run on 16,848 daily rows completes in
  < 3 s on a developer laptop. Per-ATC 30-day forecast (30 XGBoost predictions
  plus per-day feature regeneration) finishes in under 500 ms.
- **NFR-2 Reliability**: 182 tests, 100 % pass rate, no flaky tests across
  three independent runs.
- **NFR-3 Scalability**: ingestion path is pharmacy-agnostic. Any new
  pharmacy can register N ATC codes through `register_atc.py` or the Manage
  Catalog page, feed CSVs through `ingest_data.py`, and retrain with a
  single `train_model.py` invocation.

## 7.4 Limitations

1. **Single-source training data.** The forecaster is trained on one Turkish
   pharmacy's history. Seasonality and calendar effects are validated for
   that context only; the live forecast loop deliberately swaps in Saudi
   public holidays to align with the pilot pharmacy, but cross-pharmacy
   validation is required before any commercial deployment.
2. **Single-warehouse stock model.** `atc_inventory` is a single snapshot.
   Multi-branch pharmacy chains would need per-location keys and a
   transfer-aware risk classifier.
3. **No live POS feed.** Sales are imported by CSV. Until a POS integration
   exists, the lag / rolling features cannot refresh in real time and the
   forecast horizon is bounded by the staleness of the last CSV.
4. **Read-only API.** The Flask surface is intentionally read-only. Stock
   edits, batch receipts, and recalls go through the dashboard's direct
   write path, not the API. A production deployment would need an
   authenticated `POST/PATCH` surface.
5. **NLP drug-name search was scoped, not delivered.** `spacy` and
   `scispacy` remain in `requirements.txt` because the Phase 9 plan
   included a drug-name NLP search, but it was deprioritised in favour of
   the operational features (alerts, POs, catalog management, batch
   receive / recall). The codebase currently has no NLP path.

## 7.5 Future Work

The priority order below is informed by what an evaluator or pharmacist
would most likely ask for next.

1. **Live POS ingestion.** Replace the CSV import with a continuous feed
   (e.g. a small Flask endpoint that receives POS events, batched into
   `sales`). Schedule weekly retraining so lag / rolling features stay
   representative.
2. **Probabilistic forecasts at training time.** The dashboard already
   shows a bootstrap P10–P90 band on Page 1, but the underlying model is
   still a point estimate. Replace `XGBRegressor` with quantile regression
   (`reg:quantileerror`) so the order-quantity formula can use the 90th
   percentile directly and remove the fixed `safety_days` constant.
3. **Per-drug forecasts.** Move from ATC-4 to per-SKU forecasting. Requires
   sparser-history modelling (hierarchical or transfer learning).
4. **NLP drug-name search.** Re-introduce the scoped scispacy search.
   `PhraseMatcher` over the `drugs` catalog with a `difflib` fallback when
   the scispacy model is not installed.
5. **Multi-branch deployment.** Add a `location_id` to `atc_inventory`,
   `inventory_batches`, and the API path, and extend the risk classifier to
   suggest inter-branch transfers before triggering an external PO.
6. **Authenticated API + mobile client.** Add API-key auth on the Flask
   surface and ship a thin mobile client that mirrors the alert feed for
   pharmacists on rotation.
7. **Refill reminders.** Subscribe a downstream patient-reminder service to
   the existing `alerts` table — `CRITICAL` events on chronic-medication
   ATC codes can be cross-referenced with a patient prescription database
   to warn patients before their next refill is at risk.

## 7.6 Reflections

**Saleh.** Owning the architecture taught me how much benefit comes from
keeping one source of truth per concept. The `RiskAssessment` dataclass,
the `_shared.py` cache helpers, the `FEATURE_COLS` list, and the
`_migrate_schema()` migration helper are each tiny pieces of code, but the
fact that every dashboard page and the Flask API run through them is what
made Phase 9 additions safe. The single highest-value design choice was
reading model artifacts directly from the dashboard — it kept Streamlit
sub-second and made the Flask API a clean optional surface rather than a
critical path.

**Nawaf.** Building the API factory and the test client harness made me
appreciate fail-fast design. Eager loading at startup means a deployment
with no model never serves a confused 500 — it serves a deliberate 503
with a message that tells you exactly which script to run. The 18 API
tests doubled as documentation of every error path.

**Mazen.** The test suite more than doubled during the project (from 75 to
182 tests across 14 files) and the later additions were the most valuable.
Alert idempotency, two-factor expiry classification, batch-recall semantics,
and PO generation each had a non-obvious failure mode that only a test
could pin down. The discipline of writing the test alongside the fix
turned each defect into a regression guard rather than a one-off patch.

**Ali.** The dashboard is where the project comes alive. Phase 8.5 split
the single page into multiple pages, and Phase 9 turned it from a viewer
into a tool — stock edits, batch receipts and recalls, discount
acknowledgements, alert acknowledgements, and PO PDFs all happen in-app.
Plotly + Streamlit's two-tier caching let me focus on the visuals without
ever measuring a render. The P10–P90 bootstrap band on Page 1 was the
single feature that made the forecast feel honest — it shows uncertainty
without hiding the point estimate. I would like to put this in front of a
pharmacist next.

---

## References

[1] Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting
system. In *Proc. 22nd ACM SIGKDD Int. Conf. on Knowledge Discovery and
Data Mining* (pp. 785–794).

[2] Pedregosa, F. et al. (2011). Scikit-learn: Machine Learning in Python.
*Journal of Machine Learning Research*, 12, 2825–2830.

[3] McKinney, W. (2010). Data structures for statistical computing in
Python. In *Proc. 9th Python in Science Conf.* (Vol. 445, pp. 51–56).

[4] Seabold, S., & Perktold, J. (2010). statsmodels: Econometric and
statistical modeling with Python. In *Proc. 9th Python in Science Conf.*

[5] Ronacher, A. (2023). Flask: a lightweight WSGI web application
framework. https://flask.palletsprojects.com/

[6] Streamlit Inc. (2024). Streamlit — the fastest way to build data apps.
https://streamlit.io/

[7] Jiang, J. X., Zhu, M., & Liu, H. L. (2014). Demand forecasting for
pharmacy inventory: a review and perspective. *European Journal of
Operational Research*, 237(1), 1–10.
