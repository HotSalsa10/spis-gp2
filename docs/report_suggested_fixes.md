# GP Report — Suggested Fixes

_Companion to `report_consistency_review.md`. This file gives the team a
concrete, ordered to-do list with target locations and effort estimates._

## Ground rules

- **Ch1–4 were accepted at GP1.** Treat them as authoritative for content
  that was approved at GP1, but the **full Ch1–7 report is re-read at
  GP2**, so missing committee-required sections must still be added.
- **Prefer additive edits** over restructuring. Don't remove or reorganise
  what GP1 accepted; do add sections that were never there.
- Where the implementation in Ch5 contradicts Ch3/Ch4 design, **add a
  "Design Evolution" paragraph at the top of Ch5** instead of editing
  Ch3/Ch4. Ch3/Ch4 then represent the GP1 design; Ch5 documents the GP2
  refinement and why.

Each item below lists: _Problem → Location → Action → Effort → Risk_.

---

## TIER A — Highest priority (must fix for GP2 submission)

### A1. References must be one consolidated section at the end

- **Problem.** Guidelines §IX: _"a single Reference section for the whole
  report"_. Current: Ch1, Ch2, Ch5, Ch7 each have their own list; Ch3/Ch4
  have none.
- **Location.** Whole report.
- **Action.** Create a new file `docs/references.md` (or a `Bibliography`
  section at the end of Ch7) containing every cited work numbered IEEE
  style. Walk through each chapter and renumber inline citations to match
  the consolidated list. Delete the per-chapter "References" subheadings;
  keep only inline `[N]` markers in the body text.
- **Effort.** ~1–1.5 h.
- **Risk.** Low. This is structural alignment, not content change.

### A2. Add Team Qualifications mini-resumes (Ch1 §1.5)

- **Problem.** Current §1.5 is a 4-row role table. Guidelines: _"like a
  mini-resume… work experience, similar projects, references, training,
  and education that shows familiarity with the project for each member"_.
- **Location.** Ch1 §1.5.
- **Action.** For each of Saleh, Nawaf, Mazen, Ali, add a short paragraph
  (3–5 sentences) covering: relevant coursework (ML, SE, DB), prior
  projects, internships or training, and the specific GP role. Keep the
  role table as a quick-reference summary above the paragraphs.
- **Effort.** Each member writes their own paragraph — ~30 min total.
- **Risk.** None — additive.

### A3. Add chapter Conclusions to Ch1 and Ch2

- **Problem.** Guidelines: Ch1 must end with a "Conclusions" section that
  summarises problem importance, prior attempts, methodology, and bridges
  to Ch2. Ch2 must end with a "Conclusion" subsection that recaps
  background + related work + research gap and bridges to Ch3.
- **Location.** End of Ch1, end of Ch2.
- **Action.**
  - **Ch1 §1.6 Conclusions** (new) — half-page paragraph: "This chapter
    introduced the SPIS problem… Prior work has X… Our methodology applies
    XGBoost with engineered features… Chapter 2 reviews the relevant
    literature in detail."
  - **Ch2 §2.4 Conclusion** (new — or re-label §2.3 and extend) — half-page:
    recap §2.1 background, recap §2.2 categorised related work, recap §2.3
    research gap, "Chapter 3 specifies the user and system requirements
    derived from this gap."
- **Effort.** ~45 min total.
- **Risk.** None — additive.

### A4. Add an elicitation paragraph to Ch3

- **Problem.** Guidelines: _"First, describe how you arrived at the
  specified requirements (interviews, questionnaires, observations…)"_.
  Ch3 §3.1 doesn't state how requirements were elicited.
- **Location.** Ch3 §3.1 or as a new §3.1.1.
- **Action.** Add a paragraph along the lines of: "Requirements were
  derived from (a) the project advisor's input on pharmacy operations, (b)
  observation of the Kaggle Turkish-pharmacy dataset's characteristics
  (sales granularity, ATC structure, calendar dependence), (c) study of
  community-pharmacy stockout literature [refs from Ch2], and (d)
  iterative refinement during Phase 1 prototyping. Formal stakeholder
  interviews were not conducted, but the three identified roles
  (Pharmacy Manager, Clinical Pharmacist, Storekeeper) reflect duties
  documented in [WHO citation] and confirmed with the project advisor."
- **Effort.** ~15 min.
- **Risk.** Low — additive and truthful.

### A5. Resolve risk-tier contradiction (Ch3/Ch4 vs Ch5/code)

- **Problem.** Ch3 FR-4.2 and Ch4 §4.5.3 say CRITICAL < 3, LOW 3–7, OK
  7–30, OVERSTOCK ≥ 30. Code and Ch5 say 7 / 14 / 90.
- **Location.** Two options:
  - **Safer (preserves GP1):** Top of Ch5 §5.4.4. Add a "Design Evolution"
    note: "The original tier thresholds defined in Chapter 4 §4.5.3 were
    `(3, 7, 30)` days. During Phase 8.5 these were re-calibrated to
    `(7, 14, 90)` days to match community-pharmacy lead times — typical
    distributor lead time from `suppliers.lead_time_days` ranges from 3 to
    7 days, so a CRITICAL tier of "less than 3 days" left no time to act
    on the alert. The wider bands give the pharmacist a usable response
    window."
  - **Direct (changes GP1):** Edit Ch3 FR-4.2 and Ch4 §4.5.3 to match the
    code, and add a one-line note explaining the recalibration.
- **Effort.** Safer option: ~10 min. Direct: ~20 min.
- **Risk.** Direct edits to GP1-accepted chapters carry small risk; the
  safer option is preferred.

### A6. Add a "Design Evolution / Phase 9 Scope" paragraph at the top of Ch5

- **Problem.** Ch3 has no FRs for expiry advisor, alerts, suppliers, POs,
  batch lifecycle, catalog management. Ch5 documents all of them as
  delivered. The committee will ask where the requirements came from.
- **Location.** Top of Ch5, just after the chapter intro paragraph (new
  §5.0 or sub-heading "Design Evolution and Phase 9 Scope Extension").
- **Action.** Half-page paragraph: "Chapters 3 and 4 captured the
  requirements and design as of GP1. Between GP1 and GP2 the scope was
  extended (Phase 8.5 and Phase 9) to deliver an end-to-end operational
  tool rather than a forecasting demo. The additions — per-batch expiry
  tracking and discount advisor, idempotent notification alerts, supplier
  directory and one-click PDF purchase orders, batch receipt and recall
  flows, and dashboard-driven catalog management — were prioritised
  after consultation with the project advisor as the features most
  likely to differentiate SPIS from a textbook ML demo. The implementation
  documented in this chapter therefore supersedes the GP1 design where
  the two diverge. Section 5.4.3 (recursive forecast loop) and §5.4.4
  (tier threshold recalibration) note the two design-level
  departures explicitly."
- **Effort.** ~20 min.
- **Risk.** None — frames the gap honestly and pre-empts committee
  questions.

### A7. Update test count and phase table in Ch1

- **Problem.** Ch1 §1.4 Phase 7 deliverable says "75 automated tests";
  Ch1 §1.4 timeline ends at Phase 8 "GP Report". Reality: 182 tests,
  Phase 8.5 and Phase 9 were executed.
- **Location.** Ch1 §1.4 phase table.
- **Action.** Add Phase 8.5 row ("Multi-page dashboard, expiry advisor,
  batch lifecycle") and Phase 9 row ("Alerts, suppliers, POs, catalog
  management, analytics") to the phase table. Update Phase 7 to "182
  automated tests across 14 files". Keep Phase 8 ("GP Report") as-is or
  renumber.
- **Effort.** ~10 min.
- **Risk.** Low — table extension, not removal.

---

## TIER B — Structural / diagram work

### B1. Use case diagram for Ch3 §3.5

- **Problem.** Guidelines: _"use the use case diagram **and** use case
  descriptions"_. Current Ch3 has descriptions only.
- **Action.** Draw a UML use case diagram with the three actors
  (Pharmacy Manager, Clinical Pharmacist, Storekeeper) plus the External
  System actor, and the existing UC-1..UC-4 use cases. Add UC-5
  (Receive / Recall Batch), UC-6 (Manage Catalog & Suppliers), UC-7
  (Acknowledge Alert), UC-8 (Generate Purchase Order PDF) — these cover
  the Phase 9 additions. Tool suggestion: draw.io or PlantUML.
- **Effort.** ~1 h (drawing + descriptions for new use cases).
- **Risk.** None — additive.

### B2. Gantt chart for Ch1 §1.4 and Ch3 Project Management Plan

- **Problem.** Guidelines explicitly require Gantt chart at Ch1 §1.4
  ("usually as a Gantt Chart") and Ch3 ("Gantt Chart of the project
  plan must be supplied here. It should be drawn using a professional
  project management tool like MS Project").
- **Action.** Use MS Project, GanttProject, or Excel timeline. Show
  weeks/months along the x-axis, phases 1–9 as bars, dependencies between
  phases as arrows. Insert as an image in both Ch1 §1.4 and Ch3 (new
  §3.7 "Project Management Plan").
- **Effort.** ~1–1.5 h.
- **Risk.** Low.

### B3. Alternative Designs/Methods section in Ch4

- **Problem.** Guidelines require this section explicitly in Ch4.
- **Action.** New section Ch4 §4.7 covering:
  - **Forecasting:** XGBoost vs ARIMA / Prophet / LSTM — chose XGBoost
    for tabular feature support, single multi-drug model, and tree-based
    interpretability (already touched in Ch2 §2.1.2).
  - **Storage:** SQLite vs PostgreSQL / MongoDB — chose SQLite for
    zero-administration single-file deployment.
  - **Frontend:** Streamlit vs Flask templates / React — chose Streamlit
    for rapid iteration and Python-only stack.
  - **Forecast loop:** held-constant features vs recursive — the
    recursive variant was chosen during Phase 8.5 for day-to-day
    variation.
- **Effort.** ~1 h.
- **Risk.** None — additive.

### B4. Data dictionary in Ch4 §4.2

- **Problem.** Guidelines: _"Database design is provided using data
  dictionary, E/R diagrams…"_. Current Ch4 has ERD only.
- **Action.** Add a table per database table listing every column with
  type, constraints, and a short description. The 8 tables are
  `atc_categories`, `drugs`, `sales`, `atc_inventory`, `inventory_batches`,
  `alerts`, `suppliers`, `purchase_orders`. The data is already in
  `spis/data/database.py` `_create_tables()` — just transcribe it.
- **Effort.** ~45 min.
- **Risk.** None — additive.

### B5. NFR re-classification per Figure 1 of guidelines

- **Problem.** Guidelines' Figure 1 splits NFRs into Product (Efficiency /
  Dependability / Security / Usability), Organizational (Environmental /
  Operational / Development), and External (Regulatory / Ethical /
  Legislative). Current Ch3 §3.4.2 uses NFR-1…NFR-6 categories that don't
  map to this taxonomy.
- **Action.** Either rename the existing categories to match the Figure 1
  taxonomy, or add a one-paragraph note that maps each current NFR to a
  Figure 1 branch.
- **Effort.** ~30 min for the mapping note; ~1 h for a full rename.
- **Risk.** Renaming is a structural edit to a GP1-accepted chapter.
  Mapping note is the safer choice.

---

## TIER C — Polish / nice-to-have

### C1. Hardware Requirements paragraph in Ch5 §5.1

- **Action.** One paragraph: "Development and demonstration use a
  consumer laptop (Windows 11, ≥ 8 GB RAM, ≥ 5 GB free disk for the
  database, model artifacts, and processed CSVs). No GPU is required —
  XGBoost training on the full 16,848-row feature set completes in
  under 10 minutes on CPU. The Streamlit dashboard and Flask API both
  bind to `127.0.0.1` by default; the `scripts/run_public.py` launcher
  binds to `0.0.0.0` for the lab-network demo."
- **Effort.** ~10 min.

### C2. Deployment / Installation subsection in Ch5

- **Action.** New §5.7 "Deployment and Installation" listing the four
  setup commands as a numbered list with prerequisites:
  1. `py -3.11 -m venv venv`
  2. `.\venv\Scripts\activate`
  3. `pip install -r requirements.txt`
  4. `python scripts/ingest_kaggle.py`
  5. `python scripts/run_pipeline.py`
  6. `python scripts/train_model.py`
  7. `python scripts/run_dashboard.py`
- **Effort.** ~15 min.

### C3. Dashboard screenshots in Ch5

- **Action.** Capture one screenshot per page (Overview, History &
  Forecast, Stock Update, Expiry Offers, Analytics, Receive Stock,
  Alerts, Manage Catalog, Purchase Orders). Embed under a new §5.5.8
  "Graphical User Interface Description". Use a screenshot of the demo
  DB (seeded with the four real Saudi suppliers) for realism.
- **Effort.** ~45 min.

### C4. Path-testing label in Ch6

- **Action.** Rename or re-introduce §6.4 as "Path Testing" and note
  that the API 200/404/503 paths, the alert engine's
  insert / acknowledge / re-insert lifecycle, and the batch
  receive / recall / re-recall sequence all exercise distinct paths.
- **Effort.** ~10 min.

### C5. State-of-the-art tool comparison in Ch5

- **Action.** Add a paragraph in Ch5 §5.1 (or new §5.1.1) briefly
  comparing the chosen tools against alternatives: XGBoost vs
  scikit-learn GradientBoostingRegressor (chose XGBoost for speed and
  feature-importance API); Streamlit vs Flask templates (chose
  Streamlit for built-in widgets and caching); fpdf2 vs ReportLab
  (chose fpdf2 for zero-dependency deployment).
- **Effort.** ~20 min.

### C6. Sync Ch1 team-role descriptions with Ch7 reflections

- **Action.** Ch1 §1.5 says "Saleh: ML pipeline, model training, API"
  while Ch7 reflection has Saleh on architecture and Nawaf on API. Pick
  one allocation and use it consistently. Recommendation: keep Ch7's
  allocation (it matches what was actually done) and update Ch1 §1.5.
- **Effort.** ~5 min.

### C7. Sequence diagram for one use case in Ch4

- **Action.** Draw a sequence diagram for UC-1 (View Dashboard) showing
  the user → Streamlit → `_shared.py` → forecaster → SQLite flow. One
  diagram is enough to satisfy the guideline.
- **Effort.** ~30 min.

### C8. Move defects table from Ch6 §6.6 to Ch5

- **Problem.** Guidelines locate "unexpected problems encountered and
  how resolved" in Ch5, not Ch6.
- **Action.** Either move the defects table from Ch6 §6.6 to a new
  Ch5 §5.6 "Challenges and Resolutions", or duplicate it (less ideal).
- **Effort.** ~15 min.
- **Risk.** Low — moves correctly per guidelines.

---

## Suggested execution order

If the team has _one weekend_ before submission:

| Slot | Task | Owner | Hours |
|---|---|---|---|
| Sat AM | A1 References consolidation | one person | 1.5 |
| Sat AM | A2 Mini-resumes | each member writes own | 0.5 |
| Sat AM | A3 Ch1 + Ch2 Conclusions | one person | 0.75 |
| Sat PM | A5 Design Evolution paragraph (Ch5) | one person | 0.5 |
| Sat PM | A6 Phase 9 Scope paragraph (Ch5) | one person | 0.3 |
| Sat PM | A4 Elicitation paragraph (Ch3) | one person | 0.25 |
| Sat PM | A7 Phase table update (Ch1) | one person | 0.2 |
| Sun AM | B1 Use case diagram | one person | 1 |
| Sun AM | B2 Gantt chart | one person | 1.5 |
| Sun PM | B3 Alternative Designs (Ch4) | one person | 1 |
| Sun PM | B4 Data dictionary (Ch4) | one person | 0.75 |
| Sun PM | B5 NFR mapping note (Ch3) | one person | 0.5 |
| Sun eve | C1–C8 polish | divided | 2 |

Total ≈ 12 hours of work split across the team.

If the team has _one evening_: do A1, A2, A5, A6 only (~3 hours, removes
the biggest committee-visible deductions).

---

## Won't-fix recommendations

- **Don't restructure Ch3/Ch4 to add Phase 9 FRs.** Tempting, but high
  risk against GP1 acceptance. Use the §5.0 Design Evolution paragraph
  (item A6) to bridge instead.
- **Don't redraw the Ch4 ERD with all 8 tables.** Keep the GP1 ERD; add
  a small note "the ERD reflects the GP1 design; the inventory_batches,
  alerts, suppliers, and purchase_orders tables added in Phase 9 are
  documented in Ch5 §5.3.1".
- **Don't rewrite Ch2's literature review.** It's solid and
  implementation-agnostic; the only required change is item A3 (proper
  chapter conclusion).
