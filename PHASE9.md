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

- Total items pending: 2 (items 1-8 done; refill reminders deferred, not counted)
- Last updated: 2026-05-07
