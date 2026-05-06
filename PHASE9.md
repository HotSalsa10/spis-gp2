# Phase 9 — "Make It Smart" (Professor Feedback Round)

> **Goal:** address the prof's "isn't actually smart" critique by making the existing
> ML core visible and adding the operational loop (receive -> alert -> order -> recall).
>
> **Background:** SPIS already has XGBoost forecasting (MAE 1.06, beats naive 4.23),
> risk tiers, expiry-tiered discounts, ABC analysis, 94 tests. The prof's reaction is
> mostly a *framing* problem plus three real gaps (operational loop, financial impact,
> drug-name labels). Most "new" items below are extensions of what already exists.

---

## Instructions for whoever is executing this file

1. Work top-to-bottom. Items are ordered by **defense impact per hour**.
2. **As soon as an item is fully done (code + tests + docs/project_summary.txt updated), DELETE that whole section from this file.** Do not just check it off — remove it. The file shrinks as Phase 9 progresses, so what's left is always "what's still pending."
3. After every deletion, update the "Status snapshot" line at the bottom.
4. If an item turns out to be wrong or out-of-scope mid-implementation, replace its section with a one-line "SKIPPED: <reason>" entry instead of deleting silently.
5. Do NOT add Co-Authored-By attribution to commits. Do NOT mention AI tooling anywhere in the codebase, commits, or docs. The team does not use Claude Code.
6. Each item below already states the files to touch, the approach, and the test bar. Stay surgical — no adjacent refactors unless the section explicitly calls for one.
7. Windows terminal is cp1252 — keep all written code/docs ASCII-only (no Unicode box-drawing or emoji).

---

## 6. Notification Center (low stock + expiry alerts)  [1 day]  Rating 8/10

**Why:** turns the dashboard from passive ("here are tier counts") to active
("you have 3 unacknowledged alerts").

**Approach:**
1. New table in `spis/data/database.py`:
   ```
   alerts (
       alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
       alert_type TEXT,  -- 'LOW_STOCK' | 'EXPIRY' | 'RECALL'
       atc_code TEXT,
       batch_number TEXT,  -- nullable
       severity TEXT,  -- 'CRITICAL' | 'WARNING' | 'INFO'
       message TEXT,
       created_at TEXT DEFAULT CURRENT_TIMESTAMP,
       acknowledged_at TEXT  -- nullable
   )
   ```
2. Helper `spis/models/alert_engine.py` — pure functions that take risk
   assessments + expiry assessments and emit a list of `Alert` dataclasses.
   Idempotent: if an open alert already exists for the same key, skip.
3. New page `spis/dashboard/pages/6_Alerts.py`:
   - Top: count tiles (open / critical / warnings).
   - Feed: timestamped alert rows, severity badge, "Acknowledge" button per row.
   - Filter: severity + alert_type + acknowledged toggle.
4. Run `alert_engine.refresh()` whenever the dashboard loads or when stock/batches change.

**Files:** `spis/data/database.py` (alerts table + helpers), `spis/models/alert_engine.py` (new),
`spis/dashboard/pages/6_Alerts.py` (new), `tests/test_alert_engine.py` (new).
**Tests:** 8+ tests — generation from each risk tier, dedup behaviour, acknowledge flow,
expiry-driven alerts.
**Done when:** changing stock to 5 units triggers a CRITICAL alert visible on Alerts page,
and acknowledging it removes it from "open" count.

---

## 7. Seasonal decomposition + YoY chart  [1 day]  Rating 8/10

**Why:** looks like a Bloomberg terminal — non-technical reviewers read this as "smart."

**Approach:**
1. Add `statsmodels>=0.14` to `requirements.txt` (already a transitive dep of scipy stack).
2. New helper `spis/models/decomposition.py`:
   `decompose(series, period=365)` -> dict with `trend`, `seasonal`, `residual` arrays.
   Wraps `statsmodels.tsa.seasonal.seasonal_decompose(model='additive')`.
3. New panel on `pages/4_Analytics.py` below ABC:
   - ATC selector
   - Three small line charts stacked: trend, seasonal, residual (Plotly subplots).
   - Caption explains: *"Trend = long-term direction; Seasonal = repeating pattern;
     Residual = unexplained noise. Low residual = the model captures the signal well."*
4. Second panel: **YoY Growth %** by ATC code — bar chart of `(this_year - last_year) / last_year`
   computed from the daily features CSV.

**Files:** `spis/models/decomposition.py` (new), `tests/test_decomposition.py` (new),
`spis/dashboard/pages/4_Analytics.py`.
**Tests:** 4 tests — additive decomposition reconstructs series, period validation,
NaN handling, output shape.
**Done when:** Analytics page has a 3-panel decomposition + YoY chart, both reactive to ATC selection.

---

## 8. Manage Catalog (add drug + add ATC)  [0.5 day]  Rating 7/10

**Why:** proves the pharmacy-agnostic scalability story is real, not academic.

**Approach:**
1. New page `spis/dashboard/pages/7_Manage_Catalog.py`:
   - Section A: read-only table of existing ATC categories with drug counts.
   - Section B: form "Add Drug" — name, ATC code (dropdown of existing), unit, is_critical.
   - Section C: form "Add ATC Code" — calls existing `register_atc.py` logic via import.
     Shows clear warning: *"After registering, upload sales history (`scripts/ingest_data.py`)
     and retrain (`scripts/train_model.py`). The forecaster cannot predict for new ATC codes
     until both steps are complete."*
2. Wrap `scripts/register_atc.py` core logic into `spis/data/catalog.py:add_atc_code(...)`
   and `spis/data/catalog.py:add_drug(...)` so both CLI and UI share one path.

**Files:** `spis/data/catalog.py` (new), `spis/dashboard/pages/7_Manage_Catalog.py` (new),
`scripts/register_atc.py` (refactor to use new helpers), `tests/test_catalog.py` (new).
**Tests:** 5+ tests — add_drug happy path, duplicate name rejection, unknown ATC rejection,
add_atc_code success, idempotent re-registration.
**Done when:** demo can add "Naproxen 500" under M01AE without touching code.

---

## 9. Suppliers + Purchase Order PDF  [1 day]  Rating 8/10

**Why:** closes the loop — turns model recommendations into a sendable document.

**Approach:**
1. Schema additions in `spis/data/database.py`:
   ```
   suppliers (supplier_id PK, name, email, phone, lead_time_days, notes)
   ```
   Add nullable `supplier_id` FK to `drugs` (or to `inventory_batches`, decide one).
   Seed 3-4 fake suppliers.
2. New helper `spis/models/po_generator.py`:
   - Group risk-classified ATC codes (CRITICAL + LOW) by primary supplier.
   - Build a PO dict per supplier: header, line items (drug name, batch suggestion,
     qty, unit cost, total), totals.
3. PDF generator using ReportLab (already used in `scripts/export_committee_pdf.py`):
   `generate_po_pdf(po_dict) -> bytes`. Reuse existing styles.
4. New page `spis/dashboard/pages/8_Purchase_Orders.py`:
   - Table of suggested POs grouped by supplier (collapsible).
   - "Generate PDF" button per supplier -> `st.download_button`.
   - "Mark as Sent" button -> stores PO in a `purchase_orders` table for history.

**Files:** `spis/data/database.py` (suppliers + purchase_orders tables),
`spis/models/po_generator.py` (new), `spis/dashboard/pages/8_Purchase_Orders.py` (new),
`tests/test_po_generator.py` (new).
**Tests:** 6+ tests — grouping logic, totals math, empty supplier handling, PDF byte output non-empty.
**Done when:** Purchase Orders page shows 2-3 grouped supplier POs based on current risk state,
clicking download yields a valid PDF.

---

## 10. Inventory turnover ratio  [0.5 day]  Rating 7/10

**Why:** real pharmacy KPI. Adds a second analytical lens beyond DoS tier.

**Approach:**
1. Helper `spis/models/inventory_kpi.py:compute_turnover(db_path, period_days=365)`:
   Returns `{atc_code: {"units_sold": float, "avg_inventory": float, "turnover": float,
   "classification": str}}` where classification is `Healthy 6-12x | Slow <4 | Excessive >24`.
2. Surface in two places:
   - Overview medications table: new "Turnover" column with classification badge.
   - Analytics page: new KPI strip with avg/min/max turnover across ATC codes.
3. Tooltip / caption explains the formula and thresholds.

**Files:** `spis/models/inventory_kpi.py` (new), `tests/test_inventory_kpi.py` (new),
`spis/dashboard/app.py`, `spis/dashboard/pages/4_Analytics.py`.
**Tests:** 5 tests — turnover formula, classification thresholds, empty-period handling,
zero-inventory edge case, multi-ATC aggregation.
**Done when:** every drug in the medications table has a turnover number and a Healthy/Slow/Excessive label.

---

## 11. Refill reminders — DEFERRED to Future Work

**Do not build.** The data model has no patient/customer entity; faking one weakens
credibility and pulls scope outside "inventory system." Add a paragraph in
`docs/report/ch7_conclusion.md` (or wherever the Future Work section lives):

> *"Prescription refill reminders require integration with a patient management
> system and a notification gateway (SMS/email), both outside the inventory MVP scope.
> The forecasting and risk modules in SPIS provide the supply-side foundation that a
> future patient-facing module would consume."*

**Done when:** Future Work paragraph is added to Chapter 7.

---

## After every item

- Update `docs/project_summary.txt` (team reads this to stay in sync).
- Run `pytest` — all tests must pass before deletion from this file.
- Commit with `feat:` or `fix:` prefix, no AI attribution.
- Delete the completed section from this file. Update status snapshot below.

---

## Status snapshot

- Total items pending: 5 (items 1, 2, 3, 4, 5 done; refill reminders deferred, not counted)
- Last updated: 2026-05-06
