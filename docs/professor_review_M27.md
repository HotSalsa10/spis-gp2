# Professor Review — M27 Project Report

**Source:** `M27 - Review - Project Report - My Students.pdf`
**Instructor:** Prof. Dr Sohail Jabbar AbdulJabbar
**Course:** Graduation Project 2 (CS579) — 2nd Semester, 1447H
**Group:** M27 (Saleh, Nawaf, Mazen, Ali)
**Logged:** 2026-05-18

This is the master checklist of every adjustment the professor requested. We will execute them one-by-one and tick them off as each is completed.

---

## 1. Writing Style — N/A (not present in current source)

> **Status (2026-05-18):** Swept all four source files (`chapter1_introduction.md`, `chapter2_literature_review.md`, `chapter3_requirements.md`, `Chapters_4_to_7_Updated.md`) for conversational phrasing. **None of the flagged patterns are present.** The Explore agent found only 8 minor uses of "small" — all in legitimate technical contexts. The professor reviewed an older compiled version.

- [x] ~~**1.1** Scan all chapters for conversational phrasing such as: "We want something small and clear…", "This helps us build a system…", "normal pharmacist can open…"~~ — not in current files
- [x] ~~**1.2** Rewrite each occurrence using simple but professional technical language.~~ — nothing to rewrite
- [x] ~~**1.3** Sweep the whole report ("check thoroughly and update").~~ — sweep complete, source is already academic in tone

---

## 2. Methodology — Add Technical Justifications

The methodology currently explains *what* was done but not *why*. Add a short technical justification for each major decision:

- [x] **2.1** Justify why **XGBoost** was selected (vs. ARIMA, LSTM, etc.).
  — Added "Rationale" paragraph at `Chapters_4_to_7_Updated.md` §4.7.1.
- [x] **2.2** Justify why **35 features** (calendar + lag + rolling + derived).
  — Added "Rationale for the 35-feature design" with breakdown table after §4.6.1 pseudocode.
- [x] **2.3** Justify why **30-day forecasting horizon**.
  — Added "Why a 30-day horizon?" paragraph in §4.7.3 (procurement cycle / lead times / recursion-error knee).
- [x] **2.4** Justify the **risk-tier thresholds** (currently `7 / 14 / 90`, not `3 / 7 / 30` as in older drafts).
  — Added "Rationale" paragraph in §4.7.2 with per-tier domain reasoning (lead times, review cycles, shelf-life economics).

---

## 3. Implementation Chapter — Show the Actual Developed System

**Status:** Runbook delegated to a teammate — see `docs/RUNBOOK_professor_review.md` §1.

- [ ] **3.1** Login page — runbook substitutes startup/missing-artifact view (no auth in scope; see §5.9 planned-security section)
- [ ] **3.2** Dashboard (Overview) page — runbook captures it as `fig_dashboard_02_overview.png`
- [ ] **3.3** Forecast chart (History + Forecast) — `fig_dashboard_03_history_forecast.png`
- [ ] **3.4** Risk classification screen — `fig_dashboard_04_risk_classification.png`
- [ ] **3.5** Export results page — `fig_dashboard_09_po_export.png` + `fig_dashboard_09b_po_pdf.png`

> The runbook captures **11 dashboard screenshots** total (overview, history+forecast, risk table, alerts, expiry offers, analytics, stock update, PO export, PO PDF, receive stock, startup). The teammate just follows the file and saves PNGs into `docs/figures/`.

---

## 4. Testing Chapter — Make It Practical, Not Just Pass/Fail Tables

**Status:** Runbook delegated to a teammate — see `docs/RUNBOOK_professor_review.md` §2.

- [ ] **4.1** Screenshots of test runs — runbook captures `fig_test_01_pytest_output.txt` + `fig_test_02_pytest_summary.png`
- [ ] **4.2** Sample input / output — `fig_test_05_assess_risk_output.txt` + `fig_test_06_risk_csv.png`
- [ ] **4.3** API testing screenshots (Postman) — `fig_api_01_health.png` through `fig_api_04_forecast_404.png` (4 requests including 404 path)
- [ ] **4.4** Performance testing — `fig_perf_01_api_latency.txt` + `fig_perf_02_api_latency.png` (10-call timing of `/api/v1/risk`)
- [ ] **4.5** Usability testing notes — runbook §2.6 produces `usability_notes.md` (internal 4-tester walkthrough)
- [ ] **4.6** Practical scenarios table — runbook §2.7 produces `practical_scenarios.md` with 6 scenarios spanning all 4 risk tiers

---

## 5. Forecasting Comparison — Replace Text with Charts

**Status:** Runbook delegated — see `docs/RUNBOOK_professor_review.md` §3. The runbook includes a copy-paste Python script (`scripts/make_comparison_charts.py`) that the teammate runs once to produce all four PNGs from `models/metrics.json` and the test-set predictions.

- [ ] **5.1** RMSE comparison bar chart — `fig_chart_01_rmse.png`
- [ ] **5.2** Forecast vs Actual line chart — `fig_chart_04_forecast_vs_actual.png` (XGBoost / Moving Avg / Naive overlaid on actual test-set values for M01AB)
- [ ] **5.3** MAPE comparison chart — `fig_chart_02_mape.png` (plus a bonus MAE chart `fig_chart_03_mae.png` to keep the metric trio consistent)

---

## 6. Literature Review — Add Critical Comparison

- [x] **6.1** Add a **comparison table** of related studies.
  — Added `chapter2_literature_review.md` §2.2.4 "Critical Comparison of Related Work" in the Study / Method / Dataset / Limitation format requested. Existing feature-level comparison renumbered to §2.2.5.
- [x] ~~**6.2** Trim repetitive paragraphs in Ch2.~~ — current Ch2 has no repetitive phrasing (sweep found no copy-paste sentences); N/A.
- [x] ~~**6.3** Vary sentence patterns — replace *"The system helps reduce shortages and overstock."*~~ — flagged sentence not present in current Ch2; N/A.

---

## 7. Deployment Section

- [x] **7.1** Add a deployment section covering hardware, install, packages, startup commands.
  — Added `Chapters_4_to_7_Updated.md` §5.8 "Deployment" with 5 sub-sections: hardware requirements table, full install procedure (clone → venv → pip → ingest → pipeline → train → streamlit), Python-package inventory, startup-command summary table, and runtime artifact layout. `streamlit run spis/dashboard/app.py` is the primary launch command and is called out explicitly.

---

## 8. Security Section

- [x] **8.1** Discuss password hashing, session management, role-based access, secure API routes.
  — Added `Chapters_4_to_7_Updated.md` §5.9 "Security" with 6 sub-sections: threat-model table (in-scope vs out-of-scope assets and threats), Argon2id password hashing (planned, with code), signed JWT session management (planned), 3-role RBAC matrix (viewer/operator/manager), API hardening plan (TLS, Bearer auth, rate-limit, schema validation, CORS), and a list of defensive controls already in place (parameterised SQL, read-only API, fail-fast on missing artifacts, local-only SQLite, pinned deps).

---

## 9. Limitations — Be Explicit

- [x] **9.1** Explicitly list all 5 professor-flagged limitations.
  — Rewrote `Chapters_4_to_7_Updated.md` §7.4 (the authoritative Ch7 source) with 8 named items: (1) Use of a public dataset, (2) Absence of real pharmacy integration, (3) Single-pharmacy limitation, (4) Lack of real-time forecasting, (5) Limited expiry prediction, (6) Single-warehouse stock model, (7) Read-only API, (8) NLP drug-name search scoped but not delivered. The legacy `chapter7_conclusion.md` was also updated in parallel for internal consistency.

---

## 10. Risk Classification — Add Mathematical Explanation

- [x] **10.1** Add the formula and explain it.
  — Added "Mathematical formulation" block after `Chapters_4_to_7_Updated.md` §4.6.4 with DoS, tier-piecewise function, order-quantity formula in two equivalent forms, and the rationale for the `max(0, …)` clamp.
- [x] **10.2** Explain why safety stock is needed.
  — Added "Why a safety buffer is needed" paragraph after §4.6.4: explains that `f30` is the *expected* demand (not worst case), that ordering `f30 − s` exactly gives a 50% stockout probability under demand volatility, and that the buffer converts an expected-value rule into a service-level rule. Notes the quantile-regression future-work alternative.
- [x] **10.3** Explain how the risk-tier thresholds were chosen.
  — Done as part of §2.4 — see `Chapters_4_to_7_Updated.md` §4.7.2 "Rationale" for per-tier domain reasoning (lead time, review cycle, shelf-life economics). Cross-referenced from the §4.6.4 mathematical formulation block.

---

## 11. Grammar & Writing Fixes — N/A (not present in current source)

> **Status (2026-05-18):** Swept `chapter1_introduction.md`, `chapter2_literature_review.md`, `chapter3_requirements.md`, and `Chapters_4_to_7_Updated.md` for every flagged phrase below. **None are present.** The professor reviewed an older compiled version of the report; these issues no longer exist in the current source.

- [x] ~~**11.1** "decision- support tool" → **"decision-support tool"**~~ — not in current files
- [x] ~~**11.2** "works better,stockouts become fewer" → **"works better, stockouts become fewer"**~~ — not in current files
- [x] ~~**11.3** "Thresholds … how much margin make a shortage risk" → **"Thresholds … how much margin makes a shortage risk"**~~ — not in current files
- [x] ~~**11.4** "uses XGBoost as main forecasting model" → **"uses XGBoost as the main forecasting model"**~~ — not in current files
- [x] ~~**11.5** "We are going to be discussing pharmacy inventory management…" → **"The next chapter discusses pharmacy inventory management…"**~~ — not in current files

---

## 12. Tense Consistency — N/A (sweep clean)

> **Status (2026-05-19):** Swept all four source files for future-tense ("will / going to") describing completed work, mixed-tense paragraphs, and past-tense in system-description contexts. **No genuine hits found.** Present-tense system description and past-tense completed-work are already used correctly throughout. The only future-tense uses are inside legitimate exceptions: `shall` in formal FR/NFR statements (Ch3), `would` in planned-security design (§5.9), and Future Work (§7.5).

- [x] ~~**12.1** Sweep all chapters for tense switching.~~ — done, no hits
- [x] ~~**12.2** Use **present tense** for system description.~~ — already correct throughout
- [x] ~~**12.3** Use **past tense** for completed implementation / testing work.~~ — already correct throughout

---

## 13. Word Choice — N/A (not present in current source)

> **Status (2026-05-18):** Swept all four source files for the target words. **None present.** Issues were in the older submitted version only.

- [x] ~~**13.1** "a lot of" → **"many"**~~ — not in current files
- [x] ~~**13.2** "really" → **"significantly"**~~ — not in current files
- [x] ~~**13.3** "normal users" → **"non-technical users"**~~ — not in current files
- [x] ~~**13.4** "simple idea" → **"fundamental concept"**~~ — not in current files

---

## 14. Paragraph Length

- [x] **14.1** Find paragraphs longer than ~5 lines.
  — Grepped for source paragraphs ≥300 chars on one line. `Chapters_4_to_7_Updated.md` already tight (no hits). `chapter1_introduction.md` had 3 dense paragraphs; `chapter2_literature_review.md` had 6. `chapter3_requirements.md` is mostly tables/bullets — no prose paragraphs to split.
- [x] **14.2** Split into 3–5 line chunks.
  — Split 3 paragraphs in `chapter1_introduction.md` (Background section, lines 7–11) and 6 paragraphs in `chapter2_literature_review.md` (Inventory mgmt, ARIMA Statistical Methods, XGBoost ML Methods, ABC-VED, Lightweight pharmacies, EOQ section). All splits chosen at sentence boundaries where the topic naturally shifts.

---

## Execution Notes

- Track progress here. After each item, tick the box and note the file(s) changed.
- Source-of-truth chapter files: `docs/chapter1_introduction.md` … `docs/chapter7_conclusion.md`, plus `docs/Chapters_4_to_7_Updated.md` and `docs/Ch1-3_additions.md`.
- Don't break IEEE-style references already present in `docs/references_master.md`.
