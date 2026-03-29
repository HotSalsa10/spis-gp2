# Phase 9 — Enhancement Plan (Post Phase 8)
# Smart Pharmacy Inventory System (SPIS) — GP Improvement Roadmap
# Written: March 2026
# Purpose: Detailed implementation guide for the next development session.
#           Every feature is described with enough context to implement
#           from scratch without additional explanation.

---

## Context: What We Have After Phase 8

After 8 phases, SPIS has:
- SQLite DB: 4 tables (atc_categories, drugs, sales, atc_inventory)
- Data pipeline: 35 features, daily granularity, 2014–2019
- XGBoost forecaster: MAE 1.07, 36 features, GridSearchCV-tuned
- Risk classifier: 4 tiers (CRITICAL <3d, LOW 3–7d, OK 7–30d, OVERSTOCK ≥30d)
- Flask API: GET /health, GET /api/v1/risk, GET /api/v1/forecast/<atc_code>
- Streamlit dashboard: 1 page, 4 static sections (metric cards, risk table, bar chart, medications table)
- 75 tests, all passing
- GP report: 7 chapters (IEEE)

The **major gap** is the dashboard. It is a single static page that shows the same
information every time with no interactivity, no charts of historical data, no way for
the pharmacist to update anything. The backend is strong; the interface is weak.

Also: spacy and scispacy are in requirements.txt but NEVER used anywhere in the
codebase. An evaluator will notice this. We need to use them.

---

## Priority Order (do in this order for maximum GP impact)

1. Historical demand chart + forecast overlay (biggest visual impact)
2. Interactive stock update (makes it a real tool, not a demo)
3. Expiry-aware offers system (original, impressive business value)
4. Demand anomaly detection (shows intelligence beyond static calculation)
5. Drug NLP search using scispacy (justifies the dependency)
6. Financial / waste dashboard (elevates to business solution)
7. Feature importance chart (academic rigor)
8. Sidebar filters + alerts panel (UX polish)
9. ABC / Pareto analysis (inventory theory)
10. Automated PDF report (deliverable output)

---

## Feature 1: Historical Demand Chart + Forecast Overlay

### Why
The model forecasts 30-day demand but the dashboard only shows a single number.
The data (5+ years of daily sales) already exists in the DB but is never visualized.
A pharmacist's first question is always "what does demand look like?" A chart that shows
the past and predicts the future is the single highest-impact addition.

### What to build
A Streamlit chart section (new tab or expander per ATC code) showing:
- Left side (solid line): historical daily sales for the selected ATC code
  - X axis: date, Y axis: quantity sold per day
  - Show last 90 or 180 days by default (use a slider or selectbox)
- Right side (dashed line, different color): the 30-day day-by-day forecast
  - Currently `forecast_30_days()` only returns the TOTAL (sum of 30 days).
    We need a small change: make it also return the day-by-day list.
  - Add an optional `return_daily=True` parameter to `forecast_30_days()` in
    `spis/models/risk_classifier.py` — if True, return list[float] instead of float.
- Vertical dashed line at "today" separating history from forecast
- Shaded area for forecast (light color) to visually distinguish from real data
- Title: "M01AB — Acetic acid derivatives: 90-day history + 30-day forecast"

### Code changes needed
1. `spis/models/risk_classifier.py` — modify `forecast_30_days()`:
   ```python
   def forecast_30_days(..., return_daily=False):
       daily_preds = [max(0.0, model.predict(X)[0]) for each day]
       if return_daily:
           return daily_preds  # list of 30 floats
       return sum(daily_preds)  # existing behavior (unchanged)
   ```
2. `spis/dashboard/app.py` — add a new section:
   - Use `st.selectbox` to pick ATC code
   - Load historical data from DB with `pd.read_sql_query`
   - Get daily forecast via modified `forecast_30_days(return_daily=True)`
   - Build a combined DataFrame: historical rows with `type="history"`,
     forecast rows with `type="forecast"`
   - Use `st.line_chart` or Plotly `go.Figure` (Plotly preferred for styling)
   - Plotly is already available in the streamlit environment; use
     `import plotly.graph_objects as go` and `st.plotly_chart(fig)`

### DB query for historical data
```sql
SELECT sale_date as date, quantity
FROM sales
WHERE atc_code = ? AND granularity = 'daily'
ORDER BY sale_date DESC
LIMIT 90
```

---

## Feature 2: Interactive Stock Update

### Why
Right now, `atc_inventory` is seeded with mock values at DB init time and never
changes. The pharmacist has no way to update stock through the dashboard. This means
the "inventory system" can't actually manage inventory — it just shows a static snapshot.
Making stock editable transforms SPIS from a demo into a real tool.

### What to build
A new dashboard section or sidebar panel:
- Table with one row per ATC code showing: code, name, current stock, unit
- Each row has a numeric input field (`st.number_input`) pre-filled with current stock
- A single "Update Stock Levels" button at the bottom
- On click: write all changed values to `atc_inventory` table in SQLite,
  clear the `@st.cache_data` cache so the risk assessment re-runs with new values
- Show a success message: "Stock updated. Risk assessment refreshed."
- The risk tiers and order quantities on the main table update immediately

### Code changes needed
1. `spis/data/database.py` — add a new public function:
   ```python
   def update_stock(db_path, atc_code: str, new_stock: float) -> None:
       with sqlite3.connect(db_path) as conn:
           conn.execute(
               "UPDATE atc_inventory SET current_stock=?, last_updated=CURRENT_TIMESTAMP WHERE atc_code=?",
               (new_stock, atc_code)
           )
           conn.commit()
   ```
2. `spis/dashboard/app.py` — new section "Update Stock Levels":
   - Load current inventory from DB (already done via `load_atc_inventory`)
   - Use `st.form` to wrap the inputs (avoids re-running on every keystroke)
   - On form submit: call `update_stock()` for each ATC code
   - Call `st.cache_data.clear()` to force re-assessment
   - `st.rerun()` to refresh the page with new values

### Tests to add
`tests/test_database.py` — add test for `update_stock()`:
- Create temp DB, seed inventory, call update_stock, verify new value in DB

---

## Feature 3: Expiry-Aware Offers System

### Why (the original idea from our session)
This is the most original feature in the whole project. Most pharmacy systems just flag
"expiring soon." SPIS will calculate exactly how many units will expire if unsold,
suggest the optimal discount to clear them, and show the pharmacist how much money
they save vs. letting them expire.

Real problem: OVERSTOCK + approaching expiry = financial loss. The system should
proactively suggest discounts/promotions to move stock before it goes to waste.

This feature requires a new database concept: **inventory batches**. Currently
`atc_inventory` has one row per ATC code with total current_stock. We need to track
multiple batches per ATC code, each with an expiry date and unit cost.

### What to build

#### New DB table: `inventory_batches`
```sql
CREATE TABLE IF NOT EXISTS inventory_batches (
    batch_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    atc_code      TEXT    NOT NULL REFERENCES atc_categories(atc_code),
    batch_number  TEXT    NOT NULL,        -- e.g. "LOT-2024-001"
    quantity      REAL    NOT NULL CHECK (quantity >= 0),
    unit_cost     REAL    NOT NULL CHECK (unit_cost >= 0),   -- cost per unit in local currency
    expiry_date   TEXT    NOT NULL,        -- ISO-8601: YYYY-MM-DD
    received_date TEXT    NOT NULL DEFAULT CURRENT_DATE,
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_batches_atc_expiry
    ON inventory_batches (atc_code, expiry_date);
```

#### Offer suggestion logic (new module: `spis/models/expiry_advisor.py`)
```python
@dataclass(frozen=True)
class ExpiryOffer:
    atc_code: str
    batch_number: str
    quantity: float
    expiry_date: date
    days_to_expiry: int
    forecasted_sales_before_expiry: float
    units_at_risk: float          # quantity - forecasted_sales_before_expiry
    unit_cost: float
    waste_value: float            # units_at_risk * unit_cost
    suggested_discount_pct: float # 0–100
    offer_label: str              # "Clearance — 30% off", etc.
    action: str                   # "discount" | "return_to_supplier" | "donate"
```

**Discount tiers:**
- 60–45 days to expiry → 15% off → "Buy More, Save More"
- 44–30 days → 25% off → "Expiring Soon — Special Price"
- 29–14 days → 40% off → "Clearance Sale"
- 13–7 days → 55% off → "Final Week — Deep Discount"
- <7 days → action = "return_to_supplier" or "donate_to_charity"

**Core formula:**
```
forecast_before_expiry = forecast_daily_demand * days_to_expiry
units_at_risk = max(0, batch_quantity - forecast_before_expiry)
waste_value = units_at_risk * unit_cost
```

**Only generate an offer if `units_at_risk > 0` AND `days_to_expiry <= 60`.**

**ROI logic (show in dashboard):**
- Revenue at full price: units_at_risk * unit_price (unit_price = unit_cost * 1.3 typical margin)
- Revenue with discount: units_at_risk * unit_price * (1 - discount_pct/100)
- Cost of waste (no action): waste_value (you lose unit_cost per unit)
- Saving from discount vs waste: waste_value - max(0, cost_basis - discounted_revenue)
- Show this as: "Offering 30% discount saves you $X vs letting it expire"

#### Dashboard section: "Expiry & Offers"
- Table: Batch | Drug | Qty at Risk | Expires In | Suggested Discount | Action | Est. Saving
- Color coding: red for <14 days, orange for 14-30, yellow for 30-60
- "Generate Shelf Label" button per row (print-ready discount label)
- Summary card: "Total inventory at expiry risk: $X — discounting could recover $Y"

#### Seed data for demo
Add mock batch data to `database.py` `ATC_INVENTORY_SEED` equivalent for batches.
Create batches that expire in 10, 25, 45 days so all tiers are shown in the demo.
```python
BATCH_SEED = [
    # atc_code, batch_number, quantity, unit_cost, expiry_date, received_date
    ("M01AE", "LOT-2024-001", 200, 0.50, "2026-04-15", "2024-10-01"),  # 17 days, clearance
    ("R06",   "LOT-2024-002", 180, 0.35, "2026-04-28", "2024-10-01"),  # 30 days, expiring soon
    ("N02BA", "LOT-2024-003", 80,  0.20, "2026-05-20", "2024-11-01"),  # 52 days, buy more
]
```
Note: expiry dates in the seed should be set relative to ~March 2026 (project date).
Adjust the exact dates when seeding so the demo always shows relevant tiers.

### Files to create/modify
- `spis/data/database.py` — add `inventory_batches` table + seed + helper query
- `spis/models/expiry_advisor.py` — NEW file with ExpiryOffer logic
- `spis/dashboard/app.py` — new "Expiry & Offers" section
- `tests/test_expiry_advisor.py` — NEW tests

---

## Feature 4: Demand Anomaly Detection

### Why
When an unusual event happens (flu outbreak, allergy season spike, pandemic), the
system should automatically detect it and alert the pharmacist — without waiting
for the pharmacist to notice the stock dropping.

### What to build
A continuous anomaly detection layer that runs every time the dashboard loads:

**Algorithm:**
1. For each ATC code, compute: `baseline = rolling_mean_28` (from features_daily.csv)
2. Compute: `recent_demand = mean of last 7 days` (query DB directly for freshest data)
3. Compute: `std = rolling_std_28`
4. Z-score: `z = (recent_demand - baseline) / std`
5. If `z > 2.0` → **SURGE** (unusual high demand)
6. If `z < -2.0` → **SLUMP** (unusual low demand — possible supply issue or seasonal drop)

**Dashboard additions:**
- Orange banner if any SURGE detected: "⚠️ Demand surge detected for R06 (antihistamines)
  — current demand is 2.8x above normal. Consider increasing your next order."
- Adjust risk assessment: if SURGE detected for an ATC code, add a note to the
  risk table: "Forecast may underestimate — demand trending above historical average"
- Anomaly log in the sidebar showing recent anomalies with timestamps

### New module: `spis/models/anomaly_detector.py`
```python
@dataclass(frozen=True)
class AnomalyResult:
    atc_code: str
    z_score: float
    recent_7d_avg: float
    historical_28d_avg: float
    anomaly_type: str   # "SURGE" | "SLUMP" | "NORMAL"
    severity: str       # "MILD" (z>2) | "MODERATE" (z>3) | "SEVERE" (z>4)
    message: str
```

---

## Feature 5: Drug Name NLP Search (uses scispacy)

### Why
spacy and scispacy are listed in requirements.txt but NEVER used anywhere in the
codebase. A GP evaluator will notice this gap immediately. We need to actually use them.

The real use case: a pharmacist types "paracetamol" or "headache medicine" and the
system finds the right ATC code and its risk status.

### What to build
A search box at the top of the dashboard:
- User types any drug name (generic name, brand name, or symptom description)
- System uses scispacy to:
  1. Load the `en_core_sci_sm` model (or `en_ner_bc5cdr_md` for drug-specific NER)
  2. Process the query text through the NLP pipeline
  3. Extract medical entities (drug names)
  4. Fuzzy-match against the `drugs` table (57 drugs in DB)
  5. Return the matching drug(s), their ATC code, and the current risk assessment

### How the matching works
```python
import spacy
import scispacy
from spacy.matcher import PhraseMatcher

# Load model once at startup
nlp = spacy.load("en_core_sci_sm")

# Build matcher from the drugs catalog
def build_drug_matcher(drug_names: list[str]):
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    patterns = [nlp.make_doc(name.lower()) for name in drug_names]
    matcher.add("DRUG", patterns)
    return matcher
```

Fallback if scispacy model not installed: use simple fuzzy string matching with
`difflib.get_close_matches(query, drug_names, n=3, cutoff=0.6)`.

### Dashboard implementation
```
[Search drug or symptom...] [🔍 Search]

Results:
 Drug: Paracetamol (N02BE — Anilides)
 Risk: 🔴 CRITICAL (1.9 days of stock)
 Order Qty: 42 units
 [View Details]
```

### Files to create
- `spis/data/drug_search.py` — NEW: NLP search logic, loads scispacy, matcher
- `spis/dashboard/app.py` — add search box at top of page

---

## Feature 6: Financial / Waste Dashboard

### Why
Pharmacy owners are businesspeople. Every decision is ultimately financial.
Showing financial impact (cost of waste, cost of stockouts, savings from the system)
elevates SPIS from a "tech project" to a "business solution."

### What to build
New dashboard tab or page: "Financial Overview"

**Sections:**
1. **Capital tied in inventory** — total value of all stock on hand
   - `SUM(batch.quantity * batch.unit_cost)` per ATC code
   - Bar chart: which ATC code has most capital tied up
   - Highlight OVERSTOCK in red: "You have $X tied in overstock that won't be
     needed for 30+ days"

2. **Waste risk** — value of inventory at risk of expiring unsold
   - Sum of `waste_value` from ExpiryOffer calculations (Feature 3)
   - Big number card: "At current sales pace, $X of inventory may expire this month"

3. **Stockout cost estimate** — cost of being CRITICAL
   - For each CRITICAL item: estimate lost revenue = daily_demand * days_already_stockout * avg_unit_price
   - Caveat in UI: "Estimated — actual lost sales may vary"

4. **System ROI story** (for the GP demo)
   - "Without SPIS: order based on gut feel → overstock costs $X in waste per year"
   - "With SPIS: data-driven ordering → estimated waste reduction: $Y"
   - This can use mock numbers but should be framed as "based on industry averages"
   - Industry reference: pharmacies waste 2–5% of inventory to expiry; SPIS aims to cut this

---

## Feature 7: Feature Importance Chart

### Why
The XGBoost model is the core of SPIS. Evaluators will ask "why does the model
predict what it predicts?" The dashboard should answer this visually.
The feature importance data already exists in `get_feature_importance()` in
`spis/models/forecaster.py` — it just needs to be displayed.

### What to build
A horizontal bar chart in the dashboard:
- X axis: importance score (0 to 1)
- Y axis: feature names (sorted descending by importance)
- Top 10 features only (full list of 36 would be cluttered)
- Color the bars by feature type:
  - EMA features → blue
  - Lag features → green
  - Calendar features → orange
  - Derived features → purple
- Caption: "Top features show the model relies most on recent trend (EMA)
  rather than calendar effects — consistent with demand forecasting literature."

### Code changes needed
1. `scripts/train_model.py` — save feature importances to `models/feature_importance.json`
   alongside `metrics.json` (already saves metrics)
2. `spis/dashboard/app.py` — load `feature_importance.json` and render bar chart

---

## Feature 8: Sidebar Filters + Alerts Panel

### Why
The dashboard shows everything at once. When there are 2 CRITICAL items, the
pharmacist has to scan through the table to find them. Critical alerts should be
impossible to miss.

### What to build

**Persistent sidebar:**
- Filter by risk tier (checkboxes: CRITICAL, LOW, OK, OVERSTOCK)
- Filter by drug system (Musculoskeletal, Nervous, Respiratory)
- Slider: "Show items with less than N days of stock"
- Toggle: "Show critical only"

**Alert banner (top of page, only when CRITICAL items exist):**
```
🚨 URGENT: 2 drug categories require immediate ordering
   • N02BE (Paracetamol group) — 1.9 days of stock remaining
   • R03 (Respiratory) — 2.1 days of stock remaining
   [Order Now] button (downloads CSV order form)
```

**Alert logic:**
- CRITICAL: red banner, always shown at top
- LOW: orange info box, collapsible
- OVERSTOCK: blue info box, "Consider reducing next order or running promotions"

---

## Feature 9: ABC / Pareto Analysis

### Why
ABC analysis (a standard inventory management technique) classifies items into:
- A items: top 20% of items by volume/value → 80% of total demand
- B items: next 30% → 15% of demand
- C items: bottom 50% → 5% of demand
This demonstrates understanding of inventory management theory, not just ML.

### What to build
A new dashboard section or tab: "ABC Analysis"
- Calculate total forecasted demand per ATC code (already available)
- Sort by demand descending
- Assign A/B/C tier based on cumulative % of total demand
- Pareto chart: bar chart (demand per ATC) + cumulative line (% of total)
- Table: ATC code | Drug name | Total Demand | % of Total | Cumulative % | ABC Tier
- Business insight: "A-tier items (R06, N02BE) need tighter stock control and more
  frequent reordering. C-tier items can be ordered less frequently."

---

## Feature 10: Automated PDF Report

### Why
The pharmacist needs something they can email to their supplier or show to their
manager. A one-click PDF report makes SPIS produce a tangible, professional output.

### What to build
"Generate Report" button in the dashboard.
Output: a 2-3 page PDF containing:
1. Header: pharmacy name, date, report period
2. Executive summary: CRITICAL/LOW/OK/OVERSTOCK counts + key numbers
3. Risk table (same as dashboard table but formatted for print)
4. Order recommendations table: what to order and how much
5. Expiry alerts (if any batches flagged)
6. Footer: "Generated by SPIS v0.1.0"

**Library to use:** `fpdf2` (lightweight, pure Python, no LaTeX)
```
pip install fpdf2
```

### New file: `spis/reports/pdf_generator.py`
```python
from fpdf import FPDF

def generate_risk_report(results: list[RiskAssessment], output_path: str) -> None:
    pdf = FPDF()
    pdf.add_page()
    # ... build the report ...
    pdf.output(output_path)
```

### Dashboard integration
```python
if st.button("Download PDF Report"):
    pdf_bytes = generate_risk_report_bytes(results)
    st.download_button("Save PDF", data=pdf_bytes, file_name="spis_report.pdf", mime="application/pdf")
```

---

## Dashboard Architecture After These Changes

The current single-page dashboard becomes a **multi-page Streamlit app**:

```
spis/dashboard/
    app.py                  ← main page (overview, risk table, alerts)
    pages/
        1_History_Forecast.py   ← Feature 1
        2_Stock_Update.py       ← Feature 2
        3_Expiry_Offers.py      ← Feature 3
        4_Financials.py         ← Feature 6
        5_Analytics.py          ← Features 7, 9 (feature importance, ABC)
        6_Search.py             ← Feature 5 (NLP search)
```

Streamlit multi-page apps work by putting files in a `pages/` subdirectory.
Each file becomes a separate page in the left sidebar navigation.
All pages share the same cached model and encoder via `@st.cache_resource`.

---

## New Database Tables Summary

After Phase 9 we'll have 5 tables (currently 4):

| Table | Rows | Purpose |
|-------|------|---------|
| atc_categories | 8+ | ATC classification dimension |
| drugs | 57+ | Clinical drug catalog |
| sales | 424,080 | Time-series sales fact table |
| atc_inventory | 8+ | Current stock per ATC code |
| inventory_batches | N | Per-batch stock with expiry + cost (NEW) |

---

## New Python Modules Summary

| Module | Purpose |
|--------|---------|
| `spis/models/expiry_advisor.py` | ExpiryOffer dataclass + discount logic |
| `spis/models/anomaly_detector.py` | Z-score anomaly detection per ATC |
| `spis/data/drug_search.py` | NLP drug name → ATC code lookup |
| `spis/reports/pdf_generator.py` | PDF report generation via fpdf2 |

---

## New Test Files Summary

| File | What to test |
|------|-------------|
| `tests/test_expiry_advisor.py` | ExpiryOffer calculation, discount tiers, waste_value formula |
| `tests/test_anomaly_detector.py` | Z-score logic, SURGE/SLUMP/NORMAL classification |
| `tests/test_drug_search.py` | Drug name matching, unknown name fallback, case-insensitivity |

---

## New Dependencies

Add to `requirements.txt`:
```
fpdf2>=2.7        # PDF report generation (Feature 10)
plotly>=5.0       # Interactive charts (Features 1, 6, 7, 9)
```

Note: spacy and scispacy are already in requirements.txt. When using scispacy, the
NLP model must be downloaded separately at setup time:
```
pip install https://s3-us-west-2.amazonaws.com/ai2-s3-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz
```
Document this in README and project_summary.txt. The search feature should degrade
gracefully if the model is not installed (fall back to fuzzy string match).

---

## Key Rules for This Project (DO NOT FORGET)

1. NO Co-Authored-By attribution in any commit messages
2. NO mention of AI tooling anywhere (commits, code, docs)
3. Team members: Saleh, Nawaf, Mazen, Ali — team does NOT have Claude Code
4. Keep all docs self-explanatory for teammates
5. Always update `docs/project_summary.txt` after any phase
6. Windows terminal: avoid Unicode box-drawing chars (cp1252) — use ASCII only
7. Python 3.11.9 only (Python 3.14 installed but breaks scispacy)
8. Activate venv: `source venv/Scripts/activate` (bash) or `.\venv\Scripts\activate` (PowerShell)
9. Test DB is separate from `data/inventory.db` — use `tmp_path` fixture in pytest

---

## GP Defense Narrative After Phase 9

If you implement Features 1–5, the GP defense story becomes:

"SPIS is not just a forecasting tool — it is a complete inventory intelligence system.
It predicts demand 30 days ahead, flags stockout risk in real time, detects demand
surges automatically, and — uniquely — calculates which overstock items are heading
toward expiry and generates discount offers to recover their value before they are lost.
The system serves three stakeholders: the pharmacist (stock alerts, order recommendations),
the pharmacy owner (financial waste reduction, ROI tracking), and the patient (cheaper
medication through data-driven clearance offers)."

That is a strong, coherent story with a clear value proposition at every level.
