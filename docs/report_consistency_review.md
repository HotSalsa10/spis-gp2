# GP Report Consistency Review (Ch1–Ch7)

_For the SPIS team — pre-submission cross-chapter audit._
_Author: review pass, 2026-05-11._

This document records a careful read of Chapters 1 through 7 of the GP report,
checking how the older chapters (Ch1–4, drafted in GP1 / early GP2) line up
with the final implementation as captured in Ch5–7 and the current codebase.

The goal is to flag anything a committee member could catch by reading the
chapters back-to-back. Nothing here changes the code or the chapters — this
is a checklist for the team to triage before submission.

---

## Overall flow: solid spine, but the joint between Ch3–4 and Ch5–7 has cracked

At the narrative level the arc still reads fine: problem → literature →
requirements → design → implementation → testing → conclusion. A committee
member skimming for structure will be satisfied.

The problem is that Ch3 and Ch4 appear to have been frozen around the end of
GP1 / mid-GP2, while the codebase has moved on substantially since
(Phase 8.5 and Phase 9 added expiry, alerts, suppliers, POs, batch
receive/recall, multi-page dashboard, recursive forecast, etc.). Ch5–7 reflect
the current code accurately. So a reader **comparing** the FR/design pages
against the implementation chapter will hit direct contradictions.

---

## Critical contradictions a committee will see

These are the highest-risk items — most likely to draw a question or a
deduction.

### 1. Risk tier thresholds — direct contradiction

- Ch3 FR-4.2 **and** Ch4 §4.5.3 specify
  `CRITICAL < 3, LOW 3–7, OK 7–30, OVERSTOCK ≥ 30`.
- Ch5 §5.4.4 specifies (correctly, matching the code)
  `CRITICAL < 7, LOW < 14, OK < 90, OVERSTOCK ≥ 90`.

A reader doing a traceability check (Ch3 → code → Ch5) will catch this
immediately.

### 2. Database has 8 tables, not 4

- Ch3 FR-1.2 and Ch4 §4.2 ERD both list four tables
  (`atc_categories`, `drugs`, `sales`, `atc_inventory`).
- Ch5 §5.3.1 lists eight (adds `inventory_batches`, `alerts`, `suppliers`,
  `purchase_orders`).

Ch4's ERD diagram would need expansion to match reality.

### 3. Dashboard is multi-page, not single-page

- Ch3 FR-6.1–FR-6.5 and Ch4 §4.4.1 describe a single Streamlit page
  (`spis/dashboard/app.py`) with four sections.
- Ch5 §5.5.1 documents Overview + 8 sub-pages with batch receive/recall,
  alerts, POs, catalog, supplier management, etc.

### 4. Forecast loop strategy — opposite of what Ch4 says

- Ch4 §4.5.3 step b: _"Lag / rolling / EMA features **held constant** from
  the seed row (best available estimate)"._
- Ch5 §5.4.3 (correct): a **recursive** loop — each prediction is appended
  to a 365-day history buffer; lag, rolling, and EMA features are
  **recomputed** from that buffer before the next step.

This is the opposite of the original design and should be acknowledged
explicitly.

### 5. Ch3 has no FRs for half the Ch5 features

Ch3 contains no functional requirements for:

- Expiry-aware discount advisor (Page 3)
- Alert engine and notification center (Page 6)
- Supplier directory (Page 7 sections D & E)
- Purchase order generator + PDF export (Page 8)
- Batch receipt and recall (Page 5)
- Catalog management — add drug / register ATC (Page 7)
- Stock audit CSV
- Inventory turnover KPI (Overview + Analytics)
- Seasonal decomposition, YoY growth, rolling trend (Analytics)
- ABC / Pareto analysis (Analytics)
- P10–P90 bootstrap forecast band (Page 1)

Ch5–7 describe all of these as delivered. The committee will notice the gap
when they try to map features back to requirements via Ch3 §3.6's
traceability matrix.

---

## Smaller but real drift

### 6. Test count

- Ch1 Phase 7 deliverable: _"75 automated tests"_.
- Ch3 NFR-2.1: _"minimum of 75 automated unit and integration tests"_.
- Ch6 reports **182 tests across 14 files** (verified).

Not a hard contradiction — the floor was met 2.4× — but the Ch1 phase table
reads as stale.

### 7. Phase timeline ends at 8

- Ch1 §1.4 lists 8 phases, ending at "GP Report".
- Ch5–7 reference Phase 8.5 and Phase 9 work throughout.

The phase table doesn't acknowledge them.

### 8. MAE target vs achievement

- Ch1 Obj 3 sets a target of _"MAE below 2.0 units per day"_.
- Achieved MAE = **1.06** — exceeds the target by roughly 2×.

Not a contradiction, but Ch5 never quotes the original target, so the
over-delivery is never called out as a strength.

### 9. GridSearchCV grid

- Ch4 §4.5.2 lists
  `n_estimators=[200, 500], max_depth=[4, 6], learning_rate=[0.05, 0.1]`.
- Production code uses
  `n_estimators=[500, 800], max_depth=[6, 8], learning_rate=[0.03, 0.05]`,
  plus `reg_alpha=[0, 0.1]` (Ch4 says `[0]`).

Small but a direct contradiction if a committee member reads both
chapters carefully.

### 10. API factory attachment pattern

- Ch4 §4.4.2 says model artifacts are attached to `app.extensions["spis_model"]`.
- Actual code stores them at `app.config["_MODEL"]` and `app.config["_ENCODER"]`.

Cosmetic — but factually wrong against the source.

### 11. Use Case UC-1 description is stale

Ch3 §3.5 describes the dashboard flow as 4 cards + risk table + order
chart + medications table only. The current dashboard has all that plus
eight more pages (history/forecast, stock update, expiry offers, analytics,
receive stock, alerts, manage catalog, purchase orders). A reader walking
through UC-1 will be surprised by Ch5.

### 12. Holidays

- Ch1 / Ch2 / Ch4 mention Turkish holidays only (consistent with the
  Kaggle dataset's origin).
- Ch5 explains the deliberate Saudi-vs-Turkey split: training pipeline
  uses `holidays.Turkey(...)` (because the training data is Turkish),
  but the live forecast loop uses `holidays.SaudiArabia(...)` (because
  the pilot pharmacy is in Saudi). The split is well-explained in Ch5
  but not anticipated anywhere in Ch1–4.

---

## What holds up well

- **Ch1's problem statement and motivation** still describe the real
  project accurately. The "small pharmacy, no ML, manual ordering" framing
  is sound.
- **Ch2's literature review** is implementation-agnostic and remains
  solid — it doesn't depend on Phase 9 features. The comparison table at
  §2.2.4 still positions SPIS correctly.
- **Ch3's NFRs** (performance, reliability, scalability, portability,
  maintainability) are all met or exceeded.
- **Team roles** are consistent between Ch1 §1.5 and Ch7's reflections.
- **"Lightweight / local-only / SQLite / no cloud"** thesis is consistent
  across all seven chapters.
- **57 drugs across 8 ATC categories** — consistent in every chapter.

---

## Three options before submission, by effort

### Option A — Minimum (~30 min, low risk)

Add **one paragraph** at the top of Ch5 saying "the design in Chapter 4
evolved during Phase 8.5 and Phase 9; the deviations are summarised below."
Then explicitly call out:

- Tier thresholds were re-calibrated from `(3, 7, 30)` to `(7, 14, 90)`
  to match community-pharmacy lead times (typically 3–7 days from order
  to delivery).
- The forecast loop became recursive instead of holding lag/rolling
  features constant, so 30-day forecasts capture day-to-day variation
  rather than converging to a flat line.

That single paragraph defuses 80% of the committee questions in this
review.

### Option B — Medium (~2 h)

Edit Ch3 FR-4.2 and Ch4 §4.5.3 directly so the tier numbers and the
forecast algorithm match the code. Update Ch4 §4.5.2 to the production
grid. These three localised edits remove the most damaging contradictions.

### Option C — Full refresh (most marks, most effort)

Refresh Ch3 with new functional requirements for the Phase 9 features:

- **FR-7 Expiry Advisor** — two-factor discount tier per batch
- **FR-8 Alerts** — idempotent low-stock + expiry notifications
- **FR-9 Suppliers & Purchase Orders** — directory + PDF PO export
- **FR-10 Batch Lifecycle** — receive / recall + audit CSV
- **FR-11 Catalog Management** — add drug / register ATC / assign supplier

Expand Ch4's ERD to all 8 tables. Update Ch4 §4.4.1 package structure to
include all the new modules (`expiry_advisor.py`, `expiry_finance.py`,
`alert_engine.py`, `decomposition.py`, `inventory_kpi.py`,
`po_generator.py`, `catalog.py`, `_shared.py`, the 8 dashboard pages).
Refresh the Ch1 phase table to include Phase 8.5 and Phase 9.

Best from a marks perspective; takes the most time.

---

## TL;DR for the team (internal-consistency review)

The report is **submittable as-is** — the narrative holds, the technical
content is correct in Ch5–7, and the over-delivery story (182 tests vs 75
target, MAE 1.06 vs 2.0 target, 8 tables vs 4, multi-page dashboard vs
single-page) is genuine. But Ch3 and Ch4 contain frozen design decisions
that no longer match the code. A careful committee member **will** find at
least items 1 (tier thresholds) and 4 (forecast loop) by reading
sequentially. Spending half an hour on Option A above is the
highest-leverage edit available before submission.

---

# Part 2 — Committee Guidelines Compliance Audit

A second pass through Ch1–7 against the official document
_"Graduation Project Guidelines — Software"_. This audit asks a different
question from Part 1: "does each chapter contain everything the committee
expects it to contain, regardless of whether the content is consistent?"

GP1 acceptance note: Ch1–4 were submitted and accepted at the GP1 milestone.
GP1 acceptance is _directional_ approval — it confirms the content was
acceptable at that time, but at GP2 the same committee re-reads the full
Ch1–7 report. Missing sections that the guidelines require explicitly will
still be flagged at GP2 even if GP1 didn't enforce them. The recommendation
below is to **add** missing sections rather than to remove or restructure
GP1 content.

---

## Chapter 1 — Introduction

| Guideline item | Status |
|----|----|
| Motivating background | ✓ §1.1 |
| Brief related-work discussion in intro | ⚠️ glanced at (ML / XGBoost) but no named prior work |
| **Overview of chapter contents** | ✗ missing |
| Problem Definition | ✓ §1.2 |
| Aims and Objectives | ✓ §1.3 |
| **Project Timeline as Gantt chart** | ✗ table at §1.4 only — guidelines require Gantt chart drawn in MS Project or equivalent |
| **Team Qualifications as mini-resumes** | ✗ §1.5 is a 4-row role table — guidelines: _"mini-resume… work experience, similar projects, references, training, education"_ |
| **Chapter Conclusions section** | ✗ entirely missing |

## Chapter 2 — Literature Review

| Guideline item | Status |
|----|----|
| **Chapter introduction** (recap of Ch1, focus statement, overview) | ✗ missing |
| Background | ✓ §2.1 |
| Related work categorised | ✓ §2.2 |
| Short intro paragraph before each category + closing recap | ⚠️ partial |
| Comparison table | ✓ §2.2.4 |
| **Proper chapter Conclusion** (recap background + related work + research gap + bridge to Ch3) | ⚠️ §2.3 "Research Gap" exists but is not labelled "Conclusion" and does not explicitly mention Ch3 |

## Chapter 3 — Requirements Analysis

| Guideline item | Status |
|----|----|
| **How requirements were elicited** (interviews / questionnaires / observations) | ✗ missing |
| Functional requirements | ✓ §3.4.1 (stale — see Part 1) |
| **NFRs following committee Figure 1 classification** (Product → Efficiency / Dependability / Security / Usability; Organizational → Environmental / Operational / Development; External → Regulatory / Ethical / Legislative) | ✗ your NFR-1…NFR-6 don't map to this taxonomy |
| **Use case diagram (UML)** | ✗ missing — guidelines require both diagram **and** descriptions |
| Use case descriptions | ✓ §3.5 |
| **Project Management Plan with Gantt chart drawn in MS Project** | ✗ missing entirely |

## Chapter 4 — Design

| Guideline item | Status |
|----|----|
| System Architecture diagram | ✓ §4.1 |
| Communication pattern explicitly named | ✓ "layered pipeline" |
| **Database design with data dictionary** | ⚠️ have ERD; data dictionary (column → type → constraints → description per table) missing |
| Modular decomposition with class diagrams | ⚠️ have package structure and dataclass listing; no UML class diagram |
| System organisation (sequence / state / activity diagrams) | ⚠️ have data-flow diagram; no sequence, state, or activity diagrams |
| Algorithm pseudocode | ✓ §4.5 |
| **Alternative Designs/Methods section** | ✗ missing — guidelines explicitly require discussion of alternatives + justification |
| **GUI Design proposal** (mockups / wireframes) | ✗ missing as a section |

## Chapter 5 — Implementation

| Guideline item | Status |
|----|----|
| **Hardware Requirements + reasons** | ✗ missing as a section |
| Software Requirements | ⚠️ deps table at §5.1 but no explicit "we chose X because Y" prose |
| Programming language justification | ⚠️ Python 3.11 mentioned with scispacy reason only |
| **State of the art and comparison of tools** | ✗ missing |
| **Deployment and Installation steps** | ✗ missing as a dedicated subsection |
| Data Structures Description | ✓ §5.3.1 |
| Procedures Description | ✓ §5.3.2 / §5.4 / §5.5 |
| **GUI Description with screenshots** | ⚠️ pages described textually, no screenshots |
| **Unexpected problems encountered + how resolved** (in Ch5, not Ch6) | ⚠️ the defects table lives in Ch6 §6.6 — guidelines locate it in Ch5 |
| No flowcharts in Ch5 | ✓ |
| Code snippets brief | ✓ |

## Chapter 6 — Testing

| Guideline item | Status |
|----|----|
| Code coverage testing | ✓ |
| Condition testing | ✓ |
| **Path testing explicitly named** | ⚠️ done implicitly, not labelled |
| At least one test case per implemented task | ✓ (182 tests) |
| Show error results + why + how overcome | ✓ §6.6 |
| GUI / database / integration coverage | ⚠️ database ✓, integration ✓, GUI only manual |

## Chapter 7 — Conclusion

✓ Compliant. Summary, requirements-met, shortfalls, future work all present.

## Cross-cutting issues

### 1. References — major structural mismatch
Guidelines explicitly state:
> _"Note that you have only a **single Reference section** for the whole report and it should grow as you progress in writing the remaining chapters."_

Current state: Ch1, Ch2, Ch5, Ch7 each have their own References section;
Ch3 and Ch4 have none at all. This is the single most visible structural
deviation and will be obvious on a flip-through.

### 2. Appendices chapter — missing
Guidelines §VIII requires an Appendices chapter holding the complete source
code: _"Complete source code should be added separately on the appendix
section along with CD"._

### 3. IEEE citation style
Style itself is fine where references exist — only the multi-list structure
(item 1) is wrong.

---

## Combined severity ranking (Part 1 + Part 2)

**Tier A — visible deductions, easy to fix:**
1. Consolidate references into one section at the end.
2. Add Team Qualifications mini-resumes in Ch1 §1.5.
3. Add chapter Conclusions to Ch1 (and re-label / extend §2.3 as Ch2's Conclusion).
4. Add an elicitation paragraph to Ch3 §3.1 or §3.3.
5. Fix the **tier-threshold contradiction** between Ch3/Ch4 and Ch5 — either
   via the "Design Evolution" paragraph at the top of Ch5 (safer) or by
   editing Ch3 FR-4.2 and Ch4 §4.5.3 directly.

**Tier B — structural, needs UML / diagram work:**
6. Use case diagram for Ch3.
7. Gantt chart for Ch1 §1.4 (and Ch3 Project Management Plan).
8. Alternative Designs/Methods section in Ch4.
9. Data dictionary table for Ch4.

**Tier C — polish:**
10. Hardware Requirements paragraph in Ch5.
11. Deployment / Installation subsection in Ch5.
12. Dashboard screenshots in Ch5 GUI Description.
13. Path-testing label in Ch6.
14. State-of-the-art tool comparison in Ch5.
15. Add Phase 8.5 / Phase 9 to Ch1 §1.4 timeline.
16. Update Ch1 §1.5 team-role descriptions to match Ch7 reflections (architecture / API / tests / dashboard).

A concrete action list with file pointers and effort estimates is in the
companion document `report_suggested_fixes.md`.
