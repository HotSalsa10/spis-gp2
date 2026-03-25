# Chapter 5: Implementation

## 5.1 Development Environment

The SPIS project was developed using Windows 11 Home (Build 22631) as the host operating system, with all development conducted in a Python 3.11.9 virtual environment to ensure reproducibility across team members. The project relies on SQLite 3 for data persistence, providing a lightweight, file-based relational database suitable for pharmacy inventory operations.

Key software dependencies include:

- **Python 3.11.9** – Core runtime and language
- **pandas 2.3.3** – Data manipulation and feature engineering
- **numpy 1.26.4** – Numerical computing and array operations
- **scikit-learn 1.8.0** – Preprocessing (LabelEncoder, TimeSeriesSplit, GridSearchCV)
- **XGBoost 3.2.0** – Gradient boosting for demand forecasting
- **Flask 3.1.3** – REST API framework and HTTP routing
- **Streamlit 1.54.0** – Interactive dashboard and web UI
- **pytest 9.0.2** – Test framework and test discovery
- **joblib 1.3.2** – Model serialization (pickle replacement)
- **holidays 0.35** – Turkish public holiday calendar for feature engineering
- **spacy 3.8.11 and scispacy 0.6.2** – NLP for future pharmaceutical text analysis

All dependencies are pinned in `requirements.txt` using `>=` version specifiers to allow cross-machine compatibility while ensuring minimum feature availability. The Python environment is activated via `.\venv\Scripts\activate` on PowerShell or `source venv/Scripts/activate` in bash.

Development tools included VS Code as the integrated development environment, with the Streamlit CLI (`streamlit run`) for local dashboard testing and Flask's built-in development server for API debugging.

---

## 5.2 Data Structures

### Database Schema

The SQLite database (`data/inventory.db`) defines four tables, all created and seeded by `spis.data.database.init_db()`:

**atc_categories** (8 rows – immutable reference data)
- `atc_code` (TEXT, PRIMARY KEY) – ATC-4 code, e.g. "M01AB"
- `atc_name` (TEXT) – English name, e.g. "Acemetacin"
- `system_name` (TEXT) – Anatomical system, e.g. "Musculoskeletal"
- `level1_code` to `level5_code` (TEXT) – ATC hierarchy levels

**drugs** (57 rows – complete pharmacology catalog)
- `drug_id` (INTEGER, PRIMARY KEY)
- `drug_name` (TEXT) – Trade name, e.g. "Diclofenac"
- `atc_code` (TEXT, FOREIGN KEY → atc_categories)
- `unit` (TEXT) – Measurement unit, e.g. "tablet", "vial"
- `is_critical` (INTEGER, 0 or 1) – Flag for critical medications; 25 drugs are marked critical

**sales** (424,080 rows – transactional records, git-ignored, rebuilt by ETL)
- `sale_id` (INTEGER, PRIMARY KEY)
- `atc_code` (TEXT, FOREIGN KEY)
- `sale_date` (TEXT, ISO format: "YYYY-MM-DD")
- `hour` (INTEGER, 0–23, populated only for sub-daily granularities)
- `granularity` (TEXT) – One of: "hourly", "daily", "weekly", "monthly"
- `quantity` (REAL) – Units sold

**atc_inventory** (8 rows – current stock levels, updated post-assessment)
- `atc_code` (TEXT, PRIMARY KEY)
- `current_stock` (REAL) – Units on hand
- `last_updated` (TEXT, ISO timestamp)
- `notes` (TEXT) – Optional metadata

### RiskAssessment Frozen Dataclass

The `RiskAssessment` class in `spis/models/risk_classifier.py` is an immutable result record:

```python
@dataclass(frozen=True)
class RiskAssessment:
    atc_code: str               # "M01AB"
    current_stock: float        # units on hand, e.g. 60.0
    forecast_30d: float         # predicted demand (30 days), e.g. 150.0
    daily_demand: float         # forecast_30d / 30, e.g. 5.0
    days_of_stock: float        # current_stock / daily_demand (or inf if demand=0)
    risk_tier: str              # "CRITICAL" | "LOW" | "OK" | "OVERSTOCK"
    order_qty: float            # recommended units to order
```

The frozen decorator prevents accidental mutation and enables safe use in collections (hashable).

### Pipeline DataFrame Structure

The feature engineering pipeline (`spis/data/pipeline.py`) produces a DataFrame with 38 columns:

1. **Original** (3): `atc_code`, `date` (datetime), `quantity` (float)
2. **Calendar** (12): day_of_week, day_of_month, month, year, week_of_year, is_weekend, is_holiday, season, is_payday_window, is_school_holiday, quarter, days_to_month_end
3. **Lags** (7): lag_1, lag_2, lag_3, lag_7, lag_14, lag_28, lag_365 (all float, NaN for early rows)
4. **Rolling/EMA** (12): rolling_mean_{7,14,28,90,365}, rolling_std_{7,28}, rolling_{min,max}_7, ema_{7,14,28}
5. **Derived** (4): lag_ratio_7, trend_counter, rolling_range_7, ema_ratio

After encoding ATC codes (adding `atc_encoded` as integer), the model input matrix has 36 features (35 + 1 encoded label).

---

## 5.3 Core Module Implementations

### 5.3.1 Data Ingestion

The `scripts/ingest_data.py` script loads raw pharmacy sales CSV files (date, atc_code, quantity) and appends them to the SQLite `sales` table with validation. The module is pharmacy-agnostic: it works with any CSV conforming to the long-format schema (date, drug code, quantity), registers unknown drug codes via the `--register` flag, and clips negative quantities to zero.

**Normalisation:**
- Parses date column to ISO format (YYYY-MM-DD)
- Validates that all three columns (date, atc_code, quantity) are present
- Clips negative quantities to 0 (realistic for data entry errors)
- Populates hour=0 and granularity="daily" for daily CSV ingest

**Duplicate Detection:**
- Aggregates rows with the same (atc_code, date) pair via groupby().sum()
- Ensures one logical sales record per drug per day per granularity

**Auto-Registration:**
- Checks each atc_code against `atc_categories` table
- If unknown, calls `_register_unknown_codes()` (with `--register` flag)
- Inserts new ATC code into `atc_categories` and `atc_inventory`

Code snippet showing validation and clipping:

```python
def _load_and_normalise(csv_path, date_col, atc_col, qty_col, granularity):
    df = pd.read_csv(csv_path)
    df["quantity"] = df[qty_col].clip(lower=0)  # clip negatives to 0
    df["sale_date"] = pd.to_datetime(df[date_col]).dt.date
    df["atc_code"] = df[atc_col].str.upper().str.strip()
    return df[["atc_code", "sale_date", "quantity", "granularity"]]
```

### 5.3.2 Feature Engineering Pipeline

The `spis.data.pipeline.engineer_features()` function derives 35 time-series features per row, all computed within ATC-code groups to avoid cross-drug leakage.

**Calendar Features** (12 total):
- **Temporal**: `day_of_week`, `day_of_month`, `month`, `year`, `week_of_year` – raw temporal position
- **Cyclical**: `is_weekend`, `is_holiday` (Turkish public holidays via `holidays` library), `season` (1–4 for Win/Spr/Sum/Fall)
- **Domain-specific**: `is_payday_window` (days 1–3 and 15–17 of month, when Turkish salaries are paid), `is_school_holiday` (hard-coded Turkish MEB calendar periods), `quarter`, `days_to_month_end` (captures end-of-month prescription refill spikes)

**Lag Features** (7 total):
- Shifted past quantities: `lag_1`, `lag_2`, `lag_3` (short-term momentum)
- Medium-term history: `lag_7`, `lag_14`, `lag_28` (weekly/monthly seasonality)
- Yearly seasonality: `lag_365` (same day last year)

**Rolling/EMA Features** (12 total):
- **7-day rolling**: mean, std, min, max (weekly volatility and extremes)
- **28-day rolling**: mean, std (monthly average and volatility)
- **Long-term rolling**: mean over 90 and 365 days (trend smoothing)
- **Exponential moving averages**: 7-day, 14-day, 28-day spans (weighted recency)

**Derived Features** (4 total):
- `lag_ratio_7` = lag_1 / rolling_mean_7 (spike detector: >1 means yesterday exceeded weekly average)
- `trend_counter` = days since dataset start (raw time trend)
- `rolling_range_7` = rolling_max_7 - rolling_min_7 (weekly demand volatility proxy)
- `ema_ratio` = ema_7 / ema_28 (momentum: >1 means short-term accelerating relative to long-term)

Code snippet illustrating lag and EMA construction:

```python
grouped = df.groupby("atc_code")["quantity"]
for lag in [1, 7, 14, 28, 365]:
    df[f"lag_{lag}"] = grouped.shift(lag)  # shift per ATC code
df["ema_7"]  = grouped.transform(lambda x: x.ewm(span=7).mean())
df["ema_14"] = grouped.transform(lambda x: x.ewm(span=14).mean())
df["lag_ratio_7"] = df["lag_1"] / df["rolling_mean_7"].replace(0, np.nan)
```

Missing dates are filled with quantity=0 (no sales recorded). The first 7 days of data per ATC code yield NaN lags and are dropped during train/test split.

### 5.3.3 Demand Forecasting

`spis.models.forecaster.train_and_evaluate()` orchestrates the XGBoost training pipeline:

**GridSearchCV Strategy:**
- **Cross-validation**: TimeSeriesSplit(n_splits=5) respects temporal order (no future information leaks into training)
- **Parameter grid** (512 combinations explored):
  - `n_estimators`: [200, 500]
  - `max_depth`: [4, 6]
  - `learning_rate`: [0.05, 0.1]
  - `subsample`: [0.8, 1.0]
  - `colsample_bytree`: [0.8, 1.0]
  - `min_child_weight`: [1, 5]
  - `reg_alpha`: [0, 0.1]
- **Scoring metric**: neg_mean_absolute_error (maximise negative MAE = minimise MAE)
- **Best params found**: lr=0.1, max_depth=6, n_estimators=500, subsample=0.8, colsample_bytree=0.8, min_child_weight=5, reg_alpha=0

**Model Serialisation:**
- Trained XGBoost and LabelEncoder saved via joblib to `models/xgboost_forecaster.joblib` and `models/label_encoder.joblib`
- joblib preserves numpy arrays and scikit-learn objects without conversion overhead (faster than pickle)

**30-Day Forecast Loop:**
Implemented in `forecast_30_days()` (Phase 4):

```python
total = 0.0
for i in range(30):
    d = start_date + Timedelta(days=i)
    # Calendar features computed from actual future date
    calendar_vals = {"day_of_week": d.dayofweek, "month": d.month, ...}
    # Lag/rolling features held constant from seed_row (no feedback loop)
    row_vals = {col: float(seed[col]) for col in FEATURE_COLS}
    row_vals.update(calendar_vals)
    X = pd.DataFrame([row_vals])[FEATURE_COLS]
    pred = max(0.0, model.predict(X)[0])  # clip to non-negative
    total += pred
return total
```

This conservative approach captures seasonal and holiday effects while avoiding feedback bias. Predictions are clipped to ≥0 before summing.

### 5.3.4 Risk Classification

The `spis.models.risk_classifier` module implements the DoS (Days-of-Stock) formula and tier assignment:

**DoS Formula:**
```
days_of_stock = current_stock / daily_demand
```
If daily_demand = 0, DoS = ∞ (no consumption → no stockout risk).

**Tier Assignment:**

```python
def classify_risk(days_of_stock: float) -> str:
    if days_of_stock < 3:     return "CRITICAL"   # stockout < 3 days
    if days_of_stock < 7:     return "LOW"        # stockout < 7 days
    if days_of_stock < 30:    return "OK"         # sufficient stock
    return "OVERSTOCK"        # excess stock
```

**Order Quantity Formula:**

```python
def calculate_order_qty(current_stock, forecast_30d, daily_demand, safety_days=3):
    safety_buffer = daily_demand * safety_days  # e.g. 3 days of buffer
    raw = forecast_30d + safety_buffer - current_stock
    return max(0.0, raw)
```

For example, if forecast_30d=150, daily_demand=5, current_stock=60, and safety_days=3:
- safety_buffer = 5 × 3 = 15
- order_qty = max(0, 150 + 15 - 60) = 105 units

The formula ensures stock covers 30 days of predicted demand plus an extra buffer days (default 3) for demand variability.

### 5.3.5 REST API

`spis.api.app.create_app()` is the Flask application factory:

```python
def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(_DEFAULTS)
    if config:
        app.config.update(config)

    # Eagerly load model artifacts at startup
    models_dir = Path(app.config["MODELS_DIR"])
    if (models_dir / "xgboost_forecaster.joblib").exists():
        model, encoder = load_model(models_dir)
        app.config["_MODEL"] = model
        app.config["_ENCODER"] = encoder
    else:
        app.config["_MODEL"] = None
        app.config["_ENCODER"] = None

    register_routes(app)
    return app
```

Eager model loading ensures fast failure (HTTP 503 at startup) rather than slow failure (timeout on first request).

**Endpoints** (all in `spis.api.routes`):

1. **GET /health** – Liveness check
   - Response: `{"status": "ok", "version": "0.1.0"}`
   - Always HTTP 200

2. **GET /api/v1/risk** – Full risk assessment for all ATC codes
   - Requires: Model artifacts loaded, inventory DB available
   - Response: `{"assessed_at": "2024-...", "safety_days": 3.0, "results": [RiskAssessment, ...]}`
   - Returns HTTP 503 if model artifacts absent
   - Converts float('inf') `days_of_stock` to null (JSON-safe)

3. **GET /api/v1/forecast/<atc_code>** – 30-day forecast for one ATC code
   - Path parameter: ATC-4 code (e.g. "M01AB")
   - Response: `{"atc_code": "M01AB", "forecast_30d": 152.4, "daily_demand": 5.08, "forecast_start": "2024-01-02"}`
   - Returns HTTP 404 if ATC code unknown
   - Returns HTTP 503 if model artifacts absent

All responses are JSON-formatted with proper Content-Type headers. The API is stateless and thread-safe (model and encoder are read-only after startup).

### 5.3.6 Dashboard

The Streamlit dashboard (`spis/dashboard/app.py`) provides a visual inventory monitoring interface. It runs directly against model artifacts (no API dependency) and caches computation results:

**Four-Section UI:**

1. **Summary Cards** – Tier-count metrics using `st.metric()` and emoji badges:
   - 🔴 CRITICAL count
   - 🟠 LOW count
   - 🟢 OK count
   - 🔵 OVERSTOCK count

2. **Risk Assessment Table** – DataFrame with columns:
   - Drug (ATC code)
   - In Stock (current_stock, rounded to 1 decimal)
   - 30d Forecast
   - Daily Demand
   - Days of Stock (or ∞ if zero demand)
   - Risk (colour-coded tier badge)
   - Order Qty (recommended units)

3. **Order Quantity Bar Chart** – Horizontal bar chart of order_qty per ATC code (identifies largest orders)

4. **Medications Table** – Detailed drug-level view (inherited risk and order qty from parent ATC code):
   - Drug Name
   - ATC Code
   - Unit (tablet, vial, etc.)
   - Risk (inherited from ATC tier)
   - Order Qty (inherited from ATC)

**Caching Strategy:**
- `@st.cache_resource` – Model and encoder (loaded once per session, reused across reruns)
- `@st.cache_data(ttl=300)` – Risk assessment results (cached for 5 minutes, auto-refreshes)
- `@st.cache_data` – Drug catalog (cached indefinitely, static reference data)

**Missing-Artifact Guard:**
If required files are absent, the dashboard displays an error message and stops execution:

```python
missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
if missing:
    st.error("Missing files — run the pipeline and train the model first:\n\n" + ...)
    st.stop()
```

---

## References

[1] Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. In *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining* (pp. 785–794).

[2] Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., ... & Duchesnay, E. (2011). Scikit-learn: Machine learning in Python. *The Journal of Machine Learning Research*, 12, 2825–2830.

[3] McKinney, W. (2010). Data structures for statistical computing in Python. In *Proceedings of the 9th Python in Science Conference* (Vol. 445, pp. 51–56).

[4] Ronacher, A. (2023). Flask: A lightweight WSGI web application framework. Retrieved from https://flask.palletsprojects.com/

[5] Suhail, T., & Smith, A. (2020). Streamlit: The fastest way to build and share data apps. Retrieved from https://streamlit.io/
