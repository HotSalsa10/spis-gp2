# Nawaf — Presentation Script

**Sections:** Testing & Validation + Chapter 05 (Results, Limitations, Future Work, Conclusion)
**Slides:** 24 to 31 (eight slides)
**Target time:** ~7 minutes
**Hand-off from:** Saleh (Implementation & Live Demo)
**Followed by:** Thank-you slide 32, then Q&A

---

## Tips for delivery

- You close the presentation, so you set the final impression. Be calm, confident, and a little energetic on the conclusion slide.
- On slide 25 (defects), don't apologise for finding bugs — frame them as evidence of *thorough testing*.
- On slide 29 (limitations), be honest, not defensive. Stating limits clearly *strengthens* the project.
- On slide 31 (three takeaways), pause briefly after each one to let it land.
- After slide 31, advance to the thank-you slide and invite questions.

---

## SLIDE 24 — Testing: 182 Tests, 14 Modules, 80% Coverage  (≈ 1 minute 15 seconds)

> Thanks Saleh. Testing was a discipline throughout the project, not
> an afterthought — and it shows in the numbers.
>
> The suite has grown to **182 passing tests across 14 modules**,
> with **80 percent or higher coverage** on critical paths. A full
> run completes in about 25 seconds. Pass rate is 100 percent.
>
> The coverage table on the right gives the breakdown by module. The
> highest coverage is on the risk classifier — 98 percent — because
> the tier-boundary logic is the most important thing to get right.
> The XGBoost forecaster, the REST API, and the data pipeline are
> each above 90 percent.
>
> The Database / Catalog module has 29 tests after Phase 9 — that
> increase came from adding the inventory batches, suppliers, alerts,
> and purchase-orders tables.
>
> We follow a three-layer test pyramid: roughly 100 unit tests for
> individual functions, 60 integration tests across the API and the
> pipeline, and about 22 explicit error-handling tests for the
> failure cases.

*[Advance to slide 25.]*

---

## SLIDE 25 — Defects Caught and Fixed  (≈ 1 minute)

> Integration testing surfaced six real defects during development —
> each is now a regression test in the suite.
>
> *D-001*: a feature-count mismatch in the forecaster — the pipeline
> emitted 36 columns but the trained model expected 27. Fixed by
> tightening the `FEATURE_COLS` contract.
>
> *D-002*: `float('inf')` values for days-of-stock weren't
> JSON-serialisable, so the API crashed on drugs with zero demand.
> Fixed by replacing infinity with null in the API layer.
>
> *D-003*: the first 7 days of each drug had NaN lag features that
> leaked into the train/test split. Fixed by dropping NaN rows
> explicitly.
>
> *D-004*: the ingester silently accepted negative quantities. Fixed
> by clipping to zero.
>
> *D-005*: XGBoost can return tiny negative predictions due to
> numerical artifacts. Fixed with `max(0, pred)` before the value is
> ever used.
>
> *D-006*: emoji rendering broke on Windows cp1252. Fixed with text
> shortcodes and re-tested.
>
> Every defect produced a new test — so the test suite has become
> the *living specification* of how the system actually behaves.

*[Advance to slide 26.]*

---

## SLIDE 26 — Chapter divider: "Results & Conclusion"  (≈ 15 seconds)

> Now the results, what SPIS cannot do yet, and where it goes next.

*[Advance to slide 27.]*

---

## SLIDE 27 — Results: Forecast Accuracy  (≈ 1 minute)

> The headline result: on the held-out test set, XGBoost achieves a
> Mean Absolute Error roughly **four times lower** than the naive
> baseline.
>
> Why does the model perform that well? Four reasons, all coming from
> our feature engineering.
> First, it captures calendar effects — weekly cycles, holidays,
> paydays.
> Second, it models lag autocorrelation across multiple horizons —
> yesterday, last week, last month, last year.
> Third, it reflects payday and holiday spikes via dedicated calendar
> flags.
> And fourth, it tracks momentum shifts — short-term EMAs that
> change faster than long-term ones.
>
> These four signals, combined in one model, are what let XGBoost
> out-perform every baseline we tested.

*[Advance to slide 28.]*

---

## SLIDE 28 — Objectives: Every One Achieved  (≈ 1 minute)

> Eight objectives were set at the start of GP1; all eight delivered.
>
> *Pharmacy database* — SQLite with 8 tables, 57 drugs, 424,000 sales
> records.
> *Data pipeline* — a 5-step ETL producing 35 features and 14,500
> training rows.
> *Demand forecaster* — XGBoost MAE 1.07 across all 8 ATC codes in
> one unified model.
> *Risk classification* — four tiers, the days-of-stock formula, and
> immutable assessment records.
> *REST API* — 3 endpoints, 18 tests, 200, 404, and 503 status codes
> handled.
> *Dashboard* — multi-page with 8 pages, cached for performance, and
> a missing-file safeguard.
> *Testing* — 182 tests, 14 files, 80 percent or higher coverage.
> *Generalisation* — command-line tools to register new drugs and
> new pharmacies without touching the source code.

*[Advance to slide 29.]*

---

## SLIDE 29 — Limitations  (≈ 1 minute 15 seconds)

> An honest scope statement — where the prototype stops and
> production work would need to start.
>
> *Single-pharmacy data* — the model was trained on one Turkish
> pharmacy from 2014 to 2019. Generalisation to other contexts is
> not validated.
>
> *No live POS integration* — we ingest CSV snapshots, not real-time
> transactions. Forecasts go stale without a fresh feed.
>
> *Single-pharmacy scope* — multi-site coordination, transfer
> learning, and aggregation are out of scope for this project.
>
> *Batch expiry is seeded, not live* — the public sales dataset has
> no batch expiry dates. We seeded demo batches into the
> `inventory_batches` table and built the expiry advisor on top, but
> a live POS feed would be needed to supply real batch metadata.
>
> *Fixed safety stock* — the `safety_days` parameter is hardcoded
> at three. A quantile or stochastic model would adapt the buffer to
> demand volatility automatically.
>
> These are scope boundaries — none of them is a defect, and each
> has a clear path forward.

*[Advance to slide 30.]*

---

## SLIDE 30 — Future Work  (≈ 1 minute)

> Five concrete next steps directly addressing those limitations.
>
> One — a **real-time POS feed**: continuous ingestion every 10
> minutes with automatic weekly re-training.
>
> Two — **probabilistic forecasting**: replace point forecasts with
> P10, P50, and P90 quantiles so the safety buffer scales with
> uncertainty rather than a fixed constant.
>
> Three — **per-drug models**: move from 8 ATC-level forecasters to
> 57 SKU-level forecasters, one per drug.
>
> Four — **mobile push alerts**: a React Native UI with SMS or Slack
> notifications for CRITICAL events on the road.
>
> And five — **refill reminders**: patient-facing notifications
> driven by the existing alert engine, joined to a prescription
> database.
>
> Each item is sized so a follow-on team could pick any one of them
> independently.

*[Advance to slide 31.]*

---

## SLIDE 31 — Conclusion: Three Takeaways  (≈ 1 minute 15 seconds)

> Three things to take away from this project.
>
> **One — end-to-end, not just a model.** SPIS is a complete pipeline
> from raw CSV ingest to dashboard alerts. The forecaster is the
> centrepiece, but the integration with risk classification, the
> dashboard, the alert engine, and the purchase-order generator is
> the actual contribution.
>
> **Two — four times better than naive forecasting.** XGBoost with
> 35 engineered features achieves a Mean Absolute Error of 1.07
> versus 4.23 for the naive baseline. That is measurable predictive
> value beyond what any pharmacy could get from a spreadsheet
> formula.
>
> **Three — reproducible and lightweight.** The whole system runs on
> commodity hardware and rebuilds from source in under five minutes.
> Open dataset, open code, open architecture. Anyone can re-run our
> results.
>
> Built across two semesters — 182 tests — 80 percent or higher
> coverage — open source.
>
> Thank you. We're now happy to take questions.

*[Advance to slide 32 (Thank You) and stay there for Q&A.]*

---

## During Q&A

You stay on the Thank-You slide (slide 32) for the whole Q&A. No
slide-flipping — just answer verbally. Below are short prepared
answers for the five questions most likely to come up. Read them
once before the talk so they're fresh.

### Q1 — "Why XGBoost instead of LSTM or other deep models?"

> Our dataset is moderate — about 17,000 daily rows across 8 ATC
> codes. LSTMs need much larger sequences to outperform tree models,
> and they need a GPU plus careful hyperparameter tuning that wasn't
> justified for our scale.
>
> XGBoost trains in seconds on CPU, handles missing values natively
> via sparsity-aware splits — we needed that because of the lag-365
> NaN window — and gives us feature-importance scores that a
> pharmacist can interpret. Built-in L1 and L2 regularisation also
> reduces overfitting risk on a moderate-sized dataset.
>
> Multiple recent papers in pharmaceutical and retail forecasting
> show XGBoost competitive with deep models on tabular sales data.

### Q2 — "Why did you revise risk thresholds from 3/7/30 to 7/14/90 days?"

> Typical supplier lead times are 3 to 7 days. With the original
> design, if a drug fell below 3 days of stock the alert was already
> too late — replenishment couldn't arrive before the stockout.
> Pushing CRITICAL up to under 7 days gives the staff time to
> actually act before a stockout occurs.
>
> LOW at 14 days adds a two-week early-warning window, and OK
> stretching to 90 days reflects the three-month working-capital
> ceiling we don't want to cross. These boundaries are now
> domain-driven, not arbitrary.

### Q3 — "How well does SPIS generalise to other pharmacies?"

> Honestly — not yet validated. Cross-pharmacy validation is in
> the limitations slide.
>
> What is already pharmacy-agnostic: the CSV ingestion accepts any
> `date, atc_code, quantity` schema. `register_atc.py` adds new
> drugs dynamically. The risk thresholds and `safety_days` are
> configurable per deployment. The pipeline scales linearly with
> the number of ATC codes.
>
> What would need work: cross-pharmacy validation on different
> demand patterns, per-region calendar features — Turkey holidays
> are currently hardcoded for training — a retraining strategy for
> each new site, and possibly transfer learning to share patterns
> across pharmacies.

### Q4 — "Why exactly 35 features? Why not fewer or more?"

> It's a deliberate trade-off between predictive signal and
> overfitting risk on a moderate-sized dataset. Empirically
> validated.
>
> With fewer than 15 features we lose calendar effects, weekly
> patterns, and momentum — the model underfits volatile demand.
> With more than 50 we add noise variables and overfit. At 35,
> calendar plus lags plus rolling plus derived features cover
> four temporal scales — day, week, month, and year — and produce
> the best held-out MAE.
>
> Removing any of the four families raised the held-out MAE.
> Adding noise variables didn't lower it. So 35 is the empirical
> sweet spot, not an arbitrary number.

### Q5 — "How does SPIS handle drug-batch expiry today?"

> Through the expiry advisor module — `spis/models/expiry_advisor.py`.
> It's a two-factor discount classifier that takes `days_to_expiry`
> and a `risk_ratio` (units at risk over batch quantity), and
> outputs a recommended action: none, discount tier, return to
> supplier, or write-off. There's a dedicated Expiry Offers page in
> the dashboard.
>
> The current limitation is that batch data is seeded — the public
> sales dataset doesn't include real batch expiry dates. In a live
> deployment, batches would be registered through a POS feed at
> receive time. The advisor logic is already in place; only the
> data source needs to change.

### Other questions

For any question not in this list, answer honestly. If you don't
know, say so — *"We didn't explore that; it would be a follow-on
study"* is a complete and acceptable answer for a graduation
project committee.

---

## Quick reference — numbers you might be asked about

- 182 tests across 14 files; 80%+ coverage on critical paths; ~25s full run; 100% pass rate.
- Module coverage: Risk Classifier 98%, REST API 94%, XGBoost Forecaster 92%, Data Pipeline 95%.
- 6 defects caught during development, all fixed and now regression-tested.
- XGBoost MAE 1.07 vs naive 4.23 = ~4× improvement; moving-avg baseline 2.89.
- 8 objectives → 8 delivered.
- 5 limitations explicitly named (public dataset, no POS, single-pharmacy, batch expiry seeded, fixed safety stock).
- 5 future-work items, each independently scoped.
