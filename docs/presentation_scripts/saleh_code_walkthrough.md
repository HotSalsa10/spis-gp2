# Saleh's Code Walkthrough — A Defense Preparation Learning Guide

**Purpose.** A genuine learning document, not a cheat sheet. After working through this once carefully, you should be able to defend any file in `spis/` to a committee, reason about choices you didn't personally make, and answer follow-up questions on the spot.

**Estimated reading time.** 3–4 hours done carefully. Don't try to do it in one sitting. Suggested split:

- **Session 1 (60 min):** Parts 0, 1, 2 — foundations and architecture.
- **Session 2 (60 min):** Parts 3, 4 — database + feature pipeline.
- **Session 3 (60 min):** Parts 5, 6 — forecaster + risk classifier (the heart).
- **Session 4 (60 min):** Parts 7, 8, 9 — API, dashboard, expiry.
- **Session 5 (30 min):** Parts 10, 11, 12, 13 — demo, Q&A drills, fallbacks.

**Working method.** For every file: read the section here → open the file in VS Code → trace through the code with the explanation → say the "If asked X" answers out loud → highlight the line numbers I tell you to highlight.

**The core mindset.** You don't have to have written every line. You have to be able to (a) read it, (b) explain what it does, (c) justify why it's there. Those are three different skills and they get easier in that order. We will build all three.

---

# Part 0 — How to use this document

This guide has 13 parts. Each part is self-contained but they build on each other.

### Conventions used throughout

- **Bold** = something you need to remember as a fact.
- *Italic* = a term being defined.
- `monospace` = code or file/identifier name.
- > Block-quoted text = exact words you can use in the defense.

### When you see a "Try this" box

These are mental exercises. Pause and actually do them. They are how the knowledge sticks. Two minutes of trying beats twenty minutes of re-reading.

### When you see an "If asked" box

That's a prepared answer to a likely question. Say it out loud at least once. By the third repetition it will sound natural in your own voice. The phrasing is deliberately conversational because the alternative is sounding like a textbook.

### When you see a "Honest fallback" box

When you don't know an answer, you can use this template instead of bluffing. Bluffing in a defense ends badly; admitting you'd need to check the code does not.

---

# Part 1 — Foundations: the concepts the code is built on

Before reading any file, you need a working mental model of the underlying ideas. This section gives you those models in plain language. None of this requires prior ML coursework.

## 1.1 What is "demand forecasting" really?

Imagine you sell paracetamol. Every day, some number of boxes leaves the shelf. Forecasting asks: **given the past, how many will leave in the next 30 days?**

A *time series* is just a sequence of numbers indexed by time. Daily sales of paracetamol is a time series. So is daily sales of ibuprofen, antihistamines, inhalers — anything where you can count "how much happened on each day."

Demand forecasting is the act of predicting future entries in a time series from its past entries.

### Why is it hard?

Because the past doesn't repeat perfectly. Demand changes because of:

- **Day-of-week effects** — Mondays might be busier than Fridays.
- **Seasonality** — flu medication peaks in winter.
- **Holidays** — pharmacies close on Eid; the day before sees a spike.
- **Paydays** — people stock up on payday.
- **Unpredictable events** — a flu outbreak, a price promotion.

A good forecaster captures the predictable patterns (the first four) while being honest about the unpredictable parts (the fifth).

## 1.2 What are "features"?

When a machine-learning model predicts something, it needs *inputs*. Those inputs are called **features**.

For SPIS, the *target* we want to predict is `quantity` — units sold on day D for drug group G. The *features* are everything we know that might help predict that number.

You could try to predict from just one feature ("how many did we sell yesterday?"), but that throws away most of the signal. We use 35 features grouped into 4 families. Each family captures a different temporal pattern.

### The four feature families, with examples

Imagine today is **Wednesday, March 15, 2026**, and you sold 100 boxes yesterday.

**Calendar features (12)** — *what is today like?*
- `day_of_week = 2` (Mon=0, Tue=1, Wed=2)
- `day_of_month = 15`
- `month = 3`
- `is_weekend = 0`
- `is_holiday = 0`
- `is_payday_window = 1` (the 15th is in the second payday window)
- *Why these matter:* Wednesdays might behave differently from Saturdays; mid-month after payday is a spike day.

**Lag features (7)** — *what happened on the same day in the past?*
- `lag_1 = 100` (yesterday)
- `lag_2 = 95` (two days ago)
- `lag_7 = 110` (last Wednesday)
- `lag_28 = 105` (four weeks ago)
- `lag_365 = 90` (one year ago today)
- *Why these matter:* If last Wednesday was 110 and the Wednesday before that was 108, the trend is informative. `lag_365` captures yearly seasonality (last year's March 15 was probably also a payday weekday).

**Rolling and EMA features (12)** — *what's the local average?*
- `rolling_mean_7 = 102` (average of last 7 days)
- `rolling_std_7 = 8` (volatility of last 7 days)
- `rolling_mean_28 = 98` (average of last 4 weeks)
- `ema_7 = 103` (exponentially weighted — recent days matter more)
- *Why these matter:* Smooths out noise. If yesterday was an outlier, the rolling mean isn't fooled.

**Derived features (4)** — *combinations of the above that the model would struggle to compute itself.*
- `lag_ratio_7 = lag_1 / rolling_mean_7 = 100/102 ≈ 0.98` — today's level vs. the local average. >1 means trending up.
- `ema_ratio = ema_7 / ema_28` — short-term vs. medium-term momentum.
- *Why these matter:* XGBoost can find these only by splitting on multiple features in sequence. Computing them as features makes them directly visible to a single split decision.

### Try this

Pick yesterday's date. Now imagine you sold 200 boxes of one drug yesterday. Without writing anything down, list out:

- What `lag_1`, `lag_7`, and `lag_365` would *mean* for your prediction tomorrow.
- Why `rolling_mean_7` smooths things out.

If you can do this for ten seconds, you understand why we have these features.

## 1.3 What is XGBoost, really?

XGBoost stands for **eXtreme Gradient Boosting**. It's a kind of machine-learning model built from many small **decision trees** combined together.

### A decision tree

A decision tree asks yes/no questions to make a prediction. For example:

```
Is it a weekend?
├── Yes → Is lag_7 > 100?
│        ├── Yes → predict 110
│        └── No  → predict 80
└── No  → Is ema_7 > 90?
         ├── Yes → predict 100
         └── No  → predict 70
```

One tree is usually too simple. It captures one or two rules.

### Boosting — combining many trees

*Boosting* means: train one tree, see where it's wrong, train a second tree to **correct the errors**, see where the combined prediction is wrong, train a third tree to correct *those* errors, and so on.

Each new tree is small and shallow but specifically targets the residual errors of all previous trees. After 800 trees (our `n_estimators` setting), you have a powerful combined model.

### Why "gradient" boosting

The math behind how each new tree decides what to fix uses *gradients* of a loss function. You don't need to memorise the math. You only need to know: *XGBoost trains by iteratively correcting its own mistakes, and "gradient" is the technical name for the direction it uses to do that.*

### Why XGBoost specifically (and not a deep neural network)

| Property | XGBoost | Deep neural net (LSTM, etc.) |
|---|---|---|
| Needs lots of data | No (works on thousands of rows) | Yes (millions for best results) |
| Needs a GPU | No | Often yes |
| Training time | Seconds to minutes | Minutes to hours |
| Handles tabular features | Excellent | OK but not its strength |
| Handles missing values natively | Yes (sparsity-aware splits) | Needs imputation |
| Interpretability | Feature importance scores | Black box |
| Code complexity to deploy | One `.joblib` file | A whole stack |

For *our* dataset (~17,000 daily rows × 8 drug categories), XGBoost is the natural choice. LSTM might beat it on millions of rows but would be massive overkill at this scale.

## 1.4 Train / test split and the leakage problem

When training any ML model you have to **set aside data the model never sees during training** so you can honestly measure how good it is. That set-aside data is the *test set*.

For ordinary tabular data (predicting credit risk from customer attributes), you can split randomly — pick 80% of rows for training, 20% for testing.

**For time-series data, you cannot split randomly.** Because if you do, your training set might contain July rows and your test set might contain June rows. Your model would learn from *the future* to predict *the past*, which is impossible in real life.

So we **split by date**. In SPIS:

- **Training data:** all rows where `date < 2019-01-01`. About 14,500 rows.
- **Test data:** all rows where `date >= 2019-01-01`. About 2,250 rows.

The model never sees 2019 during training. When we evaluate on 2019, we're measuring how well the model generalises to dates it has never seen.

### Cross-validation — TimeSeriesSplit, not KFold

During *training*, we also want to validate the model on multiple slices of data to pick the best hyperparameters. This is called *cross-validation*.

Regular cross-validation (`KFold`) splits randomly, which is again wrong for time series. Instead we use `TimeSeriesSplit(n_splits=5)`, which creates 5 folds like this:

```
Fold 1: train [Jan 2014 – Feb 2015],  validate [Mar 2015 – Apr 2015]
Fold 2: train [Jan 2014 – Apr 2015],  validate [May 2015 – Jun 2015]
Fold 3: train [Jan 2014 – Jun 2015],  validate [Jul 2015 – Aug 2015]
Fold 4: train [Jan 2014 – Aug 2015],  validate [Sep 2015 – Oct 2015]
Fold 5: train [Jan 2014 – Oct 2015],  validate [Nov 2015 – Dec 2015]
```

Validation always comes *after* training, chronologically. This is the only honest way to cross-validate a time series.

### If asked: "Why TimeSeriesSplit instead of KFold?"

> "Because random folds would let validation data come from earlier dates than the training data, which is impossible in production. The model would effectively be predicting the past from the future. `TimeSeriesSplit` builds folds where each validation set comes strictly after its training set chronologically, so the cross-validation behaves like real deployment."

## 1.5 Metrics: MAE, RMSE, MAPE

Once a model produces predictions, we measure error. SPIS reports three metrics:

- **MAE — Mean Absolute Error.** Average of `|prediction − actual|`. In our case, the unit is "boxes." MAE of 1.07 means "on average our prediction is off by 1.07 boxes per day per drug group."
- **RMSE — Root Mean Squared Error.** Same idea, but each error is squared before averaging, then a square root is taken. This **punishes large errors more heavily** than MAE does. RMSE is always ≥ MAE.
- **MAPE — Mean Absolute Percentage Error.** Average of `|prediction − actual| / actual × 100%`. Tells you the error relative to the actual value. Has one quirk: undefined when `actual = 0`, so we skip those rows.

### Why report all three?

Because each captures something different:

- MAE tells you the *typical* error size.
- RMSE tells you whether you're occasionally making big mistakes.
- MAPE tells you the error *relative to demand* (a 5-box error matters more for a low-volume drug than a high-volume one).

### Our numbers

| Method | MAE | RMSE | MAPE |
|---|---|---|---|
| Naive (yesterday's value) | 4.23 | 7.23 | 98.4% |
| 7-day moving average | 2.89 | 4.98 | 67.8% |
| **XGBoost** | **1.06** | **2.29** | **20.6%** |

XGBoost is roughly 4× better than naive on MAE and 5× better on MAPE.

## 1.6 The LabelEncoder concept

XGBoost can only learn from numbers. But our drug groups are strings like `"M01AB"`, `"R03"`, etc. We need to turn those into integers.

`LabelEncoder` from scikit-learn does exactly that:

```
"M01AB" → 0
"M01AE" → 1
"N02BA" → 2
"N02BE" → 3
"N05B"  → 4
"N05C"  → 5
"R03"   → 6
"R06"   → 7
```

This becomes the `atc_encoded` feature. When we predict for a new drug, we pass that same encoder the drug code and get back the same integer. The encoder is saved to `label_encoder.joblib` alongside the model.

### A small gotcha worth knowing

If someone tries to call `/api/v1/forecast/XYZ` for an ATC code that wasn't in the training data, `encoder.transform(["XYZ"])` would raise an error. The API checks `if atc_code not in encoder.classes_` first and returns a clean HTTP 404 instead of letting the error propagate.

## 1.7 Joblib and model serialization

After training, we want to save the model so we don't retrain it every time we start the server.

`joblib.dump(model, "model.joblib")` writes the trained model to a file. `joblib.load("model.joblib")` reads it back. We do this for:

- `xgboost_forecaster.joblib` — the trained XGBoost regressor
- `label_encoder.joblib` — the LabelEncoder fitted on training ATC codes

Joblib is a Python library specialised for serialising NumPy arrays efficiently, which is why we use it instead of plain `pickle`.

### If asked: "Is joblib secure?"

> "Joblib uses pickle under the hood, which is unsafe if you load files from untrusted sources because pickle can execute arbitrary code on load. In our case the model files are produced locally by our own training script and never come from outside, so it's not a security risk. In a production deployment we'd hash-pin the artifacts and validate the checksum before loading."

## 1.8 Flask app factory pattern

A Flask "app" is a single object that holds your routes, configuration, and state. The simplest pattern is to create it at module level:

```python
# don't do this in real projects
app = Flask(__name__)

@app.route("/health")
def health():
    return "ok"
```

This works for tiny demos but has two problems: (1) you can't easily configure it differently for tests vs. production, and (2) imports at the top of the module trigger app creation before you're ready.

The **application factory pattern** wraps creation in a function:

```python
def create_app(config=None):
    app = Flask(__name__)
    app.config.update(_DEFAULTS)
    if config:
        app.config.update(config)
    # load model into app.config["_MODEL"]
    register_routes(app)
    return app
```

Now tests can do `app = create_app({"DB_PATH": ":memory:"})` to inject test config. Production does `app = create_app()` to use defaults. This is the pattern we use in `spis/api/app.py`.

## 1.9 Streamlit caching: `@st.cache_resource` vs `@st.cache_data`

Streamlit re-runs your whole script every time the user interacts with the page. That would normally re-load the model, re-query the database, re-run the assessment every time — which would be horribly slow.

The fix is *caching*. Streamlit has two decorators:

- **`@st.cache_resource`** — caches an object that should be shared across users and across all reruns. Use it for *resources* like database connections and ML models. The cached object stays in memory for the lifetime of the process.

- **`@st.cache_data`** — caches the *return value of a function* and re-runs the function if its inputs change. Optionally with a TTL. Use it for *data* like query results that might change.

In `_shared.py`:

```python
@st.cache_resource
def load_artifacts():
    """Loaded once per process."""
    ...

@st.cache_data(ttl=300)
def run_assessment(_model, _encoder, _inventory):
    """Re-runs every 5 min."""
    ...
```

The first one loads the model **once per server lifetime**. The second one re-runs the risk assessment every 5 minutes (`ttl=300` seconds).

Note the underscore prefix on the arguments to `run_assessment` (`_model`, `_encoder`, `_inventory`) — that's a Streamlit convention meaning "don't hash this argument, just pass it through." Without that, Streamlit would try to compute a hash of the entire XGBoost model object every time, which is slow and would defeat the cache.

## 1.10 Frozen dataclasses

A *dataclass* in Python is a class designed primarily to hold data:

```python
@dataclass(frozen=True)
class RiskAssessment:
    atc_code: str
    current_stock: float
    forecast_30d: float
    daily_demand: float
    days_of_stock: float
    risk_tier: str
    order_qty: float
```

The `frozen=True` part makes instances **immutable** — you can't reassign their fields after creation. This is deliberate: a `RiskAssessment` is a snapshot of the system's view at one moment, and if you mutate it later you might silently corrupt downstream consumers (the dashboard, the API, the PO generator).

If you need a modified copy, you create a new one:

```python
new_ra = dataclasses.replace(ra, current_stock=ra.current_stock + 100)
```

### If asked: "Why frozen?"

> "Because a `RiskAssessment` represents a *result* — a calculation at one point in time, with a specific input snapshot. Allowing it to be mutated later would make it ambiguous whether downstream consumers are seeing the original assessment or a modified version. Freezing it forces any change to produce a new object, which keeps the data flow explicit."

## 1.11 SQLite foreign keys

A foreign key (FK) is a column in one table that references the primary key of another table. It's how relational databases enforce data integrity.

Example from our schema:

```sql
CREATE TABLE drugs (
    drug_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name   TEXT    NOT NULL UNIQUE,
    atc_code    TEXT    NOT NULL REFERENCES atc_categories(atc_code),
    ...
);
```

The `atc_code` column in `drugs` references `atc_categories.atc_code`. SQLite will refuse to let you insert a drug with an ATC code that doesn't exist in `atc_categories`.

**Important note about SQLite:** foreign keys are not enforced by default — you have to enable them per-connection:

```python
conn.execute("PRAGMA foreign_keys = ON;")
```

We do this in `init_db()`. Without it, FK constraints in `CREATE TABLE` statements are decorative; SQLite would still let you insert invalid rows.

### Cascading deletes

When a table is created with `ON DELETE CASCADE`, deleting a parent row automatically deletes the dependent rows. Our schema doesn't currently use cascade, but the design is documented as supporting it for cleanup of deprecated ATC categories.

## 1.12 The recursive forecast — why a 30-day forecast isn't 30 independent predictions

This concept comes up several times in SPIS and is worth understanding now.

XGBoost is a *one-step regressor*. Given today's features, it predicts today's quantity. It doesn't natively predict 30 days into the future.

To produce a 30-day forecast we call the model 30 times in a loop. But there's a catch: features 8 through 30 depend on lag values that *don't exist yet* because they fall after today.

There are two ways to handle this:

**A. Flat forecast (the bad way):** keep the lag, rolling, and EMA features fixed at whatever they were on the seed day, and only vary the calendar features (day of week, month, etc.). Easy to code; produces a boring flat curve with weekly wobble.

**B. Recursive forecast (the right way):** every day we predict, we *append our own prediction* to a running history buffer. The next day's lag and rolling features are computed from that updated buffer. The model's own dynamics carry through the horizon.

We use option B. Mechanically it looks like:

```
history = [seed.lag_365, seed.lag_364, ..., seed.lag_1]  # 365 numbers

for day in 0..29:
    # compute features from history's last 365 entries
    features = build_features_from(history, calendar=date+day)
    # predict
    pred = model.predict(features)
    # add it to history for the next iteration
    history.append(pred)
```

This way, the lag and rolling features evolve along with the model's own predictions, producing a realistic forward trajectory.

The downside: errors compound. If the model is off by 1 on day 1, day 2's lag features see that error, day 3 sees the compounded error, etc. That's why we picked a 30-day horizon — beyond that, the compound error starts to make the forecast unreliable.

---

# Part 2 — The architecture: four layers, top-down dependency

```
┌──────────────────────────────────────────────────────────────────┐
│  PRESENTATION                                                    │
│  - spis/dashboard/   Streamlit multi-page app (Overview + 8)     │
│  - spis/api/         Flask REST API (3 endpoints)                │
│  - scripts/          CLI tools (ingest, train, run_api, ...)     │
└────────────────────────────┬─────────────────────────────────────┘
                             ↓ calls
┌──────────────────────────────────────────────────────────────────┐
│  MODEL                                                           │
│  - spis/models/forecaster.py        XGBoost training + baselines │
│  - spis/models/risk_classifier.py   Tiering + 30-day forecast    │
│  - spis/models/expiry_advisor.py    Discount/return advisor      │
│  - spis/models/alert_engine.py      Idempotent alert emission    │
│  - spis/models/po_generator.py      Supplier-grouped PO builder  │
│  - spis/models/inventory_kpi.py     Turnover ratio                │
└────────────────────────────┬─────────────────────────────────────┘
                             ↓ reads from
┌──────────────────────────────────────────────────────────────────┐
│  PROCESSING                                                      │
│  - spis/data/pipeline.py            Feature engineering           │
│                                     35 features per (atc, day)    │
└────────────────────────────┬─────────────────────────────────────┘
                             ↓ reads from
┌──────────────────────────────────────────────────────────────────┐
│  DATA                                                            │
│  - spis/data/database.py            SQLite schema, seed, CRUD    │
│  - data/inventory.db                The actual SQLite file       │
│  - data/processed/*.csv             Feature cache (rebuildable)  │
│  - models/*.joblib                  Trained artifacts            │
└──────────────────────────────────────────────────────────────────┘
```

### Why "top-down dependency"?

The presentation layer **may** import from model, processing, and data. The model layer **may** import from processing and data. Processing **may** import from data. The data layer imports from *nothing* in `spis/`.

In other words: arrows only point downward. This means:

1. **You can change any single layer without touching the others** — provided the boundary contracts (function signatures, return types) stay the same.
2. **You can test each layer in isolation** — for example, every model test gets fake training data and doesn't need the database.
3. **You can replace any component** — swap SQLite for PostgreSQL by changing the data layer; swap Streamlit for a React app by changing the presentation layer. The rest stays the same.

### If asked: "Why this architecture?"

> "Layered architecture is the canonical way to organise a system with distinct concerns. Each of the four layers owns one job — persistence, processing, modelling, presentation. The top-down dependency rule means lower layers don't know who their callers are, which makes them reusable and independently testable. We also avoided harder alternatives like microservices because we're targeting a single-host deployment and didn't want to introduce network calls inside the system."

### The one-sentence pitch (memorise this)

> *"SPIS pulls historical sales out of SQLite, engineers 35 time-series features per day, trains XGBoost on a chronological split, classifies each drug into one of four risk tiers, and surfaces the result through a Streamlit dashboard and a Flask REST API."*

That sentence is the answer to "What is SPIS?" — and the rest of the defense is filling in details. Be able to say it in your sleep.

---

# Part 3 — The Data Layer: `spis/data/database.py`

**Open this file now and have it in front of you as you read this section.**

## 3.1 What this file does

It defines the SQLite schema (the 8 tables), seeds reference data on first run, and provides small helper functions for common CRUD operations.

The schema is **idempotent**: running `init_db()` against an existing database is safe — it uses `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE`. Nothing gets duplicated or corrupted on a second run.

## 3.2 The 8 tables, what each one stores, and why

### Reference tables (seeded once)

**`atc_categories`** — the 8 ATC drug groups.

```sql
CREATE TABLE atc_categories (
    atc_code    TEXT PRIMARY KEY,         -- 'M01AB', 'N02BE', ...
    atc_name    TEXT NOT NULL,            -- 'Acetic acid derivatives', ...
    system_name TEXT NOT NULL,            -- 'Musculoskeletal system', ...
    level1_code TEXT NOT NULL,            -- 'M', 'N', 'R'
    level2_code TEXT NOT NULL             -- 'M01', 'N02', 'N05'
);
```

The eight rows seeded in `ATC_CATEGORIES`: M01AB, M01AE, N02BA, N02BE, N05B, N05C, R03, R06. Each row also includes the higher-level WHO ATC hierarchy.

### Why ATC?

> "ATC stands for Anatomical Therapeutic Chemical Classification — it's the WHO's international system for classifying medications. Every drug in the world is assigned one. The hierarchy goes from level 1 (the anatomical system, e.g. M = Musculoskeletal) down to level 5 (the active substance). Working at level 4 (e.g. M01AB) groups related drugs by mechanism — for example all acetic acid NSAIDs together — which gives the forecaster denser, more predictable signal than forecasting each individual brand separately."

**`drugs`** — 57 individual medications, each linked to one ATC category.

```sql
CREATE TABLE drugs (
    drug_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name   TEXT    NOT NULL UNIQUE,
    atc_code    TEXT    NOT NULL REFERENCES atc_categories(atc_code),
    unit        TEXT    NOT NULL DEFAULT 'tablets',
    is_critical INTEGER NOT NULL DEFAULT 0
                CHECK (is_critical IN (0, 1))
);
```

Look at `DRUGS_CATALOG` in the file — it's a Python list of 57 tuples like `("Paracetamol", "N02BE", "tablets", 1)`. The fourth column, `is_critical`, is 1 when a stockout has direct clinical risk:
- N05B and N05C anxiolytics/hypnotics (controlled substances → withdrawal risk)
- N02BE paracetamol family (fever in children → urgent)
- R03 respiratory inhalers (asthma → emergency)

25 of the 57 drugs are flagged critical. They get surfaced in the red alert banner on the Overview page.

**`suppliers`** (Phase 9) — 4 Saudi pharma distributors with their lead times.

```sql
CREATE TABLE suppliers (
    supplier_id    INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    email          TEXT,
    phone          TEXT,
    lead_time_days INTEGER NOT NULL DEFAULT 7,
    notes          TEXT
);
```

Seeded with Tamer (3-day lead), Banaja (5), Cigalah (7), Jamjoom (4). These lead times are what motivated re-calibrating the CRITICAL threshold from <3 days to <7 days — if your supplier takes 7 days to deliver, you must alert at least that early.

### Operational tables (updated at runtime)

**`sales`** — 424,080 historical transactions.

```sql
CREATE TABLE sales (
    sale_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    atc_code    TEXT    NOT NULL REFERENCES atc_categories(atc_code),
    sale_date   TEXT    NOT NULL,
    hour        INTEGER,
    granularity TEXT    NOT NULL CHECK (granularity IN ('hourly', 'daily', 'weekly', 'monthly')),
    quantity    REAL    NOT NULL CHECK (quantity >= 0)
);
```

The Kaggle source dataset has the same sales reported at four time granularities — hourly, daily, weekly, monthly. We store all four but the forecaster only uses `granularity = 'daily'`. The other granularities are kept in case future work needs them.

The index `idx_sales_atc_date` on `(atc_code, sale_date)` speeds up the pipeline query that selects daily sales sorted by ATC and date.

**`atc_inventory`** — one row per ATC code, current stock level.

```sql
CREATE TABLE atc_inventory (
    atc_code      TEXT PRIMARY KEY REFERENCES atc_categories(atc_code),
    current_stock REAL NOT NULL CHECK (current_stock >= 0),
    last_updated  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes         TEXT
);
```

Seed values are chosen to demo all four risk tiers (40 for N02BE → CRITICAL, 60 for M01AB → LOW, 90 for N02BA → OK, 500 for M01AE → OVERSTOCK).

**`inventory_batches`** — per-batch tracking with expiry and unit cost (Phase 8.5).

```sql
CREATE TABLE inventory_batches (
    batch_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    atc_code         TEXT    NOT NULL REFERENCES atc_categories(atc_code),
    batch_number     TEXT    NOT NULL,
    quantity         REAL    NOT NULL CHECK (quantity >= 0),
    unit_cost        REAL    NOT NULL CHECK (unit_cost >= 0),
    expiry_date      TEXT    NOT NULL,
    received_date    TEXT    NOT NULL DEFAULT CURRENT_DATE,
    notes            TEXT,
    applied_discount REAL,
    returned         INTEGER NOT NULL DEFAULT 0 CHECK (returned IN (0, 1))
);
```

Three demo batches are seeded covering all expiry-tier outcomes:
- M01AE batch expires in 16 days → "cannot dispense, return to supplier"
- R06 batch expires in 41 days → "special offer 25% off"
- N02BA batch expires in 77 days → "early discount 15%"

The `returned` flag distinguishes "this batch was recalled" from "this batch sold out naturally" in the audit trail.

**`alerts`** — notification events (Phase 9).

```sql
CREATE TABLE alerts (
    alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type      TEXT NOT NULL,           -- 'LOW_STOCK', 'EXPIRY', ...
    atc_code        TEXT,
    batch_number    TEXT,
    severity        TEXT NOT NULL,           -- 'CRITICAL' / 'WARNING' / 'INFO'
    message         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TEXT
);
```

Alerts have a deterministic key `(alert_type, atc_code, batch_number)`. The alert engine refuses to create a duplicate OPEN alert with the same key — that's how the same recurring condition can't spam the operator. Acknowledging an alert sets `acknowledged_at`, which retains a history while clearing the OPEN backlog.

**`purchase_orders`** — generated POs (Phase 9).

```sql
CREATE TABLE purchase_orders (
    po_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id   INTEGER REFERENCES suppliers(supplier_id),
    supplier_name TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status        TEXT NOT NULL DEFAULT 'SENT',
    total_cost    REAL NOT NULL DEFAULT 0,
    lines_json    TEXT
);
```

`lines_json` stores the order lines as a JSON blob — this avoids creating yet another table for what's effectively a serialised payload. The PO PDF generator (`po_generator.py`) reads from this table to re-render previously sent POs if needed.

## 3.3 The `init_db` function — what it actually does

```python
def init_db(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        _create_tables(conn)
        _migrate_schema(conn)
        _seed_reference_data(conn)
        conn.commit()
```

Four steps:

1. **Enable foreign keys.** SQLite ignores FK constraints by default; this turns them on.
2. **Create tables.** All 8 with `CREATE TABLE IF NOT EXISTS` — safe to re-run.
3. **Migrate schema.** Phase 9 added two new columns to old tables (`applied_discount` and `returned` on `inventory_batches`, plus `supplier_id` on `atc_categories`). `_migrate_schema` adds these columns to *existing* databases without dropping data. New databases get them as part of `_create_tables`.
4. **Seed reference data.** Insert the 8 ATC categories, 57 drugs, 4 suppliers, 8 inventory rows, and 3 demo batches. All use `INSERT OR IGNORE` — second run is a no-op.

### If asked: "How does your schema evolve?"

> "We use additive migrations. `_migrate_schema` introspects the existing database via `PRAGMA table_info(table)`, checks whether new columns are present, and adds them with `ALTER TABLE` if missing. We don't run `DROP COLUMN` because SQLite doesn't support it cleanly and we'd rather have an unused column than risk data loss. For a production deployment we'd switch to a proper migration tool like Alembic."

## 3.4 Three lines to highlight in `database.py`

1. **Line 154–155** — `PRAGMA foreign_keys = ON;` — this is the one line that turns on referential integrity. Without it, the `REFERENCES` clauses in the schema are decorative.
2. **Lines 263–278** — the `_migrate_schema` function — shows how we evolved the schema additively between Phase 8.5 and Phase 9.
3. **Line 295** — `INSERT OR IGNORE` — the idempotency mechanism. Re-running `init_db` against an already-seeded database doesn't duplicate rows.

---

# Part 4 — The Processing Layer: `spis/data/pipeline.py`

**Open this file now.**

## 4.1 What this file does

It loads raw daily sales from SQLite, cleans them, fills missing dates, engineers 35 time-series features per row, and writes train/test CSVs split at a fixed cutoff date.

The pipeline is **deterministic** and **reproducible**: given the same database, you always get the same `train.csv` and `test.csv`. This matters because the model training depends on these files, and reproducibility is a non-negotiable for a scientific project.

## 4.2 The five stages in order

The orchestrator is `run_pipeline(db_path, output_dir)` (line 198). It calls five stages in sequence. Walk through each.

### Stage 1 — `load_daily_sales` (line 20)

```python
query = """
    SELECT atc_code, sale_date, quantity
    FROM sales
    WHERE granularity = 'daily'
    ORDER BY atc_code, sale_date
"""
```

Pulls only the daily-granularity rows from the sales table — we ignore hourly, weekly, monthly. Returns a pandas DataFrame with columns `[atc_code, date, quantity]`.

**Why daily only?** Because our forecasts are at daily resolution. The hourly data was retained for potential future work but increases noise — many drug categories have very few hourly transactions, so the daily aggregate is more informative.

### Stage 2 — `validate` (line 36)

Performs three quality checks:

1. **Drop nulls.** If any row has a null in any column, drop it and warn.
2. **Clip negatives.** Negative quantities are nonsensical (you can't sell -3 boxes). Set them to 0 and warn. This was defect D-004 — earlier versions silently kept negatives.
3. **Aggregate duplicates.** If two rows have the same `(atc_code, date)` (which shouldn't happen but can from data-entry errors), sum their quantities.

Then prints a summary of row count, date range, and ATC codes found.

### Stage 3 — `fill_missing_dates` (line 62)

This is subtle but important. For each ATC code, we want a row for **every day** in the date range — even days with zero sales.

```python
date_min = df["date"].min()
date_max = df["date"].max()
full_range = pd.date_range(date_min, date_max, freq="D")

for atc_code, group in df.groupby("atc_code"):
    group = group.set_index("date").reindex(full_range)
    group["quantity"] = group["quantity"].fillna(0.0)
    ...
```

The `reindex(full_range)` operation inserts blank rows for any missing dates, and `fillna(0.0)` fills the missing quantities with zero.

### Why is this important?

> "Because lag features depend on calendar alignment. If a pharmacy reports nothing on Sunday because it was closed, the database has no row for that Sunday. Without filling it, computing `lag_7` for Monday would skip back to Saturday — silently misaligning the seasonal signal. Filling missing dates with zero ensures `lag_7` for any Monday is genuinely 'seven calendar days ago,' which is the only correct semantics for time-series lag features."

### Stage 4 — `engineer_features` (line 110)

This is the heart of the file. It produces the 35 features in four families. The output dataframe has 3 original columns plus 35 new ones = 38 columns total.

**The four families with the code that produces them:**

**Calendar (12):** lines 115–142.

```python
df["day_of_week"]  = df["date"].dt.dayofweek
df["day_of_month"] = df["date"].dt.day
df["month"]        = df["date"].dt.month
df["year"]         = df["date"].dt.year
df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)
df["is_holiday"]   = df["date"].dt.date.isin(tr_holidays).astype(int)
df["season"]       = df["month"].map({12:1,1:1,2:1, 3:2,4:2,5:2, 6:3,7:3,8:3, 9:4,10:4,11:4})
df["is_payday_window"] = (((dom >= 1) & (dom <= 3)) | ((dom >= 15) & (dom <= 17))).astype(int)
df["is_school_holiday"] = _is_school_holiday(df["date"])
df["quarter"] = df["date"].dt.quarter
df["days_to_month_end"] = df["date"].dt.days_in_month - df["day_of_month"]
```

Notice the **training holidays are Turkish** because the training data is from a Turkish pharmacy. The live forecast in `risk_classifier.py` (we'll see this in Part 6) swaps in Saudi holidays because we're serving a Saudi pharmacy.

**Lag (7):** lines 145–149.

```python
grouped = df.groupby("atc_code")["quantity"]
for lag in [1, 2, 3, 7, 14, 28, 365]:
    df[f"lag_{lag}"] = grouped.shift(lag)
```

The seven lag horizons cover: immediate trend (1, 2, 3 days), weekly recurrence (7), bi-weekly and monthly (14, 28), and annual seasonality (365).

The **`groupby` is the critical bit**. `grouped.shift(lag)` operates *within each ATC group* — so `lag_7` for drug M01AB never accidentally picks up drug R03's history. This prevents cross-drug leakage.

**Rolling and EMA (12):** lines 151–163.

```python
df["rolling_mean_7"]  = grouped.transform(lambda x: x.rolling(7).mean())
df["rolling_std_7"]   = grouped.transform(lambda x: x.rolling(7).std())
df["rolling_mean_14"] = grouped.transform(lambda x: x.rolling(14).mean())
# ... rolling_mean_28, rolling_std_28, rolling_min_7, rolling_max_7
# ... rolling_mean_90, rolling_mean_365
df["ema_7"]  = grouped.transform(lambda x: x.ewm(span=7).mean())
df["ema_14"] = grouped.transform(lambda x: x.ewm(span=14).mean())
df["ema_28"] = grouped.transform(lambda x: x.ewm(span=28).mean())
```

Five rolling means at different windows (7, 14, 28, 90, 365 days), plus rolling standard deviation at 7 and 28 days, plus rolling min/max at 7 days, plus three exponential moving averages.

### What's an EMA?

A rolling mean weights all days in the window equally. An EMA weights *recent* days more heavily. The formula is:

```
ema_today = alpha * value_today + (1 - alpha) * ema_yesterday
```

where `alpha = 2 / (span + 1)`. So `ema_7` has `alpha = 2/8 = 0.25` — today gets 25% weight, yesterday gets 18.75%, the day before 14%, and so on geometrically.

EMAs respond to changes faster than rolling means but still smooth out single-day noise. They turned out to be the *most important* features in the trained model (`ema_14` is 48% of total importance).

**Derived (4):** lines 165–170.

```python
df["lag_ratio_7"]     = df["lag_1"] / df["rolling_mean_7"].replace(0, np.nan)
df["trend_counter"]   = (df["date"] - date_min).dt.days
df["rolling_range_7"] = df["rolling_max_7"] - df["rolling_min_7"]
df["ema_ratio"]       = df["ema_7"] / df["ema_28"].replace(0, np.nan)
```

Four engineered combinations of the base features. XGBoost can find these by chaining splits, but precomputing them makes the signal directly visible to a single tree split.

### Stage 5 — `split_train_test` (line 176)

```python
def split_train_test(df, cutoff="2019-01-01"):
    df = df.dropna(subset=["lag_7"])      # drop first 7 days per drug
    train = df[df["date"] < cutoff_dt]    # everything before cutoff
    test  = df[df["date"] >= cutoff_dt]   # everything from cutoff onwards
```

Two operations:

1. **Drop rows with NaN `lag_7`.** Those are the first 7 days of each drug — lag_7 doesn't exist yet. Note: this drops *7* rows per drug, but the forecaster's later cleanup drops a full 365 rows per drug because `lag_365` requires a full year.
2. **Split at the fixed cutoff.** `2019-01-01` is the boundary. Train ends 2018-12-31, test starts 2019-01-01.

## 4.3 Anti-leakage in this file

There are three places leakage could happen, and we prevent each one:

1. **Cross-drug leakage in lag/rolling features.** Prevented by `groupby("atc_code")` before every shift / rolling / transform.
2. **Future-to-past leakage in the train/test split.** Prevented by splitting on a fixed date rather than randomly.
3. **Holiday calendar leakage between training and serving.** The training pipeline uses Turkish holidays (matching the source data). The live `forecast_30_days` function in `risk_classifier.py` uses Saudi holidays (matching the deployment).

## 4.4 Three lines to highlight in `pipeline.py`

1. **Line 145** — `grouped = df.groupby("atc_code")["quantity"]`. This is the anti-leakage line for the lag/rolling stage.
2. **Line 148–149** — the seven-lag loop. Compact and important.
3. **Line 184** — `df = df.dropna(subset=["lag_7"])`. The reason the pipeline output has fewer rows than the raw input.

## 4.5 If asked: "Walk me through the pipeline"

> "Sure. The pipeline has five stages. First, `load_daily_sales` reads the daily-granularity rows from the `sales` table — about 17,000 rows across our 8 ATC codes. Second, `validate` drops nulls, clips negative quantities to zero, and aggregates any duplicate (atc, date) rows. Third, `fill_missing_dates` reindexes each ATC code to a complete daily date range, filling the missing days with zero so the lag features stay calendar-aligned.
>
> Fourth, `engineer_features` adds the 35 features — 12 calendar, 7 lag, 12 rolling and EMA, 4 derived. Every group-wise operation uses `groupby("atc_code")` to prevent cross-drug leakage. Fifth, `split_train_test` drops the first 7 days per drug and splits at 2019-01-01 — earlier rows are training, later rows are test.
>
> The output is three CSVs in `data/processed/`: `features_daily.csv`, `train.csv`, and `test.csv`."

---

# Part 5 — The Model Layer: `spis/models/forecaster.py`

**Open this file now.**

## 5.1 What this file does

It loads the train/test CSVs, encodes the ATC codes into integers, computes naive and moving-average baselines, performs GridSearchCV over 128 XGBoost hyperparameter combinations using TimeSeriesSplit, evaluates all three methods on the test set, and saves the trained model plus metrics plus feature importance to `models/`.

This is **the** file the committee is most likely to ask you about. Read every function in it carefully.

## 5.2 The `FEATURE_COLS` contract (lines 14–28)

```python
FEATURE_COLS = [
    "atc_encoded",
    # calendar (12)
    "day_of_week", "day_of_month", "month", "year", "week_of_year", "is_weekend",
    "is_holiday", "season", "is_payday_window", "is_school_holiday",
    "quarter", "days_to_month_end",
    # lags (7)
    "lag_1", "lag_2", "lag_3", "lag_7", "lag_14", "lag_28", "lag_365",
    # rolling (12)
    "rolling_mean_7", "rolling_std_7", "rolling_mean_14", "rolling_mean_28",
    "rolling_std_28", "rolling_min_7", "rolling_max_7", "rolling_mean_90",
    "rolling_mean_365", "ema_7", "ema_14", "ema_28",
    # derived (4)
    "lag_ratio_7", "trend_counter", "rolling_range_7", "ema_ratio",
]
```

This is the **contract between the pipeline and the model**. 36 entries: `atc_encoded` (the LabelEncoder output) plus the 35 engineered features. If the pipeline produces a different set, the model will throw a feature-count error — this was defect D-001.

The order matters: when we serialise the model and reload it later, the prediction code passes features in this exact order.

## 5.3 `encode_atc` (line 33)

```python
def encode_atc(train, test):
    encoder = LabelEncoder()
    train["atc_encoded"] = encoder.fit_transform(train["atc_code"])
    test["atc_encoded"]  = encoder.transform(test["atc_code"])
    return train, test, encoder
```

**Important detail:** `fit_transform` on train, then `transform` (not fit_transform) on test. We fit the encoder *only* on the training set, then use the same mapping for the test set. This avoids data leakage — the encoder doesn't see test data during fitting.

In our specific case it doesn't matter because all 8 ATC codes appear in both train and test, but the discipline is correct.

## 5.4 The baselines: `baseline_naive` and `baseline_moving_avg` (lines 48–55)

```python
def baseline_naive(test):
    return test["lag_1"].fillna(0).values

def baseline_moving_avg(test):
    return test["rolling_mean_7"].fillna(0).values
```

Two helper functions. Each returns a numpy array of predictions for the test set.

- **Naive baseline:** predict that today's quantity equals yesterday's quantity. Just read the `lag_1` column.
- **Moving-average baseline:** predict that today's quantity equals the average of the last 7 days. Just read the `rolling_mean_7` column.

Notice: both baselines come *from features the pipeline already computed*. The baselines cost nothing to evaluate.

### Why have baselines at all?

> "Because without them you can't tell whether the model is doing anything useful. If the naive baseline achieves MAE 4.23 and XGBoost achieves MAE 4.20, all the engineering effort was wasted. The fact that we get MAE 1.06 — roughly 4× better than naive — is the evidence that the feature engineering and the gradient boosting are actually adding value beyond what a spreadsheet formula could do."

## 5.5 `evaluate` (line 58) — the three metrics

```python
def evaluate(y_true, y_pred, label):
    mae  = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mask = y_true != 0
    if mask.sum() > 0:
        mape = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)
    else:
        mape = 0.0
    return {"model": label, "mae": mae, "rmse": rmse, "mape": mape}
```

Walk through each metric:

- **MAE:** average absolute error. Robust to outliers.
- **RMSE:** root of the mean of squared errors. Penalises large errors more (because errors are squared first).
- **MAPE:** average of `|error|/|actual| × 100`. Only computed on rows where `y_true ≠ 0` (division-by-zero protection).

## 5.6 `train_xgboost` (line 76) — the heart of the file

```python
def train_xgboost(X_train, y_train):
    param_grid = {
        "n_estimators":     [500, 800],
        "max_depth":        [6, 8],
        "learning_rate":    [0.03, 0.05],
        "subsample":        [0.8, 1.0],
        "colsample_bytree": [0.8, 1.0],
        "min_child_weight": [1, 5],
        "reg_alpha":        [0, 0.1],
    }
    xgb = XGBRegressor(objective="reg:squarederror", random_state=42, n_jobs=-1)
    tscv = TimeSeriesSplit(n_splits=5)
    grid = GridSearchCV(xgb, param_grid, cv=tscv,
                        scoring="neg_mean_absolute_error", n_jobs=-1)
    grid.fit(X_train, y_train)
    return grid.best_estimator_
```

Walk through this slowly.

### The seven hyperparameters being searched

Each has two choices, so we have 2⁷ = **128 combinations** total.

| Param | Choices | What it controls | Effect of higher value |
|---|---|---|---|
| `n_estimators` | 500 or 800 | Number of trees in the ensemble | More capacity, slower training, more overfitting risk |
| `max_depth` | 6 or 8 | Max depth of each tree | Captures finer interactions, but overfits faster |
| `learning_rate` | 0.03 or 0.05 | How much each new tree's correction influences the prediction | Faster learning, less stable |
| `subsample` | 0.8 or 1.0 | Fraction of rows each tree sees | 1.0 = use all rows; 0.8 = stochastic, reduces overfitting |
| `colsample_bytree` | 0.8 or 1.0 | Fraction of features each tree sees | Same idea but for features |
| `min_child_weight` | 1 or 5 | Min sum of instance weight per leaf | Higher = more conservative splits |
| `reg_alpha` | 0 or 0.1 | L1 regularisation on leaf weights | Higher = simpler model |

### `objective="reg:squarederror"`

This tells XGBoost we're doing **regression** (predicting a continuous number) and using **squared error** as the loss function. Each new tree is trained to reduce the squared error of the previous ensemble's predictions.

### `random_state=42`

Reproducibility. With this fixed, the stochastic operations (subsample row selection, column subsampling) are deterministic. Re-running training gives identical results.

### `n_jobs=-1`

Use all available CPU cores. XGBoost is parallelised internally and so is GridSearchCV.

### `cv=tscv` — TimeSeriesSplit(5)

This is the cross-validation strategy. With 5 splits, each candidate hyperparameter combination is evaluated 5 times across the 5 chronological folds, and the *average* validation MAE is what GridSearchCV uses to pick the best.

### `scoring="neg_mean_absolute_error"`

GridSearchCV wants to *maximise* the score. We want to *minimise* MAE. So scikit-learn defines `neg_mean_absolute_error` = `-MAE` — maximising it is equivalent to minimising MAE.

### Total fits

128 combinations × 5 folds = **640 model fits** during the search. That takes ~10–20 minutes on a laptop.

### The actual best parameters chosen

After the grid runs, the best combination is:

```
n_estimators=800, max_depth=6, learning_rate=0.03,
subsample=0.8, colsample_bytree=0.8, min_child_weight=1, reg_alpha=0
```

Interpretation: the grid picked the **most flexible** settings on every axis except `max_depth` and `learning_rate`, where it picked the **more conservative** option. That's a sensible combination — let the ensemble be wide and stochastic, but keep each tree shallow and learn gently.

### If asked: "Why these parameter ranges?"

> "We deliberately picked a narrow grid with 2 values per parameter, giving 128 total combinations. We learned from earlier Phase 3 experiments that the model was relatively robust to hyperparameter choices in the right neighbourhood, so a narrow grid was sufficient to find a good combination without spending hours on a huge search. The chosen values bracket what we expected to be reasonable defaults — learning_rate around 0.03–0.05, max_depth 6–8, subsample 0.8–1.0 — and the grid confirmed the lower-learning-rate, shallower-tree combination."

## 5.7 `get_feature_importance` (line 112)

```python
def get_feature_importance(model, feature_names):
    importance = model.feature_importances_
    df = pd.DataFrame({"feature": feature_names, "importance": importance})
    return df.sort_values("importance", ascending=False)
```

XGBoost computes a built-in measure of how much each feature contributed to splits across all trees. We sort by importance and save the result to `models/feature_importance.json` so the dashboard's Analytics page can display it.

### The actual top features

From a real training run:

| Feature | Importance |
|---|---|
| `ema_14` | 0.48 |
| `ema_7` | 0.27 |
| `rolling_mean_14` | 0.03 |
| `is_weekend` | 0.03 |
| `ema_28` | 0.02 |

The EMA features together account for ~77% of model importance. This tells you a lot: the model is mostly learning from smoothed recent demand. The calendar features are useful but secondary.

### If asked: "Show me the most important feature"

> "It's `ema_14` — the 14-day exponentially weighted moving average. It's by far the most informative single feature, contributing about 48% of total importance. Together with `ema_7` and `ema_28` it captures 77% of the model's signal. That makes intuitive sense: recent demand smoothed at medium horizon is the strongest indicator of next-day demand."

## 5.8 `train_and_evaluate` (line 125) — the orchestrator

This function ties everything together. It:

1. Loads `train.csv` and `test.csv`.
2. Encodes the ATC codes (`encode_atc`).
3. Drops training rows with NaN features (incomplete history — the first year of each drug).
4. Splits features and target. For the test set, fills any remaining NaNs with 0 — these are early test rows where some lag features haven't existed long enough.
5. Computes the two baseline predictions (no training needed).
6. Trains XGBoost (`train_xgboost` — this is where the 10–20 minutes happen).
7. Predicts on the test set, clips predictions to ≥ 0.
8. Computes the three metrics for all three methods.
9. Saves four artifacts to `models/`: `xgboost_forecaster.joblib`, `label_encoder.joblib`, `metrics.json`, `feature_importance.json`.

### Why clip predictions to ≥ 0?

> "XGBoost is a regression model — it can predict any real number, including tiny negatives due to floating-point arithmetic or because the residual correction overshoots. But you can't sell a negative number of medication boxes, so we clip predictions at zero before reporting them. This was defect D-005 — earlier versions let tiny negative predictions through, which then polluted the rolling history buffer in the recursive forecast loop."

## 5.9 `load_model` (line 215)

```python
def load_model(model_dir):
    model = joblib.load(model_dir / "xgboost_forecaster.joblib")
    encoder = joblib.load(model_dir / "label_encoder.joblib")
    return model, encoder
```

Used by everything that needs the trained model — the API factory, the dashboard's `_shared.load_artifacts`, the test fixtures.

## 5.10 Three lines to highlight in `forecaster.py`

1. **Line 14** — the `FEATURE_COLS` list. The contract between pipeline and model.
2. **Line 78** — the `param_grid`. 128 combinations.
3. **Line 94** — `TimeSeriesSplit(n_splits=5)`. The no-leakage line.

## 5.11 If asked: "Walk me through training, step by step"

> "Sure. We start by loading the train and test CSVs the pipeline produced. Then we fit a LabelEncoder on the train set's ATC codes — that turns the categorical drug-group identifier into an integer the model can use. We apply the same encoder to the test set without re-fitting.
>
> Then we drop training rows with NaN features — those are the first 365 days of each drug, because `lag_365` requires a year of history. We don't want to teach the model that 'no history' looks like a zero-sales day.
>
> Then we compute the two baselines. Naive is just yesterday's value, read from `lag_1`. Moving Average is the 7-day rolling mean, read from `rolling_mean_7`.
>
> For XGBoost we set up a 7-dimensional parameter grid — 2 values for each of 7 hyperparameters, giving 128 combinations. We wrap it in scikit-learn's `GridSearchCV` with `TimeSeriesSplit` for 5 folds, scoring on negative MAE. `n_jobs=-1` runs the candidates in parallel across CPU cores.
>
> After `grid.fit` finishes, the best estimator is what we keep. We predict on the test set, clip negative predictions to zero, and compute MAE, RMSE, and MAPE for all three methods.
>
> Finally we save four artifacts — the trained model and encoder via joblib, plus the metrics and feature importance as JSON for the dashboard."

---

# Part 6 — The Model Layer: `spis/models/risk_classifier.py`

**Open this file now.** This is the second most important file in the project.

## 6.1 What this file does

It takes the trained forecaster and the current stock for each ATC code, runs a recursive 30-day forecast, divides current stock by daily demand to compute *days of stock*, classifies that into one of four risk tiers, computes a safety-buffered order quantity, and returns the result as an immutable `RiskAssessment` dataclass.

## 6.2 The tier thresholds (lines 16–18)

```python
TIER_CRITICAL: float = 7.0
TIER_LOW: float = 14.0
TIER_OK: float = 90.0
```

Three boundaries. Less than 7 days of stock is CRITICAL. 7 to 14 days is LOW. 14 to 90 days is OK. 90 days or more is OVERSTOCK.

### Why these specific numbers?

| Tier | Boundary | Why |
|---|---|---|
| CRITICAL < 7 | Supplier lead time is 3–7 days | Below 7 days you cannot guarantee replenishment before stockout |
| LOW 7–14 | Two-week early warning | One full review cycle to place a routine order |
| OK 14–90 | Normal operating band | Sufficient stock, no procurement action needed |
| OVERSTOCK ≥ 90 | Three months | Capital tied up, expiry risk begins to dominate |

The original Phase-4 design used (3, 7, 30). We re-calibrated to (7, 14, 90) in Phase 8.5 after observing that CRITICAL at <3 days was already too late given real supplier lead times.

## 6.3 The `RiskAssessment` dataclass (lines 21–29)

```python
@dataclass(frozen=True)
class RiskAssessment:
    atc_code: str
    current_stock: float
    forecast_30d: float
    daily_demand: float
    days_of_stock: float
    risk_tier: str
    order_qty: float
```

Seven fields. Immutable. This is the value object that flows through the entire system — the API returns it, the dashboard renders it, the PO generator reads it.

## 6.4 `classify_risk` (line 32)

```python
def classify_risk(days_of_stock):
    if days_of_stock < TIER_CRITICAL: return "CRITICAL"
    if days_of_stock < TIER_LOW:      return "LOW"
    if days_of_stock < TIER_OK:       return "OK"
    return "OVERSTOCK"
```

Four-way piecewise function. Test cases at boundaries:

- `classify_risk(0.0)` → CRITICAL
- `classify_risk(6.999)` → CRITICAL
- `classify_risk(7.0)` → LOW (the boundary belongs to LOW because the condition is strict `<`)
- `classify_risk(13.999)` → LOW
- `classify_risk(14.0)` → OK
- `classify_risk(89.999)` → OK
- `classify_risk(90.0)` → OVERSTOCK
- `classify_risk(inf)` → OVERSTOCK (drugs with zero demand)

## 6.5 `calculate_order_qty` (line 42) — the formula

```python
def calculate_order_qty(current_stock, forecast_30d, daily_demand, safety_days=3.0):
    safety_buffer = daily_demand * safety_days
    raw = forecast_30d + safety_buffer - current_stock
    return float(max(0.0, raw))
```

This is the formula that lives on slide 18 of the deck.

### Worked example

Say a drug has:
- Current stock: 50 units
- Forecast for next 30 days: 300 units total
- Daily demand: 300 / 30 = 10 units/day

With `safety_days = 3`:
- `safety_buffer = 10 × 3 = 30`
- `raw = 300 + 30 - 50 = 280`
- `order_qty = max(0, 280) = 280` units

If the same drug had 500 units in stock:
- `raw = 300 + 30 - 500 = -170`
- `order_qty = max(0, -170) = 0` (don't order, we already have plenty)

### If asked: "Why a safety buffer?"

> "Because the 30-day forecast is the *expected* demand, not the worst case. Demand has volatility — weekday spikes, holiday surges, prescription pattern shifts. Ordering exactly forecast minus stock would give us a 50% probability of stockout, because whenever realised demand exceeds the forecast, we'd run out. The buffer of `daily_demand × safety_days` is a deliberate over-order that absorbs forecast error and supplier lead-time variance, converting an expected-value rule into a service-level rule."

### If asked: "Why max(0, …)?"

> "Because the system never recommends a return. If current stock already exceeds the forecast plus the safety buffer, the formula would produce a negative number, which would be a nonsense recommendation. Clamping at zero gives the correct operational meaning: 'don't place an order this cycle.' The OVERSTOCK tier surfaces the over-supply condition separately."

## 6.6 `build_risk_assessment` (line 53) — the per-ATC factory

```python
def build_risk_assessment(atc_code, current_stock, forecast_30d, daily_demand,
                          safety_days=3.0):
    if daily_demand > 0:
        days_of_stock = current_stock / daily_demand
    else:
        days_of_stock = float("inf")

    risk_tier = classify_risk(days_of_stock)
    order_qty = calculate_order_qty(current_stock, forecast_30d, daily_demand, safety_days)

    return RiskAssessment(atc_code=atc_code, ...)
```

Combines days-of-stock calculation, tier classification, and order-quantity calculation into one immutable `RiskAssessment`.

The `float("inf")` for zero demand is significant. We can't divide by zero — but conceptually, if demand is zero, current stock lasts forever. We use infinity as the explicit representation of "forever," which gets classified as OVERSTOCK.

In the API layer, infinity gets converted to JSON `null` before serialisation (see Part 7).

## 6.7 `forecast_30_days` (line 88) — the recursive forecast loop

**This is the most complex function in the project. Read it carefully.**

The function produces a 30-day forecast for one ATC code starting from a "seed" row of features. The forecast is *recursive*: every predicted day is appended to a 365-day history buffer, and the next day's lag and rolling features are computed from that updated buffer.

### Signature

```python
def forecast_30_days(model, encoder, seed_row, atc_code, start_date,
                     days=30, return_daily=False):
```

- `model`, `encoder` — the trained XGBoost regressor and LabelEncoder.
- `seed_row` — one row from `features_daily.csv` containing the most recent (lag_1, lag_2, ..., lag_365, ema_7, ...) values.
- `atc_code` — the drug we're forecasting.
- `start_date` — the first day of the forecast (typically the day after the last data point).
- `days` — how far to forecast. Defaults to 30.
- `return_daily` — if True, return a list of 30 per-day predictions; if False, return the sum.

### Step 1 — sanity check (lines 98–103)

```python
if atc_code not in encoder.classes_:
    raise ValueError(...)
```

If the requested ATC code wasn't in the training data, the encoder can't transform it — raise an explicit error rather than crashing inside the model.

### Step 2 — Saudi holiday calendar (lines 107–109)

```python
tr_holidays = holidays.SaudiArabia(
    years=range(start_date.year, start_date.year + 2)
)
```

Note: the *training* pipeline used Turkish holidays (matching the source data). The *serving* code uses Saudi Arabian holidays (matching the pilot pharmacy). This is a deliberate domain-adaptation choice — we want the calendar features at serving time to reflect *the operating context*, not the training context.

### Step 3 — Initialise the 365-day history buffer (lines 111–125)

```python
history = [float(seed.get("lag_365", seed["lag_1"]))] * (365 - 28)
history += [float(seed.get("lag_28", seed["lag_1"]))] * (28 - 14)
history += [float(seed.get("lag_14", seed["lag_1"]))] * (14 - 7)
history += [float(seed.get("lag_7",  seed["lag_1"]))] * (7 - 3)
history += [
    float(seed.get("lag_3", seed["lag_1"])),
    float(seed.get("lag_2", seed["lag_1"])),
    float(seed["lag_1"]),
]
```

We need 365 historical values to compute `rolling_mean_365`. We only have 7 lag values stored in the seed row (lag_1, lag_2, lag_3, lag_7, lag_14, lag_28, lag_365). We approximate the missing days by **repeating** the nearest lag value:

- Days 1–337 (i.e. 365–28 days back): repeat the lag_365 value.
- Days 338–351 (28–14 back): repeat lag_28.
- Days 352–358 (14–7 back): repeat lag_14.
- Days 359–362 (7–3 back): repeat lag_7.
- Day 363 = lag_3, Day 364 = lag_2, Day 365 = lag_1.

This isn't perfect — we don't reconstruct the actual day-by-day history. But the model needs the *rolling means* and they're robust to this approximation. The `rolling_mean_365` is still accurate because it averages over a year and individual days don't matter much.

### Step 4 — Initialise EMA state and the daily loop (lines 127–212)

EMAs are stateful — they depend on their previous value. We initialise from the seed row:

```python
ema7  = seed.ema_7
ema14 = seed.ema_14
ema28 = seed.ema_28
```

Then the main loop:

```python
for i in range(30):
    d = start_date + pd.Timedelta(days=i)

    # Compute all 35 features for day d using:
    #   - the calendar of d (day_of_week, month, is_weekend, is_holiday, ...)
    #   - lag_X read from history[-X]
    #   - rolling stats computed over slices of history
    #   - the running EMA values

    X = pd.DataFrame([feature_dict])[FEATURE_COLS]
    pred = max(0.0, float(model.predict(X)[0]))  # clip to ≥ 0
    daily_preds.append(pred)

    # Update state for the next iteration:
    history.append(pred)
    ema7  = ema7  + alpha7  * (pred - ema7)
    ema14 = ema14 + alpha14 * (pred - ema14)
    ema28 = ema28 + alpha28 * (pred - ema28)
    trend_counter += 1
```

The five things happening each iteration:

1. **Compute the day's features** from the history buffer (lags, rollings) and the calendar of the current date.
2. **Predict** with the model. Clip at 0.
3. **Append the prediction to the history buffer** — this is the "recursive" part.
4. **Update the EMA values** using the standard EMA recursion: `new = old + alpha * (pred - old)`.
5. **Increment `trend_counter`** so it grows by 1 each day.

After 30 iterations, the function returns either the list of daily predictions (if `return_daily=True`) or their sum.

### EMA update formula explained

```
new_ema = old_ema + alpha * (prediction - old_ema)
```

This is mathematically identical to:

```
new_ema = alpha * prediction + (1 - alpha) * old_ema
```

Both express: "the new EMA is a weighted average of today's prediction and yesterday's EMA, with weight alpha on today." We use the first form because it's the conventional incremental update — easier to read and slightly faster numerically.

### Try this

Imagine the seed row says `lag_1=100`, `lag_7=110`, `ema_14=105`, `is_weekend=0` and today is a Tuesday. The model predicts 102 for tomorrow. What changes?

- `history.append(102)` — now `history[-1] = 102`.
- For *the day after tomorrow*, `lag_1` will be 102 (from this iteration), `lag_2` will be 100 (the seed's lag_1), `lag_7` will become whatever was at history[-7].
- `ema_14` will update: `new = 105 + (2/15) × (102 − 105) = 105 + 0.133 × (-3) ≈ 104.6`. The EMA edges slightly down because today's prediction was below the EMA.

If you can walk through this in your head, you understand the recursive forecast.

## 6.8 `assess_from_features` (line 228)

```python
def assess_from_features(features_csv, inventory, model, encoder,
                         start_date=None, safety_days=3.0, output_csv=None):
```

This is the orchestrator that runs the per-ATC assessment for **every** ATC code in the inventory dict, returns the list of `RiskAssessment` records, optionally writes a CSV.

The loop body (lines 250–270) for each ATC code:

1. Pull the most recent feature row for that ATC from the cached features CSV.
2. Call `forecast_30_days` to get the 30-day total.
3. Compute `daily_demand = forecast_30d / 30`.
4. Call `build_risk_assessment` to wrap everything into a `RiskAssessment`.
5. Print a one-line summary to the console.

After the loop, print a tier-count summary (`_print_summary`, line 303) and optionally write the assessment CSV.

## 6.9 Three lines to highlight in `risk_classifier.py`

1. **Lines 16–18** — the tier thresholds. `7 / 14 / 90`.
2. **Lines 42–50** — `calculate_order_qty`. The formula.
3. **Line 208** — `history.append(pred)`. The single line that makes the forecast recursive.

## 6.10 If asked: "Why recursive forecasting?"

> "If we held the lag and rolling features constant at the seed-row values for all 30 days, the forecast would be a flat line with only a weekly calendar wobble. The model never actually changes its internal view. By appending each prediction to a 365-day history buffer and recomputing lag, rolling, and EMA features from that buffer, the model's own dynamics carry through the horizon — the 30-day curve shows realistic day-to-day variation that matches what XGBoost learned from the training data. The cost is that errors compound, which is one reason we cap the horizon at 30 days rather than going longer."

---

# Part 7 — The Presentation Layer: REST API

**Open `spis/api/app.py` and `spis/api/routes.py`.**

## 7.1 `spis/api/app.py` — the Flask application factory

40 lines. Read every one.

```python
_DEFAULTS: dict = {
    "DB_PATH":       "data/inventory.db",
    "FEATURES_PATH": "data/processed/features_daily.csv",
    "MODELS_DIR":    "models",
    "SAFETY_DAYS":   3.0,
}

def create_app(config=None):
    app = Flask(__name__)
    app.config.update(_DEFAULTS)
    if config:
        app.config.update(config)

    models_dir = Path(app.config["MODELS_DIR"])
    model_file = models_dir / "xgboost_forecaster.joblib"
    encoder_file = models_dir / "label_encoder.joblib"

    if model_file.exists() and encoder_file.exists():
        model, encoder = load_model(models_dir)
        app.config["_MODEL"] = model
        app.config["_ENCODER"] = encoder
    else:
        app.config["_MODEL"] = None
        app.config["_ENCODER"] = None

    register_routes(app)
    return app
```

### The four pieces

1. **`_DEFAULTS`** — sensible default config that any test or production call can override.
2. **`create_app(config=None)`** — the factory. Accepts an optional config dict for testing.
3. **Eager model loading** — at startup, check whether the model files exist. If yes, load them and stash in `app.config`. If no, set both to `None`.
4. **`register_routes(app)`** — wire the API routes onto the app.

### If asked: "Why eager-load the model?"

> "Joblib deserialisation of the trained tree ensemble takes a couple of seconds. If we lazy-loaded on the first request, the first user would experience a slow request. By eager-loading at app startup, the first request is as fast as the hundredth. The trade-off is that the server takes a few seconds to start, which is acceptable. The eager load also lets us fail-fast at startup if artifacts are corrupted, rather than mid-request."

### If asked: "What happens if the model files don't exist?"

> "The factory still creates the app — it doesn't crash — but `_MODEL` and `_ENCODER` stay `None`. Any route that needs them checks `_model_loaded()` and returns HTTP 503 Service Unavailable with a JSON message telling the operator to run `scripts/train_model.py`. The `/health` endpoint still works so a load balancer or supervisor can tell the process itself is alive."

## 7.2 `spis/api/routes.py` — the three endpoints

109 lines. Three endpoints. All read-only.

### `_ra_to_dict` helper (line 25)

```python
def _ra_to_dict(ra) -> dict:
    d = dataclasses.asdict(ra)
    if d.get("days_of_stock") == float("inf"):
        d["days_of_stock"] = None
    return d
```

Converts a `RiskAssessment` dataclass into a dict ready for JSON serialisation. The catch: JSON has no representation for infinity. For drugs with zero daily demand, `days_of_stock = inf`. We convert that to JSON `null` so the response is valid.

This was defect D-002 — earlier versions tried to serialise `inf` directly and crashed.

### `_model_loaded` helper (line 33)

```python
def _model_loaded():
    return (
        current_app.config.get("_MODEL") is not None
        and current_app.config.get("_ENCODER") is not None
    )
```

Boolean check for whether the model artifacts are usable.

### `/health` (line 40)

```python
@bp.get("/health")
def health():
    return jsonify({"status": "ok", "version": VERSION})
```

Always returns 200 OK. No model required. Used by load balancers, supervisor scripts, and `pytest` smoke tests.

### `/api/v1/risk` (line 45)

```python
@bp.get("/api/v1/risk")
def risk_assessment():
    if not _model_loaded():
        return jsonify({"error": "Model artifacts not loaded..."}), 503

    model = current_app.config["_MODEL"]
    encoder = current_app.config["_ENCODER"]
    db_path = Path(current_app.config["DB_PATH"])
    features_path = Path(current_app.config["FEATURES_PATH"])
    safety_days = float(current_app.config["SAFETY_DAYS"])

    inventory = load_atc_inventory(db_path)
    results = assess_from_features(
        features_csv=features_path,
        inventory=inventory,
        model=model,
        encoder=encoder,
        safety_days=safety_days,
        output_csv=None,
    )

    return jsonify({
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "safety_days": safety_days,
        "results": [_ra_to_dict(ra) for ra in results],
    })
```

Returns the full risk assessment for every ATC code. The response includes a UTC timestamp, the safety-days setting used, and the array of assessment objects.

### `/api/v1/forecast/<atc_code>` (line 76)

```python
@bp.get("/api/v1/forecast/<atc_code>")
def forecast(atc_code):
    if not _model_loaded():
        return jsonify({"error": "Model artifacts not loaded..."}), 503

    model = current_app.config["_MODEL"]
    encoder = current_app.config["_ENCODER"]

    if atc_code not in encoder.classes_:
        return jsonify({"error": f"Unknown ATC code: {atc_code}"}), 404

    features_path = Path(current_app.config["FEATURES_PATH"])
    df = pd.read_csv(features_path, parse_dates=["date"])
    atc_rows = df[df["atc_code"] == atc_code].sort_values("date")
    if atc_rows.empty:
        return jsonify({"error": f"No feature data found for {atc_code}"}), 404

    seed_row = atc_rows.tail(1).reset_index(drop=True)
    start_date = df["date"].max() + pd.Timedelta(days=1)

    forecast_30d = forecast_30_days(model, encoder, seed_row, atc_code, start_date)
    daily_demand = forecast_30d / 30.0

    return jsonify({
        "atc_code":       atc_code,
        "forecast_30d":   round(forecast_30d, 4),
        "daily_demand":   round(daily_demand, 4),
        "forecast_start": start_date.date().isoformat(),
    })
```

Returns the 30-day forecast for a single ATC code. Three error paths:

- 503 if the model isn't loaded.
- 404 if the ATC code isn't in the encoder.
- 404 if there's no feature data for it (shouldn't happen if it's in the encoder, but defensive).

The success response has `atc_code`, the 30-day total, the implied daily demand, and the start date of the forecast.

## 7.3 Three lines to highlight in the API code

1. **`app.py` line 31** — `if model_file.exists() and encoder_file.exists():` — the existence check that drives 503 behaviour.
2. **`routes.py` line 28** — `if d.get("days_of_stock") == float("inf"): d["days_of_stock"] = None` — the JSON-safety fix.
3. **`routes.py` line 87** — `if atc_code not in encoder.classes_:` — the 404 path for unknown codes.

## 7.4 If asked: "Walk me through what `/api/v1/risk` does"

> "First it checks that the model is loaded. If not, return 503 with a JSON message telling the operator what to do.
>
> Then we pull the model, encoder, database path, features path, and safety-days setting from the app config.
>
> We load the current stock for every ATC code from the `atc_inventory` table — that's `load_atc_inventory`. It returns a dict mapping ATC code to current stock.
>
> Then we hand everything off to `assess_from_features` in the risk_classifier module. It runs the 30-day forecast for each ATC code, computes days-of-stock, classifies the tier, and computes the order quantity. It returns a list of `RiskAssessment` records.
>
> We serialise that list to JSON. The `_ra_to_dict` helper converts each dataclass to a dict and replaces any `float('inf')` with `null` so the JSON is valid. The response includes a UTC timestamp, the safety-days setting, and the array of assessments."

---

# Part 8 — The Presentation Layer: Streamlit Dashboard

**Open `spis/dashboard/_shared.py` and `spis/dashboard/app.py`.**

## 8.1 `_shared.py` — caching, helpers, CSS

This is the "library" file every dashboard page imports from. It's responsible for:

1. **CSS injection** — the dark-mode visual theme.
2. **Caching helpers** — `load_artifacts`, `run_assessment`, `load_atc_names`, `load_drugs`, `load_atc_labels`.
3. **Path constants** — `MODELS_DIR`, `DB_PATH`, `FEATURES_CSV`.
4. **Required-files guard** — `check_required_files()`.

### `inject_css()` (line 202)

```python
def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)
```

Streamlit doesn't have first-class theming. We inject a `<style>` block with custom CSS that styles:

- Dark backgrounds (`#0e1117` app, `#161b27` cards).
- KPI cards with coloured top borders (red/orange/green/blue for the four tiers).
- The CRITICAL alert banner.
- DataFrames with rounded corners and shadows.
- Buttons and form containers.

The actual CSS is the `_CSS` constant — about 180 lines of stylesheet, just modifying Streamlit's defaults.

### `load_artifacts()` (line 220)

```python
@st.cache_resource
def load_artifacts():
    model, encoder = load_model(MODELS_DIR)
    inventory = load_atc_inventory(DB_PATH)
    return model, encoder, inventory
```

`@st.cache_resource` means this function runs **once per server lifetime**. The model and encoder are deserialised once; subsequent page navigations reuse the same in-memory objects.

### `run_assessment()` (line 228)

```python
@st.cache_data(ttl=300)
def run_assessment(_model, _encoder, _inventory):
    return assess_from_features(
        features_csv=FEATURES_CSV,
        inventory=_inventory,
        model=_model,
        encoder=_encoder,
    )
```

`@st.cache_data(ttl=300)` caches the result for 5 minutes. Subsequent page loads within 5 minutes reuse the cached assessment without re-running the recursive forecast loop.

The underscore prefix on the arguments (`_model`, `_encoder`) tells Streamlit "don't try to hash these arguments to invalidate the cache." Without it, Streamlit would attempt to hash the entire XGBoost model, which is slow and would defeat the cache.

### `load_atc_names`, `load_drugs`, `load_atc_labels`

Three `@st.cache_data` helpers that query the SQLite database for reference data (ATC categories, drug names, drug-to-ATC mappings). All cached without TTL — they don't change at runtime.

### `check_required_files()` (line 284)

```python
def check_required_files():
    missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
    if missing:
        st.error("Missing files — run the pipeline and train the model first:\n\n"
                 + "\n".join(f"- `{p}`" for p in missing))
        st.stop()
    return True
```

Before any page renders content, we check that the four required files exist:

- `models/xgboost_forecaster.joblib`
- `models/label_encoder.joblib`
- `data/inventory.db`
- `data/processed/features_daily.csv`

If any is missing, display an error message listing exactly which files are missing and which command would regenerate them, then **stop the page** (`st.stop()`). This means the user sees a clear actionable message rather than a stack trace or empty page. This was defect D-006 territory — early versions silently failed.

## 8.2 `app.py` — the Overview page

255 lines. This is the page the committee will see at the start of your live demo. Read every section.

### Layout sections in render order

1. **Header (lines 32–45)** — title, subtitle, divider.
2. **Required-files guard (line 47)** — `check_required_files()` halts the page if anything is missing.
3. **Spinner-wrapped assessment (lines 49–51)** — runs the risk assessment, cached.
4. **CRITICAL alert banner (lines 62–86)** — appears at the top if any drug is in the CRITICAL tier.
5. **Four KPI cards (lines 88–108)** — tier counts as big numbers with hint text.
6. **Donut chart + Order bar chart side-by-side (lines 113–171)** — two Plotly charts in a `st.columns([2, 3])` grid.
7. **Inventory risk table (lines 175–214)** — Pandas DataFrame styled with progress columns for days-of-stock.
8. **Medications table (lines 218–254)** — drug-level view with inherited tier and order quantity, plus turnover ratio.

### The CRITICAL banner

```python
critical_items = [ra for ra in results if ra.risk_tier == "CRITICAL"]
if critical_items:
    items_html = " · ".join(
        f"<strong>{drugs}</strong> ({code}) — order {qty:.0f} units"
        for ra in critical_items
    )
    st.markdown(f'<div class="alert-critical">...</div>', unsafe_allow_html=True)
```

If any drug is in the CRITICAL tier, we build an HTML snippet listing them with their recommended order quantities and inject it as a styled banner.

### The KPI cards

```python
kpi_items = [
    ("CRITICAL",  "Critical",   "Reorder immediately",     "kpi-critical"),
    ("LOW",       "Low Stock",  "Reorder within 14 days",  "kpi-low"),
    ("OK",        "Adequate",   "14 – 90 days of stock",   "kpi-ok"),
    ("OVERSTOCK", "Overstock",  "More than 90 days",       "kpi-overstock"),
]

cols = st.columns(4)
for col, (tier, label, hint, cls) in zip(cols, kpi_items):
    n = tier_counts.get(tier, 0)
    col.markdown(f'<div class="kpi-card {cls}">...</div>', unsafe_allow_html=True)
```

Four cards in a row, each showing the count for one tier. The `kpi-critical`, `kpi-low`, `kpi-ok`, `kpi-overstock` CSS classes (defined in `_shared.py`) apply the coloured top border.

### The donut chart

A Plotly Pie chart with `hole=0.65` to make it a donut. Each slice represents one tier with the tier's accent colour. An annotation in the centre shows the total number of ATC codes.

### The order quantity bar chart

A Plotly Bar chart sorted by order quantity descending. Each bar's colour matches the recommended drug's risk tier — so CRITICAL bars are red, LOW are orange, etc. This makes it easy to spot the urgent items at a glance.

### The risk table

```python
risk_df = pd.DataFrame(rows)
st.dataframe(
    risk_df,
    column_config={
        "Days of Stock": st.column_config.ProgressColumn(
            "Days of Stock",
            min_value=0, max_value=365,
            format="%.0f d",
        ),
    },
)
```

Standard Pandas DataFrame rendered with Streamlit's `st.dataframe`. The clever bit is `ProgressColumn` for the days-of-stock column — it renders a horizontal bar with a numeric label, so the operator can visually scan for low values.

### The medications table

Joins the per-ATC risk assessment with the full drug catalog (57 rows). Each drug inherits its parent ATC group's risk tier and order quantity. Also shows the turnover ratio (annual units sold ÷ current stock) with a classification label (Slow / Low / Healthy / High / Excessive).

## 8.3 The other 8 dashboard pages — a quick tour

The `spis/dashboard/pages/` folder contains 8 more page modules. Streamlit's multi-page convention picks them up automatically and adds them to the sidebar.

| Page | Filename | What it shows |
|---|---|---|
| History & Forecast | `1_History_Forecast.py` | Plotly chart of past sales + 30-day forecast + P10–P90 confidence band |
| Stock Update | `2_Stock_Update.py` | Form per ATC code to manually update current stock |
| Expiry Offers | `3_Expiry_Offers.py` | Table of batches near expiry with discount labels and waste-value chart |
| Analytics | `4_Analytics.py` | Feature-importance bar, ABC turnover Pareto, seasonal decomposition |
| Alerts Centre | `5_Alerts.py` | Open and acknowledged alerts; acknowledge button |
| Purchase Orders | `6_Purchase_Orders.py` | Supplier-grouped POs with PDF download |
| Receive Stock | `7_Receive_Stock.py` | Form to register a new batch with expiry date |
| Manage Catalog | `8_Manage_Catalog.py` | CRUD for drugs, ATC codes, suppliers |

You don't need to know these in depth. Know that they exist, know which file each is in, know which one to open during the demo.

## 8.4 If asked: "Why a `_shared.py` module?"

> "Because we have a multi-page Streamlit app — Overview plus 8 sub-pages — and every page needs the same set of helper functions: load model artifacts, run the risk assessment, fetch the ATC labels from the database, inject the dashboard CSS. Putting them in one shared module means one source of truth and one place to fix bugs. Streamlit's `@st.cache_resource` and `@st.cache_data` decorators in `_shared.py` ensure the heavy work — loading the model, running the assessment — happens only once across all pages."

---

# Part 9 — Other model modules you should know about

These are smaller files that often come up in questions. Skim each.

## 9.1 `spis/models/expiry_advisor.py` — the discount/return advisor

**One sentence:** Given a batch's days-to-expiry and its forecasted sell-through, recommend either no action, a discount tier, return-to-supplier, or write-off.

### The two factors

1. **`days_to_expiry`** — calendar countdown.
2. **`risk_ratio = units_at_risk / quantity`** — what fraction of the batch is unlikely to sell before expiry, given the daily demand for that ATC code.

`units_at_risk = max(0, quantity − daily_demand × days_to_expiry)`.

### The classification logic (`classify_discount`)

```python
def classify_discount(days_to_expiry, risk_ratio=0.5):
    if days_to_expiry < 0:                    return (0,  "Expired",         "write_off")
    if days_to_expiry < 30:                   return (0,  "Cannot Dispense", "return_to_supplier")
    if days_to_expiry < 60:
        if risk_ratio < 0.33:  return (10, "Special Offer", "promote")
        if risk_ratio < 0.66:  return (20, "Special Offer", "promote")
        return                       (30, "Special Offer", "promote")
    if days_to_expiry <= 90:
        if risk_ratio < 0.33:  return (0,  "Monitor",        "none")
        if risk_ratio < 0.66:  return (10, "Early Discount", "promote")
        return                       (15, "Early Discount", "promote")
    return (0, "OK", "none")
```

Three time windows (60-90, 30-60, <30) × three risk levels (<33%, 33-66%, ≥66%) gives a 9-cell grid with appropriate discount percentages and recommended actions.

### Worked example

Batch of 100 boxes expires in 50 days. Daily demand is 1 box/day.

- `forecasted_sales = 1 × 50 = 50 boxes`
- `units_at_risk = max(0, 100 − 50) = 50 boxes`
- `risk_ratio = 50 / 100 = 0.5` (medium)
- 30 ≤ days_to_expiry < 60 → "Special Offer" tier
- 0.33 ≤ risk_ratio < 0.66 → 20% discount

Result: 20% discount, "Special Offer", action = "promote."

### If asked: "Why two factors and not just days_to_expiry?"

> "Because days_to_expiry alone treats a 100-box batch with 95 boxes at risk the same as a 100-box batch with 5 boxes at risk. The risk-ratio factor adjusts for demand — if demand will absorb almost all the stock before expiry, we don't need an aggressive discount; if very little will sell, we need a deeper discount to clear it. The two-factor rule lets a near-expiry batch that demand will absorb naturally avoid over-discounting."

## 9.2 `spis/models/inventory_kpi.py` — turnover ratio

**One sentence:** Computes annual inventory turnover ratio (units sold per year ÷ current stock) and classifies it as Slow, Low, Healthy, High, or Excessive.

```
Turnover = annual_units_sold / current_stock

Slow      < 4x
Low       4 – 6x
Healthy   6 – 12x
High      12 – 24x
Excessive > 24x
```

This is a standard inventory KPI. Healthy turnover means stock cycles through 6–12 times a year — you're not sitting on dead inventory, but also not running out constantly. Used by the medications table on the Overview page.

## 9.3 `spis/models/alert_engine.py` — idempotent alert emission

**One sentence:** Translates risk assessments and expiry offers into rows in the `alerts` table, refusing to create duplicates with the same `(alert_type, atc_code, batch_number)` key.

The mapping is:
- `RiskAssessment` with `risk_tier == CRITICAL` → LOW_STOCK alert with severity CRITICAL
- `RiskAssessment` with `risk_tier == LOW` → LOW_STOCK alert with severity WARNING
- `ExpiryOffer` with `action == write_off` → EXPIRY alert with severity CRITICAL
- `ExpiryOffer` with `action == return_to_supplier` → EXPIRY alert with severity WARNING
- etc.

The idempotency means re-running the assessment every 5 minutes doesn't spam the operator with duplicate alerts for the same conditions.

## 9.4 `spis/models/po_generator.py` — supplier-grouped purchase orders

**One sentence:** Given the risk assessments, groups items by their supplier (via the `ATC_SUPPLIER_MAP`), builds a Purchase Order with line items, persists it to the `purchase_orders` table, and renders a PDF via fpdf2.

This is what gets triggered when the operator clicks "Generate PO" on the Purchase Orders dashboard page.

---

# Part 10 — Live Demo Runbook

This is the slide-23 segment of your script. Detailed enough that you can recover from anything that goes wrong.

## 10.1 Pre-flight checks (do these 30 minutes before the talk)

1. **Open VS Code** with the project. Make sure these tabs are open and ready to switch to:
   - `spis/models/forecaster.py`
   - `spis/models/risk_classifier.py`
   - `spis/data/pipeline.py`
   - `spis/dashboard/app.py`
2. **Open a terminal**, activate the venv (`.\venv\Scripts\activate`), and run `streamlit run spis/dashboard/app.py`. Confirm the browser tab opens on `http://localhost:8501`.
3. **Open a second terminal**, activate the venv, and run `python scripts/run_api.py --port 5000`. Confirm "Running on http://127.0.0.1:5000".
4. **Click through every sidebar page** in the dashboard once to confirm none of them crash and all the artifacts are present.
5. **Open `docs/figures/`** in a file-explorer window as the fallback.
6. **Close anything else** — Slack, Discord, browser tabs not related to the demo. Quiet the laptop.

## 10.2 The four demo segments

Follow your script's runbook, but here's the expanded version:

### Segment 1: Overview page (1 minute)

> "This is the page a pharmacy manager opens in the morning. The four cards across the top show the count of drug categories in each risk tier — currently we have 2 CRITICAL, 1 LOW, 3 OK, and 2 OVERSTOCK out of 8 total."
>
> *[Point at the red alert banner if present.]*
>
> "When any of our 25 critical-flagged drugs is in CRITICAL or LOW status, this banner appears at the top. Right now it's showing two items that need immediate reorder."
>
> *[Scroll to the risk table.]*
>
> "The risk table lists every ATC category. Each row shows the current stock, the 30-day forecast, daily demand, days of stock as a progress bar, the colour-coded tier, and the recommended order quantity. The progress bar makes it visually obvious which drugs are running low."
>
> *[Scroll to the order quantity bar chart.]*
>
> "The order quantity chart shows the recommended procurement quantities sorted descending. Colour matches the tier. The pharmacist can see at a glance which drugs need the largest orders and which are urgent."

### Segment 2: History & Forecast page (1 minute)

*[Click "1 History Forecast" in the sidebar. Use the ATC dropdown to pick M01AB or N02BE.]*

> "Here you can drill into one drug category. The black solid line is actual sales — the last 90 days of history. The dashed line is the 30-day forecast from XGBoost.
>
> The shaded band around the forecast is a P10 to P90 confidence interval computed by bootstrap — the model runs the forecast several times with small perturbations to estimate uncertainty. This is important because a point forecast alone doesn't tell the operator how confident the model is. A narrow band means high confidence; a wide band means be cautious."
>
> *[Scroll to the forecast summary.]*
>
> "Below the chart we summarise the forecast: total predicted demand over 30 days, average daily demand, and the implied days of stock at the current level."

### Segment 3: Alerts Centre (1 minute)

*[Click "5 Alerts Centre" in the sidebar.]*

> "The Alerts page is where the alert engine surfaces actionable items. Every CRITICAL or LOW risk assessment produces an alert with a deterministic key — so the same condition can't generate duplicate alerts if you re-run the assessment.
>
> *[Point at any OPEN alert.]*
>
> "Each alert has a type — LOW_STOCK or EXPIRY — a severity, a message, and a timestamp. The pharmacist can acknowledge an alert here, which moves it from OPEN to ACKNOWLEDGED but doesn't delete it. So there's always an audit trail of what was alerted and when it was acted on."

### Segment 4: Purchase Orders (1 minute)

*[Click "6 Purchase Orders" in the sidebar.]*

> "Finally, the system closes the loop from forecast to procurement. CRITICAL and LOW assessments get grouped by supplier — each ATC code is mapped to one of our four seeded suppliers, with their lead times. The Purchase Orders page lets the pharmacist generate a real procurement document.
>
> *[Click "Generate PO" on any supplier or "Download PDF" on an existing one.]*
>
> "Each PO has line items with the drug name, ATC code, recommended quantity, unit cost, and line total. The 'Download PDF' button generates a real PDF using fpdf2 — let me show one.
>
> *[Open the downloaded PDF in the browser's PDF preview. 3-second pause.]*
>
> "That PDF is what the storekeeper would print or email to the supplier. The full loop is closed: raw sales data → engineered features → forecast → risk classification → alert → procurement document."

### Switch back to PowerPoint

> "Let me close the demo and hand back to Nawaf for testing and results."

*[Alt+Tab back to slide deck. Advance to next slide.]*

## 10.3 Recovery scripts — what to say if something breaks

### If Streamlit fails to start

> "Looks like the dashboard didn't start — let me switch to the screenshots, which capture the same flow."

Open `docs/figures/` and walk through `fig_dashboard_02_overview.png`, `fig_dashboard_03_history_forecast.png`, `fig_dashboard_05_alert_centre.png`, `fig_dashboard_09_po_export.png`. Same narration as the live segments.

### If the dashboard loads but shows "Required files missing"

> "Looks like the model artifacts aren't in the expected location — let me try to fix it briefly."

Check the terminal. Most likely the venv isn't activated or you're in the wrong directory. If you can't fix it in 15 seconds, say:

> "I'll move to the screenshots for now — we can come back to this in Q&A if you'd like."

### If a specific page crashes mid-demo

> "Looks like that page hit an edge case — let me move on to the rest of the demo."

Click to a page you know works. Don't try to debug live.

### If the committee asks for something you didn't plan to show

> "Sure, let me navigate there."

Then click. If you can't find what they're asking for within 10 seconds:

> "That feature is in the sidebar but I want to make sure I show you the right view — let me come back to it after the rest of the demo."

### If a question comes mid-demo and you don't know

> "Good question — let me finish the demo flow first and we can dig into that as we go."

This buys you time to think while continuing with the flow.

---

# Part 11 — Q&A drills (40+ likely questions)

Read every one of these out loud at least once. The phrasing is conversational on purpose — it sounds like your own voice by the third repetition.

## 11.1 Architecture and design

**Q1. "Why a layered architecture?"**

> "Layered architecture is the canonical way to organise a system with distinct concerns. We have four layers — data, processing, model, presentation. Each layer owns one job and only depends downward. That gives us three benefits: we can change any single layer without touching the others provided the contracts stay the same; we can test each layer in isolation; and we can replace any component — SQLite for PostgreSQL, Streamlit for React — by swapping out one layer."

**Q2. "Why not microservices?"**

> "Microservices add network calls, deployment complexity, and a service-discovery overhead that don't pay off at our scale. Our deployment is single-host — one Python process running Streamlit, optionally a second running Flask. Going to microservices would add cost without benefit."

**Q3. "What's the relationship between Flask and Streamlit in your system?"**

> "They're two separate surfaces serving different consumers. Streamlit is for humans — the dashboard with charts, forms, and alerts. Flask exposes the same data as a REST API for machine consumers — an external system that wants to integrate with SPIS without going through the UI. Both read from the same model artifacts on disk."

**Q4. "Could you swap SQLite for PostgreSQL?"**

> "Yes, with isolated changes. The data access is all in `spis/data/database.py`. We'd update the connection logic to use psycopg2 instead of sqlite3, swap SQLite-specific SQL (PRAGMA, AUTOINCREMENT) for the Postgres equivalents (SERIAL, etc.), and we'd be done. The pipeline, model, API, and dashboard would not need to change because they all read through this module."

## 11.2 Forecasting model

**Q5. "Why XGBoost over LSTM?"**

> "Our dataset is moderate — about 17,000 daily rows across 8 ATC codes. LSTMs need much larger sequences to outperform tree models, and they need a GPU plus careful hyperparameter tuning. XGBoost trains in seconds on CPU, handles missing values natively via sparsity-aware splits — we needed that because of the lag-365 NaN window — and gives us interpretable feature-importance scores. Built-in regularisation reduces overfitting on a moderate-sized dataset."

**Q6. "Why XGBoost over LightGBM or CatBoost?"**

> "XGBoost has the longest track record and the most mature documentation. LightGBM would have been a reasonable alternative with similar accuracy and slightly faster training, but we didn't see a compelling reason to switch. CatBoost is best when most features are categorical — our features are mostly numerical lag and rolling statistics, so XGBoost was the natural fit."

**Q7. "How does XGBoost actually work?"**

> "It's a gradient-boosted ensemble of decision trees. The first tree learns a basic prediction. The second tree learns to correct the first tree's errors — it's trained on the residuals. The third tree corrects the combined first-plus-second prediction's errors. And so on for 800 trees in our case. Each new tree is small and shallow but targets exactly the mistakes its predecessors are making. The 'gradient' part is the technical name for the direction the new tree uses to correct — it's the gradient of the loss function with respect to the previous prediction."

**Q8. "What's TimeSeriesSplit and why did you use it?"**

> "It's scikit-learn's cross-validation strategy for time-series data. Regular K-Fold splits the data randomly, which would let the validation set come from earlier dates than the training set — the model would effectively be predicting the past from the future, which is impossible in production. TimeSeriesSplit creates folds where the validation set always comes after the training set chronologically. So with 5 splits, fold 1 trains on the earliest data and validates on the slice right after; fold 5 trains on most of the data and validates on the last slice. This matches how the model is actually used in deployment."

**Q9. "Walk me through the grid search."**

> "We have 7 hyperparameters, each with 2 candidate values — n_estimators 500 or 800, max_depth 6 or 8, learning_rate 0.03 or 0.05, subsample 0.8 or 1.0, colsample_bytree 0.8 or 1.0, min_child_weight 1 or 5, reg_alpha 0 or 0.1. Two to the seventh is 128 combinations. With 5 TimeSeriesSplit folds, that's 640 model fits total. The scoring is negative mean absolute error so GridSearchCV maximises the score, which is equivalent to minimising MAE. The best estimator comes back with n_estimators 800, max_depth 6, learning_rate 0.03, subsample 0.8, colsample_bytree 0.8, min_child_weight 1, reg_alpha 0. The grid picked flexibility on every axis except depth and learning rate, where it preferred the more conservative option."

**Q10. "What's the final MAE?"**

> "1.07. The naive baseline — yesterday's value — gives MAE 4.23. The 7-day moving average baseline gives 2.89. So XGBoost is roughly 4× better than naive and about 2.7× better than the moving average. The numbers are in `models/metrics.json`."

**Q11. "Why MAE? Why not RMSE or MAPE?"**

> "We report all three. MAE is the headline metric because it's robust to outliers — it gives us the typical error size. RMSE is also reported because it punishes large errors more heavily, which is useful for spotting when the model is making rare-but-big mistakes. MAPE gives us the error as a percentage of actual demand — useful for comparing across drugs with very different demand levels. We optimise on MAE during the grid search."

**Q12. "Which features are most important?"**

> "The top is `ema_14` — the 14-day exponentially weighted moving average — at about 48% of total importance. Then `ema_7` at 27%, `rolling_mean_14` at 3%, `is_weekend` at 3%, and `ema_28` at 2%. Together the three EMA features account for roughly 77% of model importance, which tells you the model is mostly learning from recent smoothed demand. The calendar features are useful but secondary."

**Q13. "How would you improve the model?"**

> "Three directions. One — replace point forecasts with quantile regression that natively outputs P10, P50, P90 predictions. That would let us replace the fixed safety_days constant with an actual confidence-driven safety stock. Two — move from ATC-category-level forecasting to per-SKU forecasting — 57 individual drug models — which would give finer resolution at the cost of needing sparser-history modelling. Three — fold in external regressors like local weather, regional outbreak data, or competitor pricing if we could obtain them."

## 11.3 Feature engineering

**Q14. "Why 35 features?"**

> "Empirically validated. Phase 3 experiments started with 21 features and got MAE around 2.80. Expanding to 35 features dropped MAE to 1.06. Adding more features beyond 35 didn't lower it further — diminishing returns. So 35 represents the point where marginal feature value drops below the marginal cost of pipeline maintenance."

**Q15. "Walk me through the four feature families."**

> "Twelve calendar features — day of week, day of month, month, year, week of year, weekend flag, holiday flag, season, payday window flag, school holiday flag, quarter, and days to month end. They capture weekly cycles, payday spikes, and seasonal patterns.
>
> Seven lag features — sales from 1, 2, 3, 7, 14, 28, and 365 days ago. They capture short-, medium-, and yearly autocorrelation.
>
> Twelve rolling and EMA features — rolling means at 7, 14, 28, 90, and 365 days, rolling standard deviation at 7 and 28, rolling min and max at 7, plus exponential moving averages at 7, 14, and 28 days. They smooth out noise at multiple time horizons.
>
> Four derived features — `lag_ratio_7` which is yesterday's value over the 7-day mean — a spike detector; `trend_counter` which is days since the dataset start — a long-run drift signal; `rolling_range_7` which is the max minus min of the last week — a volatility measure; and `ema_ratio` which is the 7-day EMA over the 28-day EMA — a momentum indicator."

**Q16. "What's an EMA exactly?"**

> "An exponentially weighted moving average. Each new value is `alpha × current + (1 − alpha) × previous_ema`, where alpha is `2 / (span + 1)`. For span 7, alpha is 0.25 — today gets 25% weight, yesterday 18.75%, the day before 14%, and so on geometrically. Compared to a simple rolling mean which weights all days equally, an EMA reacts faster to recent changes while still smoothing single-day noise. EMA features turned out to be the most important features in our trained model."

**Q17. "How do you prevent leakage in the lag features?"**

> "Three ways. First, all lag and rolling operations use `groupby('atc_code')` in pandas, so a lag for one drug never accidentally uses another drug's history. Second, the train/test split is done on a fixed cutoff date, not randomly — so the model never trains on dates that come after dates in the test set. Third, the training cross-validation uses `TimeSeriesSplit` rather than KFold, which preserves chronological order within the training set."

**Q18. "Why fill missing dates with zero?"**

> "Because lag features need calendar alignment. If a pharmacy reports nothing on Sundays because it's closed, the database has no row for those Sundays. Computing `lag_7` for Monday would skip back to Saturday — silently misaligning the weekly seasonality. Filling missing dates with zero ensures `lag_7` for any Monday is genuinely 'seven calendar days ago,' which is the only correct semantics."

## 11.4 Risk classification

**Q19. "Why these thresholds — 7, 14, 90?"**

> "They map to real pharmacy-operations timescales. Supplier lead times in our seeded suppliers range from 3 to 7 days — so anything below 7 days of stock cannot be guaranteed to replenish before stockout. That's CRITICAL. Between 7 and 14 days is an early-warning window — enough time for a routine order. 14 to 90 days is the normal operating band. Above 90 days, capital is tied up and expiry risk starts to dominate — that's OVERSTOCK."

**Q20. "Why did you revise the thresholds from 3/7/30 to 7/14/90?"**

> "The original Phase-4 design used (3, 7, 30). During Phase 8.5 we observed that our seeded supplier lead times span 3 to 7 days. A CRITICAL alert at less than 3 days of stock comes too late — the order can't physically arrive in time. We pushed CRITICAL up to less than 7 days so the alert gives staff at least a week to act, which matches the longest lead time."

**Q21. "Why a 30-day forecast horizon and not 7 or 60?"**

> "Three reasons. One, pharmacy procurement runs on a monthly cycle — purchase-order review, supplier invoicing, and budget reporting are calendar-month aligned, so 30 days fits the natural ordering rhythm. Two, supplier lead times are 3–7 days, so 30 days gives roughly 4× headroom over the longest lead time. Three, the recursive forecast compounds errors over time, and 30 days sits at the knee of the error curve — long enough to be actionable, short enough to stay within our MAE target. Shorter horizons fail to cover the OVERSTOCK threshold which sits at 90 days; longer horizons add compound error without procurement value."

**Q22. "Explain the order quantity formula."**

> "Order quantity equals the maximum of zero, or — the 30-day forecast plus the safety buffer minus the current stock. The safety buffer is daily demand times a configurable number of safety days, default three. We clamp at zero because the system never recommends a return — if you already have enough stock, the recommendation is to not order. The OVERSTOCK tier surfaces that condition separately."

**Q23. "Why a safety buffer at all?"**

> "Because the 30-day forecast is the expected demand, not the worst case. Real demand has volatility — weekday spikes, holiday surges, prescription pattern shifts. Ordering exactly forecast minus stock would give us a 50% probability of stockout in any cycle where actual demand exceeds the forecast. The buffer of daily demand times safety days absorbs forecast error and supplier lead-time variance — it converts an expected-value rule into a service-level rule."

**Q24. "Why is the recursive forecast loop necessary?"**

> "Because the model is a one-step regressor — it predicts today's quantity from today's features. To get a 30-day forecast we call it in a loop, but each new day's lag and rolling features depend on the previous days' values, which don't exist yet. We solve that by appending each prediction to a 365-day history buffer, so the next day's features see the model's own forecast. Without this, the lag and rolling features would stay frozen at the seed-day values and the forecast curve would be a flat line with only weekly calendar wobble. The recursive form gives realistic day-to-day variation."

## 11.5 Tech-stack questions

**Q25. "Why Python 3.11 specifically?"**

> "Because scispacy, which we'd planned to use for drug-name NLP search, isn't yet compatible with Python 3.12 or 3.14. Even though we deferred the NLP work, we kept 3.11 so the lockfile stays consistent and the eventual NLP addition won't require an environment change."

**Q26. "Why SQLite over PostgreSQL?"**

> "SQLite is a single file with no server — that matches our non-functional requirement of being lightweight and self-contained. Our data volume — 424,000 sales rows — fits comfortably in SQLite. The whole database is one file we can put under version control, copy between machines in one step, or back up trivially. PostgreSQL would have given us nothing at this scale."

**Q27. "Why Streamlit?"**

> "Two reasons. Pure Python — no JavaScript build chain. And the multi-page convention is essentially free — files in a `pages/` folder automatically become sidebar entries. Streamlit's caching with `@st.cache_resource` and `@st.cache_data` solved the performance problem of re-running the script on every interaction. The trade-off is less control over the visual design than Flask plus React would give, but for our committee defence and the pharmacy staff demo, Streamlit is the right level of polish."

**Q28. "Why Flask, given you already have Streamlit?"**

> "Streamlit is for humans. Flask is for machines. A future integration — say a pharmacy chain's enterprise system wants the daily risk assessment in JSON — would call the Flask API, not navigate the Streamlit dashboard. Having both means we serve both audiences without coupling them."

## 11.6 Testing

**Q29. "What's the test count and coverage?"**

> "182 tests across 14 test files. 80% or higher coverage on critical paths — the risk classifier is at 98%, the API is at 94%, the forecaster is at 92%, the pipeline at 95%. A full run completes in about 25 seconds. Pass rate is 100%."

**Q30. "How do you structure tests?"**

> "Three layers. Unit tests for individual functions — tier classification given a days-of-stock value, order quantity given the four inputs, feature engineering on a small synthetic dataframe. Integration tests for the full request path — the Flask test client hits each endpoint and asserts on status codes and JSON structure; the pipeline-then-train sequence is exercised end-to-end on a tiny fixture. Error-handling tests for failure cases — what happens when the model is missing, when an ATC code is unknown, when a CSV is malformed."

**Q31. "Which test caught the most bugs during development?"**

> "The feature-count invariant test caught defect D-001 — the pipeline emitted 36 features but the model expected 27 after a refactor. The Flask test client tests caught the infinity-serialisation bug — D-002. The alert idempotency test made sure we don't spam the operator. Each defect produced a regression test alongside its fix, so the test suite is the living specification of how the system actually behaves."

## 11.7 Live demo follow-ups

**Q32. "Show me where the forecast comes from in the code."**

Open `spis/models/risk_classifier.py`, scroll to line 88 (`forecast_30_days`). Walk through the loop briefly.

**Q33. "Show me the order quantity formula in the code."**

Open `spis/models/risk_classifier.py`, line 42 (`calculate_order_qty`). Read the 5 lines aloud.

**Q34. "Show me the database schema."**

Open `spis/data/database.py`, line 165 (`_create_tables`). Walk through the 8 `CREATE TABLE` statements.

**Q35. "Where do you load the model?"**

Open `spis/models/forecaster.py`, line 215 (`load_model`). Then show `spis/api/app.py` line 31 to demonstrate where it's called for the API. Then show `spis/dashboard/_shared.py` line 220 (`load_artifacts`) for the dashboard case.

## 11.8 Limitations and future work

**Q36. "What's your biggest limitation?"**

> "Honestly — single-pharmacy training data. We trained on one Turkish pharmacy from 2014 to 2019. Generalisation to other pharmacies isn't validated. The seasonality, calendar patterns, and demand levels would all be different at another site. A new pharmacy would need cross-validation on their own historical data before relying on the model."

**Q37. "How would you deploy this to production?"**

> "Incrementally. First, integrate a real-time POS feed so sales arrive continuously rather than as CSV snapshots. Second, schedule weekly retraining so the model stays current. Third, add authentication and role-based access — Argon2id password hashing, JWT sessions, three roles for viewer, operator, manager. Fourth, harden the API with TLS, Bearer tokens, and rate limits. Fifth, code-sign the model artifacts so they can't be tampered with. The current single-host design becomes a starting point — none of it would need to be rewritten."

**Q38. "What about scaling to multiple pharmacy sites?"**

> "The database schema would need a `location_id` on the operational tables — atc_inventory, inventory_batches, sales, alerts, purchase_orders. The risk classifier becomes location-aware. And we'd want transfer learning to share patterns across sites without re-training from scratch for each new pharmacy. The forecaster's single-multi-drug architecture already prepares for this — instead of one drug per model we could go to one site-per-drug as a feature."

## 11.9 The Claude / AI angle (if asked, be calm and honest)

**Q39. "Did you use AI tools to write this code?"**

> "Yes, we used AI coding assistants as part of the development process. The decisions — the architecture, the feature design, the threshold choices, the testing strategy — were ours. The implementation was a collaboration. Every algorithm in this system was reviewed and validated by us before being committed. The 182 tests were written to make sure we could verify each decision, regardless of how the code was first drafted."

> *(Honesty here is much better than denial. If the committee asks deeper, you can add:)*

> "I can walk you through any file in the codebase and explain what it does and why we made the choices we did — because owning the architectural decisions is different from typing every line."

## 11.10 Graceful "I don't know" templates

**Template 1 — for implementation details you genuinely forgot:**

> "Honestly, I don't remember that specific detail off the top of my head — let me pull up the file."
>
> *Then open it. Reading code in real time is fine. Pretending and getting it wrong is not.*

**Template 2 — for a design choice you didn't make personally:**

> "That decision was discussed across the team — the rationale that won was [your understanding]. If you'd like the full debate I can walk through it after the talk."

**Template 3 — for something genuinely outside scope:**

> "We didn't explore that direction — it would be follow-on work. The current system stops at [point Y], and going further would require [the missing piece]."

**Template 4 — for something that exposes a real gap:**

> "That's a fair limitation. We address it in section 7.4 of the report — [closest matching limitation]. Future work item [N] would close that gap."

The pattern: **acknowledge, don't bluff, point at where the answer lives**. That's exactly what a working engineer does.

---

# Part 12 — The night before the defense

## 12.1 Three-day checklist (recommended)

**Day 1 (T-3):** Read Parts 1, 2, 3 of this document carefully. Open the files I mentioned. Spend 2 hours.

**Day 2 (T-2):** Read Parts 4, 5, 6. Walk through the recursive forecast loop with pen and paper. Spend 2 hours.

**Day 3 (T-1):** Read Parts 7, 8, 9, 10, 11. Practice the demo runbook. Practice the Q&A drills aloud. Spend 2 hours.

## 12.2 Day-of checklist

The morning of the defense:

- [ ] Run `pytest -q` on your machine. Confirm 182 tests pass.
- [ ] Start the dashboard. Click through every sidebar page. Confirm nothing crashes.
- [ ] Start the API on port 5000 in a second terminal. `curl http://127.0.0.1:5000/health` to confirm.
- [ ] Open VS Code with 4 file tabs ready: `forecaster.py`, `risk_classifier.py`, `pipeline.py`, `dashboard/app.py`.
- [ ] Open `docs/figures/` in a file-explorer window as the fallback.
- [ ] Close everything else — Slack, browser tabs, notifications.
- [ ] Do one full read-through of your script (`saleh_script.md`) out loud, timed.

## 12.3 The mental model to bring with you

You have spent **months** on this project. You may not have typed every line, but you:

- Made the architecture decisions.
- Validated every number that ended up in the report.
- Caught the bugs in the slide deck before they shipped.
- Wrote the limitations section honestly.
- Built a runbook so your teammates can produce the missing artifacts.

That body of work is *yours*. The committee is talking to you, not to a script.

**Defending code you can read is a different skill from writing it from scratch.** This document teaches the first skill. The second skill is what your career will demand later. Right now, the goal is the defense.

You've got this.

---

# Part 13 — Quick reference numbers (last-minute glance card)

If you have 5 minutes before the defense and want a single page to scan, these are the facts most likely to come up.

| Topic | Number |
|---|---|
| Total tests | **182** across 14 files |
| Coverage | **80%+** on critical paths (Risk Classifier 98%, API 94%, Forecaster 92%, Pipeline 95%) |
| Test run time | ~25 seconds |
| Database tables | **8** (atc_categories, drugs, sales, atc_inventory, inventory_batches, alerts, suppliers, purchase_orders) |
| Sales rows | **424,080** |
| Drugs | **57** total, **25** flagged critical |
| ATC categories | **8** (M01AB, M01AE, N02BA, N02BE, N05B, N05C, R03, R06) |
| Suppliers | **4** (Tamer, Banaja, Cigalah, Jamjoom; lead times 3 / 5 / 7 / 4 days) |
| Engineered features | **35** (12 calendar + 7 lag + 12 rolling/EMA + 4 derived) |
| Model inputs | **36** (35 engineered + atc_encoded) |
| Hyperparameters tuned | **7** with 2 choices each → **128 combinations** |
| Cross-validation folds | **5** TimeSeriesSplit folds → 640 fits total |
| Best XGBoost params | n_estimators **800**, max_depth **6**, learning_rate **0.03**, subsample **0.8**, colsample_bytree **0.8**, min_child_weight **1**, reg_alpha **0** |
| XGBoost MAE | **1.06** |
| Naive baseline MAE | **4.23** (4× worse) |
| Moving avg baseline MAE | **2.89** (2.7× worse) |
| XGBoost RMSE | **2.29** |
| XGBoost MAPE | **20.6%** |
| Risk tier thresholds | CRITICAL **<7d**, LOW **7–14d**, OK **14–90d**, OVERSTOCK **≥90d** |
| Original tier thresholds | (3, 7, 30) — revised because supplier lead times are 3–7 days |
| Order quantity formula | `max(0, forecast_30d + daily_demand × safety_days − current_stock)` |
| Default safety_days | **3** |
| Days of stock formula | `current_stock / daily_demand` |
| Forecast horizon | **30 days** |
| Recursive forecast buffer | **365 days** of history |
| API endpoints | **3** — `/health`, `/api/v1/risk`, `/api/v1/forecast/<atc>` |
| API status codes | **200 / 404 / 503** all tested |
| Dashboard pages | **Overview + 8** sub-pages |
| Streamlit cache TTL on assessment | **300 seconds** (5 min) |
| Full pipeline rebuild | **< 5 minutes** on a normal laptop |
| Python version | **3.11.9** |
| Top feature by importance | **ema_14** (~48%) followed by ema_7 (~27%) |
| Top three EMA features combined | **~77%** of model importance |
| Top training cutoff | **2019-01-01** (train < cutoff, test ≥ cutoff) |
| Training rows | **14,500** after dropping NaN-lag rows |
| Test rows | **2,250** |

Print this. Glance at it on the morning of. It's all the trivia.
