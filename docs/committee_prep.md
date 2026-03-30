# GP Committee Prep — Questions & Answers
### Smart Pharmacy Inventory System (SPIS)
**Team:** Saleh · Nawaf · Mazen · Ali

> Use this document to study before the presentation.
> Add your own notes in the "Team Notes" sections under each answer.

---

## Table of Contents

1. [The Problem](#1-the-problem)
2. [The Data](#2-the-data)
3. [Feature Engineering](#3-feature-engineering)
4. [The Forecasting Model](#4-the-forecasting-model)
5. [Risk Classification](#5-risk-classification)
6. [Expiry Advisor](#6-expiry-advisor)
7. [The Dashboard](#7-the-dashboard)
8. [Testing](#8-testing)
9. [System Design](#9-system-design)
10. [Scalability & Future Work](#10-scalability--future-work)

---

## 1. The Problem

**Q: Why did you choose this problem?**

Pharmacies — especially in Saudi Arabia — often manage hundreds of SKUs manually using spreadsheets or basic POS systems. This leads to two costly problems:
- **Stockouts**: a medication runs out and patients cannot be served.
- **Waste from expiry**: batches expire before being sold, causing direct financial loss.

SPIS addresses both by using historical sales data to forecast demand, classify risk automatically, and flag expiring batches before it is too late.

> **Team Notes:**
>

---

**Q: What is the real-world impact of poor pharmacy inventory?**

- Patient safety risk when critical medications are unavailable.
- Financial loss from expired stock that must be written off.
- Regulatory exposure — pharmacies in Saudi Arabia are inspected by SFDA and must maintain adequate stock of essential medications.
- Staff time wasted on manual counting and guesswork.

> **Team Notes:**
>

---

**Q: Is there an existing solution for this in Saudi Arabia?**

Most pharmacy management software (e.g., Al-Nafhah, Maktabi) tracks stock quantities but does not forecast demand or proactively flag expiry risk. SPIS adds a predictive layer on top of transactional data.

> **Team Notes:**
>

---

## 2. The Data

**Q: Where did your data come from?**

We used a publicly available pharmaceutical sales dataset from Kaggle ("Pharma Sales Data") which contains 6 years of daily, weekly, monthly, and hourly sales records for 8 ATC drug categories from a real European pharmacy. We used it because real Saudi pharmacy data is not publicly available, and this dataset has the same structure a pharmacy POS system would export.

> **Team Notes:**
>

---

**Q: What does ATC code mean?**

ATC stands for Anatomical Therapeutic Chemical — it is a WHO classification system that groups medications by their therapeutic purpose. For example:
- M01AE = Propionic acid derivatives (Ibuprofen, Naproxen)
- N02BE = Anilides (Paracetamol)
- R06 = Antihistamines

We work at the ATC-4 level (the 4th level of the hierarchy), which groups related drugs together. This is how most pharmacy inventory systems categorise stock.

> **Team Notes:**
>

---

**Q: How much data did you have?**

- 424,080 total sales records across 4 granularities (hourly/daily/weekly/monthly)
- We trained exclusively on **daily** granularity: 16,848 rows (8 ATC codes × 2,106 days)
- Date range: **2 January 2014 → 8 October 2019** (~5.75 years)

> **Team Notes:**
>

---

**Q: Did you do any data cleaning?**

Yes. The main preprocessing steps were:
1. Normalised column names and parsed dates across 4 CSV files.
2. Used only daily granularity for modelling (other granularities are stored for reference).
3. Dropped rows with NaN lag/rolling features (approximately the first year of each ATC's history) rather than filling with zero — filling with zero would have distorted the rolling averages.
4. No outlier removal — pharmacy sales have genuine spikes (flu season, Ramadan) and removing them would hurt forecasting accuracy.

> **Team Notes:**
>

---

## 3. Feature Engineering

**Q: What features did you engineer and why?**

We built 35 features in 4 groups:

| Group | Features | Why |
|-------|----------|-----|
| Calendar | day_of_week, month, year, week_of_year, is_weekend, is_holiday, season, is_payday_window, is_school_holiday, quarter, days_to_month_end | Demand follows time patterns — people buy more painkillers on weekdays, more antihistamines in summer |
| Lag | lag_1, lag_2, lag_3, lag_7, lag_14, lag_28, lag_365 | Yesterday's and last week's sales are strong predictors of today's |
| Rolling | rolling_mean_7/14/28/90/365, rolling_std_7/28, rolling_min/max_7 | Capture short and long trend context |
| Derived | ema_7, ema_14, ema_28, ema_ratio, lag_ratio_7, trend_counter, rolling_range_7 | Exponential moving averages weight recent sales more heavily than simple averages |

> **Team Notes:**
>

---

**Q: Why exponential moving averages (EMA) instead of simple averages?**

Simple moving averages treat a sale from 28 days ago the same as yesterday's. EMA gives more weight to recent sales, which matters in pharmacy demand because a sudden spike (e.g. flu outbreak) should shift the forecast faster than a simple average would allow.

The model confirmed this — EMA features ranked as the top 3 most important features: ema_14 (41%), ema_7 (36%), ema_28 (4%).

> **Team Notes:**
>

---

## 4. The Forecasting Model

**Q: Why XGBoost and not a deep learning model (LSTM, Transformer)?**

Three reasons:
1. **Data size**: 16,848 rows is relatively small for deep learning. XGBoost performs well on tabular data at this scale without overfitting.
2. **Interpretability**: XGBoost provides feature importance scores, which we can show the committee and explain to pharmacists. A black-box neural network cannot do this.
3. **Speed and deployment**: XGBoost trains in seconds and runs inference instantly. An LSTM would need a GPU or much longer inference time for a real-time dashboard.

We did consider ARIMA and Prophet as baselines. XGBoost outperformed both (MAE 1.07 vs ARIMA-equivalent naive baseline MAE 4.23).

> **Team Notes:**
>

---

**Q: How did you validate the model? Isn't train/test split enough?**

We used **TimeSeriesSplit** cross-validation with 5 folds during hyperparameter tuning. Standard k-fold cross-validation shuffles data randomly, which would leak future information into the training set for time series. TimeSeriesSplit always trains on the past and validates on the future — the same way the model will be used in production.

After cross-validation tuning, we did a final evaluation on a held-out test set (Jan–Oct 2019, never seen during training).

> **Team Notes:**
>

---

**Q: What were your model's accuracy results?**

| Metric | Our Model (XGBoost) | Naive Baseline | Moving Average |
|--------|--------------------|--------------:|---------------:|
| MAE    | **1.07** units/day | 4.23 | 2.89 |
| RMSE   | **2.49** units/day | — | — |
| MAPE   | **18.8%** | — | — |

MAE of 1.07 means on average our forecast is off by about 1 unit per day. For context, average daily sales in the dataset are around 5–6 units, so this is approximately 18% error — acceptable for inventory planning purposes.

> **Team Notes:**
>

---

**Q: Why do you forecast 30 days and not 7 or 60?**

30 days matches a typical pharmacy's ordering cycle — most pharmacies place orders monthly. Forecasting 7 days would be too short to plan procurement (lead times from suppliers can be 1–2 weeks). Forecasting 60+ days introduces compounding prediction error that makes the numbers unreliable.

> **Team Notes:**
>

---

**Q: How does the 30-day forecast work for future dates when you have no data?**

We use a "seed row" approach:
- The last known feature row for each ATC code is used as the base.
- Calendar features (day_of_week, month, holiday, etc.) are computed from the actual future date.
- Lag and rolling features are held constant from the seed row (conservative assumption — no feedback loop).
- Each day is predicted independently, clipped to >= 0.

This is a practical compromise: a true recursive forecast would feed each day's prediction back as a lag feature, but prediction errors compound quickly. Holding lags constant is more stable for a 30-day window.

> **Team Notes:**
>

---

## 5. Risk Classification

**Q: How do you define the risk tiers?**

Risk is measured by **Days of Stock (DoS)** = current_stock ÷ daily_demand.

| Tier | DoS Range | Meaning |
|------|-----------|---------|
| CRITICAL | < 7 days | Will run out within a week — order immediately |
| LOW | 7–14 days | Running low — place order soon |
| OK | 14–90 days | Adequate stock |
| OVERSTOCK | ≥ 90 days | More than 3 months of stock on hand |

> **Team Notes:**
>

---

**Q: Why 7 days for CRITICAL and not 3 or 14?**

7 days accounts for a realistic supplier lead time. Most pharmaceutical distributors in Saudi Arabia deliver within 3–5 business days. 7 days gives the pharmacist 2–3 days of buffer to place an order and receive it before stockout. Using 3 days would be dangerously tight; using 14 days would generate too many false alarms.

> **Team Notes:**
>

---

**Q: Why is OVERSTOCK at 90 days and not 30 or 60?**

OVERSTOCK is a different concern from running out — it is about tied-up capital and expiry risk. A medication with 2 years on its shelf life is not a problem at 90 days of stock. We set the threshold at 90 days because:
- Below 90 days: normal operating range.
- Above 90 days: the pharmacy has more than a quarter's worth of stock — worth reviewing whether to slow purchasing.

Note: OVERSTOCK does not mean "take action immediately" — it is an informational flag.

> **Team Notes:**
>

---

**Q: What if daily demand is zero (a drug that hasn't sold recently)?**

Days of Stock = infinity. We classify this as OVERSTOCK and set order quantity to 0. The system will not recommend ordering a drug that has no recent demand — the pharmacist should investigate why sales stopped.

> **Team Notes:**
>

---

## 6. Expiry Advisor

**Q: How does the expiry discount system work?**

We use two factors together:

1. **Days to expiry**: how much time is left on the batch.
2. **Risk ratio**: what fraction of the batch demand will NOT cover before expiry (units_at_risk ÷ batch_quantity).

| Days Left | Low risk (<33%) | Medium risk (33–66%) | High risk (>66%) |
|-----------|----------------|---------------------|-----------------|
| 60–90 days | Monitor (0%) | Early Discount 10% | Early Discount 15% |
| 30–59 days | Special Offer 10% | Special Offer 20% | Special Offer 30% |
| < 30 days | **Cannot Dispense — return to supplier** |
| Expired | Write off |

> **Team Notes:**
>

---

**Q: Why can't you sell a medication with less than 30 days left?**

This is based on international Good Distribution Practice (GDP). The standard rule used by most pharmacy chains and adopted in GCC countries is that a medication must have a minimum of 30 days remaining shelf life to be dispensed to a patient. Dispensing a near-expiry medication gives the patient insufficient time to complete a full course of treatment.

Reference: WHO Guidelines on Good Distribution Practices for Pharmaceutical Products; Saudi SFDA Good Pharmacy Practice guidelines.

> **Team Notes:**
>

---

**Q: What is risk_ratio and why does it matter for discounts?**

risk_ratio = units_at_risk ÷ batch_quantity. It answers: "Of this batch, what percentage will we fail to sell before expiry?"

Example: A batch of 200 units, 40 days to expiry, daily demand = 2.
- Forecasted sales = 2 × 40 = 80 units
- Units at risk = 200 − 80 = 120 units
- Risk ratio = 120 / 200 = **60% (medium risk)**
- Recommended discount: 20% Special Offer

Without risk_ratio, a batch of 5 units and a batch of 5,000 units both expiring in 40 days would get the same discount. With risk_ratio, a batch where 80% will expire gets a deeper discount than one where only 10% will expire.

> **Team Notes:**
>

---

## 7. The Dashboard

**Q: Walk us through the dashboard pages.**

The dashboard has 5 pages:

| Page | Purpose |
|------|---------|
| Overview (Home) | Critical alert banner · tier summary cards · risk table · order quantity chart · medications table |
| History & Forecast | Plotly chart showing 90-day actual sales + 30-day forecast · drug selector within ATC group |
| Stock Update | Form to update current stock levels for any ATC code |
| Expiry Offers | Expiry discount recommendations with pharmacist override for applied discount |
| Analytics | Feature importance chart · ABC demand Pareto analysis |

> **Team Notes:**
>

---

**Q: Can the pharmacist change anything in the system?**

Yes — two things:
1. **Stock levels** (Stock Update page): the pharmacist enters the actual current count after a physical stock check.
2. **Applied discount** (Expiry Offers page): the system suggests a discount but the pharmacist can override it before printing promotional labels.

Everything else (forecasts, risk tiers, order quantities) is calculated automatically.

> **Team Notes:**
>

---

## 8. Testing

**Q: How did you test the system?**

We have 101 automated tests using pytest, covering:

| Test File | What it tests |
|-----------|--------------|
| test_pipeline.py | Feature engineering, train/test split, column counts |
| test_forecaster.py | Model loading, prediction shapes, no negative output |
| test_risk_classifier.py | Tier boundaries, order qty formula, edge cases (zero demand, infinity) |
| test_expiry_advisor.py | 2D discount matrix, all risk/day combinations, batch assessment |
| test_api.py | All 3 Flask endpoints, error codes, serialisation |
| test_database.py | Schema, seeds, idempotency, stock update function |
| test_ingest_data.py | CSV normalisation, ATC registration, unknown code handling |
| test_register_atc.py | ATC level inference edge cases |

All 101 tests pass on the current codebase.

> **Team Notes:**
>

---

**Q: Why write tests for a GP project?**

Two reasons:
1. When we change a threshold or a formula (which happened several times), tests immediately tell us if something else broke. Without tests we would have to manually verify every page of the dashboard after every change.
2. It demonstrates software engineering discipline — any production pharmacy system would require this before deployment.

> **Team Notes:**
>

---

## 9. System Design

**Q: What is the overall system architecture?**

```
Raw CSV data
    ↓
scripts/ingest_kaggle.py   → SQLite database (inventory.db)
    ↓
scripts/run_pipeline.py    → Feature engineering → features_daily.csv
    ↓
scripts/train_model.py     → XGBoost model + LabelEncoder (joblib artifacts)
    ↓
spis/api/        → Flask REST API  (GET /health, /risk, /forecast/<atc>)
spis/dashboard/  → Streamlit dashboard (5 pages, reads DB + model artifacts)
```

The database, pipeline outputs, and model artifacts are all local files. There is no cloud dependency — the system runs entirely on a single machine.

> **Team Notes:**
>

---

**Q: Why SQLite and not MySQL or PostgreSQL?**

SQLite is sufficient for a single-pharmacy deployment — it handles thousands of reads per second and requires zero server setup. The schema is designed so that migrating to PostgreSQL later (for a multi-branch deployment) would only require changing the connection string and driver, not the query logic.

> **Team Notes:**
>

---

**Q: Why Streamlit for the dashboard and not a custom web app?**

Streamlit lets us build an interactive data dashboard in pure Python without writing HTML/CSS/JavaScript. For a GP project focused on the data science and pharmacy logic, this was the right trade-off. A production version would likely be rebuilt in a proper web framework, but the business logic (models, risk classifier, expiry advisor) is already separated into importable Python modules — so the frontend can be replaced without touching the core logic.

> **Team Notes:**
>

---

## 10. Scalability & Future Work

**Q: Does this only work for the 8 drugs in your dataset?**

No. The system is designed to be pharmacy-agnostic:
- `scripts/register_atc.py` — add any new ATC code to the database
- `scripts/ingest_data.py` — ingest sales data in a standard `date, atc_code, quantity` format
- The model trains on whatever ATC codes are present in the data

The 8 codes are from the dataset we used for development. A real pharmacy would run the same pipeline on its own historical export.

> **Team Notes:**
>

---

**Q: What would you add if you had more time?**

Honest priority list:
1. **Per-drug forecasting** — currently forecasts are at ATC group level; individual drug brands within a group can have very different demand patterns.
2. **Supplier lead time integration** — if a specific supplier takes 10 days to deliver, the CRITICAL threshold should adjust automatically.
3. **Automated reorder emails/alerts** — instead of the pharmacist checking the dashboard, the system sends a daily alert for CRITICAL items.
4. **Multi-branch support** — aggregate stock across branches, transfer between locations before ordering externally.
5. **Actual Saudi pharmacy data** — train on local data to capture Ramadan, Hajj season, and Saudi-specific prescription patterns.

> **Team Notes:**
>

---

**Q: What are the limitations of your system?**

Be honest with the committee — they respect honesty over overselling:
1. The model was trained on European pharmacy data, not Saudi. Demand patterns may differ (Ramadan stock-up, different disease prevalence).
2. The 30-day forecast holds lag features constant, which becomes less accurate as the forecast window extends.
3. The system has no real-time POS integration — stock levels must be updated manually by the pharmacist.
4. The expiry batch tracking requires manual data entry; it does not read from a supplier invoice automatically.

> **Team Notes:**
>

---

*Last updated: 2026-03-30 — add your notes directly under each answer.*
