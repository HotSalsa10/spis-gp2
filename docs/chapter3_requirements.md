# Chapter 3: Requirements Analysis

---

## 3.1 Overview

This chapter defines the user and system requirements for the Smart Pharmacy Inventory System (SPIS). Requirements were derived from the problem statement (Chapter 1), the characteristics of the target data source (a real single-site pharmacy sales dataset), and the need for a deployable, testable system by the end of GP2.

Requirements are categorised as either **functional** (what the system must do) or **non-functional** (constraints on how it must do it). Use case descriptions follow to illustrate how the identified stakeholders interact with the system.

---

## 3.2 Stakeholders

Three primary stakeholders were identified:

| Stakeholder | Role | Primary Need |
|-------------|------|--------------|
| **Pharmacy Manager** | Overall operations and procurement decisions | High-level risk summary; know what to order and how much |
| **Clinical Pharmacist** | Drug dispensing and patient interaction | Know which medications are low or critical at a glance |
| **Inventory / Storekeeper** | Day-to-day stock management | Specific order quantities and per-category stock levels |

---

## 3.3 User Requirements

User requirements are stated from the perspective of each stakeholder, expressed in natural language.

### 3.3.1 Pharmacy Manager

- **UR-M1**: The system shall provide a daily summary showing how many drug categories fall into each risk tier (CRITICAL, LOW, OK, OVERSTOCK).
- **UR-M2**: The system shall recommend how many units to order for each drug category to cover the next 30 days of demand.
- **UR-M3**: The system shall present inventory risk and order recommendations in a single web interface accessible without technical knowledge.

### 3.3.2 Clinical Pharmacist

- **UR-C1**: The system shall clearly highlight drug categories that are at risk of stockout within 3 days (CRITICAL tier).
- **UR-C2**: The system shall show, for each ATC drug category, the individual medications it contains and their risk status.
- **UR-C3**: The system shall display the predicted daily demand for each drug category alongside its current stock.

### 3.3.3 Inventory / Storekeeper

- **UR-I1**: The system shall accept historical sales data in a standard CSV format for loading into the database.
- **UR-I2**: The system shall support the registration of new drug categories (ATC codes) without code modifications.
- **UR-I3**: The system shall provide recommended order quantities per drug category, derived from a 30-day demand forecast and a configurable safety buffer.

---

## 3.4 System Requirements

### 3.4.1 Functional Requirements

```
FR-1   Data Ingestion
  FR-1.1  The system shall accept CSV files in long/tidy format
          (date, atc_code, quantity columns; names configurable).
  FR-1.2  The system shall store ingested sales records in a SQLite
          database with tables: atc_categories, drugs, sales,
          atc_inventory.
  FR-1.3  The system shall auto-register unknown ATC codes when
          invoked with the --register flag.
  FR-1.4  The system shall clip negative quantity values to zero
          during ingestion.

FR-2   Feature Engineering Pipeline
  FR-2.1  The pipeline shall operate on daily granularity data only.
  FR-2.2  The pipeline shall fill missing dates with quantity = 0.
  FR-2.3  The pipeline shall produce 35 engineered features per row:
            12 calendar  (day_of_week, month, season, is_holiday, etc.)
             7 lag        (lag_1 through lag_365)
            12 rolling   (rolling_mean_7/14/28/90/365, std, min, max, EMA)
             4 derived   (lag_ratio_7, trend_counter, rolling_range_7, ema_ratio)
  FR-2.4  The pipeline shall split data at a fixed date cutoff into
          non-overlapping train and test sets (no data leakage).

FR-3   Demand Forecasting
  FR-3.1  The system shall train an XGBoost regression model on
          the training split.
  FR-3.2  The system shall evaluate the model against a naïve
          baseline (lag_1) and a 7-day moving average baseline.
  FR-3.3  The system shall produce a 30-day ahead demand forecast
          for any registered ATC code.
  FR-3.4  Forecast predictions shall be non-negative.
  FR-3.5  Trained model artifacts shall be serialised to disk
          (xgboost_forecaster.joblib, label_encoder.joblib,
          metrics.json) and reloadable.

FR-4   Risk Classification
  FR-4.1  The system shall compute Days of Stock (DoS) as:
            DoS = current_stock / daily_demand
  FR-4.2  The system shall assign a risk tier to each ATC code:
            CRITICAL  : DoS < 3 days
            LOW       : 3 ≤ DoS < 7 days
            OK        : 7 ≤ DoS < 30 days
            OVERSTOCK : DoS ≥ 30 days
  FR-4.3  The system shall compute a recommended order quantity:
            order_qty = max(0, forecast_30d + safety_buffer − current_stock)
            where safety_buffer = daily_demand × safety_days (default: 3)
  FR-4.4  The system shall return an immutable RiskAssessment record
          per ATC code containing: atc_code, current_stock,
          forecast_30d, daily_demand, days_of_stock, risk_tier,
          order_qty.

FR-5   REST API
  FR-5.1  The API shall expose three endpoints:
            GET /health
            GET /api/v1/risk
            GET /api/v1/forecast/<atc_code>
  FR-5.2  /health shall always return HTTP 200 with system version.
  FR-5.3  /api/v1/risk shall return a full risk assessment for all
          registered ATC codes.
  FR-5.4  /api/v1/forecast/<atc_code> shall return a 30-day forecast
          for the specified code, or HTTP 404 if unknown.
  FR-5.5  All ML endpoints shall return HTTP 503 if model artifacts
          are not loaded at startup.

FR-6   Dashboard
  FR-6.1  The dashboard shall display four summary metric cards
          showing the count of ATC codes in each risk tier.
  FR-6.2  The dashboard shall display an inventory risk table with:
          ATC code, current stock, 30d forecast, daily demand,
          days of stock, risk tier (colour-coded), order quantity.
  FR-6.3  The dashboard shall display a bar chart of recommended
          order quantities per ATC code.
  FR-6.4  The dashboard shall display a medications table listing
          all individual drugs with their parent ATC code's
          risk tier and order quantity.
  FR-6.5  The dashboard shall display a clear error message if
          required model artifacts are missing, and halt execution.
```

### 3.4.2 Non-Functional Requirements

```
NFR-1   Performance
  NFR-1.1  A full risk assessment over 8 ATC codes shall complete
           in under 10 seconds on a standard laptop.
  NFR-1.2  The API /api/v1/risk endpoint shall respond in under
           5 seconds after the first warm request.

NFR-2   Reliability
  NFR-2.1  The system shall include a minimum of 75 automated unit
           and integration tests, all of which shall pass.
  NFR-2.2  The data pipeline shall detect and reject duplicate
           date-ATC pairs, null quantities, and negative values.
  NFR-2.3  The database initialisation shall be idempotent — safe
           to call multiple times without data corruption.

NFR-3   Scalability
  NFR-3.1  The system shall not hardcode any specific ATC codes
           in its core pipeline logic, enabling use with any
           pharmacy's drug catalogue.
  NFR-3.2  New drug categories shall be onboardable via a single
           CLI command without rewriting pipeline code.

NFR-4   Usability
  NFR-4.1  The full pipeline (ingest → feature engineering →
           train → dashboard) shall be reproducible via four
           sequential shell commands.
  NFR-4.2  The dashboard shall require no technical knowledge
           to operate — all controls shall be self-explanatory.

NFR-5   Portability
  NFR-5.1  The system shall run on Python 3.11 on any standard
           operating system (Windows, macOS, Linux).
  NFR-5.2  The system shall use only SQLite for storage — no
           external database server shall be required.
  NFR-5.3  All dependencies shall be declarable in a single
           requirements.txt file with minimum-version pins.

NFR-6   Maintainability
  NFR-6.1  Each pipeline stage shall be implemented as a distinct,
           independently testable module.
  NFR-6.2  Model artifacts shall be stored separately from source
           code and be rebuildable from raw data at any time.
```

---

## 3.5 Use Cases

### Use Case Diagram Summary

Four primary use cases were identified:

| Use Case | Actor | Description |
|----------|-------|-------------|
| UC-1 | Pharmacy Manager / Clinical Pharmacist | View inventory risk dashboard |
| UC-2 | Pharmacy Manager / Storekeeper | Get order recommendations |
| UC-3 | Storekeeper | Onboard new pharmacy data (register + ingest) |
| UC-4 | External System / Developer | Query forecast or risk via REST API |

---

### UC-1: View Inventory Risk Dashboard

**Actor:** Pharmacy Manager, Clinical Pharmacist

**Precondition:** Model artifacts exist (`xgboost_forecaster.joblib`, `label_encoder.joblib`) and the feature pipeline has been run.

**Main Flow:**
1. Actor opens the Streamlit dashboard via browser (`http://localhost:8501`).
2. System loads model artifacts from disk (cached after first load).
3. System runs the risk assessment for all registered ATC codes.
4. System displays four summary cards showing the count of CRITICAL, LOW, OK, and OVERSTOCK categories.
5. System displays the full risk table with stock levels, forecasts, days-of-stock, and risk tier badges.
6. System displays the order quantity bar chart and the medications table.

**Alternative Flow — Missing Artifacts:**
- At step 2, if any required file is missing, the system displays an error message listing the missing files and halts. The actor must run the pipeline and retrain the model before proceeding.

**Postcondition:** Actor has a current inventory risk snapshot for all drug categories.

---

### UC-2: Get Order Recommendations

**Actor:** Pharmacy Manager, Storekeeper

**Precondition:** Same as UC-1.

**Main Flow:**
1. Actor views the "Order Qty" column in the dashboard risk table, or calls `GET /api/v1/risk` via the REST API.
2. System returns the recommended order quantity for each ATC code, calculated as: `max(0, forecast_30d + safety_buffer − current_stock)`.
3. Actor uses the recommended quantities to place a procurement order.

**Postcondition:** Actor has data-driven order quantities for all drug categories requiring restocking.

---

### UC-3: Onboard New Pharmacy Data

**Actor:** Storekeeper / System Administrator

**Precondition:** Python environment configured; `requirements.txt` dependencies installed.

**Main Flow:**
1. Actor prepares historical sales data as a CSV file with columns: `date`, `atc_code`, `quantity`.
2. Actor runs `python scripts/register_atc.py --code <CODE> --name "<NAME>" --stock <N>` for each new drug category. *(Optional if using `--register` flag in step 3.)*
3. Actor runs `python scripts/ingest_data.py --csv sales.csv --register` to load sales data and auto-register unknown codes.
4. Actor runs `python scripts/run_pipeline.py` to rebuild the feature dataset.
5. Actor runs `python scripts/train_model.py` to retrain the XGBoost model on the new data.
6. Actor launches the dashboard to verify the results.

**Alternative Flow — Column Name Mismatch:**
- If the CSV uses non-standard column names, actor passes `--date-col`, `--atc-col`, `--qty-col` arguments to `ingest_data.py`.

**Postcondition:** System is fully configured with the new pharmacy's drug catalogue and trained on its historical data.

---

### UC-4: Query Forecast via REST API

**Actor:** External system, developer, or integration test

**Precondition:** API server running (`python scripts/run_api.py`); model artifacts loaded.

**Main Flow:**
1. Actor sends `GET /api/v1/forecast/<atc_code>` (e.g. `GET /api/v1/forecast/M01AB`).
2. System returns a JSON object with: `atc_code`, `forecast_30d`, `daily_demand`, `forecast_start`.

**Alternative Flows:**
- Unknown ATC code → HTTP 404 with `{"error": "Unknown ATC code: <code>"}`.
- Model artifacts not loaded → HTTP 503 with `{"error": "Model not loaded"}`.

**Postcondition:** Caller receives a structured 30-day demand forecast for the requested drug category.

---

## 3.6 Traceability Matrix

The table below maps each functional requirement to the system component that implements it and the test file that verifies it.

| FR | Component | Test File |
|----|-----------|-----------|
| FR-1.1 – FR-1.4 | `scripts/ingest_data.py` | `tests/test_ingest_data.py` |
| FR-2.1 – FR-2.4 | `spis/data/pipeline.py` | `tests/test_pipeline.py` |
| FR-3.1 – FR-3.5 | `spis/models/forecaster.py` | `tests/test_forecaster.py` |
| FR-4.1 – FR-4.4 | `spis/models/risk_classifier.py` | `tests/test_risk_classifier.py` |
| FR-5.1 – FR-5.5 | `spis/api/app.py`, `spis/api/routes.py` | `tests/test_api.py` |
| FR-6.1 – FR-6.5 | `spis/dashboard/app.py` | Manual (Streamlit UI) |
