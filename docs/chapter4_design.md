# Chapter 4: Design

---

## 4.1 System Architecture

SPIS follows a **layered pipeline architecture** with four distinct layers: Data, Processing, Model, and Presentation. Each layer depends only on the layer below it, ensuring that individual components can be developed, tested, and reused independently.

```
┌─────────────────────────────────────────────────────────────────┐
│                     PRESENTATION LAYER                          │
│                                                                 │
│   ┌──────────────────────┐      ┌──────────────────────────┐   │
│   │   Streamlit Dashboard│      │    Flask REST API        │   │
│   │   (app.py)           │      │    (routes.py)           │   │
│   └──────────┬───────────┘      └──────────┬───────────────┘   │
└──────────────┼──────────────────────────────┼───────────────────┘
               │                              │
┌──────────────┼──────────────────────────────┼───────────────────┐
│              │        MODEL LAYER           │                   │
│   ┌──────────▼───────────────────────────── ▼────────────────┐  │
│   │             Risk Classifier (risk_classifier.py)         │  │
│   │           assess_from_features() → [RiskAssessment]      │  │
│   └──────────────────────┬────────────────────────────────────┘  │
│                          │                                       │
│   ┌──────────────────────▼───────────────────────────────────┐  │
│   │             XGBoost Forecaster (forecaster.py)           │  │
│   │           forecast_30_days(atc_code) → float             │  │
│   └──────────────────────┬───────────────────────────────────┘  │
└──────────────────────────┼────────────────────────────────────────┘
                           │
┌──────────────────────────┼────────────────────────────────────────┐
│                          │   PROCESSING LAYER                     │
│   ┌──────────────────────▼───────────────────────────────────┐   │
│   │          Feature Engineering Pipeline (pipeline.py)      │   │
│   │          raw daily sales → 35-feature DataFrame          │   │
│   └──────────────────────┬───────────────────────────────────┘   │
└──────────────────────────┼────────────────────────────────────────┘
                           │
┌──────────────────────────┼────────────────────────────────────────┐
│                          │       DATA LAYER                       │
│   ┌──────────────────────▼───────────────────────────────────┐   │
│   │              SQLite Database (inventory.db)               │   │
│   │   atc_categories | drugs | sales | atc_inventory          │   │
│   └──────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────┐    │
│   │              Processed CSVs (data/processed/)            │    │
│   │   features_daily.csv | train.csv | test.csv              │    │
│   └─────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────┘
```

**Data Layer** — SQLite stores the drug reference catalogue, historical sales records, and current inventory levels. Processed CSV files cache the feature-engineered dataset to avoid recomputing the full pipeline on every forecast call.

**Processing Layer** — The pipeline module reads raw daily sales from SQLite, fills date gaps, engineers 35 time-series features, and writes `train.csv`, `test.csv`, and `features_daily.csv` to disk.

**Model Layer** — The forecaster trains and serialises the XGBoost model. The risk classifier consumes the trained model and `features_daily.csv` to produce `RiskAssessment` records.

**Presentation Layer** — The Streamlit dashboard and Flask REST API both call the risk classifier directly. The dashboard is designed for daily use by pharmacy staff; the API enables programmatic integration with external systems.

---

## 4.2 Entity-Relationship Database Design

The database consists of four tables. The two reference tables (`atc_categories`, `drugs`) are seeded at initialisation and are read-only during normal operation. The two operational tables (`sales`, `atc_inventory`) are populated and updated at runtime.

```
┌──────────────────────┐         ┌───────────────────────────────┐
│    atc_categories    │         │           drugs               │
├──────────────────────┤         ├───────────────────────────────┤
│ atc_code (PK)        │◄────────│ atc_code (FK)                 │
│ atc_name             │  1   N  │ drug_name (PK)                │
│ system_name          │         │ unit                          │
│ level1_code          │         │ is_critical                   │
│ level2_code          │         └───────────────────────────────┘
└──────────┬───────────┘
           │ 1
           │
           │ N
┌──────────▼───────────┐         ┌───────────────────────────────┐
│        sales         │         │       atc_inventory           │
├──────────────────────┤         ├───────────────────────────────┤
│ id (PK, autoincrement│         │ atc_code (PK, FK)             │
│ atc_code (FK)        │         │ current_stock                 │
│ sale_date            │         │ notes                         │
│ hour                 │         └───────────────────────────────┘
│ granularity          │
│ quantity             │
└──────────────────────┘
```

### Table Descriptions

**`atc_categories`** — Reference table for WHO ATC Level 4 drug categories. Primary key `atc_code` (e.g. `M01AB`). Stores the human-readable category name, the anatomical system, and the Level 1 and Level 2 ancestor codes for hierarchical queries.

**`drugs`** — Clinical drug catalogue. Each row represents one drug product with its parent `atc_code` (foreign key), the dispensing unit (tablets, capsules, etc.), and a binary `is_critical` flag set to 1 when a stockout poses direct patient risk (controlled substances, first-line analgesics, bronchodilators).

**`sales`** — Time-series fact table. Each row records the quantity of a drug category sold on a given date, at a given granularity (hourly, daily, weekly, or monthly). The pipeline operates exclusively on `granularity = 'daily'` rows.

**`atc_inventory`** — One row per ATC code recording the current physical stock level (`current_stock`). This table is the bridge between the database and the risk classifier: `load_atc_inventory()` reads this table and returns it as a `{atc_code: stock}` dictionary.

### Referential Integrity

- `drugs.atc_code` references `atc_categories.atc_code` (ON DELETE CASCADE).
- `sales.atc_code` references `atc_categories.atc_code`.
- `atc_inventory.atc_code` references `atc_categories.atc_code`.
- All insertions of new ATC codes must register in `atc_categories` first, then `atc_inventory`; the helper `_register_unknown_codes()` enforces this order.

---

## 4.3 Data Flow Design

The complete SPIS data flow from raw input to dashboard output proceeds in six stages:

```
┌──────────┐    ┌──────────────┐    ┌─────────────────┐
│  Raw CSV │───►│  Ingestion   │───►│  SQLite DB      │
│ (Kaggle) │    │ ingest_*.py  │    │  inventory.db   │
└──────────┘    └──────────────┘    └────────┬────────┘
                                             │ daily sales
                                             ▼
                                   ┌─────────────────────┐
                                   │  Feature Pipeline   │
                                   │  pipeline.py        │
                                   │                     │
                                   │  1. Extract daily   │
                                   │  2. Fill date gaps  │
                                   │  3. Engineer 35     │
                                   │     features        │
                                   │  4. Train/test split│
                                   └─────────┬───────────┘
                                             │ features_daily.csv
                                             │ train.csv / test.csv
                                             ▼
                                   ┌─────────────────────┐
                                   │  XGBoost Training   │
                                   │  forecaster.py      │
                                   │                     │
                                   │  1. Encode ATC      │
                                   │  2. Drop NaN rows   │
                                   │  3. GridSearchCV    │
                                   │     (512 combos,    │
                                   │      5-fold TS CV)  │
                                   │  4. Evaluate        │
                                   │  5. Serialise       │
                                   └─────────┬───────────┘
                                             │ .joblib artifacts
                                             ▼
                                   ┌─────────────────────┐
                                   │  Risk Assessment    │
                                   │  risk_classifier.py │
                                   │                     │
                                   │  For each ATC code: │
                                   │  1. Load last row   │
                                   │     as seed         │
                                   │  2. Forecast 30d    │
                                   │  3. Compute DoS     │
                                   │  4. Assign tier     │
                                   │  5. Compute order   │
                                   └──────────┬──────────┘
                                              │ [RiskAssessment]
                               ┌──────────────┴─────────────┐
                               ▼                             ▼
                   ┌───────────────────┐         ┌────────────────────┐
                   │ Streamlit Dashboard│         │  Flask REST API    │
                   │ (browser UI)       │         │  (JSON responses)  │
                   └───────────────────┘         └────────────────────┘
```

---

## 4.4 Module and Class Design

### 4.4.1 Package Structure

```
spis/
├── __init__.py                  # Package root (v0.1.0)
├── data/
│   ├── database.py              # Schema, seed data, init_db()
│   └── pipeline.py              # Feature engineering, PipelineResult
├── models/
│   ├── forecaster.py            # XGBoost training, load_model(), FEATURE_COLS
│   └── risk_classifier.py       # RiskAssessment, assess_from_features()
├── api/
│   ├── app.py                   # Flask factory: create_app()
│   └── routes.py                # Blueprint: /health, /risk, /forecast/<code>
└── dashboard/
    └── app.py                   # Streamlit single-page app
```

### 4.4.2 Key Classes and Data Structures

**`RiskAssessment` (frozen dataclass)**

```
RiskAssessment
  + atc_code:       str          -- ATC category code (e.g. "M01AB")
  + current_stock:  float        -- Units on hand at assessment time
  + forecast_30d:   float        -- Total predicted demand over 30 days
  + daily_demand:   float        -- forecast_30d / 30
  + days_of_stock:  float        -- current_stock / daily_demand (inf if demand = 0)
  + risk_tier:      str          -- CRITICAL | LOW | OK | OVERSTOCK
  + order_qty:      float        -- Recommended units to order (≥ 0)
```

Declared with `@dataclass(frozen=True)` — instances are immutable after creation, preventing accidental mutation in the presentation layer.

**`PipelineResult` (named tuple / DataFrame output)**

The pipeline module returns a dictionary of DataFrames keyed by split name:
```
{
  "features": DataFrame[date, atc_code, quantity, <35 feature cols>],
  "train":    DataFrame (rows before cutoff date),
  "test":     DataFrame (rows from cutoff date onwards)
}
```

**Flask Application Object**

Created via the `create_app(config=None)` factory. Model artifacts are loaded once at startup and attached to `app.extensions["spis_model"]` and `app.extensions["spis_encoder"]`. If artifacts are absent, the extensions are set to `None` and ML routes return HTTP 503.

### 4.4.3 Key Interfaces

```
# Data layer
init_db(db_path: str | Path) -> None
load_atc_inventory(db_path: str | Path) -> dict[str, float]

# Processing layer
run_pipeline(db_path, output_dir, cutoff_date) -> dict[str, DataFrame]

# Model layer
train_model(train_df, test_df) -> tuple[XGBRegressor, LabelEncoder, dict]
load_model(model_dir: Path) -> tuple[XGBRegressor, LabelEncoder]
forecast_30_days(atc_code, seed_row, model, encoder) -> float
assess_from_features(features_csv, inventory, model, encoder) -> list[RiskAssessment]

# Presentation layer (API)
GET /health                      -> {"status": "ok", "version": str}
GET /api/v1/risk                 -> {"assessed_at": str, "results": list[dict]}
GET /api/v1/forecast/<atc_code>  -> {"atc_code": str, "forecast_30d": float, ...}
```

---

## 4.5 Algorithm Design

### 4.5.1 Feature Engineering Algorithm

```
Algorithm: engineer_features(daily_sales_df)

Input:  DataFrame with columns [sale_date, atc_code, quantity]
        Sorted by (atc_code, sale_date) ascending.
Output: DataFrame with 35 additional feature columns.

For each atc_code group G in daily_sales_df:

    1.  CALENDAR FEATURES
        day_of_week        <- sale_date.weekday()          (0=Mon … 6=Sun)
        day_of_month       <- sale_date.day
        month              <- sale_date.month
        year               <- sale_date.year
        week_of_year       <- sale_date.isocalendar().week
        quarter            <- ceil(month / 3)
        is_weekend         <- 1 if day_of_week >= 5, else 0
        is_holiday         <- 1 if sale_date in TR_HOLIDAYS, else 0
        is_school_holiday  <- 1 if sale_date in TR_SCHOOL_BREAKS, else 0
        is_payday_window   <- 1 if day_of_month in {1,2,3,15,16,17}, else 0
        season             <- floor((month - 1) / 3) mod 4 + 1
        days_to_month_end  <- last_day_of_month(sale_date) - day_of_month

    2.  LAG FEATURES
        For d in {1, 2, 3, 7, 14, 28, 365}:
            lag_d <- quantity shifted by d rows within group G

    3.  ROLLING FEATURES
        For w in {7, 14, 28, 90, 365}:
            rolling_mean_w <- mean of quantity over past w rows
        rolling_std_7   <- std of quantity over past 7 rows
        rolling_std_28  <- std of quantity over past 28 rows
        rolling_min_7   <- min of quantity over past 7 rows
        rolling_max_7   <- max of quantity over past 7 rows

    4.  EXPONENTIAL MOVING AVERAGES
        For span in {7, 14, 28}:
            ema_span <- exponentially weighted mean (adjust=False)

    5.  DERIVED FEATURES
        lag_ratio_7   <- lag_1 / (rolling_mean_7 + ε)
        trend_counter <- days since first date in dataset
        rolling_range_7 <- rolling_max_7 - rolling_min_7
        ema_ratio       <- ema_7 / (ema_28 + ε)

Return concatenated feature DataFrame for all groups.
```

### 4.5.2 Training Algorithm

```
Algorithm: train_xgboost(train_df, test_df)

Input:  train_df, test_df — DataFrames with 35 feature columns + quantity target
Output: (best_model, label_encoder, metrics_dict)

1.  Encode ATC codes:
        encoder <- LabelEncoder()
        train_df["atc_encoded"] <- encoder.fit_transform(train_df["atc_code"])
        test_df["atc_encoded"]  <- encoder.transform(test_df["atc_code"])

2.  Drop NaN rows (from lag/rolling requiring historical lookback):
        train_df <- train_df.dropna(subset=FEATURE_COLS)

3.  Define feature matrix and target:
        X_train <- train_df[FEATURE_COLS]     // 36 columns incl. atc_encoded
        y_train <- train_df["quantity"]
        X_test  <- test_df[FEATURE_COLS]
        y_test  <- test_df["quantity"]

4.  Hyperparameter search:
        param_grid <- {
          n_estimators:    [200, 500],
          max_depth:       [4, 6],
          learning_rate:   [0.05, 0.1],
          subsample:       [0.8, 1.0],
          colsample_bytree:[0.8, 1.0],
          min_child_weight:[1, 5],
          reg_alpha:       [0]
        }
        cv <- TimeSeriesSplit(n_splits=5)
        grid <- GridSearchCV(XGBRegressor, param_grid, cv=cv,
                             scoring="neg_mean_absolute_error")
        grid.fit(X_train, y_train)
        best_model <- grid.best_estimator_

5.  Evaluate on test set:
        y_pred  <- clip(best_model.predict(X_test), min=0)
        MAE     <- mean(|y_test - y_pred|)
        RMSE    <- sqrt(mean((y_test - y_pred)^2))
        MAPE    <- mean(|y_test - y_pred| / (y_test + ε)) * 100

6.  Compute baselines for comparison:
        naive_mae   <- MAE using lag_1 as prediction
        moving_mae  <- MAE using rolling_mean_7 as prediction

7.  Serialise:
        save(best_model,  "models/xgboost_forecaster.joblib")
        save(encoder,     "models/label_encoder.joblib")
        save(metrics,     "models/metrics.json")

Return (best_model, encoder, {MAE, RMSE, MAPE, naive_mae, moving_mae})
```

### 4.5.3 Risk Assessment Algorithm

```
Algorithm: assess_from_features(features_csv, inventory, model, encoder)

Input:  features_csv — path to features_daily.csv
        inventory    — {atc_code: current_stock} dict
        model        — trained XGBRegressor
        encoder      — fitted LabelEncoder
Output: list[RiskAssessment]

1.  Load features_csv into DataFrame F.
2.  results <- []

3.  For each atc_code C in inventory:

    a.  SEED ROW: take the last row for C in F as starting context.

    b.  FORECAST 30 DAYS:
        total <- 0
        For day d in 1 .. 30:
            Build feature row R for date (last_date + d days):
              - Calendar features from actual calendar date
              - Lag / rolling / EMA features held constant
                from the seed row (best available estimate)
            R["atc_encoded"] <- encoder.transform([C])
            pred  <- max(0, model.predict(R))
            total <- total + pred
        forecast_30d <- total

    c.  COMPUTE METRICS:
        daily_demand <- forecast_30d / 30
        If daily_demand == 0:
            days_of_stock <- infinity
        Else:
            days_of_stock <- inventory[C] / daily_demand

    d.  CLASSIFY RISK TIER:
        If   days_of_stock <  3  : tier <- CRITICAL
        Elif days_of_stock <  7  : tier <- LOW
        Elif days_of_stock < 30  : tier <- OK
        Else                     : tier <- OVERSTOCK

    e.  COMPUTE ORDER QUANTITY:
        safety_buffer <- daily_demand * safety_days   (default: 3)
        order_qty     <- max(0, forecast_30d + safety_buffer - inventory[C])

    f.  Append RiskAssessment(C, inventory[C], forecast_30d,
                              daily_demand, days_of_stock, tier, order_qty)
        to results.

4.  Return results.
```

---

## 4.6 System Organisation

### 4.6.1 Module Dependencies

```
scripts/
  ingest_kaggle.py ──────────────► spis.data.database
  ingest_data.py   ──────────────► spis.data.database
  register_atc.py  ──────────────► (stdlib sqlite3 only)
  run_pipeline.py  ──────────────► spis.data.pipeline
                                     └──► spis.data.database
  train_model.py   ──────────────► spis.models.forecaster
  assess_risk.py   ──────────────► spis.models.risk_classifier
                                     └──► spis.models.forecaster (FEATURE_COLS)
  run_api.py       ──────────────► spis.api.app
                                     └──► spis.api.routes
                                            └──► spis.models.risk_classifier
  run_dashboard.py ──────────────► (subprocess: streamlit)

spis/dashboard/app.py ─────────► spis.models.forecaster
                                  spis.models.risk_classifier
```

### 4.6.2 Offline Reproducibility

All persistent state lives in three places:

| Location | Contents | Git-tracked |
|----------|----------|-------------|
| `data/inventory.db` | Drug catalogue, sales records, stock levels | No (rebuilt by scripts) |
| `data/processed/*.csv` | Feature-engineered datasets | No (rebuilt by pipeline) |
| `models/*.joblib` / `metrics.json` | Trained model artifacts | No (rebuilt by train script) |
| `spis/` Python source | All logic | **Yes** |
| `tests/` | All test code | **Yes** |
| `requirements.txt` | Dependency pins | **Yes** |

The full system can be reproduced from source code alone by running four commands:
```
python scripts/ingest_kaggle.py
python scripts/run_pipeline.py
python scripts/train_model.py
python scripts/run_dashboard.py
```
