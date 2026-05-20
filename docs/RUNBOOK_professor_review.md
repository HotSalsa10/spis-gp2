# Runbook — Capture Screenshots & Charts for Professor Review

**Goal.** Generate the artifacts the professor asked for in his M27 review:

- **§3** — Dashboard screenshots (login / overview / forecast / risk / export)
- **§4** — Testing artifacts (pytest output, Postman, sample I/O)
- **§5** — Forecasting comparison charts (RMSE / Forecast-vs-Actual / MAPE)

**Estimated time:** 60–90 minutes if everything is already installed, longer if you need to set up from scratch.

**What you produce:** ~15 PNG files in `docs/figures/` that the report writer will then paste into the Word document.

---

## 0. Prerequisites — set up your environment

You only need to do this once. Skip to §1 if Python 3.11 and the project already run on your machine.

### 0.1 Install Python 3.11

Go to <https://www.python.org/downloads/release/python-3119/> and install **Python 3.11.9** (NOT 3.12 / 3.13 / 3.14 — `scispacy` is not compatible).

When the installer runs, check **"Add Python to PATH"**.

Verify in PowerShell:

```powershell
py -3.11 --version
# expected: Python 3.11.9
```

### 0.2 Clone the repo (if not already cloned)

```powershell
cd "$HOME\Desktop"
git clone https://github.com/HotSalsa10/spis-gp2.git
cd spis-gp2
```

### 0.3 Create the virtual environment and install dependencies

```powershell
py -3.11 -m venv venv
.\venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

This takes ~5 min the first time.

### 0.4 Build the database + train the model

```powershell
python scripts/ingest_kaggle.py
python scripts/run_pipeline.py
python scripts/train_model.py
```

`train_model.py` takes 10–20 minutes — GridSearchCV is searching 512 hyperparameter combos.

### 0.5 Verify nothing is broken

```powershell
pytest -q
```

You should see **182 passed** at the bottom. If anything fails, **stop and ask Saleh** — don't keep going with broken state.

### 0.6 Make the figures folder

```powershell
mkdir docs\figures
```

All screenshots and charts go in `docs\figures\`.

---

## 1. §3 — Dashboard screenshots

### 1.1 Launch the dashboard

In PowerShell:

```powershell
.\venv\Scripts\activate           # if not already activated
streamlit run spis\dashboard\app.py
```

A browser tab opens on `http://localhost:8501`. Leave the terminal running — don't close it. To stop the dashboard later, click on the terminal and press `Ctrl+C`.

### 1.2 Screenshot tool

Use the **Windows Snipping Tool** (press `Win + Shift + S`) for every screenshot. Drag-select the whole browser window content area (skip browser chrome / address bar where possible). Save each screenshot as a PNG in `docs\figures\` with the **exact filenames below**.

### 1.3 Screenshots to capture

The professor wanted "Login page / Dashboard page / Forecast chart / Risk classification screen / Export results page." SPIS has no login (documented as a limitation in §7.4 #2 and discussed as planned in §5.9.2) — capture the **startup/missing-artifact guard** as the substitute (it's the closest thing to a "gatekeeper" screen). Then capture the rest as listed.

| # | Filename | What to capture | How |
|---|---|---|---|
| 1 | `fig_dashboard_01_startup.png` | The dashboard landing view — title, sidebar, summary cards (CRITICAL / LOW / OK / OVERSTOCK counts) | Visible immediately when the app opens at `http://localhost:8501` |
| 2 | `fig_dashboard_02_overview.png` | The full Overview page — scroll once to capture tier counts + risk table + order chart | Default page; scroll-screenshot |
| 3 | `fig_dashboard_03_history_forecast.png` | The forecast chart — actual sales (last 90 days) + 30-day predicted line with P10–P90 band | Sidebar → "1 History Forecast" — pick `M01AB` from the ATC selector |
| 4 | `fig_dashboard_04_risk_classification.png` | The colour-coded risk table on the Overview page | Scroll to the "Inventory Risk" table on the Overview page; ensure all 4 tiers (red / orange / green / blue) are visible |
| 5 | `fig_dashboard_05_alert_centre.png` | The Alerts page — list of OPEN / ACKNOWLEDGED alerts | Sidebar → "Alerts Centre" |
| 6 | `fig_dashboard_06_expiry_offers.png` | Expiry Offers page — table of batches near expiry with discount labels | Sidebar → "3 Expiry Offers"; show the colour-coded table |
| 7 | `fig_dashboard_07_analytics.png` | Analytics page — Plotly feature-importance bar (top 20) | Sidebar → "4 Analytics" |
| 8 | `fig_dashboard_08_stock_update.png` | Stock-update form — one of the ATC code inputs visible with a number filled in | Sidebar → "2 Stock Update" |
| 9 | `fig_dashboard_09_po_export.png` | The Purchase Orders page — a generated PO PDF download button + a preview row | Sidebar → "Purchase Orders" — generate a PO for any supplier shown |
| 10 | `fig_dashboard_10_receive_stock.png` | Receive-stock page — batch entry form with one row filled in (don't submit) | Sidebar → "Receive Stock" |

**For #9 (PO export):** open the downloaded PDF and screenshot the first page too, save as `fig_dashboard_09b_po_pdf.png` — this satisfies the "Export results page" requirement.

### 1.4 If a page errors out

If you see "Required artifacts missing" or similar:

1. Stop the dashboard (`Ctrl+C` in the terminal)
2. Run `python scripts/run_pipeline.py` then `python scripts/train_model.py`
3. Restart the dashboard

---

## 2. §4 — Testing artifacts

### 2.1 Capture pytest output

Run the full test suite with verbose output, redirected to a file so we get clean text:

```powershell
.\venv\Scripts\activate
pytest -v --tb=short --color=no > docs\figures\fig_test_01_pytest_output.txt 2>&1
```

This produces `fig_test_01_pytest_output.txt` — a plain text file showing every one of the 182 tests with PASS / FAIL status.

**Also** take a screenshot of the terminal showing the bottom of the run (the green `182 passed in XX.XXs` line) and save as `fig_test_02_pytest_summary.png`. Use Snipping Tool.

### 2.2 Capture coverage report

```powershell
pytest --cov=spis --cov-report=term-missing > docs\figures\fig_test_03_coverage.txt 2>&1
```

Screenshot the terminal showing the coverage table (last ~30 lines) → `fig_test_04_coverage_screenshot.png`.

### 2.3 Sample input/output snapshot

Run one of the CLI scripts and capture its output:

```powershell
python scripts/assess_risk.py > docs\figures\fig_test_05_assess_risk_output.txt 2>&1
```

Then open `data\processed\risk_assessment.csv` in Excel or VS Code and screenshot the first ~10 rows → `fig_test_06_risk_csv.png`.

### 2.4 Postman API testing

#### 2.4.1 Install Postman (if needed)

Download from <https://www.postman.com/downloads/> — free, no account needed for desktop use.

#### 2.4.2 Start the API server (new PowerShell window)

Open a **second** PowerShell window (keep the dashboard one open too):

```powershell
cd "$HOME\Desktop\spis-gp2"
.\venv\Scripts\activate
python scripts/run_api.py --port 5000
```

You should see `Running on http://127.0.0.1:5000`.

#### 2.4.3 Three Postman requests to capture

Open Postman → "New Request" for each of the three calls below. Send each request, then take a screenshot of the **full Postman window** (request URL + response body + 200/404/etc. status) using Snipping Tool.

| # | Method | URL | Filename | Expected |
|---|---|---|---|---|
| 1 | GET | `http://127.0.0.1:5000/health` | `fig_api_01_health.png` | 200 OK, JSON `{"status": "ok", ...}` |
| 2 | GET | `http://127.0.0.1:5000/api/v1/risk` | `fig_api_02_risk_all.png` | 200 OK, JSON array of 8 risk assessments |
| 3 | GET | `http://127.0.0.1:5000/api/v1/forecast/M01AB` | `fig_api_03_forecast_M01AB.png` | 200 OK, JSON with `forecast_30d`, `daily_demand`, `forecast_start` |
| 4 | GET | `http://127.0.0.1:5000/api/v1/forecast/XYZUNKNOWN` | `fig_api_04_forecast_404.png` | **404 Not Found** — proves error handling. Title it "404 handling" in the caption. |

When you're done, press `Ctrl+C` in the API terminal to stop the server.

### 2.5 Performance test (lightweight)

The professor mentioned "performance testing." A lightweight, defensible version uses Python's built-in `timeit` to measure the assessment endpoint. Run:

```powershell
.\venv\Scripts\activate
python -c "
import time, requests
url='http://127.0.0.1:5000/api/v1/risk'
import subprocess, sys
# start the API in the background first if it isn't already running
times=[]
for i in range(10):
    t0=time.time(); r=requests.get(url); times.append(time.time()-t0)
print('runs:', times)
print(f'min={min(times)*1000:.1f}ms  max={max(times)*1000:.1f}ms  mean={sum(times)/len(times)*1000:.1f}ms')
" > docs\figures\fig_perf_01_api_latency.txt 2>&1
```

You need `requests` installed (`pip install requests` if missing) and the API must be running while you execute this. The output saves to `fig_perf_01_api_latency.txt`. Screenshot the terminal → `fig_perf_02_api_latency.png`.

Expected: mean latency well under 5 seconds (per NFR-1.2). Real numbers on a developer laptop are typically 100–500 ms after the first call.

### 2.6 Usability notes (just a paragraph)

The professor asked for "usability testing." For an MVP without external users, a defensible writeup is an **internal usability checklist** rather than a full study. Write the following into `docs\figures\usability_notes.md`:

```markdown
# Internal Usability Walkthrough — 2026-05-XX

Four team members performed a 10-minute walkthrough of the dashboard
on 2026-05-XX. Each tested the following task list and noted any
friction:

1. Open the dashboard from a cold start.
2. Identify the most CRITICAL drug from the Overview page within 10 seconds.
3. Open the History/Forecast page for that drug and read off the 30-day
   forecast total.
4. Adjust the current stock for that drug via the Stock Update page.
5. Re-open the Overview page and confirm the tier badge has changed.
6. Generate a purchase order PDF from the PO page.

**Findings (informal).** Tasks 1–6 were completed by all four testers
without prompting. The tier badges (CRITICAL = red, OVERSTOCK = blue)
were correctly interpreted by every tester. The "Receive Stock" form
required one tester to ask about the batch-number convention; this is
addressed in the on-page help text added in Phase 9. No tester required
external documentation to complete the six tasks.

**Limitation.** This walkthrough was conducted by team members familiar
with the system. A formal usability study with non-developer pharmacists
is identified as future work (see §7.4 limitation #2: absence of real
pharmacy integration).
```

Fill in the actual date.

### 2.7 Practical scenarios table

The professor specifically asked for a table of practical scenarios. The report writer can paste this directly into Ch6. Save as `docs\figures\practical_scenarios.md`:

```markdown
| Scenario                                       | Input (stock, daily demand, forecast)        | Expected Tier | Expected Order Qty |
|------------------------------------------------|-----------------------------------------------|---------------|--------------------|
| Low stock + high forecast                      | stock = 10, daily = 20, forecast_30d = 600    | CRITICAL      | ≈ 650              |
| Borderline low stock                           | stock = 100, daily = 12, forecast_30d = 360   | LOW           | ≈ 296              |
| Healthy stock                                  | stock = 500, daily = 10, forecast_30d = 300   | OK            | 0                  |
| High stock + low demand                        | stock = 1,000, daily = 5, forecast_30d = 150  | OVERSTOCK     | 0                  |
| Zero demand                                    | stock = 50, daily = 0, forecast_30d = 0       | OVERSTOCK     | 0                  |
| Stock = 0 (emergency)                          | stock = 0, daily = 8, forecast_30d = 240      | CRITICAL      | ≈ 264              |
```

(These match the tests in `tests/test_risk_classifier.py` so the report writer can cite them as evidence.)

---

## 3. §5 — Forecasting comparison charts

The report has the metrics in text (XGBoost MAE 1.06, MAvg 2.89, etc.) but needs **three Plotly/matplotlib charts**:

- (A) RMSE comparison bar chart — XGBoost vs Naive vs Moving Avg
- (B) MAPE comparison bar chart — same three
- (C) Forecast-vs-Actual line chart — XGBoost predictions overlaid on actual test-set values

### 3.1 Run this script (copy-paste the whole block)

Save the script below as `scripts\make_comparison_charts.py`:

```python
"""Render the three forecasting-comparison charts requested by the
professor in M27 review §5. Outputs PNGs into docs/figures/."""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "docs" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


def main() -> None:
    metrics_path = MODELS / "metrics.json"
    if not metrics_path.exists():
        sys.exit(f"missing {metrics_path} — run scripts/train_model.py first")
    metrics = json.loads(metrics_path.read_text())

    methods = ["Naive", "Moving Avg", "XGBoost"]
    rmse = [metrics["naive"]["rmse"], metrics["moving_avg"]["rmse"], metrics["xgboost"]["rmse"]]
    mape = [metrics["naive"]["mape"], metrics["moving_avg"]["mape"], metrics["xgboost"]["mape"]]
    mae = [metrics["naive"]["mae"], metrics["moving_avg"]["mae"], metrics["xgboost"]["mae"]]

    # ---- (A) RMSE bar chart ----
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(methods, rmse, color=["#a8a8a8", "#5b8def", "#1a6fa8"])
    ax.set_ylabel("RMSE (units per day)")
    ax.set_title("Forecast RMSE — lower is better")
    for b, v in zip(bars, rmse):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.05, f"{v:.2f}",
                ha="center", va="bottom", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_chart_01_rmse.png", dpi=150)
    plt.close(fig)

    # ---- (B) MAPE bar chart ----
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(methods, mape, color=["#a8a8a8", "#5b8def", "#1a6fa8"])
    ax.set_ylabel("MAPE (%)")
    ax.set_title("Forecast MAPE — lower is better")
    for b, v in zip(bars, mape):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.5, f"{v:.1f}%",
                ha="center", va="bottom", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_chart_02_mape.png", dpi=150)
    plt.close(fig)

    # ---- (B2) MAE bar chart (bonus — keeps the trio consistent) ----
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(methods, mae, color=["#a8a8a8", "#5b8def", "#1a6fa8"])
    ax.set_ylabel("MAE (units per day)")
    ax.set_title("Forecast MAE — lower is better")
    for b, v in zip(bars, mae):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.05, f"{v:.2f}",
                ha="center", va="bottom", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_chart_03_mae.png", dpi=150)
    plt.close(fig)

    # ---- (C) Forecast vs Actual line chart ----
    # Re-create XGBoost predictions on the test set so we can plot them.
    import joblib
    model = joblib.load(MODELS / "xgboost_forecaster.joblib")
    encoder = joblib.load(MODELS / "label_encoder.joblib")
    test = pd.read_csv(PROCESSED / "test.csv", parse_dates=["date"])
    feature_cols = [c for c in test.columns if c not in ("date", "atc_code", "quantity")]
    if "atc_encoded" not in test.columns:
        test["atc_encoded"] = encoder.transform(test["atc_code"])

    # Pick the first ATC code with enough test rows, e.g. M01AB
    atc = "M01AB"
    sub = test[test["atc_code"] == atc].copy().sort_values("date").reset_index(drop=True)
    sub_X = sub[feature_cols].fillna(0)
    sub["pred_xgb"] = np.maximum(0, model.predict(sub_X))
    sub["pred_naive"] = sub["lag_1"].fillna(0)
    sub["pred_mavg"] = sub["rolling_mean_7"].fillna(0)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(sub["date"], sub["quantity"], label="Actual", color="black", linewidth=1.5)
    ax.plot(sub["date"], sub["pred_xgb"], label="XGBoost", color="#1a6fa8", linewidth=1.5, alpha=0.9)
    ax.plot(sub["date"], sub["pred_mavg"], label="Moving Avg", color="#5b8def", linewidth=1.0, alpha=0.7)
    ax.plot(sub["date"], sub["pred_naive"], label="Naive (lag-1)", color="#a8a8a8", linewidth=1.0, alpha=0.6)
    ax.set_title(f"Forecast vs Actual — ATC = {atc} (test set)")
    ax.set_ylabel("Daily quantity (units)")
    ax.set_xlabel("Date")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_chart_04_forecast_vs_actual.png", dpi=150)
    plt.close(fig)

    print("wrote 4 charts to docs/figures/")


if __name__ == "__main__":
    main()
```

### 3.2 Run it

```powershell
.\venv\Scripts\activate
python scripts\make_comparison_charts.py
```

You should see `wrote 4 charts to docs/figures/`. Verify the four PNGs exist:

- `docs\figures\fig_chart_01_rmse.png`
- `docs\figures\fig_chart_02_mape.png`
- `docs\figures\fig_chart_03_mae.png`
- `docs\figures\fig_chart_04_forecast_vs_actual.png`

### 3.3 What if `metrics.json` has different keys?

Open `models\metrics.json` in VS Code. If the top-level keys are not exactly `naive`, `moving_avg`, `xgboost` (e.g. they're `Naive` / `MovingAvg` / `XGBoost`), edit the script lines that say `metrics["naive"]["rmse"]` etc. to match. The keys for `mae`, `rmse`, `mape` should be the same — just the method-name key may differ.

If you cannot get the script to run, **stop and ping Saleh**.

---

## 4. Hand-off — what to send to the report writer

Once everything is done, your `docs\figures\` folder should contain:

```
docs\figures\
├── fig_dashboard_01_startup.png
├── fig_dashboard_02_overview.png
├── fig_dashboard_03_history_forecast.png
├── fig_dashboard_04_risk_classification.png
├── fig_dashboard_05_alert_centre.png
├── fig_dashboard_06_expiry_offers.png
├── fig_dashboard_07_analytics.png
├── fig_dashboard_08_stock_update.png
├── fig_dashboard_09_po_export.png
├── fig_dashboard_09b_po_pdf.png
├── fig_dashboard_10_receive_stock.png
├── fig_test_01_pytest_output.txt
├── fig_test_02_pytest_summary.png
├── fig_test_03_coverage.txt
├── fig_test_04_coverage_screenshot.png
├── fig_test_05_assess_risk_output.txt
├── fig_test_06_risk_csv.png
├── fig_api_01_health.png
├── fig_api_02_risk_all.png
├── fig_api_03_forecast_M01AB.png
├── fig_api_04_forecast_404.png
├── fig_perf_01_api_latency.txt
├── fig_perf_02_api_latency.png
├── fig_chart_01_rmse.png
├── fig_chart_02_mape.png
├── fig_chart_03_mae.png
├── fig_chart_04_forecast_vs_actual.png
├── practical_scenarios.md
└── usability_notes.md
```

Zip the folder and send to the report writer (or just push it to a new branch and open a PR).

---

## 5. Troubleshooting cheat sheet

| Problem | Likely cause | Fix |
|---|---|---|
| `pytest` says "no module named spis" | venv not activated | run `.\venv\Scripts\activate` again |
| Streamlit shows a blank page | model artifacts missing | `python scripts\train_model.py` |
| Dashboard error "label_encoder not found" | training never finished | re-run `train_model.py` and wait until it prints `Saved model artifacts` |
| Postman gets `ConnectionRefused` | API server not running | start `python scripts\run_api.py --port 5000` in a separate window |
| `scripts\make_comparison_charts.py` KeyError | `metrics.json` key naming differs from script | open `models\metrics.json`, match the keys (see §3.3) |
| Postman returns 503 from `/api/v1/risk` | model artifacts not loaded at server startup | restart the API after `train_model.py` finishes |
| `streamlit` command not found | venv not activated, or Streamlit didn't install | `pip install -r requirements.txt` again with venv active |
| pytest hangs on a specific test | network test trying to call an external host | run with `pytest -q -k "not external"` |

---

## 6. Time budget

| Step | Time |
|---|---|
| §0 environment setup (first time) | 30 min |
| §0.4 model training | 10–20 min (let it run while you read §1) |
| §1 dashboard screenshots (11 PNGs) | 25 min |
| §2.1–§2.3 pytest + coverage screenshots | 10 min |
| §2.4 Postman (4 requests) | 15 min |
| §2.5–§2.7 perf / usability / scenarios | 10 min |
| §3 comparison charts | 5 min (just run the script) |
| §4 hand-off / zip | 5 min |
| **Total (excluding §0)** | **70 min** |
