# Saleh — Presentation Script

**Sections:** Chapter 04 (Implementation) + Live Demo
**Slides:** 19 to 23 (five slides + live demo)
**Target time:** ~9 minutes (≈ 4 min content + ≈ 5 min demo)
**Hand-off from:** Mazen (System Design)
**Hand-off to:** Nawaf (Testing & Validation)

---

## Tips for delivery

- This is the heart of the talk — own it. You built most of this code.
- On slide 20 (tech stack), don't read every package name — pick highlights and move.
- On slide 21 (training), the MAE 1.07 vs naive 4.23 is your one big number. Land it.
- Before slide 23 (live demo), **make sure the dashboard is already open in a browser tab** behind the slide deck. Have the API server running in a hidden terminal. Test once before the talk starts.
- If the live demo crashes, **fall back to the screenshots** in `docs/figures/` — open them in a viewer instead. Don't panic. The screenshots tell the same story.

---

## SLIDE 19 — Chapter divider: "Implementation"  (≈ 15 seconds)

> Thanks Mazen. Now into the implementation — the tech stack we used,
> how we trained the forecaster, and how users get insights out of
> the system. After that we'll switch to a live demo of the dashboard.

*[Advance to slide 20.]*

---

## SLIDE 20 — Tech Stack  (≈ 45 seconds)

> SPIS is built entirely on a production-ready open-source Python
> stack. The whole thing reproduces from source in under five minutes.
>
> The runtime is **Python 3.11**. Data manipulation is **pandas 2.3**
> on top of **NumPy 1.26**. The forecasting model is **XGBoost 3.2**,
> and we use **scikit-learn 1.8** for the grid search and the label
> encoding. Storage is **SQLite 3** — one file, no server.
>
> The REST API is built on **Flask 3.1**, and the dashboard is
> **Streamlit 1.54**. Testing is **pytest 9**.
>
> The hardware requirement is deliberately modest: a 64-bit dual-core
> CPU, four gigabytes of RAM, about one gigabyte of disk. Validated
> on Windows 11, and the same stack runs on macOS and Linux.

*[Advance to slide 21.]*

---

## SLIDE 21 — Training the XGBoost Forecaster  (≈ 1 minute 30 seconds)

> Training was a systematic hyperparameter search with strict
> temporal validation — meaning no future data ever leaked into the
> training set.
>
> The process: we encode the ATC codes with a LabelEncoder so the
> model sees them as numeric features. We drop the first 365 days of
> each drug because the `lag_365` feature is undefined until we have
> a year of history. We use `TimeSeriesSplit` with 5 chronological
> folds, then run `GridSearchCV` across 128 parameter combinations,
> optimising on Mean Absolute Error. After prediction we clip any
> tiny negative values to zero, and the final model is serialised to
> disk via joblib.
>
> The best hyperparameters came out as: 800 estimators, max depth 6,
> learning rate 0.03, subsample 0.8, colsample bytree 0.8, and
> minimum child weight 1.
>
> The result that matters: a final MAE of **1.07** — roughly four
> times better than the naive baseline at 4.23. That is the
> measurable predictive value the model adds beyond simple methods.

*[Advance to slide 22.]*

---

## SLIDE 22 — REST API and Dashboard  (≈ 1 minute)

> Once the model is trained, users get insights through two surfaces.
>
> **Flask serves a REST API** with three endpoints. `/health` is a
> liveness check. `/api/v1/risk` returns the full risk assessment as
> JSON. And `/api/v1/forecast/<atc_code>` returns the 30-day forecast
> for a single drug category. All three endpoints have HTTP 200, 404,
> and 503 paths fully tested.
>
> **Streamlit serves the dashboard**, cached for performance. The
> Overview page has four core sections — summary cards with tier
> counts, the risk table, the order-quantity chart, and a
> drug-level medications table. Beyond the Overview, the dashboard
> has eight more pages — history and forecast, stock update,
> expiry offers, analytics, alerts, purchase orders, receive stock,
> and a catalog manager — but rather than walk through static slides,
> let me show you the live system.

*[Advance to slide 23.]*

---

## SLIDE 23 — Live Demo  (≈ 4 minutes)

> Switching to the live application now.

*[Switch from PowerPoint to the browser tab where the dashboard is open.
If you're using a single screen, use Win+Tab or Alt+Tab. Make sure the
URL bar is hidden if possible — F11 for fullscreen.]*

### Demo runbook — do these four things, in this order

**1. Overview page** (≈ 1 minute)

> This is the Overview — the main page a pharmacy manager would open
> in the morning. The four cards across the top show the count of
> drug categories in each risk tier. Below them, this red alert
> banner appears when any of the 25 critical drugs is in CRITICAL or
> LOW status — so the most important items rise to the top.
>
> The risk table below lists every ATC category with its current
> stock, the 30-day forecast, daily demand, and the days-of-stock
> metric. The tier column is colour-coded — red for CRITICAL, orange
> for LOW, green for OK, blue for OVERSTOCK.
>
> And the bar chart shows the recommended order quantity per ATC
> category — exactly the number to procure to bring the next 30 days
> back into the OK range.

**2. History & Forecast page** (≈ 1 minute)

*[Click "1 History Forecast" in the sidebar. Pick M01AB or N02BE from
the ATC selector.]*

> Here you can drill into one drug category. The chart shows the
> actual sales history in solid black, and the dashed line is the
> 30-day forecast from XGBoost. The shaded band around the forecast
> is a P10 to P90 confidence interval — we add this so the user can
> see when the model is uncertain, not just the point estimate.
>
> Below the chart we summarise the forecast — total predicted demand
> for the next 30 days, average daily demand, and the implied days
> of stock at the current level.

**3. Alerts page or Notification Center** (≈ 1 minute)

*[Click the "Alerts" page in the sidebar.]*

> The alerts page is where the alert engine surfaces actionable items.
> Every CRITICAL or LOW risk assessment generates an alert with a
> deterministic key, so the same condition can't generate duplicate
> alerts. Expiring batches also produce alerts. The user can
> acknowledge an alert here, which moves it from OPEN to ACKNOWLEDGED
> without deleting it — there's always a history.

**4. Purchase Orders** (≈ 1 minute)

*[Click "Purchase Orders" in the sidebar.]*

> Finally, the system can convert CRITICAL and LOW assessments into
> a real procurement document. Items are grouped by supplier, with
> line totals and a default unit cost when the catalog price isn't
> available. The "Download PDF" button generates a real PDF — let
> me show one.

*[Click Download PDF for any supplier. Open the file in the browser's
PDF preview to show the formatted output briefly. Don't dwell on it —
3 seconds is enough.]*

> That PDF is what the storekeeper would print or email to the
> supplier. The system closes the loop from raw sales data all the
> way to an actionable procurement document.

*[Switch back to PowerPoint. Advance to slide 24.]*

> With the implementation walked through, Nawaf will now cover
> testing and the results we measured.

---

## Emergency fallback if live demo fails

If anything crashes — Streamlit, the database, the model load — open
`docs/figures/` and walk through the screenshots in this order
instead:

1. `fig_dashboard_02_overview.png`
2. `fig_dashboard_03_history_forecast.png`
3. `fig_dashboard_05_alert_centre.png`
4. `fig_dashboard_09_po_export.png` and `fig_dashboard_09b_po_pdf.png`

Same script, just point at the images instead of the live UI.

---

## Quick reference — numbers you might be asked about

- Python 3.11.9, all dependencies pinned in `requirements.txt` with `>=`.
- 128 hyperparameter combinations (2⁷), 5 TimeSeriesSplit folds = 640 fits.
- Best params: n_estimators 800, max_depth 6, learning_rate 0.03, subsample 0.8, colsample_bytree 0.8, min_child_weight 1, reg_alpha 0.
- MAE 1.0553 (≈ 1.07) — naive 4.23 — moving avg 2.89.
- Forecast horizon: 30 days, recursive (history buffer fed back each step).
- 3 REST API endpoints, 18 API tests, 200/404/503 paths covered.
- Dashboard pages: Overview + 8 sub-pages.
- Full pipeline rebuild time: under 5 minutes.
