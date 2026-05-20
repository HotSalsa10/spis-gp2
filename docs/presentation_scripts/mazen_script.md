# Mazen — Presentation Script

**Sections:** System Requirements + Chapter 03 (System Design)
**Slides:** 11 to 18 (eight slides)
**Target time:** ~7 minutes
**Hand-off from:** Ali (Background & Related Work)
**Hand-off to:** Saleh (Implementation)

---

## Tips for delivery

- This section is the most technical so far — slow down on slides 15, 17, and 18.
- When you mention numbers (8 tables, 35 features, 7/14/90 thresholds), say them clearly.
- The risk-tier formula on slide 18 is the most important moment in your block — read it slowly.
- Don't apologise for the slides being dense. Confidently walk through them.

---

## SLIDE 11 — Stakeholders  (≈ 1 minute)

> Thanks Ali. Before we move into the design itself, it helps to know
> who SPIS is built for. We identified three stakeholder roles, each
> with different information needs from the same underlying data.
>
> The **pharmacy manager** needs a strategic overview — high-level
> demand trends, aggregate risk levels, and recommended actions. A
> one-page summary, not raw data.
>
> The **pharmacist** is on the floor every day. They need low-stock
> alerts, items at shortage risk, and a quick view of what's about to
> expire.
>
> And the **inventory storekeeper** needs the detailed picture —
> per-item quantity tables, risk flags, and exact reorder quantities.
>
> The dashboard has separate views for each of these roles, so the
> same data serves all three without overwhelming any of them.

*[Advance to slide 12.]*

---

## SLIDE 12 — System Requirements  (≈ 1 minute)

> From those stakeholder needs, we derived two sets of requirements.
>
> The **functional requirements** are: data management — ingest and
> validate sales; the forecasting engine — train baselines and
> XGBoost, evaluate with MAE, RMSE, and MAPE; the risk-analysis logic
> — classify items into tiers with configurable thresholds; the
> dashboard — risk views, time-series charts, filtering, exports; and
> reporting — generate reorder reports as CSV or PDF.
>
> The **non-functional requirements** target the qualities of the
> system: performance — forecasts in seconds on a laptop; usability —
> intuitive for non-technical staff; reliability — graceful handling
> of bad data; maintainability — clear modular code; portability —
> standard Python stack; data integrity — consistent formats; and
> scalability — easy to add new risk rules.
>
> Every requirement maps to a traceability test in our test suite — we'll
> come back to that.

*[Advance to slide 13.]*

---

## SLIDE 13 — Chapter divider: "System Design"  (≈ 15 seconds)

> Now into the system design — architecture, database, data flow,
> features, and the risk-classification logic.

*[Advance to slide 14.]*

---

## SLIDE 14 — System Architecture: Four Layers  (≈ 1 minute)

> The system is organised into four layers, each depending only on
> the one below it.
>
> At the bottom is the **data layer** — a single SQLite database file
> plus a cached CSV of engineered features.
>
> Above it sits the **processing layer** — the feature-engineering
> pipeline that turns raw sales into the 35 time-series features used
> by the model.
>
> Above that is the **model layer** — the XGBoost forecaster and the
> risk classifier.
>
> And at the top is the **presentation layer** — the Streamlit
> dashboard for human users and a Flask REST API for programmatic
> access.
>
> Top-down dependency means each layer can be developed, tested, and
> replaced independently — which mattered a lot when we extended the
> system in Phase 9 to add purchase orders and alerts.

*[Advance to slide 15.]*

---

## SLIDE 15 — Database Design: Eight Tables  (≈ 1 minute)

> The database is a single SQLite file. There are eight tables: the
> four primary ones shown on the slide — `atc_categories`, `drugs`,
> `sales`, and `atc_inventory` — plus four Phase-9 workflow tables I
> won't show in detail: `inventory_batches`, `alerts`, `suppliers`,
> and `purchase_orders`.
>
> The primary tables split cleanly into reference and operational.
> **Reference tables** are seeded once: `atc_categories` (8 rows, the
> drug-class taxonomy) and `drugs` (57 rows, with 25 flagged as
> *critical*, surfaced directly in the dashboard's red alert banner).
> **Operational tables** are updated at runtime: `sales` — 424,080
> rows of historical transactions — and `atc_inventory`, which tracks
> current stock for each category.
>
> All foreign keys cascade on delete, so deleting an ATC category
> automatically cleans up its drugs, sales, and inventory rows.

*[Advance to slide 16.]*

---

## SLIDE 16 — Data Flow: Raw Sales to Risk Alerts  (≈ 1 minute)

> Six stages take raw CSV records all the way through to the
> dashboard outputs.
>
> One — **ingest**: read the CSV, validate, clip negative quantities,
> aggregate duplicates.
> Two — **store**: persist into the SQLite tables.
> Three — **engineer**: build the 35 time-series features per row.
> Four — **train**: XGBoost with grid search across 128 hyperparameter
> combinations, using TimeSeriesSplit so we never train on future data.
> Five — **forecast**: produce a 30-day rolling demand prediction for
> each ATC category.
> Six — **classify**: map the forecast and the current stock into a
> risk tier plus a recommended order quantity.
>
> The whole pipeline rebuilds from source in under five minutes on a
> normal laptop — that's what we mean when we call SPIS lightweight.

*[Advance to slide 17.]*

---

## SLIDE 17 — Feature Engineering: 35 Features  (≈ 1 minute 15 seconds)

> The forecaster sees 35 engineered features, grouped into four
> families that each capture a different temporal pattern.
>
> **Twelve calendar features** — day of week, month, quarter, payday
> window, holiday flags, days to month end. They capture weekly cycles
> and payday spikes.
>
> **Seven lag features** — yesterday's sales, two days ago, three,
> seven, fourteen, twenty-eight, and 365. Short-, medium-, and
> long-term autocorrelation, including yearly seasonality.
>
> **Twelve rolling and EMA features** — rolling means at 7, 14, 28,
> 90, and 365 days; rolling standard deviation, min, max; and
> exponential moving averages at 7, 14, and 28 days. These smooth out
> noise while preserving the trend.
>
> And **four derived features** — `lag_ratio_7` as a spike detector, a
> trend counter, the rolling range, and an EMA ratio that captures
> momentum.
>
> We arrived at 35 empirically. Removing any family raised the
> held-out MAE; adding more features didn't lower it.

*[Advance to slide 18.]*

---

## SLIDE 18 — Risk Classification: Four Tiers, One Formula  (≈ 1 minute 15 seconds)

> The risk logic combines the forecast and the current stock into a
> single number — **days of stock** — and maps that to a tier.
>
> **CRITICAL** is under 7 days of stock — you cannot replenish before
> you stock out.
> **LOW** is 7 to 14 days — order now as an early warning.
> **OK** is 14 to 90 days — sufficient stock, no action needed.
> **OVERSTOCK** is 90 days or more — capital is tied up and expiry
> risk starts to matter.
>
> Order quantity uses one formula:
>
> *Order quantity equals the maximum of zero, or — the 30-day
> forecast plus the safety buffer minus the current stock.*
>
> The safety buffer is the daily demand multiplied by a configurable
> number of safety days, default three.
>
> One detail worth noting: the thresholds evolved during development.
> Our original Phase-4 sketch used 3, 7, and 30 days. We revised them
> to 7, 14, and 90 in Phase 8.5 because typical supplier lead times are
> 3 to 7 days — so if a tier triggers below 3 days, the alert is
> already too late. Pushing CRITICAL up to under 7 days gives the
> staff time to actually act.
>
> With the design in place, Saleh will now walk you through how we
> built it.

*[Advance to slide 19 — Saleh takes over.]*

---

## Quick reference — numbers you might be asked about

- 8 database tables total: 4 primary + 4 Phase-9 workflow tables.
- 424,080 sales rows from 2014–2019.
- 57 drugs across 8 ATC categories; 25 drugs flagged as critical.
- 35 engineered features = 12 calendar + 7 lag + 12 rolling/EMA + 4 derived.
- 128 hyperparameter combinations searched (2⁷ = 128, not 512).
- Risk thresholds: CRITICAL < 7, LOW 7–14, OK 14–90, OVERSTOCK ≥ 90 (days of stock).
- Safety buffer formula: `daily_demand × safety_days` (default safety_days = 3).
- Why thresholds were revised from (3,7,30) to (7,14,90): supplier lead times are 3–7 days, so a sub-3-day CRITICAL alert came too late.
