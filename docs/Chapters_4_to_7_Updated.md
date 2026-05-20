# Chapters 4 – 7 (Updated)

_Smart Pharmacy Inventory System (SPIS) — Graduation Project 2_
_Revision date: 2026-05-11_

This document covers Chapters 4 through 7 of the GP2 final report. Chapter 4
(Design) is new work for GP2 — it was not part of the GP1 submission. Chapters
5, 6, and 7 replace any earlier drafts. The content was verified against the
source tree at HEAD: every diagram, code snippet, tier threshold, schema
description, and test count below was read directly out of the repository
rather than carried over from the older drafts. Stale numbers, plan-only
features, and outdated tier logic from earlier revisions have been removed.

The chapter ordering follows the committee guidelines exactly: Design →
Implementation → Testing → Conclusion. Each chapter ends with a bridge to
the next.

---

# Chapter 4: Design

## 4.1 Introduction

Chapter 3 specified what SPIS must do — the user requirements per
stakeholder, the functional requirements grouped by module (Data Management,
Forecasting Engine, Risk Analysis, Dashboard and Interaction, Security and
Data Management), the non-functional requirements, and the project
assumptions and constraints. This chapter answers the natural follow-up
question: **how** does the system meet those requirements?

The design described here was reached iteratively over Phases 1 through 9.
Where a Phase 8.5 or Phase 9 enhancement (multi-page dashboard, expiry
advisor, alert engine, supplier directory, purchase orders, batch lifecycle,
analytics page) extended the original GP1 scope, the design accommodates it
by adding new modules rather than mutating existing ones. Section 4.7
discusses the design decisions explicitly and contrasts each one against
the alternatives that were considered and rejected.

The chapter is organised as follows. Section 4.2 presents the layered
system architecture and explains how the four layers communicate.
Section 4.3 details the database design: an entity-relationship diagram
covering all eight tables and a per-table data dictionary. Section 4.4
covers the modular decomposition (Python packages, modules, and the key
data structures). Section 4.5 captures system organisation — data flow,
sequence diagrams for two representative use cases, and state diagrams
for the alert and batch lifecycles. Section 4.6 gives pseudocode for the
six core algorithms. Section 4.7 documents the alternative designs
considered. Section 4.8 specifies the graphical user interface design.
Section 4.9 closes with a bridge to Chapter 5.

## 4.2 System Architecture

SPIS follows a **layered architecture** with four distinct layers: Data,
Processing, Model, and Presentation. Each layer depends only on the layer
below it. This pattern was chosen because the system has a clear
unidirectional data flow (raw sales → engineered features → model →
risk classification → user interface) and because layering makes each
concern independently testable. The communication pattern between layers
is a mix of **pipe-and-filter** (the data pipeline transforms inputs to
outputs through a chain of pure functions) and **repository** (the
SQLite database is the single source of truth for state).

```
+---------------------------------------------------------------------+
|                     PRESENTATION LAYER                              |
|                                                                     |
|   +-------------------------+    +-------------------------------+  |
|   |  Streamlit Dashboard    |    |    Flask REST API             |  |
|   |  app.py + 8 pages       |    |    app.py + routes.py         |  |
|   |  (operator UI)          |    |    (sample external surface)  |  |
|   +------------+------------+    +-------------+-----------------+  |
+----------------|-------------------------------|--------------------+
                 |                               |
                 |                               |
+----------------|-------------------------------|--------------------+
|                |        MODEL LAYER            |                    |
|   +------------v---+   +----------------+   +--v---------------+    |
|   | Risk Classifier|   | Expiry Advisor |   | Alert Engine     |    |
|   | (DoS, tiers,   |   | (2-factor      |   | (idempotent      |    |
|   |  order qty,    |   |  discount,     |   |  insert,         |    |
|   |  recursive 30d |   |  units at risk,|   |  severity        |    |
|   |  forecast)     |   |  waste value)  |   |  mapping)        |    |
|   +-------+--------+   +-------+--------+   +---+--------------+    |
|           |                    |                |                   |
|   +-------v-----------+   +----v-----------+   +v-----------------+ |
|   | XGBoost Forecaster|   | Expiry Finance |   | PO Generator     | |
|   | (35-feature input,|   | (SAR aggregates|   | (supplier-grouped| |
|   |  GridSearchCV     |   |  on offers)    |   |  PO + fpdf2 PDF) | |
|   |  TimeSeriesSplit) |   +----------------+   +------------------+ |
|   +-------+-----------+                                             |
|           |       +------------------+   +------------------+       |
|           |       | Inventory KPI    |   | Decomposition    |       |
|           |       | (turnover ratio) |   | (seasonal trend) |       |
|           |       +------------------+   +------------------+       |
+-----------|---------------------------------------------------------+
            |
+-----------|---------------------------------------------------------+
|           |                 PROCESSING LAYER                        |
|   +-------v---------------------------------------------+           |
|   |  Feature Engineering Pipeline (pipeline.py)         |           |
|   |  raw daily sales -> 35-feature DataFrame            |           |
|   |  (calendar + lag + rolling + EMA + derived)         |           |
|   +-----------------------+-----------------------------+           |
+---------------------------|-----------------------------------------+
                            |
+---------------------------|-----------------------------------------+
|                           |   DATA LAYER                            |
|   +-----------------------v---------------------------+             |
|   |               SQLite (data/inventory.db)          |             |
|   |   atc_categories | drugs | sales | atc_inventory  |             |
|   |   inventory_batches | alerts | suppliers          |             |
|   |   purchase_orders                                 |             |
|   +---------------------------------------------------+             |
|                                                                     |
|   +---------------------------------------------------+             |
|   |   Processed CSVs (data/processed/)                |             |
|   |   features_daily.csv | train.csv | test.csv       |             |
|   +---------------------------------------------------+             |
|                                                                     |
|   +---------------------------------------------------+             |
|   |   Model artifacts (models/)                       |             |
|   |   xgboost_forecaster.joblib                       |             |
|   |   label_encoder.joblib                            |             |
|   |   metrics.json | feature_importance.json          |             |
|   +---------------------------------------------------+             |
+---------------------------------------------------------------------+
```

### 4.2.1 Layer responsibilities

**Data layer.** The single SQLite file `data/inventory.db` holds eight
tables (Section 4.3). All persistent state lives here: drug catalog,
sales fact table, current stock per ATC code, per-batch stock with
expiry, alerts, suppliers, and purchase-order history. Two side caches
sit alongside the database: `data/processed/*.csv` for the
feature-engineered training set, and `models/*.joblib` for the trained
XGBoost regressor plus its `LabelEncoder`. Both are git-ignored and
rebuildable from the SQLite source.

**Processing layer.** A single Python module (`spis/data/pipeline.py`)
reads daily sales from the database, validates them (null check,
negative-quantity clip, duplicate aggregation), fills date gaps with
`quantity=0`, engineers 35 time-series features per row group-wise per
ATC code, and writes three CSVs (`features_daily.csv`, `train.csv`,
`test.csv`).

**Model layer.** Several modules compose the analytics behaviour:
`forecaster.py` (XGBoost training + persistence), `risk_classifier.py`
(DoS, four-tier classification, order-quantity formula, recursive
30-day forecast), `expiry_advisor.py` (two-factor discount classifier
and per-batch assessment), `expiry_finance.py` (SAR aggregations on
offers), `alert_engine.py` (risk + expiry → `Alert` mapping with
idempotent persistence), `decomposition.py` (additive seasonal
decomposition wrapper), `inventory_kpi.py` (annual turnover ratio),
and `po_generator.py` (supplier-grouped PO building + PDF generation
via fpdf2).

**Presentation layer.** Two surfaces sit side-by-side and read the
model and data layers independently. The Streamlit dashboard is the
primary operator interface; it reads model artifacts directly from
disk via `spis/dashboard/_shared.py` (cached `@st.cache_resource` for
the model, `@st.cache_data(ttl=300)` for assessments) so every page
stays sub-second. The Flask REST API is a separate, intentionally
minimal sample external interface that exposes the same risk and
forecast functions over HTTP for any future POS or mobile client.

### 4.2.2 Hardware architecture

SPIS is a single-host application. A consumer-grade laptop running
Windows 11 (≥ 8 GB RAM, ≥ 5 GB free disk) hosts the SQLite file, the
Streamlit dashboard process, and (when needed) the Flask server. No
GPU is required — XGBoost training on the full 16,848-row feature
set completes in under 10 minutes on CPU. No external service is
required to run the system. For a lab demo on a shared network, the
launcher `scripts/run_public.py` binds Streamlit to `0.0.0.0` so
other devices on the LAN can view the dashboard.

### 4.2.3 Why this architecture

Three alternatives were considered (Section 4.7 elaborates):
client-server with a dedicated DB engine, a microservices split, and
a monolithic single-file script. The layered single-host architecture
was chosen because it matches the requirement of "lightweight,
self-contained deployment with no cloud dependency" (Ch3 NFR-2) and
because the project's data volume (424,080 sales rows, 16,848 daily
feature rows after pipeline) fits comfortably in a single SQLite
file. The pipe-and-filter pattern keeps every transformation pure and
testable, which is reflected in the 182-test suite.

## 4.3 Database Design

The database is a single SQLite file built and seeded by
`spis/data/database.py::init_db()`. `init_db()` is idempotent: it uses
`CREATE TABLE IF NOT EXISTS` for every table and `INSERT OR IGNORE`
for every seed row, plus a `_migrate_schema()` helper that adds any
columns introduced after the initial schema (`applied_discount`,
`returned`, `atc_categories.supplier_id`). The same function is safe
to run on a fresh checkout and on an already-populated database.

### 4.3.1 Entity-Relationship Diagram

```
                       +--------------------+
                       |  atc_categories    |
                       +--------------------+
                       | atc_code (PK)      |<------+
                       | atc_name           |       |
                       | system_name        |       |
                       | level1_code        |       |
                       | level2_code        |       |
                       | supplier_id (FK)---|----+  |
                       +--------------------+    |  |
                          ^   ^         ^        |  |
                          |   |         |        |  |
                  +-------+   |         +----+   |  |
                  | 1:N       | 1:N          |   |  |
                  |           |              |   |  |
        +---------+----+  +---+----------+   |   |  |
        |   drugs      |  |   sales      |   |   |  |
        +--------------+  +--------------+   |   |  |
        | drug_id (PK) |  | sale_id (PK) |   |   |  |
        | drug_name UQ |  | atc_code (FK)|   |   |  |
        | atc_code(FK) |  | sale_date    |   |   |  |
        | unit         |  | hour         |   |   |  |
        | is_critical  |  | granularity  |   |   |  |
        +--------------+  | quantity     |   |   |  |
                          +--------------+   |   |  |
                                             |   |  |
                +----------------------------+   |  |
                | 1:1                            |  |
                v                                |  |
        +--------------------+                   |  |
        | atc_inventory      |                   |  |
        +--------------------+                   |  |
        | atc_code (PK, FK)  |                   |  |
        | current_stock      |                   |  |
        | last_updated       |                   |  |
        | notes              |                   |  |
        +--------------------+                   |  |
                                                 |  |
                +--------------------------+     |  |
                | 1:N                      |     |  |
                v                          |     |  |
        +--------------------+             |     |  |
        | inventory_batches  |             |     |  |
        +--------------------+             |     |  |
        | batch_id (PK)      |             |     |  |
        | atc_code (FK)------+-------------+     |  |
        | batch_number       |                   |  |
        | quantity           |                   |  |
        | unit_cost          |                   |  |
        | expiry_date        |                   |  |
        | received_date      |                   |  |
        | applied_discount   |                   |  |
        | returned           |                   |  |
        | notes              |                   |  |
        +--------------------+                   |  |
                                                 |  |
        +--------------------+                   |  |
        |    alerts          |                   |  |
        +--------------------+                   |  |
        | alert_id (PK)      |                   |  |
        | alert_type         |                   |  |
        | atc_code           |                   |  |
        | batch_number       |                   |  |
        | severity           |                   |  |
        | message            |                   |  |
        | created_at         |                   |  |
        | acknowledged_at    |                   |  |
        +--------------------+                   |  |
                                                 |  |
        +--------------------+                   |  |
        |   suppliers        |<------------------+  |
        +--------------------+                      |
        | supplier_id (PK)   |                      |
        | name (UNIQUE)      |                      |
        | email              |                      |
        | phone              |                      |
        | lead_time_days     |                      |
        | notes              |                      |
        +--------------------+                      |
              ^                                     |
              | 1:N                                 |
              |                                     |
        +-----+--------------+                      |
        | purchase_orders    |                      |
        +--------------------+                      |
        | po_id (PK)         |                      |
        | supplier_id (FK)   |                      |
        | supplier_name      |                      |
        | created_at         |                      |
        | status             |                      |
        | total_cost         |                      |
        | lines_json         |                      |
        +--------------------+                      |
                                                    |
                            (atc_categories<--------+
                             references suppliers
                             via supplier_id FK
                             added by Phase 9 migration)
```

The two reference tables (`atc_categories`, `drugs`, `suppliers`) are
seeded at initialisation and read-only during normal operation. The
operational tables (`sales`, `atc_inventory`, `inventory_batches`,
`alerts`, `purchase_orders`) are populated and updated at runtime by
the ingest scripts, the dashboard's stock-update and batch-receive
flows, the alert engine, and the purchase-order generator.

### 4.3.2 Data dictionary

Per-table column definitions, transcribed from
`spis/data/database.py::_create_tables()`:

**`atc_categories`** — ATC-4 classification reference, 8 seeded rows.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `atc_code` | TEXT | PRIMARY KEY | ATC-4 code, e.g. `M01AB` |
| `atc_name` | TEXT | NOT NULL | Human-readable category (e.g. "Acetic acid derivatives") |
| `system_name` | TEXT | NOT NULL | Anatomical system (Musculoskeletal / Nervous / Respiratory) |
| `level1_code` | TEXT | NOT NULL | WHO ATC level 1 (e.g. `M`) |
| `level2_code` | TEXT | NOT NULL | WHO ATC level 2 (e.g. `M01`) |
| `supplier_id` | INTEGER | FK → suppliers; NULL allowed | Primary supplier for this ATC code (Phase 9) |

**`drugs`** — clinical drug catalogue, 57 seeded rows (25 critical).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `drug_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Surrogate key |
| `drug_name` | TEXT | NOT NULL, UNIQUE | Trade or generic name |
| `atc_code` | TEXT | NOT NULL, FK → atc_categories | Parent category |
| `unit` | TEXT | NOT NULL, default `'tablets'` | Dispensing unit |
| `is_critical` | INTEGER | NOT NULL, CHECK IN (0,1), default 0 | 1 when stockout poses direct clinical harm |

**`sales`** — time-series fact table, 424,080 rows from the Kaggle
dataset.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `sale_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Surrogate key |
| `atc_code` | TEXT | NOT NULL, FK → atc_categories | Drug category |
| `sale_date` | TEXT | NOT NULL | ISO-8601 YYYY-MM-DD |
| `hour` | INTEGER | NULL allowed | 0-23 for hourly granularity, NULL otherwise |
| `granularity` | TEXT | NOT NULL, CHECK IN ('hourly','daily','weekly','monthly') | Aggregation level |
| `quantity` | REAL | NOT NULL, CHECK ≥ 0 | Units sold |

Indexed on `(atc_code, sale_date)` and on `granularity`.

**`atc_inventory`** — current stock per ATC code, 8 rows.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `atc_code` | TEXT | PRIMARY KEY, FK → atc_categories | One row per ATC |
| `current_stock` | REAL | NOT NULL, CHECK ≥ 0 | Units on hand |
| `last_updated` | TEXT | NOT NULL, default `CURRENT_TIMESTAMP` | When stock was last edited |
| `notes` | TEXT | NULL allowed | Free text |

**`inventory_batches`** — per-batch stock with expiry, populated at
runtime by `add_batch()` and seeded with 3 demo batches.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `batch_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Surrogate key |
| `atc_code` | TEXT | NOT NULL, FK → atc_categories | Drug category |
| `batch_number` | TEXT | NOT NULL | Lot identifier (e.g. `LOT-2026-001`) |
| `quantity` | REAL | NOT NULL, CHECK ≥ 0 | Units in this batch |
| `unit_cost` | REAL | NOT NULL, CHECK ≥ 0 | SAR cost per unit |
| `expiry_date` | TEXT | NOT NULL | ISO-8601 YYYY-MM-DD |
| `received_date` | TEXT | NOT NULL, default `CURRENT_DATE` | When batch arrived |
| `notes` | TEXT | NULL allowed | Recall notes appended on recall |
| `applied_discount` | REAL | NULL allowed | Pharmacist override of suggested discount |
| `returned` | INTEGER | NOT NULL, CHECK IN (0,1), default 0 | 1 when batch is recalled |

Indexed on `(atc_code, expiry_date)`.

**`alerts`** — notification log, created by `alert_engine.refresh()`.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `alert_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Surrogate key |
| `alert_type` | TEXT | NOT NULL | `'LOW_STOCK'` / `'EXPIRY'` / `'RECALL'` |
| `atc_code` | TEXT | NULL allowed | ATC code (null for non-ATC-scoped alerts) |
| `batch_number` | TEXT | NULL allowed | Batch ID (used for EXPIRY/RECALL) |
| `severity` | TEXT | NOT NULL | `'CRITICAL'` / `'WARNING'` / `'INFO'` |
| `message` | TEXT | NOT NULL | Human-readable alert text |
| `created_at` | TEXT | NOT NULL, default `CURRENT_TIMESTAMP` | Creation timestamp |
| `acknowledged_at` | TEXT | NULL allowed | Set when pharmacist acknowledges |

**`suppliers`** — distributor directory, 4 real Saudi suppliers seeded
(Tamer Group, Banaja Holdings, Cigalah Group, Jamjoom Pharma).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `supplier_id` | INTEGER | PRIMARY KEY | Auto-assigned via SQLite rowid |
| `name` | TEXT | NOT NULL, UNIQUE | Display name |
| `email` | TEXT | NULL allowed | Contact email |
| `phone` | TEXT | NULL allowed | Contact phone |
| `lead_time_days` | INTEGER | NOT NULL, default 7 | Days from order to delivery |
| `notes` | TEXT | NULL allowed | Speciality, region, etc. |

**`purchase_orders`** — sent-PO history, append-only.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `po_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Surrogate key |
| `supplier_id` | INTEGER | FK → suppliers; NULL allowed | Supplier reference |
| `supplier_name` | TEXT | NOT NULL | Snapshot of supplier name at send time |
| `created_at` | TEXT | NOT NULL, default `CURRENT_TIMESTAMP` | When PO was sent |
| `status` | TEXT | NOT NULL, default `'SENT'` | Lifecycle status |
| `total_cost` | REAL | NOT NULL, default 0 | Grand total in SAR |
| `lines_json` | TEXT | NULL allowed | Serialised line items (ATC, qty, unit cost) |

### 4.3.3 Referential integrity and audit trail

Foreign keys are enabled at connection time (`PRAGMA foreign_keys = ON`).
`drugs.atc_code`, `sales.atc_code`, `atc_inventory.atc_code`,
`inventory_batches.atc_code` all reference `atc_categories.atc_code`.
`atc_categories.supplier_id` references `suppliers.supplier_id`.
`purchase_orders.supplier_id` references `suppliers.supplier_id`.
Helper functions `add_atc_code`, `add_drug`, `add_supplier`, and
`assign_supplier_to_atc` enforce existence of the referenced row and
raise `ValueError` with a descriptive message when the FK target is
missing.

A complementary append-only audit log lives at `data/stock_audit.csv`.
Every batch receipt, recall, and manual stock edit appends one row
(`timestamp, atc_code, action, batch_number, old_stock, new_stock, delta`)
so the operational history can be reviewed outside SQL.

## 4.4 Modular Decomposition

The system is decomposed using a **pipe-and-filter** model: each
module is a pure or near-pure function (or a small collection of them)
that transforms inputs into outputs without hidden global state. The
modules are then composed into the layered architecture of Section 4.2.

### 4.4.1 Package structure

```
spis/                         Main package (v0.1.0)
  __init__.py
  data/
    __init__.py
    database.py               Schema, seeds, init_db, batch/alert/supplier helpers
    pipeline.py               Feature engineering, validate, fill_missing_dates,
                              split_train_test
    catalog.py                add_atc_code, add_drug, list_atc_codes, list_drugs
  models/
    __init__.py
    forecaster.py             FEATURE_COLS, train_xgboost (GridSearchCV +
                              TimeSeriesSplit), train_and_evaluate,
                              load_model, baselines
    risk_classifier.py        TIER_CRITICAL/LOW/OK constants, classify_risk,
                              calculate_order_qty, build_risk_assessment,
                              RiskAssessment dataclass, forecast_30_days
                              (recursive), assess_from_features
    expiry_advisor.py         TIER_NO_ACTION/EARLY_MIN/SPECIAL_MIN, RISK_LOW/HIGH,
                              ExpiryOffer dataclass, classify_discount,
                              assess_batch, assess_all_batches
    expiry_finance.py         compute_value_at_risk, compute_recovered,
                              compute_waste, waste_by_atc
    alert_engine.py           Alert dataclass, alerts_from_risk,
                              alerts_from_expiry, refresh (idempotent)
    decomposition.py          decompose (statsmodels wrapper)
    inventory_kpi.py          compute_turnover, _classify
    po_generator.py           build_all_pos, generate_po_pdf (fpdf2)
  api/
    __init__.py
    app.py                    create_app (Flask factory)
    routes.py                 Blueprint with /health, /api/v1/risk,
                              /api/v1/forecast/<atc_code>
  dashboard/
    __init__.py
    _shared.py                DB_PATH, MODELS_DIR, FEATURES_CSV constants,
                              @cache_resource load_artifacts,
                              @cache_data run_assessment, CSS injection,
                              check_required_files guard
    app.py                    Overview page (Streamlit entry)
    pages/
      1_History_Forecast.py   ATC selectbox + Plotly history+forecast chart
                              with P10-P90 bootstrap band
      2_Stock_Update.py       st.form for current_stock edit, audit CSV write
      3_Expiry_Offers.py      KPI strip + data_editor + Gantt timeline
      4_Analytics.py          6 panels: model accuracy, feature importance,
                              ABC Pareto, seasonal decomposition, YoY growth,
                              rolling trend, turnover KPI
      5_Receive_Stock.py      Receive new batch / recall faulty lot forms
      6_Alerts.py             Notification feed + acknowledge buttons
      7_Manage_Catalog.py     ATC overview, add drug, register ATC,
                              supplier directory, assign supplier
      8_Purchase_Orders.py    Per-supplier expanders, PDF download,
                              mark-as-sent, order history

scripts/                      CLI launchers (10 scripts)
  ingest_kaggle.py, ingest_data.py, register_atc.py, run_pipeline.py,
  train_model.py, assess_risk.py, run_api.py, run_dashboard.py,
  export_committee_pdf.py, run_public.py

tests/                        Pytest suite, 14 test files, 182 tests
```

### 4.4.2 Key data structures

SPIS uses three immutable dataclasses to represent the outputs of the
three main analytical functions. Each is decorated `@dataclass(frozen=True)`
so an instance captured by one part of the system cannot be silently
mutated by another. This is the project's strongest defence against
the "value drift" class of bug.

```
RiskAssessment                ExpiryOffer                    Alert
+-----------------+           +-------------------+          +-------------+
| atc_code        |           | atc_code          |          | alert_type  |
| current_stock   |           | batch_number      |          | atc_code    |
| forecast_30d    |           | quantity          |          | batch_number|
| daily_demand    |           | expiry_date       |          | severity    |
| days_of_stock   |           | days_to_expiry    |          | message     |
| risk_tier       |           | forecasted_sales  |          +-------------+
| order_qty       |           | units_at_risk     |
+-----------------+           | unit_cost         |
                              | waste_value       |
                              | suggested_discount|
                              | offer_label       |
                              | action            |
                              +-------------------+
```

`RiskAssessment` is produced by `risk_classifier.build_risk_assessment()`;
`ExpiryOffer` by `expiry_advisor.assess_batch()`; `Alert` by either
`alert_engine.alerts_from_risk()` or `alert_engine.alerts_from_expiry()`.
All three flow upwards from the model layer to the presentation layer
unchanged.

### 4.4.3 Module dependency graph

```
            +-----------------------+
            |   spis/dashboard/*    |   (Streamlit pages)
            +----------+------------+
                       |
                       v
            +-----------------------+   +---------------------+
            |  spis/api/routes.py   |   | spis/dashboard/     |
            +----------+------------+   | _shared.py (cache)  |
                       |                +----------+----------+
                       v                           |
            +-----------------------+              |
            |  spis/api/app.py      |              |
            +----------+------------+              |
                       |                           |
            +----------+---------------------------+
            |
            v
+-----------------------+   +-----------------------+   +-----------------------+
| risk_classifier.py    |   | expiry_advisor.py     |   | alert_engine.py       |
| (DoS, recursive       |   | (2-factor discount    |   | (Alert mapping,       |
|  forecast_30_days)    |   |  classify_discount)   |   |  idempotent refresh)  |
+----------+------------+   +----------+------------+   +----------+------------+
           |                           |                           |
           v                           v                           v
+-----------------------+   +-----------------------+   +-----------------------+
| forecaster.py         |   | expiry_finance.py     |   | po_generator.py       |
| (XGBoost training     |   | (SAR aggregates)      |   | (PO build + fpdf2)    |
|  + load_model)        |   +-----------------------+   +-----------------------+
+----------+------------+
           |
           v
+-----------------------+   +-----------------------+   +-----------------------+
| spis/data/pipeline.py |   | spis/data/catalog.py  |   | inventory_kpi.py /    |
| (35 features)         |   | (catalog helpers)     |   | decomposition.py      |
+----------+------------+   +----------+------------+   +-----------------------+
           |                           |
           v                           v
+---------------------------------------------------------------+
|                spis/data/database.py                          |
|   schema, seeds, init_db, update_stock, add_batch,            |
|   recall_batch, alerts CRUD, suppliers CRUD, PO history       |
+---------------------------------------------------------------+
```

No cyclic imports exist. Every arrow points from a higher layer to a
lower one. The dashboard pages depend on `_shared.py` for cached
artifacts, and on the model modules for the typed dataclasses they
render.

## 4.5 System Organisation

This section captures how the modules behave together over time, using
three views: a data flow diagram (end-to-end pipeline), two sequence
diagrams (for the two most representative use cases), and two state
diagrams (for the alert and batch lifecycles).

### 4.5.1 End-to-end data flow

```
+----------+     +--------------+     +-----------------+
|  Raw CSV |---->|  Ingestion   |---->|  SQLite DB      |
| (Kaggle  |     | ingest_*.py  |     |  inventory.db   |
|  or new  |     +--------------+     +--------+--------+
|  pharma) |                                   | daily sales
+----------+                                   v
                                     +---------------------+
                                     |  Feature Pipeline   |
                                     |  pipeline.py        |
                                     |  1. Extract daily   |
                                     |  2. Validate/clip   |
                                     |  3. Fill date gaps  |
                                     |  4. Engineer 35     |
                                     |     features        |
                                     |  5. Train/test split|
                                     +----------+----------+
                                                | features_daily.csv
                                                | train.csv / test.csv
                                                v
                                     +---------------------+
                                     |  XGBoost Training   |
                                     |  forecaster.py      |
                                     |  TimeSeriesSplit CV |
                                     |  + GridSearchCV     |
                                     +----------+----------+
                                                | xgboost_forecaster.joblib
                                                | label_encoder.joblib
                                                | feature_importance.json
                                                v
                +-------------------------------+---------------------+
                |                               |                     |
                v                               v                     v
+-----------------------+   +-----------------------+   +-----------------------+
| Risk Assessment       |   | Expiry Assessment     |   | Alert Refresh         |
| risk_classifier.py    |   | expiry_advisor.py     |   | alert_engine.py       |
| (recursive 30d        |   | (2-factor discount    |   | (insert if not        |
|  forecast + DoS)      |   |  on batches)          |   |  already open)        |
+-----------+-----------+   +----------+------------+   +----------+------------+
            |                          |                           |
            +--------+-----------------+--------+------------------+
                     |                          |
                     v                          v
            +-------------------+   +-------------------------+
            | Streamlit         |   | Flask REST API          |
            | Dashboard         |   | /health /api/v1/risk    |
            | (9 screens)       |   | /api/v1/forecast/<atc>  |
            +-------------------+   +-------------------------+
```

### 4.5.2 Sequence diagram — UC-1: View dashboard overview

```
Operator     Streamlit       _shared.py    risk_classifier   forecaster      SQLite
   |             |                |              |               |              |
   |--open URL-->|                |              |               |              |
   |             |--inject_css--->|              |               |              |
   |             |--check_required_files()->     |               |              |
   |             |<--all ok-------|              |               |              |
   |             |--load_artifacts() (cached)--->|               |              |
   |             |                |--load_model()--------------->|              |
   |             |                |                              |--read joblib |
   |             |                |<-----model + encoder---------|              |
   |             |                |--load_atc_inventory()--------------->       |
   |             |                |<---------dict[atc_code,stock]---------------|
   |             |<-(model,encoder,inventory)---|               |              |
   |             |--run_assessment(...) (cached, ttl=300)------->|              |
   |             |                |              |--for each ATC code:         |
   |             |                |              |  forecast_30_days(recursive)|
   |             |                |              |  build_risk_assessment      |
   |             |                |              |--read sales/features-------->|
   |             |                |              |<-----feature rows-----------|
   |             |<-list[RiskAssessment]---------|               |              |
   |             |--render KPI cards, donut,                                    |
   |             |  bar chart, risk table,                                      |
   |             |  medications table with turnover                             |
   |<-rendered---|                |              |               |              |
```

### 4.5.3 Sequence diagram — UC-5: Receive a new batch (Phase 9)

```
Operator   Page 5         add_batch    SQLite    audit CSV    run_assessment
   |          |              |           |           |              |
   |--fill form-->|          |           |           |              |
   |          |--add_batch(  |           |           |              |
   |          |  atc, lot,   |           |           |              |
   |          |  qty, cost,  |           |           |              |
   |          |  expiry)---->|           |           |              |
   |          |              |--check duplicate ---->|              |
   |          |              |<-----not duplicate----|              |
   |          |              |--check valid date     |              |
   |          |              |--BEGIN-------------->|              |
   |          |              |--INSERT batch ------>|              |
   |          |              |--UPDATE inventory --->|              |
   |          |              |--COMMIT ------------->|              |
   |          |              |--audit_row --------------->          |
   |          |<-success-----|           |           |              |
   |          |--clear cache ----------------------->|              |
   |          |--st.rerun()                                         |
   |<-updated-|              |           |           |              |
```

### 4.5.4 State diagram — Alert lifecycle

```
                      alert_engine.refresh()
                  (idempotent: skip if same key open)
                              |
                              v
       +----------+    +------------+    acknowledge_alert    +-------------+
       |  (none)  |--->|    OPEN    |------------------------>|ACKNOWLEDGED |
       +----------+    +------------+                         +-------------+
                              ^                                       |
                              |                                       |
                              +---------------------------------------+
                              (a new occurrence after acknowledgement
                               can create a new OPEN alert -- old one
                               stays ACKNOWLEDGED)
```

`alert_key_exists()` guards the transition into OPEN: a candidate
alert with the same `(alert_type, atc_code, batch_number)` triple is
only inserted if no existing record with that key is still OPEN.

### 4.5.5 State diagram — Batch lifecycle

```
                                                 quantity drops to 0
                                                 over time (sold)
                                                       |
   +-----------+   add_batch()   +------------+        v       +----------+
   | (no batch)|--------------->| RECEIVED   |--------------->| DEPLETED |
   +-----------+                | IN STOCK   |                +----------+
                                |            |
                                |            |--expiry_date < today---+
                                |            |                        v
                                |            |                 +-------------+
                                |            |                 |   EXPIRED   |
                                |            |                 +-------------+
                                |            |
                                |            |--recall_batch()
                                |            |  (sets quantity=0,
                                |            |   returned=1,
                                |            |   appends RECALLED suffix
                                |            |   to notes)
                                |            |              +------------+
                                |            +------------->|  RECALLED  |
                                +------------+              +------------+
```

The `inventory_batches.returned` flag distinguishes RECALLED from
naturally-DEPLETED batches in the audit trail. The expiry advisor
returns offers with `action = "write_off"` for batches in the
EXPIRED state and `action = "return_to_supplier"` for batches in
the IN STOCK state with `days_to_expiry < 30`.

## 4.6 Algorithms

This section documents the seven core algorithms in pseudocode form.
The pseudocode reflects the implementation in `spis/`; the actual
Python source is in Chapter 5 and the appendices.

### 4.6.1 Feature engineering (pipeline.engineer_features)

```
Input:  DataFrame[date, atc_code, quantity]; one row per (atc, day);
        missing days already filled with quantity=0
Output: DataFrame with 35 additional columns

Sort by (atc_code, date)
For each row:
    # 12 calendar features (computed from date)
    day_of_week, day_of_month, month, year, week_of_year <- from date
    is_weekend         <- day_of_week >= 5
    is_holiday         <- date in TR_HOLIDAYS              # Turkey, training
    season             <- 1..4 from month
    is_payday_window   <- day_of_month in {1,2,3,15,16,17}
    is_school_holiday  <- in TR_SCHOOL_BREAKS
    quarter            <- (month-1) // 3 + 1
    days_to_month_end  <- days_in_month - day_of_month

# Per-ATC group operations (no cross-drug leakage)
For each atc_code group:
    # 7 lag features
    For d in {1, 2, 3, 7, 14, 28, 365}:
        lag_d <- quantity shifted by d positions

    # 12 rolling features
    rolling_mean_{7,14,28,90,365} <- rolling mean over those windows
    rolling_std_{7,28}            <- rolling std
    rolling_min_7, rolling_max_7  <- rolling extremes
    ema_{7,14,28}                 <- exponentially weighted mean

    # 4 derived features
    lag_ratio_7    <- lag_1 / rolling_mean_7
    trend_counter  <- days since dataset start
    rolling_range_7 <- rolling_max_7 - rolling_min_7
    ema_ratio      <- ema_7 / ema_28

Return DataFrame
```

**Rationale for the 35-feature design.** The feature set was sized
to give XGBoost a complete description of the demand signal across
the temporal scales that matter for pharmacy operations, while
staying small enough to fit on commodity hardware and remain
interpretable on a single-page feature-importance chart. The 35
features fall into four functional families:

| Family | Count | Captures |
|---|---|---|
| **Calendar** | 12 | Weekly, monthly, seasonal, and holiday effects (day-of-week, day-of-month, month, year, week-of-year, weekend, holiday, season, payday-window, school-holiday, quarter, days-to-month-end). |
| **Lag** | 7 | Direct memory at horizons that match procurement and biological cycles: `lag_{1,2,3}` (immediate trend), `lag_7` (weekly recurrence), `lag_{14,28}` (bi-weekly and monthly), `lag_365` (annual seasonality). |
| **Rolling** | 12 | Smoothed local-window statistics that suppress one-day noise: rolling means at 7/14/28/90/365-day windows, rolling std at 7/28 days, rolling min/max at 7 days, and EMAs at 7/14/28 days. |
| **Derived** | 4 | Interaction terms that XGBoost cannot otherwise reach in a single split: `lag_ratio_7` (today vs. weekly average), `trend_counter` (long-run drift), `rolling_range_7` (volatility), `ema_ratio` (short vs. long EMA — momentum). |

Each family addresses a temporal scale (day, week, month, year)
that pharmacy demand actually exhibits in the Kaggle source data.
Empirically the top-five feature-importance scores are dominated
by `ema_14`, `ema_7`, and `rolling_mean_14` (≈ 78% combined),
confirming that the EMA/rolling family carries most of the signal
while the lag and calendar families provide the conditioning that
lets XGBoost separate weekday patterns from holiday effects.
Smaller feature sets (e.g. Phase 3's 21-feature set) achieved
MAE ≈ 2.80; expanding to 35 features drove MAE down to ≈ 1.06,
after which further additions produced diminishing returns. The
chosen count therefore represents the point where marginal feature
value drops below the marginal cost of pipeline maintenance.

### 4.6.2 XGBoost training (forecaster.train_and_evaluate)

```
Input:  train_path, test_path (CSVs), output_dir
Output: trained XGBRegressor, fitted LabelEncoder, metrics dict

Load train.csv, test.csv
encoder <- LabelEncoder().fit(train.atc_code)
train["atc_encoded"] <- encoder.transform(train.atc_code)
test["atc_encoded"]  <- encoder.transform(test.atc_code)

train_clean <- train.dropna(subset=FEATURE_COLS)   # drop first-year NaNs
X_train, y_train <- train_clean[FEATURE_COLS], train_clean.quantity
X_test,  y_test  <- test[FEATURE_COLS].fillna(0),  test.quantity

# Baselines (no training needed)
pred_naive <- test.lag_1.fillna(0)                  # yesterday's value
pred_mavg  <- test.rolling_mean_7.fillna(0)         # 7-day rolling mean

# XGBoost with time-aware cross-validation
param_grid <- {
    n_estimators:    [500, 800],
    max_depth:       [6, 8],
    learning_rate:   [0.03, 0.05],
    subsample:       [0.8, 1.0],
    colsample_bytree:[0.8, 1.0],
    min_child_weight:[1, 5],
    reg_alpha:       [0, 0.1]
}
cv    <- TimeSeriesSplit(n_splits=5)
grid  <- GridSearchCV(XGBRegressor, param_grid, cv=cv,
                       scoring="neg_mean_absolute_error", n_jobs=-1)
grid.fit(X_train, y_train)
model <- grid.best_estimator_
pred_xgb <- max(0, model.predict(X_test))           # clip to non-negative

# Metrics
For each (label, pred) in [("Naive", pred_naive),
                             ("Moving Avg", pred_mavg),
                             ("XGBoost",     pred_xgb)]:
    mae   <- mean(|y_test - pred|)
    rmse  <- sqrt(mean((y_test - pred)^2))
    mape  <- mean(|y_test - pred| / y_test) * 100  for y_test != 0

# Persist
save(model,   output_dir / "xgboost_forecaster.joblib")
save(encoder, output_dir / "label_encoder.joblib")
write_json(metrics,            output_dir / "metrics.json")
write_json(feature_importance, output_dir / "feature_importance.json")

Return (model, encoder, metrics)
```

### 4.6.3 Recursive 30-day forecast (risk_classifier.forecast_30_days)

This algorithm supersedes the GP1 design's "hold-features-constant"
loop. The recursive variant keeps lag and rolling features alive
across the 30-day horizon by maintaining a 365-day history buffer.

```
Input:  model, encoder, seed_row (one row with all FEATURE_COLS),
        atc_code, start_date, days=30, return_daily=False
Output: total forecast (float) OR list of daily forecasts (list[float])

If atc_code not in encoder.classes_:
    raise ValueError

atc_encoded <- encoder.transform([atc_code])[0]
holidays    <- SaudiArabia(start_date.year .. start_date.year + 1)
                                # NB: Saudi for serving, Turkey for training

# Initialise 365-day rolling buffer from the seed row's lag values
history <- [seed.lag_365] * (365-28)
        + [seed.lag_28]  * (28-14)
        + [seed.lag_14]  * (14-7)
        + [seed.lag_7]   * (7-3)
        + [seed.lag_3, seed.lag_2, seed.lag_1]

ema7, ema14, ema28        <- seed.ema_7, seed.ema_14, seed.ema_28
alpha7, alpha14, alpha28  <- 2/(7+1), 2/(14+1), 2/(28+1)
trend_counter             <- seed.trend_counter

daily_preds <- []
For i in 0..days-1:
    d <- start_date + i days

    # Recompute lag/rolling features FROM THE BUFFER (this is the recursion)
    lag_1, lag_2, lag_3   <- history[-1], history[-2], history[-3]
    lag_7, lag_14, lag_28 <- history[-7], history[-14], history[-28]
    lag_365               <- history[-365]
    rolling_mean_7        <- mean(history[-7:])
    rolling_std_7         <- std(history[-7:])
    ... # same for the other rolling windows

    # Calendar features computed from actual future date d
    calendar <- {day_of_week, month, year, is_weekend,
                  is_holiday=date in holidays, season, ...}

    # Derived features
    lag_ratio_7      <- lag_1 / lag_7
    rolling_range_7  <- rolling_max_7 - rolling_min_7
    ema_ratio        <- ema7 / ema28

    X <- DataFrame from {calendar, lag_*, rolling_*, ema_*, derived,
                          atc_encoded}
    pred <- max(0, model.predict(X)[0])      # clip to non-negative
    daily_preds.append(pred)

    # Update state for next iteration (THIS is what makes it recursive)
    history.append(pred)
    ema7  <- ema7  + alpha7  * (pred - ema7)
    ema14 <- ema14 + alpha14 * (pred - ema14)
    ema28 <- ema28 + alpha28 * (pred - ema28)
    trend_counter <- trend_counter + 1

Return daily_preds if return_daily else sum(daily_preds)
```

The recursive form gives day-to-day variation in the forecast curve
(visible in Page 1's chart) instead of the flat line that the
held-constant variant produced. Page 1 additionally renders a
P10-P90 prediction band by bootstrap-resampling test-set residuals
500 times onto this point forecast and clipping each draw to ≥ 0.

### 4.6.4 Risk classification (risk_classifier.assess_from_features)

```
Input:  features_csv path, inventory dict[atc_code -> stock],
        model, encoder, safety_days=3.0
Output: list[RiskAssessment]

Constants: TIER_CRITICAL = 7, TIER_LOW = 14, TIER_OK = 90

For each (atc_code, current_stock) in inventory:
    seed_row <- last row for atc_code in features_csv

    forecast_30d <- forecast_30_days(model, encoder, seed_row,
                                       atc_code, start_date)
    daily_demand <- forecast_30d / 30

    If daily_demand > 0:
        days_of_stock <- current_stock / daily_demand
    Else:
        days_of_stock <- infinity

    risk_tier <- classify_risk(days_of_stock):
        if dos < 7:  CRITICAL
        if dos < 14: LOW
        if dos < 90: OK
        else:        OVERSTOCK

    safety_buffer <- daily_demand * safety_days
    order_qty     <- max(0, forecast_30d + safety_buffer - current_stock)

    append RiskAssessment(atc_code, current_stock, forecast_30d,
                          daily_demand, days_of_stock, risk_tier, order_qty)

Return list
```

**Mathematical formulation.** The risk-classification logic computes
three quantities per ATC code from the 30-day forecast and the current
stock. Using the notation `f30` = sum of the 30 daily predictions,
`s` = current stock, and `d` = mean daily demand (= `f30 / 30`):

1. **Days of Stock (DoS).** The forward coverage of current stock at
   the predicted average daily consumption:

   ```
       DoS = s / d              if d > 0
       DoS = ∞                  if d = 0   (no demand → stock never runs out)
   ```

2. **Risk tier.** A piecewise classification on DoS, with thresholds
   `TIER_CRITICAL = 7`, `TIER_LOW = 14`, `TIER_OK = 90` (days). The
   rationale for these boundaries is given in §4.7.2 — they map directly
   to the longest seeded supplier lead time (CRITICAL), the typical
   pharmacy review cycle (LOW), and a three-month working-capital and
   expiry-risk ceiling (OK / OVERSTOCK):

   ```
       tier(DoS) = CRITICAL    if DoS  < 7
                 = LOW         if 7  ≤ DoS < 14
                 = OK          if 14 ≤ DoS < 90
                 = OVERSTOCK   if      DoS ≥ 90
   ```

3. **Order quantity.** The number of units to procure to cover the
   forecasted 30-day demand plus a safety buffer, less what is already
   on the shelf, floored at zero:

   ```
       safety_buffer = d × safety_days        (default safety_days = 3)
       order_qty     = max(0, f30 + safety_buffer − s)
   ```

   Equivalently:

   ```
       order_qty = max(0, f30 + d · safety_days − s).
   ```

**Why a safety buffer is needed.** The point forecast `f30` is the
*expected* demand over the next 30 days, not the *worst case*. Real
demand exhibits volatility: weekday spikes, holiday surges, and
prescription-pattern shifts can push actual demand above the
expectation for several consecutive days. Ordering exactly `f30 − s`
units would leave the pharmacy with a 50% probability of a stockout
before the next replenishment cycle (whenever realised demand exceeds
the forecast). The buffer `d × safety_days` is a deliberate over-order
that absorbs forecast error and supplier-lead-time variance,
converting an expected-value sizing rule into a service-level rule.

The default `safety_days = 3` was chosen to span the maximum seeded
supplier lead time (3–7 days) without doubling the order quantity. A
more rigorous treatment — quantile-regression forecasts that expose
P90 directly — is identified as future work (§7.5 item 2); the
constant-multiplier form is the simplest formulation that still
guarantees the buffer scales with demand rather than being a fixed
unit count.

**Why the `max(0, …)` clamp.** When current stock already exceeds the
forecasted demand plus the safety buffer (`s ≥ f30 + d · safety_days`),
the formula would emit a negative order quantity. Clamping at zero
encodes the operational fact that the system never recommends a
*return*; the OVERSTOCK tier surfaces the over-supply condition
separately, and the recommendation becomes "do not place an order this
cycle" rather than a negative procurement signal.

### 4.6.5 Two-factor expiry advisor (expiry_advisor.classify_discount)

```
Input:  days_to_expiry, risk_ratio (= units_at_risk / quantity)
Output: (discount_pct, offer_label, action)

Constants:
    TIER_NO_ACTION   = 90    # > 90 days  -> no action
    TIER_EARLY_MIN   = 60    # 60-90 days -> Early Discount window
    TIER_SPECIAL_MIN = 30    # 30-59 days -> Special Offer window
                              # < 30 days  -> Cannot Dispense (return)
    RISK_LOW  = 0.33
    RISK_HIGH = 0.66

If days < 0:                  return (0,  "Expired",          "write_off")
If days < TIER_SPECIAL_MIN:   return (0,  "Cannot Dispense",  "return_to_supplier")
If days < TIER_EARLY_MIN:     # 30-59 day "Special Offer" window
    If risk_ratio < RISK_LOW:  return (10, "Special Offer",   "promote")
    If risk_ratio <= RISK_HIGH:return (20, "Special Offer",   "promote")
    Return                          (30, "Special Offer",     "promote")
If days <= TIER_NO_ACTION:    # 60-90 day "Early Discount" window
    If risk_ratio < RISK_LOW:  return (0,  "Monitor",          "none")
    If risk_ratio <= RISK_HIGH:return (10, "Early Discount",   "promote")
    Return                          (15, "Early Discount",   "promote")
Return                              (0,  "OK",                "none")
```

The two-factor design (rather than days alone) means a near-expiry
batch that demand will absorb is not over-discounted, and a
far-from-expiry batch with low demand still gets early action.

### 4.6.6 Idempotent alert refresh (alert_engine.refresh)

```
Input:  db_path, list[RiskAssessment], list[ExpiryOffer]
Output: number of new alerts inserted

candidates <- []

# Map risk tiers to LOW_STOCK alerts
For each RiskAssessment ra:
    If ra.risk_tier == "CRITICAL":
        candidates.append(Alert(LOW_STOCK, ra.atc_code, None,
                                 CRITICAL, "<message>"))
    elif ra.risk_tier == "LOW":
        candidates.append(Alert(LOW_STOCK, ra.atc_code, None,
                                 WARNING, "<message>"))
    # OK, OVERSTOCK -> no alert

# Map expiry offers to EXPIRY alerts
For each ExpiryOffer o:
    if o.action == "none":          continue
    if o.action == "write_off":      severity <- CRITICAL
    elif o.action == "return_to_supplier": severity <- WARNING
    elif o.action == "promote" and o.days_to_expiry <= 30: severity <- WARNING
    elif o.action == "promote":      severity <- INFO
    candidates.append(Alert(EXPIRY, o.atc_code, o.batch_number,
                             severity, "<message>"))

# Idempotent persistence
inserted <- 0
For each Alert a in candidates:
    if not alert_key_exists(db, a.alert_type, a.atc_code, a.batch_number):
        create_alert(db, a.alert_type, a.atc_code, a.batch_number,
                     a.severity, a.message)
        inserted <- inserted + 1

Return inserted
```

`alert_key_exists` checks for an OPEN alert (`acknowledged_at IS NULL`)
with the same `(alert_type, atc_code, batch_number)` triple. After an
alert is acknowledged, a later refresh with the same condition will
re-insert a fresh alert — preventing the system from missing a
recurring problem the pharmacist has already actioned once.

### 4.6.7 Supplier-grouped purchase order (po_generator.build_all_pos)

```
Input:  db_path, list[RiskAssessment], default_unit_cost=1.0
Output: list of PO dicts (one per supplier)

If no assessments:        return []

atc_info   <- join atc_categories + suppliers   # supplier per ATC
unit_costs <- per-ATC most-recent batch unit_cost
drug_names <- per-ATC list of drug names

supplier_buckets <- {}
For each RiskAssessment ra:
    if ra.risk_tier not in (CRITICAL, LOW): continue
    if ra.order_qty <= 0:                    continue

    sid       <- atc_info[ra.atc_code].supplier_id   # may be NULL
    unit_cost <- unit_costs.get(ra.atc_code, default_unit_cost)

    line <- {
        atc_code, atc_name, drug_names, qty=round(ra.order_qty),
        unit_cost, total_cost = ra.order_qty * unit_cost,
        risk_tier=ra.risk_tier
    }

    bucket_key <- sid if sid is not None else 0  # 0 = unassigned bucket
    if bucket_key not in supplier_buckets:
        supplier_buckets[bucket_key] = {
            supplier = <full supplier dict or Unassigned Supplier>,
            lines    = []
        }
    supplier_buckets[bucket_key].lines.append(line)

POs <- []
For each bucket:
    POs.append({
        supplier:    bucket.supplier,
        po_date:     today.isoformat(),
        lines:       bucket.lines,
        grand_total: sum(line.total_cost for line in bucket.lines)
    })
Return POs
```

The PDF rendering step (`generate_po_pdf`) uses fpdf2 with Latin-1
encoding; non-Latin characters are passed through `_safe()` which
replaces unencodable characters rather than crashing.

## 4.7 Alternative Designs and Methods

This section documents design decisions where a clear alternative
exists. Each entry describes the choice, the rejected alternatives,
and the reason.

### 4.7.1 Forecasting model

**Chosen.** A single XGBoost regressor (`reg:squarederror`), with
all eight ATC codes encoded into one shared model via
`LabelEncoder` on `atc_code`, and hyperparameters tuned by
`GridSearchCV` over a 7-dimensional grid with
`TimeSeriesSplit(n_splits=5)`.

**Rationale.** XGBoost was selected because it performs well on
structured tabular time-series data, accepts arbitrary engineered
features (calendar, lag, rolling, EMA) as direct inputs, and trains
a single multi-drug model in seconds on commodity hardware. It
provides lower computational complexity than deep learning models
(LSTM/RNN) while delivering feature-importance scores that support
the interpretability required of a clinical decision-support tool.
Its empirical performance on the held-out test set (MAE ≈ 1.06)
beats the moving-average baseline (MAE ≈ 2.89) by roughly 3×, which
exceeded the FR-3.2 acceptance criterion. The "lightweight, no-cloud,
single-host" non-functional requirements (Ch3 NFR-1, NFR-5) ruled out
heavier deep-learning stacks.

**Considered and rejected.**

- **ARIMA / SARIMA** — strong on regular univariate seasonal series,
  but a separate model per drug is needed, and external regressors
  (calendar, payday windows, school holidays) require ARIMAX
  extensions. The aggregate effort to maintain eight ARIMA models
  exceeded the value.
- **Facebook Prophet** — handles strong seasonality and holidays
  well, but still trains one model per series, and Prophet's
  internal trend/seasonality decomposition is less expressive than
  the 35 engineered features.
- **LSTM** — has the best theoretical fit for sequential data but
  requires substantially larger training sets, careful
  hyperparameter tuning, and offers limited interpretability.
  Phase 3 experiments achieved MAE ≈ 1.06 with XGBoost; an LSTM
  would have to outperform that with much higher implementation
  cost.

XGBoost's MAE of 1.06 against the moving-average baseline of 2.89
(roughly 3× improvement) was deemed sufficient and the
single-model-multi-drug architecture was the deciding factor.

### 4.7.2 Risk-tier thresholds

**Chosen.** `TIER_CRITICAL = 7`, `TIER_LOW = 14`, `TIER_OK = 90`
(days of stock).

**Rationale.** The thresholds were chosen to match real
pharmacy-operations timescales:

- **CRITICAL (< 7 days)** — the seeded supplier lead times
  (`suppliers.lead_time_days`) span 3–7 days. A drug below one
  week of stock cannot be guaranteed to be replenished before a
  stockout if any supplier is at the slow end of that range, so
  this band marks an immediate action item.
- **LOW (7–14 days)** — provides a two-week early-warning window
  that absorbs lead-time variability and gives the pharmacist
  one full review cycle to schedule a routine purchase order
  without alarm.
- **OK (14–90 days)** — the normal operating band. Three months
  is sufficiently long that no procurement action is needed and
  capital is not yet excessively tied up.
- **OVERSTOCK (≥ 90 days)** — beyond three months the inventory
  begins to materially compete with shelf space, working
  capital, and expiry risk; the tier triggers a recommendation
  to slow future orders rather than place new ones.

The boundaries are domain-driven (lead time, calendar cycles,
shelf-life economics) rather than arbitrary; they are stored as
named constants in `risk_classifier.py` (`TIER_CRITICAL`,
`TIER_LOW`, `TIER_OK`) so they can be re-tuned per pharmacy
without touching the classification logic.

**Considered and rejected.**

- **Initial Phase 4 sketch: `(3, 7, 30)`** — the prototype used
  these. During Phase 8.5 the team observed that the seeded
  supplier lead times (`suppliers.lead_time_days`) span 3 to 7 days,
  so a CRITICAL band of "less than 3 days" left no practical time
  for the pharmacist to react to the alert. The thresholds were
  re-calibrated outward: CRITICAL now means "less than one week",
  LOW means "less than two weeks", and OVERSTOCK starts at three
  months. The wider bands give the operator a usable response
  window.

### 4.7.3 30-day forecast loop

**Chosen.** Recursive: each predicted value is appended to a
365-day history buffer, and the next iteration recomputes lag,
rolling, and EMA features from that buffer. EMAs are updated
in-place using `α = 2/(span+1)`.

**Why a 30-day horizon?** The horizon length was set to 30 days
to align with three concurrent operational cycles:

1. **Procurement cycle.** Pharmacy procurement is typically run
   on a monthly basis (purchase-order review, supplier invoicing,
   and budget reporting are calendar-month aligned), so a 30-day
   forecast slots directly into the natural ordering rhythm.
2. **Supplier lead times.** Seeded supplier lead times span 3–7
   days; a 30-day forecast leaves ≈ 4× headroom over the longest
   lead time, so an order placed today on the basis of the
   forecast is guaranteed to land well inside the predicted demand
   window.
3. **Forecast reliability.** XGBoost is a one-step regressor that
   we extend recursively. Test-set error grows with horizon as
   each predicted value is fed back into the lag buffer; 30 days
   sits at the knee of the error curve — long enough to be
   actionable, short enough that compounded recursion error stays
   within the FR-3 MAE target.

Shorter horizons (7 or 14 days) were rejected because they fail to
cover the OVERSTOCK threshold (≥ 90 DoS) decision and require the
pharmacist to re-run the assessment too frequently. Longer horizons
(60 or 90 days) were rejected because recursion error compounds and
the additional resolution adds no procurement value beyond the
monthly cycle.

**Considered and rejected (loop implementation).**

- **Hold lag/rolling/EMA features constant from the seed row.**
  Simpler — every day of the 30-day window receives the same
  lag/rolling features and only the calendar varies. This was the
  original Phase 4 design. The problem is that the resulting
  30-day curve is essentially flat with only weekly calendar
  wobble, which obscures the model's actual dynamics on Page 1.
  The recursive form gives day-to-day variation that matches what
  XGBoost has learned from the training data.

### 4.7.4 Expiry advisor: single-factor vs two-factor

**Chosen.** Two-factor: discount percentage depends on both
`days_to_expiry` and `risk_ratio = units_at_risk / quantity`.

**Considered and rejected.**

- **Single-factor on `days_to_expiry` alone** (e.g. "75 days = 15%,
  45 days = 25%, 20 days = 40%"). Simpler to explain but treats
  a 100-unit batch with 95 units at risk identically to a 100-unit
  batch with 5 units at risk. The two-factor rule lets a
  near-expiry batch that demand will absorb avoid over-discount.

### 4.7.5 Database

**Chosen.** SQLite — single file, no server, foreign keys enforced.

**Considered and rejected.**

- **PostgreSQL** — production-grade but adds an installation step,
  a configuration step, and an external dependency. The data
  volume (424,080 sales rows) fits comfortably in SQLite.
- **MongoDB** — relational integrity is the wrong fit for an ATC
  hierarchy with FK joins everywhere. Document stores would have
  required application-level join logic for every dashboard query.

The "lightweight, no cloud, self-contained" non-functional
requirement (Ch3 NFR-2, NFR-5) made SQLite the right choice.

### 4.7.6 Frontend stack

**Chosen.** Streamlit multi-page app (Overview + 8 pages),
reading model artifacts directly from disk via
`@st.cache_resource` and `@st.cache_data(ttl=300)`.

**Considered and rejected.**

- **Flask + Jinja templates** — more flexible but requires
  hand-rolled CSS, AJAX, and chart libraries. Phase 8.5 added
  multiple pages quickly because Streamlit's `pages/` convention
  did the routing automatically.
- **React SPA** — overkill for a single-host pharmacy demo and
  introduces a JavaScript build pipeline the team would have to
  maintain.
- **Streamlit thin-client over Flask API** — initially considered.
  Rejected because routing every page through the API doubled
  the latency without changing the user experience. The Flask
  API was kept as a separate sample external surface but is not
  the dashboard's backend.

### 4.7.7 API surface

**Chosen.** Three endpoints, read-only: `/health`,
`/api/v1/risk`, `/api/v1/forecast/<atc_code>`. Returns JSON.
HTTP 503 on missing model, 404 on unknown ATC.

**Considered and rejected.**

- **Full CRUD API** mirroring every dashboard write
  (stock update, batch receive, alert acknowledge, PO send).
  Out of scope for GP2 — authentication and authorisation
  would need to be designed first, and the dashboard already
  writes directly to SQLite.

## 4.8 Graphical User Interface Design

The interface is a multi-page Streamlit app with one Overview page
plus eight sub-pages. A consistent dark-mode visual language is
applied site-wide through `spis/dashboard/_shared.py::inject_css()`.

### 4.8.1 Visual language

```
Backgrounds:           #0e1117 (app), #161b27 (cards)
Card border:           #1e2d45
Section headings:      #a8c0dd (uppercase, letter-spacing)
Body text:             #c0cfe0
Caption text:          #4e6a84
Primary action:        #1a6fa8 (button), #155a8a (hover)

Tier accent colours (used everywhere -- alert bars, KPI strips,
donut slices, risk badges, table row tints):
    CRITICAL  : #ef233c (red)
    LOW       : #f77f00 (orange)
    OK        : #2dc653 (green)
    OVERSTOCK : #4361ee (blue)

Severity badges (alert centre):
    CRITICAL  : #ef233c bg, white fg
    WARNING   : #f77f00 bg, white fg
    INFO      : #4361ee bg, white fg
```

### 4.8.2 Overview page (app.py) — wireframe

```
+--------------------------------------------------------------------+
|  Smart Pharmacy Inventory System                                   |
|  30-day demand forecast . inventory risk . order recommendations   |
+--------------------------------------------------------------------+
|  [!] ACTION REQUIRED - 2 items need reordering                     |
|       Paracetamol (N02BE) -- order 165 units                       |
|       Salbutamol  (R03)   -- order 105 units                       |
+--------------------------------------------------------------------+
| +-----------+ +-----------+ +-----------+ +-----------+            |
| | CRITICAL  | | LOW STOCK | | ADEQUATE  | | OVERSTOCK |            |
| |     2     | |     1     | |     3     | |     2     |            |
| | Reorder   | | Within 14 | | 14-90 d   | | > 90 d    |            |
| +-----------+ +-----------+ +-----------+ +-----------+            |
+--------------------------------------------------------------------+
|  Risk Distribution            |  Recommended Order Qty (units)     |
|       (donut chart)           |       (horizontal bar chart)       |
+--------------------------------------------------------------------+
|  Inventory Risk Assessment                                         |
|  +--+----------+--------+-------+--------+---------+----+-------+  |
|  |  | Category | Drugs  | Stock | Fcst30 | Daily   | DoS| Order |  |
|  +--+----------+--------+-------+--------+---------+----+-------+  |
|  | ... 8 rows ...                                                  |
|  +-----------------------------------------------------------------+
+--------------------------------------------------------------------+
|  Medications by ATC Group (turnover ratio per drug)                |
|  +-------+-----+------+------+----------+------------------------+ |
|  | Drug  | ATC | Unit | Risk | Order Qty| Turnover               | |
|  | ... 57 rows ...                                                | |
+--------------------------------------------------------------------+
```

### 4.8.3 Sub-page wireframes (compact)

```
Page 1 (History & Forecast)
+--------------------------------------------------------------------+
|  [ATC selectbox]    [History window: 30 / 60 / 90 / 180 days]      |
|  +------ Medications in this group (collapsible) ----------------+ |
|  Plotly chart:                                                     |
|    - solid blue   = last N days of actual sales                    |
|    - dashed orange= 30-day forecast                                |
|    - orange ribbon= P10-P90 bootstrap band                         |
|    - vertical line at "today" separating history from forecast    |
|  [ 30d Forecast ] [ Daily Demand ] [ Days of Stock ]               |
+--------------------------------------------------------------------+

Page 2 (Stock Update)
+--------------------------------------------------------------------+
|  Form with one number_input per ATC code                           |
|  ATC | New Stock | Previous                                        |
|  ... 8 rows ...                                                    |
|  [Save All Changes] (primary)                                      |
|  After save: success toast + audit row + cache clear + rerun       |
+--------------------------------------------------------------------+

Page 3 (Expiry Offers)
+--------------------------------------------------------------------+
|  KPI strip: Value at Risk | Recovery | Written Off | Waste Rate    |
|  Red bar chart: waste by ATC                                       |
|  Filter: All / Urgent <30d / Upcoming 30-90d                       |
|  st.data_editor: ATC | Batch | Qty | Expiry | Days | At Risk | SAR |
|                   | Status | Suggested % | Applied % | Return?     |
|  [Confirm & Print Labels]                                          |
|  Gantt-style timeline coloured by urgency                          |
+--------------------------------------------------------------------+

Page 4 (Analytics) - six panels
+--------------------------------------------------------------------+
|  1. Model Accuracy (MAE / RMSE / MAPE metric cards)                |
|  2. XGBoost Feature Importance (top-20 horizontal bar)             |
|  3. Fast / Medium / Slow (ABC Pareto, 80% / 95% cutoffs)           |
|  4. Seasonal Decomposition (trend / seasonal / residual sub-plots) |
|  5. Year-over-Year Demand Growth (green/red bar)                   |
|  6. 12-Month Rolling Demand Trend (multi-line, 90-day rolling avg) |
|  + Inventory Turnover KPI strip (Slow/Low/Healthy/High/Excessive)  |
+--------------------------------------------------------------------+

Page 5 (Receive Stock)
+--------------------------------------------------------------------+
|  Section 1: Receive New Batch                                      |
|    Form: ATC | Batch # (auto-suggest LOT-YYYY-NNN) | Qty           |
|          Unit Cost (SAR) | Expiry Date | Notes                     |
|    [Receive Batch]                                                 |
|  Section 2: Recent Receipts (last 30 days)                         |
|  Section 3: Recall a Batch                                         |
|    Form: Batch Number | Reason                                     |
|    [Recall Batch]                                                  |
+--------------------------------------------------------------------+

Page 6 (Alerts)
+--------------------------------------------------------------------+
|  Sidebar filters: severity (multi), alert type (multi),            |
|                   show acknowledged (toggle)                       |
|  [ Open Alerts ] [ Critical ] [ Warnings ]                         |
|  Per-alert row: [severity badge] [type] [timestamp] [Ack button]   |
|                  message                                           |
|                  (if acked: "Done" tag + acknowledged_at)          |
+--------------------------------------------------------------------+

Page 7 (Manage Catalog)
+--------------------------------------------------------------------+
|  A. ATC Categories - read-only table                               |
|  B. Add Drug - form (name, ATC, unit, is_critical)                 |
|  C. Add ATC Code - form (code, name, system, initial_stock)        |
|  D. Suppliers - read-only table + Add Supplier form                |
|  E. Assign ATC Code to Supplier - selectbox form                   |
+--------------------------------------------------------------------+

Page 8 (Purchase Orders)
+--------------------------------------------------------------------+
|  [ Suppliers to Order From ] [ Total Line Items ] [ Total SAR ]    |
|  Per-supplier expander:                                            |
|    Supplier contact details + PO date                              |
|    Line items table                                                |
|    Grand total                                                     |
|    [Download PDF] [Mark as Sent]                                   |
|  Order History (newest first)                                      |
+--------------------------------------------------------------------+
```

### 4.8.4 Navigation and shared chrome

Streamlit's multi-page convention generates the left-sidebar nav
automatically from filenames in `spis/dashboard/pages/`. The
numeric prefix (`1_`, `2_`, …) controls ordering. Each page calls
`inject_css()` once after `set_page_config(layout="wide")` and
`check_required_files()` immediately after — the latter is the
single guard preventing a page from rendering when model artifacts
are absent.

## 4.9 Conclusion

This chapter described the SPIS design that delivers the functional
and non-functional requirements specified in Chapter 3. The system
is built as four cleanly separated layers with a pipe-and-filter
processing model and a repository pattern for state, using SQLite
as the single source of truth and joblib-serialised XGBoost as the
single source of forecast intelligence. The modular decomposition
keeps each analytical concern (forecasting, risk classification,
expiry advisor, alert engine, supplier directory, purchase orders,
turnover, decomposition) in its own module, and three frozen
dataclasses (`RiskAssessment`, `ExpiryOffer`, `Alert`) carry the
results upward to the presentation layer without mutation risk.
The algorithms — feature engineering, XGBoost training with
time-aware cross-validation, the recursive 30-day forecast loop,
the two-factor expiry classifier, idempotent alert refresh, and
supplier-grouped PO building — are documented in pseudocode here
and implemented in the next chapter. Chapter 5 walks through the
implementation in detail, including the supporting development
environment, the Phase 9 scope additions, and how every Streamlit
page is wired through `_shared.py` to the model layer.

---

# Chapter 5: Implementation

## 5.0 Design Evolution: GP1 Scope and Phase 9 Extension

Chapter 3 captured the functional requirements as agreed at the GP1
milestone — five module-level FR groups covering Data Management,
Forecasting Engine, Risk Analysis Logic, Dashboard and Interaction,
and Security and Data Management. Between GP1 and GP2 the project
scope was extended in two phases. Phase 8.5 split the single
dashboard page into nine and added per-batch expiry tracking with a
two-factor discount advisor. Phase 9 added a notification alert
engine, a directory of four real Saudi pharmaceutical suppliers
with operator-editable contacts, supplier-grouped purchase-order
PDFs, a batch receive-and-recall workflow, a catalog-management
page, an analytics page with six panels (model accuracy, feature
importance, ABC Pareto, seasonal decomposition, year-over-year
growth, rolling trend) plus a turnover KPI strip, and a P10-P90
bootstrap prediction band on the history/forecast page. The Phase 9
additions were prioritised after consultation with the project
advisor as the features most likely to differentiate SPIS from a
textbook forecasting demo. Two design-level changes also entered
during this period: the risk-tier thresholds were re-calibrated
from the original `(3, 7, 30)` days to `(7, 14, 90)` days (see
Chapter 4 §4.7.2), and the 30-day forecast loop became recursive
rather than holding lag and rolling features constant (see Chapter 4
§4.7.3). The implementation documented in this chapter therefore
extends the GP1 scope additively; nothing in Chapter 3 is
contradicted, but several modules described here have no
corresponding FR in Chapter 3 because they were added after GP1.

## 5.1 Development Environment

SPIS is built and run under Windows 11 in a Python 3.11.9 virtual environment.
Python 3.11 was chosen deliberately because `scispacy 0.6.x` is not yet
compatible with Python 3.14 (which is installed on the same machine). Cross-team
reproducibility is provided by:

- `requirements.txt` with `>=` pins on every dependency
- A single SQLite database file (`data/inventory.db`) so no external DB engine is
  required
- All artifacts (model, encoder, processed CSVs) rebuildable from `scripts/`

Key dependencies (resolved versions used during defense):

| Package | Version | Role |
|--------|--------|------|
| `pandas` | 2.3.3 | Tabular data, feature engineering |
| `numpy` | 1.26.4 | Numerical ops |
| `scikit-learn` | 1.8.0 | `LabelEncoder`, `TimeSeriesSplit`, `GridSearchCV` |
| `xgboost` | 3.2.0 | Demand forecasting model |
| `statsmodels` | latest | `seasonal_decompose` on the Analytics page |
| `holidays` | 0.35 | Public-holiday calendars |
| `joblib` | 1.3.2 | Model serialisation |
| `flask` | 3.1.3 | REST API |
| `streamlit` | 1.54.0 | Multi-page dashboard |
| `plotly` | 5.x | Interactive charts (Plotly Express + graph_objects) |
| `fpdf2` | 2.7+ | PDF generation for purchase orders and committee handout |
| `pytest` | 9.0.2 | Test runner |

The virtual environment is activated with `.\venv\Scripts\activate`
(PowerShell) or `source venv/Scripts/activate` (bash). VS Code is the team's
editor.

## 5.2 Repository Layout

The repository is one Python package (`spis/`) plus thin launcher scripts. Each
domain (data, models, API, dashboard) is its own subpackage so imports stay
explicit and unit tests can target a single concern.

```
spis-gp2/
  spis/
    data/        catalog.py  database.py  pipeline.py
    models/      forecaster.py  risk_classifier.py  expiry_advisor.py
                 expiry_finance.py  alert_engine.py  decomposition.py
                 inventory_kpi.py  po_generator.py
    api/         app.py  routes.py
    dashboard/   app.py  _shared.py  pages/1..8_*.py
  scripts/       ingest_kaggle.py  ingest_data.py  register_atc.py
                 run_pipeline.py   train_model.py  assess_risk.py
                 run_api.py        run_dashboard.py
                 export_committee_pdf.py  run_public.py
  data/          inventory.db (git-ignored, rebuilt by scripts/ingest_kaggle.py)
                 stock_audit.csv (local audit log, written by add_batch/recall_batch/Page 2)
                 processed/   features_daily.csv  train.csv  test.csv (git-ignored)
  models/        xgboost_forecaster.joblib  label_encoder.joblib
                 metrics.json  feature_importance.json (git-ignored)
  tests/         14 test_*.py files
  docs/          chapter1..7 + this file
```

## 5.3 Data Layer

### 5.3.1 SQLite Schema

`spis/data/database.py` owns the schema. `init_db()` is idempotent and is
called by every CLI before reads, so a fresh checkout can be brought to a
runnable state with a single command. The schema is **eight tables**:

| Table | Purpose |
|-------|---------|
| `atc_categories` | ATC-4 classification reference. Carries `level1_code` and `level2_code` and (after migration) a nullable `supplier_id` FK. |
| `drugs` | Per-SKU catalog: `drug_name` (unique), `atc_code`, `unit`, `is_critical`. 57 drugs seeded across 8 categories. |
| `sales` | Time-series fact table: `atc_code`, `sale_date`, `hour`, `granularity`, `quantity`. Indexed on `(atc_code, sale_date)` and on `granularity`. |
| `atc_inventory` | One row per ATC code: `current_stock`, `last_updated`. The single source of truth for the risk assessor. |
| `inventory_batches` | Per-batch stock with `batch_number`, `quantity`, `unit_cost`, `expiry_date`, `received_date`, plus `applied_discount` and `returned` (added by Phase 9 migration). |
| `alerts` | Notification log: `alert_type` (LOW_STOCK / EXPIRY / RECALL), severity, atc_code, batch_number, `created_at`, `acknowledged_at`. |
| `suppliers` | Directory of distributors with `lead_time_days`. Seeded with four real Saudi-market suppliers — Tamer Group (est. 1922), Banaja Holdings (est. 1948), Cigalah Group, and Jamjoom Pharma (est. 1988) — each routed to the ATC codes that match its known specialty. Contact-detail fields (`email`, `phone`) carry clearly-placeholder values in the seed and are intended to be overridden via the Manage Catalog page before any live order is placed. |
| `purchase_orders` | Sent-PO history: supplier, `total_cost`, `lines_json`, `status`. |

`_migrate_schema()` runs inside `init_db()` and adds the late-Phase columns
(`applied_discount`, `returned`, `atc_categories.supplier_id`) when they are
missing, so older databases keep working after pulling Phase 9.

Two append-only audit trails sit alongside the database. `data/stock_audit.csv`
captures every stock movement (manual edits, batch receipts, recalls) with
`timestamp / atc_code / action / batch_number / old_stock / new_stock / delta`.
The CSV is the only place a non-SQL viewer can read the change history, which
is intentionally separate from the live tables.

### 5.3.2 Database Public Helpers

`database.py` exposes a small, opinionated public surface so neither the
dashboard nor the API needs to write SQL directly:

| Function | Action |
|----------|--------|
| `init_db(path)` | Create / migrate the schema, seed reference data. Idempotent. |
| `update_stock(path, atc, qty)` | Set `atc_inventory.current_stock`; raises on negative input. |
| `load_batches(path)` | Return all batches as dicts (ordered by `expiry_date`). |
| `add_batch(...)` | Insert a new lot, increment `atc_inventory.current_stock`, append a `RECEIVE` row to `stock_audit.csv`. |
| `recall_batch(path, lot, reason)` | Zero a batch's quantity, set `returned=1`, decrement aggregate stock, append a `RECALL` row to the audit log. |
| `save_batch_overrides(path, [{batch_id, applied_discount, returned}])` | Persist pharmacist overrides set in the Expiry Offers data editor. |
| `create_alert / alert_key_exists / acknowledge_alert / get_open_alerts / get_all_alerts` | Alert lifecycle, used by the notification engine. |
| `load_suppliers / add_supplier / assign_supplier_to_atc` | Supplier directory CRUD: list, insert (auto-assigned `supplier_id`, rejects empty / duplicate names and negative lead times), and re-route an ATC code to a different supplier. |
| `save_purchase_order / load_purchase_orders` | PO history persistence. |
| `add_atc_code / add_drug / list_atc_codes / list_drugs` (in `catalog.py`) | Shared between the CLI (`scripts/register_atc.py`) and the Manage Catalog page. |

### 5.3.3 Ingestion Paths

Two paths exist for getting sales data into the database:

1. **`scripts/ingest_kaggle.py`** — bootstrap path. Loads the Kaggle pharmacy
   dataset (four granularities), rebuilds the `sales` fact table, and ensures
   the 8 reference ATC codes are seeded.
2. **`scripts/ingest_data.py`** — pharmacy-agnostic path. Accepts any
   long-format CSV (`date, atc_code, quantity`), normalises columns to
   uppercase / ISO date, clips negatives to zero, aggregates duplicates per
   `(atc_code, date)`, and with `--register` inserts any unseen ATC code into
   `atc_categories` + `atc_inventory`.

```python
# spis/data/pipeline.py — validate()
df["quantity"] = df["quantity"].clip(lower=0)       # negatives become 0
df = df.groupby(["atc_code", "date"], as_index=False)["quantity"].sum()  # dedup
```

## 5.4 Modelling Layer

### 5.4.1 Feature Engineering

`spis/data/pipeline.py::engineer_features()` derives **35 time-series features**
per `(atc_code, date)` row. Lag, rolling, and EMA features are computed
group-wise (`grouped = df.groupby("atc_code")["quantity"]`) so no future
information leaks across ATC codes.

- **12 calendar features**: `day_of_week`, `day_of_month`, `month`, `year`,
  `week_of_year`, `is_weekend`, `is_holiday` (Turkish — the training data is
  the Kaggle Turkish-pharmacy dataset), `season` (1 = Winter … 4 = Fall),
  `is_payday_window` (days 1–3 and 15–17), `is_school_holiday` (Turkish MEB
  calendar), `quarter`, `days_to_month_end`.
- **7 lag features**: `lag_{1, 2, 3, 7, 14, 28, 365}`.
- **12 rolling / EMA features**: `rolling_mean_{7,14,28,90,365}`,
  `rolling_std_{7,28}`, `rolling_{min,max}_7`, `ema_{7,14,28}`.
- **4 derived features**: `lag_ratio_7` (= `lag_1` / `rolling_mean_7`),
  `trend_counter` (days since dataset start), `rolling_range_7`,
  `ema_ratio` (= `ema_7` / `ema_28`).

After the ATC code is encoded with `LabelEncoder` into `atc_encoded`, the
model input matrix is **36 columns** (35 + 1). The `FEATURE_COLS` list in
`spis/models/forecaster.py` is the single source of truth for ordering — both
the pipeline outputs and the live forecaster use the same list.

### 5.4.2 XGBoost Forecaster

`spis/models/forecaster.py` trains a single `XGBRegressor` for all 8 ATC codes
(the `atc_encoded` feature lets one model learn category-specific behaviour
while sharing calendar/lag signal). `train_and_evaluate()` runs `GridSearchCV`
with `TimeSeriesSplit(n_splits=5)` so cross-validation never sees future data.

```python
# spis/models/forecaster.py — actual production grid
param_grid = {
    "n_estimators":     [500, 800],
    "max_depth":        [6, 8],
    "learning_rate":    [0.03, 0.05],
    "subsample":        [0.8, 1.0],
    "colsample_bytree": [0.8, 1.0],
    "min_child_weight": [1, 5],
    "reg_alpha":        [0, 0.1],
}
```

NaN-bearing rows (the first year of history per ATC, where `lag_365` is null)
are **dropped** before training rather than zero-filled — zero-filling would
teach the model that "no recorded sales" looks identical to an actual zero-sales
day. The held-out test set (cutoff 2019-01-01) reports MAE ≈ 1.06, RMSE ≈ 2.29,
soundly beating the naive (`lag_1`) and moving-average (`rolling_mean_7`)
baselines.

Three artifacts are written to `models/`: `xgboost_forecaster.joblib`,
`label_encoder.joblib`, `metrics.json`, and `feature_importance.json`. The
Analytics dashboard page reads both JSON files directly so the team never has
to rebuild charts after a retrain.

### 5.4.3 30-Day Forecast Loop (Recursive)

`risk_classifier.forecast_30_days()` is the live forecasting path. It is
**recursive** by design: each predicted value is appended to a rolling history
buffer (length 365), and the next iteration recomputes lag, rolling, and EMA
features from that buffer. EMAs are updated in place with the textbook
incremental formula:

```
α₇  = 2 / (7  + 1)
α₁₄ = 2 / (14 + 1)
α₂₈ = 2 / (28 + 1)
ema₇  = ema₇  + α₇  · (pred − ema₇)
ema₁₄ = ema₁₄ + α₁₄ · (pred − ema₁₄)
ema₂₈ = ema₂₈ + α₂₈ · (pred − ema₂₈)
```

Every prediction is clipped to `≥ 0` before being appended to the buffer.
`return_daily=True` returns the per-day list (used by Page 1 of the dashboard);
the default `return_daily=False` returns the 30-day sum (used by the risk
classifier).

Holiday context shifts deliberately between training and serving. The
training pipeline tags rows with **Turkish** holidays (because the Kaggle
dataset is Turkish), but `forecast_30_days` tags future dates with
**`holidays.SaudiArabia(...)`** to align with the operational context of the
pilot pharmacy. This is documented inline in the source and is the intended
behaviour.

```python
# spis/models/risk_classifier.py — header of the forecast loop
if atc_code not in encoder.classes_:
    raise ValueError(f"ATC code '{atc_code}' not found in encoder. ...")
tr_holidays = holidays.SaudiArabia(
    years=range(start_date.year, start_date.year + 2)
)
```

### 5.4.4 Risk Classification

`RiskAssessment` is a frozen dataclass — immutable by design so an assessment
captured for one render of the dashboard cannot be mutated by another:

```python
@dataclass(frozen=True)
class RiskAssessment:
    atc_code: str
    current_stock: float
    forecast_30d: float
    daily_demand: float
    days_of_stock: float       # float('inf') when daily_demand == 0
    risk_tier: str             # "CRITICAL" | "LOW" | "OK" | "OVERSTOCK"
    order_qty: float
```

The tier thresholds were calibrated for community-pharmacy lead times (3–7 days
to receive a shipment) — they sit higher than the original Phase 4 sketch and
are now codified as constants:

```python
# spis/models/risk_classifier.py
TIER_CRITICAL = 7.0    # DoS < 7   -> CRITICAL  (stockout within a week)
TIER_LOW      = 14.0   # DoS < 14  -> LOW       (stockout within two weeks)
TIER_OK       = 90.0   # DoS < 90  -> OK        (≤ 3 months of stock)
                        # DoS >= 90 -> OVERSTOCK (more than 3 months)

def classify_risk(days_of_stock):
    if days_of_stock < TIER_CRITICAL: return "CRITICAL"
    if days_of_stock < TIER_LOW:      return "LOW"
    if days_of_stock < TIER_OK:       return "OK"
    return "OVERSTOCK"

def calculate_order_qty(current_stock, forecast_30d, daily_demand, safety_days=3.0):
    safety_buffer = daily_demand * safety_days
    return float(max(0.0, forecast_30d + safety_buffer - current_stock))
```

Zero daily demand is handled by setting `days_of_stock = float('inf')` and
returning `OVERSTOCK` instead of raising — see
`build_risk_assessment()`.

### 5.4.5 Expiry-Aware Discount Advisor

`spis/models/expiry_advisor.py` decides what to do with each batch. The
decision is **two-factor**: time-to-expiry plus the share of the batch that
demand will *not* cover before expiry (`risk_ratio = units_at_risk /
quantity`).

| Days to expiry | Low risk (<0.33) | Medium risk (0.33–0.66) | High risk (>0.66) | Action |
|----------------|------------------|--------------------------|--------------------|--------|
| `> 90`         | — | — | — | `none` (filtered out before reaching the dashboard) |
| `60..90`       | Monitor (0%) | Early Discount 10% | Early Discount 15% | `promote` (or `none` for Monitor) |
| `30..59`       | Special Offer 10% | Special Offer 20% | Special Offer 30% | `promote` |
| `< 30`         | Cannot Dispense (0%) | Cannot Dispense (0%) | Cannot Dispense (0%) | `return_to_supplier` |
| `< 0`          | Expired (0%) | Expired (0%) | Expired (0%) | `write_off` |

The under-30-day "Cannot Dispense" rule is conservative on purpose: GCC/GDP
guidance discourages dispensing stock with less than a month of shelf life
remaining, so anything in that window goes back to the supplier rather than
being clearance-priced. The discount tier function is pure:

```python
def classify_discount(days_to_expiry, risk_ratio=0.5):
    if days_to_expiry < 0:        return (0, "Expired", "write_off")
    if days_to_expiry < 30:       return (0, "Cannot Dispense", "return_to_supplier")
    if days_to_expiry < 60:                                  # Special Offer
        if risk_ratio < 0.33:     return (10, "Special Offer", "promote")
        if risk_ratio <= 0.66:    return (20, "Special Offer", "promote")
        return                       (30, "Special Offer", "promote")
    if days_to_expiry <= 90:                                  # Early Discount
        if risk_ratio < 0.33:     return (0,  "Monitor",        "none")
        if risk_ratio <= 0.66:    return (10, "Early Discount", "promote")
        return                       (15, "Early Discount", "promote")
    return (0, "OK", "none")
```

`assess_batch()` returns `None` for batches more than 90 days from expiry (no
action needed) or with zero units at risk (demand will absorb them before they
expire). `assess_all_batches()` sorts the actionable offers by
`days_to_expiry` ascending so the most urgent appear at the top of the
dashboard table.

### 5.4.6 Financial Aggregations

`spis/models/expiry_finance.py` exposes the four pure functions used by Page 3
to render its KPI strip. All values are in **SAR (Saudi Riyal)**:

| Function | Formula |
|----------|---------|
| `compute_value_at_risk(offers)` | Σ `units_at_risk × unit_cost` over every offer. |
| `compute_recovered(offers, batches)` | Σ `units_at_risk × unit_cost × (1 − discount/100)` over offers that are **not** "Cannot Dispense" or "Expired". Uses the pharmacist's `applied_discount` from `inventory_batches` if it overrides the suggested value. |
| `compute_waste(offers, batches)` | Σ `waste_value` over offers that are irrecoverable (Cannot Dispense / Expired) **or** whose batch is marked `returned=1`. |
| `waste_by_atc(offers)` | Per-ATC waste totals for the red bar chart. |

### 5.4.7 Phase 9 Domain Modules

Each Phase 9 module is pure-Python, unit tested, and consumed by exactly one
dashboard page so the layering stays clean:

| Module | Purpose | Consumer |
|--------|---------|----------|
| `expiry_advisor.py` | Per-batch two-factor discount tier + units-at-risk math. | Page 3 |
| `expiry_finance.py` | SAR aggregations on top of the offer list. | Page 3 |
| `alert_engine.py` | Maps `RiskAssessment` + `ExpiryOffer` to `Alert` rows; idempotent persistence. | Page 6 |
| `decomposition.py` | Wrapper over `statsmodels.seasonal_decompose` (period = 365, additive). Edge NaNs in the trend component are extrapolated, remaining NaNs zeroed. | Page 4 |
| `inventory_kpi.py` | Annual turnover ratio (Slow < 4 ≤ Low < 6 ≤ Healthy ≤ 12 < High ≤ 24 < Excessive). | Overview + Page 4 |
| `po_generator.py` | Builds supplier-grouped POs from CRITICAL/LOW assessments, renders the PDF via `fpdf2`. | Page 8 |

The alert engine has the only mutating call. `refresh()` builds candidate
alerts from the current risk + expiry results and skips inserting any whose
`(alert_type, atc_code, batch_number)` triple already has an open record. The
notification feed therefore stays idempotent across dashboard refreshes:

```python
def refresh(db_path, assessments, offers):
    candidates = alerts_from_risk(assessments) + alerts_from_expiry(offers)
    inserted = 0
    for a in candidates:
        if not alert_key_exists(db_path, a.alert_type, a.atc_code, a.batch_number):
            create_alert(db_path, a.alert_type, a.atc_code,
                         a.batch_number, a.severity, a.message)
            inserted += 1
    return inserted
```

Risk → alert mapping uses `CRITICAL` (LOW_STOCK / CRITICAL severity) and
`LOW` (LOW_STOCK / WARNING) tiers; OK and OVERSTOCK are skipped. Expiry →
alert mapping treats `write_off` as CRITICAL, `return_to_supplier` as
WARNING, and `promote` as WARNING if `days_to_expiry ≤ 30` else INFO.

## 5.5 Streamlit Dashboard

The dashboard is the team's primary user surface. It is **not** a thin client
over the Flask API — it loads the model artifacts and SQLite database directly
from disk via `spis/dashboard/_shared.py`, which keeps every page sub-second
without any network hop. The Flask API (Section 5.6) is a separate, sample
external surface.

### 5.5.1 Page Layout

Streamlit's multi-page convention is used: `app.py` is the entry point and any
file in `spis/dashboard/pages/` shows up automatically in the sidebar in
filename order.

```
spis/dashboard/
  app.py                          Overview — KPI cards, donut, order bar,
                                  risk table, medications table with turnover
  _shared.py                      Path constants, cached loaders, CSS,
                                  missing-artifact guard
  pages/
    1_History_Forecast.py         Plotly history + 30-day forecast + P10–P90
                                  bootstrap band per ATC code
    2_Stock_Update.py             st.form to edit current_stock; writes audit row
    3_Expiry_Offers.py            Financial KPI strip, data_editor for discount
                                  overrides, Gantt-style timeline, waste bar
    4_Analytics.py                Six panels (see 5.5.3 below)
    5_Receive_Stock.py            Receive a new lot OR recall a faulty one;
                                  recent-receipts table; both flows audited
    6_Alerts.py                   Auto-refresh notification feed with ack button
                                  and sidebar severity/type filters
    7_Manage_Catalog.py           ATC overview + add-drug + register-ATC forms,
                                  supplier directory + add-supplier form,
                                  ATC-to-supplier reassignment form
    8_Purchase_Orders.py          Per-supplier expanders, PDF download,
                                  Mark-as-Sent, order history
```

### 5.5.2 How the Frontend Talks to the Models

Every page imports the same helpers from `_shared.py`, which encapsulate the
"how do I get a current view of the system" pattern:

```python
# spis/dashboard/_shared.py (excerpt)
@st.cache_resource
def load_artifacts():
    model, encoder = load_model(MODELS_DIR)
    inventory      = load_atc_inventory(DB_PATH)
    return model, encoder, inventory

@st.cache_data(ttl=300)
def run_assessment(_model, _encoder, _inventory):
    return assess_from_features(
        features_csv=FEATURES_CSV,
        inventory=_inventory,
        model=_model,
        encoder=_encoder,
    )
```

Two caches are used deliberately:

- `@st.cache_resource` is process-lifetime. The XGBoost model and the
  `LabelEncoder` are loaded exactly once per Streamlit process. Because the
  model is read-only after training, sharing it across pages and sessions is
  safe.
- `@st.cache_data(ttl=300)` is value-keyed. The full assessment is recomputed
  at most every five minutes, or immediately when a page calls
  `run_assessment.clear()` (Pages 2 and 5 do this after a stock edit / batch
  receipt so the new numbers appear on the next rerun).

Page 1 (`1_History_Forecast.py`) is the most direct demonstration of how the
frontend consumes the forecaster:

1. User picks an ATC code in a `st.selectbox` and chooses a history window
   (30/60/90/180 days) via `st.select_slider`.
2. The page reads the last N days of history straight from the SQLite `sales`
   table (`pd.read_sql_query`).
3. The cached `model` and `encoder` are passed into
   `forecast_30_days(..., return_daily=True)` to get a 30-element list of
   per-day predictions.
4. Test-set residuals are bootstrapped 500× to produce a **P10–P90 prediction
   band** around the point forecast. This is the only place the dashboard
   shows forecast uncertainty.
5. A Plotly `go.Figure` overlays history (solid blue), the P10–P90 ribbon
   (translucent orange), and the forecast line (dashed orange).

```python
# Page 1 — bootstrap interval
sampled = rng.choice(residuals, size=(n_boot, n_days), replace=True)
sims    = np.clip(forecast[None, :] + sampled, 0.0, None)
lower, upper = np.percentile(sims, 10, axis=0), np.percentile(sims, 90, axis=0)
```

Page 2 (`2_Stock_Update.py`) shows the inverse direction — the frontend
writing back into the SQLite layer:

```python
with st.form("stock_update_form"):
    new_values = { atc: st.number_input(...) for atc in inventory }
    submitted = st.form_submit_button("Save All Changes", type="primary")

if submitted:
    for atc, val in changed.items():
        update_stock(DB_PATH, atc, val)
    _append_audit([...])             # data/stock_audit.csv
    run_assessment.clear()           # so the Overview reflects new values
    st.rerun()
```

Page 6 (`6_Alerts.py`) wires the alert engine into the same loop:

```python
model, encoder, inventory = load_artifacts()
assessments = run_assessment(model, encoder, inventory)
offers      = assess_all_batches(load_batches(DB_PATH),
                                 {ra.atc_code: ra.daily_demand for ra in assessments})
new_count   = refresh(DB_PATH, assessments, offers)  # idempotent insert
if new_count:
    st.toast(f"{new_count} new alert(s) generated.")
```

### 5.5.3 Analytics Page Panels

Page 4 packs six analytical views into one screen:

1. **Model Accuracy** — MAE / RMSE / MAPE metric cards read from
   `models/metrics.json`, with an expandable baseline-comparison table.
2. **XGBoost Feature Importance** — top 20 features as a Plotly Express
   horizontal bar, coloured by importance score. Reads
   `models/feature_importance.json`.
3. **Fast / Medium / Slow Movers (ABC Pareto)** — sorts ATC codes by 30-day
   forecasted demand and computes cumulative share. Cutoffs are 80 %
   ("Fast") and 95 % ("Medium"); everything beyond is "Slow". The class
   labels are intentionally pharmacy-friendly rather than the textbook
   A/B/C letters.
4. **Seasonal Decomposition** — `statsmodels.seasonal_decompose` with
   `period=365` rendered as three stacked subplots (trend / seasonal /
   residual) for the selected ATC code.
5. **Year-over-Year Demand Growth** — bar chart comparing the most recent
   365-day total against the prior 365-day total, green for growing demand,
   red for declining.
6. **12-Month Rolling Demand Trend** — a 90-day rolling mean per ATC across
   the last year, plotted on one shared axis with a multi-select.

The page also closes with the **Inventory Turnover Ratio** strip and table
fed by `inventory_kpi.compute_turnover()`.

### 5.5.4 Expiry Offers Page Mechanics

Page 3 is the most stateful page after the alert centre. The user gets:

- A four-metric SAR KPI strip (Value at Risk, Projected Recovery, Written
  Off, Waste Rate).
- A red bar chart of waste-by-ATC sorted descending.
- A radio filter (`All` / `Urgent <30 days` / `Upcoming 30–90 days`).
- A `st.data_editor` with editable **Applied Discount %** and **Return to
  Supplier** columns. On confirm, edits go through `save_batch_overrides()`
  in `database.py`, which updates `applied_discount`, sets `returned`, and
  zeros the batch quantity when the return flag is on.
- A Gantt-style horizontal bar timeline coloured by urgency tier.

### 5.5.5 Receive Stock and Recall

Page 5 has two forms:

- **Receive New Batch** — calls `database.add_batch(...)`, which inserts the
  row, increments `atc_inventory.current_stock`, and appends a `RECEIVE`
  audit line. A helper auto-suggests the next `LOT-YYYY-NNN` number.
- **Recall a Batch** — calls `database.recall_batch(...)`, which zeros the
  batch quantity, sets `returned=1`, decrements stock with a `MAX(0, ...)`
  guard, and appends a `RECALL` audit line. The original notes string is
  preserved with a `RECALLED <ISO-timestamp>: <reason>` suffix.

Both flows invalidate the relevant caches (`run_assessment.clear()` and the
local `_load_batches_cached.clear()`) so other pages see the new state on
their next render.

### 5.5.6 Manage Catalog — Drugs, ATC Codes, and Suppliers

Page 7 (`7_Manage_Catalog.py`) is the only page that does not require model
artifacts — it operates purely against the SQLite database. It is laid out
as five vertically-stacked sections:

- **A. ATC Categories** — read-only table with drug counts and current
  stock per ATC code.
- **B. Add Drug** — form that calls `catalog.add_drug()`. Rejects empty
  names and unknown ATC codes via `ValueError` raised by the helper.
- **C. Add ATC Code** — form that calls `catalog.add_atc_code()`. Warns
  that sales history and a retrain are still required before the
  forecaster can serve the new code.
- **D. Suppliers** — read-only directory table plus an **Add Supplier**
  form bound to `database.add_supplier()`. The supplier_id is
  auto-assigned by SQLite, names are unique, and negative lead times are
  rejected. Tamer Group / Banaja Holdings / Cigalah Group / Jamjoom
  Pharma are visible here on a fresh install and are themselves editable
  data (no code change needed to add a fifth supplier or rename one of
  the seeds).
- **E. Assign ATC Code to Supplier** — selectbox-driven form bound to
  `database.assign_supplier_to_atc()`. The pharmacist picks an ATC code
  and a supplier; the change takes effect on the next render of Page 8.

This means the entire supplier directory and routing logic is operator-
editable through the dashboard — no Python edits, no SQL, no
redeployment.

### 5.5.7 Missing-Artifact Guard

Every page calls `check_required_files()` after `inject_css()`. If any of
`xgboost_forecaster.joblib`, `label_encoder.joblib`, `inventory.db`, or
`features_daily.csv` are absent, the page prints a clear error and calls
`st.stop()` instead of throwing a stack trace at the user. Page 7 (Manage
Catalog) only requires the database, so it relaxes the guard accordingly.

## 5.6 REST API (Sample External Interface)

The dashboard reads model artifacts directly, but a separate Flask app
(`spis/api/`) is provided as the sample interface for any non-Streamlit
consumer (a future POS integration, a mobile front-end, or a curl test from
the committee). It is intentionally minimal — three endpoints, no auth,
in-memory model — so the surface area stays small enough to test exhaustively.

```python
# spis/api/app.py
def create_app(config=None):
    app = Flask(__name__)
    app.config.update(_DEFAULTS)
    if config: app.config.update(config)

    models_dir = Path(app.config["MODELS_DIR"])
    if (models_dir / "xgboost_forecaster.joblib").exists() and \
       (models_dir / "label_encoder.joblib").exists():
        model, encoder = load_model(models_dir)
        app.config["_MODEL"]   = model
        app.config["_ENCODER"] = encoder
    else:
        app.config["_MODEL"] = app.config["_ENCODER"] = None
    register_routes(app)
    return app
```

The factory pattern enables tests to spin up an isolated app with a
`tmp_path`-backed `MODELS_DIR`, and the eager load means a misconfigured
deployment fails at startup rather than on the first inbound request.

| Method | Path | Behaviour |
|--------|------|-----------|
| `GET` | `/health` | Liveness; always `200` with `{status, version}`. |
| `GET` | `/api/v1/risk` | Full risk assessment for every ATC code in the inventory. `503` if model not loaded. `days_of_stock == inf` is serialised as JSON `null` via `_ra_to_dict`. |
| `GET` | `/api/v1/forecast/<atc_code>` | 30-day forecast for one code; `404` if `atc_code` is not in `encoder.classes_`; `503` if model not loaded. |

```python
# spis/api/routes.py — null-safe serialisation
def _ra_to_dict(ra):
    d = dataclasses.asdict(ra)
    if d.get("days_of_stock") == float("inf"):
        d["days_of_stock"] = None
    return d
```

`scripts/run_api.py` is the launcher; it accepts `--host`, `--port`,
`--debug`, `--db`, `--features`, `--models`, and `--safety-days` flags and
prints a startup warning when the model artifacts are missing.

## 5.7 CLI Scripts

Every long-running operation has a one-line launcher in `scripts/` so neither
the team nor the committee needs to remember module paths.

| Script | Purpose |
|--------|---------|
| `ingest_kaggle.py` | Rebuild the database from the original Kaggle dataset. |
| `ingest_data.py` | Append a new pharmacy's CSV (long format). |
| `register_atc.py` | Manually register an ATC code (or `--list` all). |
| `run_pipeline.py` | Produce `features_daily.csv`, `train.csv`, `test.csv`. |
| `train_model.py` | Run GridSearchCV and persist model + encoder + metrics + feature importance. |
| `assess_risk.py` | One-shot CLI risk assessment → CSV. |
| `run_api.py` | Start the Flask REST server. |
| `run_dashboard.py` | Start Streamlit on a chosen port. |
| `export_committee_pdf.py` | Render the committee one-pager via fpdf2. |
| `run_public.py` | Launch dashboard bound to `0.0.0.0` for the lab demo. |

The intended onboarding sequence for a new pharmacy is:

```
register_atc.py  →  ingest_data.py  →  run_pipeline.py  →  train_model.py
```

---

## 5.8 Deployment

This section describes how the system is deployed on a single host.
SPIS is intentionally single-host: the dashboard, the model artifacts,
and the SQLite database all live on the same machine, which keeps
infrastructure cost at zero and removes any network dependency for the
forecasting and risk-classification path.

### 5.8.1 Hardware requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | Dual-core x86_64 @ 2.0 GHz | Quad-core x86_64 @ 2.5 GHz or Apple Silicon |
| RAM | 4 GB | 8 GB |
| Disk | 1 GB free (for repo, virtual environment, model artifacts, SQLite DB) | 5 GB free |
| GPU | Not required | Not required (XGBoost trains on CPU; LSTM was rejected partly to avoid GPU dependency) |
| OS | Windows 10 / 11, macOS 12+, or Linux (Ubuntu 20.04+) | Same |
| Python | 3.11.x (3.14 incompatible with `scispacy`) | 3.11.9 |
| Network | None required at runtime | LAN access if the dashboard is exposed via `run_public.py` |

### 5.8.2 Installation

The full installation procedure is:

```bash
# 1. Clone the repository
git clone https://github.com/HotSalsa10/spis-gp2.git
cd spis-gp2

# 2. Create and activate a Python 3.11 virtual environment
py -3.11 -m venv venv               # Windows
# python3.11 -m venv venv           # macOS / Linux

# Activate
.\venv\Scripts\activate             # Windows PowerShell
# source venv/bin/activate          # macOS / Linux

# 3. Install dependencies (single requirements file)
pip install --upgrade pip
pip install -r requirements.txt

# 4. Build the database, run the pipeline, and train the model
python scripts/ingest_kaggle.py
python scripts/run_pipeline.py
python scripts/train_model.py

# 5. Launch the dashboard
streamlit run spis/dashboard/app.py
#  - or -
python scripts/run_dashboard.py --port 8501
```

The dashboard then opens on `http://localhost:8501`. To expose it on the
local network (for the committee demo), `python scripts/run_public.py`
binds the same Streamlit app to `0.0.0.0`.

### 5.8.3 Python packages

All runtime dependencies are declared in a single `requirements.txt`
with minimum-version pins (per NFR-5.3). Resolved versions on the
reference development machine are:

| Package | Version | Purpose |
|---|---|---|
| `pandas` | ≥ 2.3 | Data manipulation; long-format ingestion |
| `numpy` | ≥ 1.26, < 2 | Numerical primitives (pinned below 2.0 for `scispacy` compatibility) |
| `scikit-learn` | ≥ 1.8 | `LabelEncoder`, `TimeSeriesSplit`, `GridSearchCV`, metrics |
| `xgboost` | ≥ 3.2 | Demand forecaster (`XGBRegressor`) |
| `joblib` | ≥ 1.5 | Model artifact serialisation |
| `flask` | ≥ 3.1 | REST API (read-only) |
| `streamlit` | ≥ 1.54 | Multi-page dashboard |
| `plotly` | ≥ 5.0 | History/forecast/feature-importance charts |
| `fpdf2` | ≥ 2.7 | Committee one-pager and supplier-grouped PO PDFs |
| `holidays` | ≥ 0.50 | Saudi Arabia / Turkey calendar feature engineering |
| `spacy`, `scispacy` | (declared, unused) | Reserved for the future drug-name NLP search |
| `pytest` | ≥ 9.0 | Test runner (182 tests) |

### 5.8.4 Startup commands (summary)

| Component | Command |
|---|---|
| Dashboard | `streamlit run spis/dashboard/app.py` |
| Dashboard (LAN) | `python scripts/run_public.py` |
| REST API | `python scripts/run_api.py --port 5000` |
| Pipeline rebuild | `python scripts/run_pipeline.py` |
| Re-train model | `python scripts/train_model.py` |
| One-shot risk CSV | `python scripts/assess_risk.py` |
| Run full test suite | `pytest -q` |

### 5.8.5 Runtime artifact layout

```
spis-gp2/
├── data/
│   ├── raw/                   # Kaggle source CSVs
│   ├── processed/             # features_daily.csv, train.csv, test.csv
│   └── inventory.db           # SQLite — git-ignored, rebuilt by ingest
├── models/                    # xgboost_forecaster.joblib, label_encoder.joblib,
│                              # metrics.json, feature_importance.json
├── spis/                      # Python package (api, dashboard, data, models)
├── scripts/                   # CLI launchers
└── tests/                     # pytest suite (182 tests across 14 files)
```

The dashboard's missing-artifact guard (`_shared.check_required_files`)
inspects `models/` at startup. If any required file is absent, the UI
displays an explicit error listing the missing files and the command
required to regenerate them, rather than silently failing.

---

## 5.9 Security

Security was treated as an explicit design topic even though the GP2
scope does not require a production-grade hardening pass. The
single-host deployment model and the read-only public surface keep the
attack surface small, and the items below describe both what the
implementation does today and what a production-grade deployment
would add. These mirror the security checklist in standard university
secure-coding guidelines [Ch3, NFR-2; references_master.md, entry 22].

### 5.9.1 Threat model (in scope vs. out of scope)

| Asset | Threat | Current control | Production control (future work) |
|---|---|---|---|
| `inventory.db` | Tampering with stock or sales | Filesystem-only access on the host; SQLite WAL not exposed over network | Encrypted disk; row-level audit log; signed snapshots |
| Model artifacts (`.joblib`) | Replacement with a malicious pickle | Artifacts are local-only and regenerable from raw data | Code-signed artifacts; SHA-256 checksum manifest |
| Flask REST API | Unauthorised reads | API is read-only and bound to `localhost` by default | Bearer-token auth on every endpoint; HTTPS via reverse proxy |
| Dashboard writes | Unauthorised stock edits | Single-host trust boundary — only LAN users with the URL can write | Streamlit's `experimental_user` + RBAC (see 5.9.4) |
| User credentials | Credential theft | Not stored — no auth layer in GP2 scope | Argon2id-hashed password store (see 5.9.2) |

### 5.9.2 Password hashing (planned)

A production deployment would store passwords using **Argon2id** via
the `argon2-cffi` library — the OWASP-recommended modern hash with
memory-hard parameters. The reasons Argon2id was chosen over MD5,
SHA-256, and bcrypt are:

- MD5 and unsalted SHA-256 are vulnerable to GPU-accelerated rainbow
  table attacks and are explicitly deprecated by NIST SP 800-63B.
- bcrypt remains acceptable but is CPU-only and has a 72-byte input
  limit; Argon2id is the explicit winner of the Password Hashing
  Competition (2015) and is memory-hard.

Pseudocode:

```python
from argon2 import PasswordHasher

ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
hash_str = ph.hash(plain_password)        # store this
ph.verify(hash_str, candidate_password)   # raises VerifyMismatchError on bad password
```

The schema would add a `users(id, username, password_hash, role,
created_at)` table; `password_hash` would store the full Argon2id
output (algorithm identifier + salt + parameters + digest in a single
string).

### 5.9.3 Session management (planned)

For Streamlit, session management is currently implicit (the dashboard
trusts whoever can reach the port). A production version would use
**signed, time-limited session tokens**:

- On login, the server issues a JSON Web Token (JWT) signed with a
  server-side secret, with `exp` set to 30 minutes and a refresh
  token valid for 8 hours.
- The token is stored in an HTTP-only, `SameSite=Strict` cookie to
  prevent XSS theft and CSRF replay.
- All dashboard pages would call a `require_session()` helper at the
  top of the page; tokens are revoked on logout (via a server-side
  blocklist of refresh-token JTIs).

### 5.9.4 Role-based access control (planned)

Three roles are sufficient to cover the use cases identified in Ch3:

| Role | Read | Write (stock / batch / alert ack) | Manage catalog | Export PO PDFs |
|---|---|---|---|---|
| `viewer` (clinical pharmacist) | ✓ | — | — | — |
| `operator` (storekeeper) | ✓ | ✓ | — | ✓ |
| `manager` (pharmacy manager) | ✓ | ✓ | ✓ | ✓ |

A `require_role(role)` decorator on every Streamlit page and Flask
route would enforce this. The role would be stamped into the JWT at
login time so that a downgraded user cannot re-elevate without
re-authenticating.

### 5.9.5 Secure API routes (planned)

The Flask REST API currently exposes three read-only endpoints
(`/health`, `/api/v1/risk`, `/api/v1/forecast/<atc_code>`). A
production deployment would harden the API as follows:

- **TLS**: terminate HTTPS at a reverse proxy (nginx or Caddy) and
  redirect all plain HTTP to HTTPS.
- **Authentication**: require a Bearer token on every non-`/health`
  endpoint; validate against the JWT issued by the dashboard login.
- **Rate limiting**: apply per-token rate limits (e.g. 60 req/min) via
  `flask-limiter` to blunt scraping and accidental denial-of-service.
- **Input validation**: ATC codes are already validated against
  `encoder.classes_` (returning HTTP 404 for unknown codes); future
  write endpoints (`POST /api/v1/stock`, `POST /api/v1/batches`) would
  add JSON-schema validation via `marshmallow` or `pydantic` to reject
  malformed payloads before they touch the database.
- **CORS**: restrict `Access-Control-Allow-Origin` to the dashboard
  origin only.
- **Error responses**: never leak stack traces; the existing 503/404
  responses are already structured JSON with no implementation detail.

### 5.9.6 Defensive practices already in place

The following controls are already implemented in GP2 and would carry
forward to a production deployment without change:

- **Parameterised SQL**: every `INSERT` / `UPDATE` / `SELECT` in
  `spis/data/database.py` uses `?` placeholders, so the codebase is
  free of string-concatenated queries (no SQL-injection surface).
- **Read-only public API**: the Flask app exposes no write endpoints,
  removing every server-side mutation as an attack vector.
- **Fail-fast on missing artifacts**: the dashboard and the API both
  return a deliberate error rather than a silent fallback when model
  artifacts are absent, preventing serving stale or empty predictions.
- **Local-only SQLite**: the database file is not network-mountable
  and is excluded from the Git history (`.gitignore`) to prevent
  accidental publication of pharmacy data.
- **Pinned dependencies**: `requirements.txt` uses minimum-version
  pins so the build is reproducible; supply-chain integrity would be
  hardened in production by adding hash-pinning (`pip install
  --require-hashes`).

---

# Chapter 6: Testing

## 6.1 Testing Strategy

The team applies a three-layer strategy across every phase:

- **Unit tests** exercise pure functions in isolation with synthetic fixtures —
  tier classification, order-quantity arithmetic, expiry-discount mapping,
  feature counts, ATC-level inference.
- **Integration tests** exercise multi-module flows against temporary SQLite
  databases and the Flask test client. The pipeline ingest, the API endpoints,
  the alert engine's idempotency, and the PO generator's PDF output are all
  validated this way.
- **Manual UI testing** is performed locally with `python scripts/run_dashboard.py`.
  The team verifies tier colours, cache invalidation after a stock edit, batch
  receipts, recalls, and alert acknowledgement on every page before each
  milestone.

The runner is **pytest 9.0.2**. Fixtures live next to their test files (no
global `conftest.py`), so test ownership is local and the dependency graph
between tests is obvious. Slow fixtures (a tiny `XGBRegressor` with
`n_estimators=10`) are widened to session scope where it is safe to do so.
Every test is deterministic — random seeds are fixed, dates are pinned, and
SQLite paths are created in `tmp_path` so no test sees another test's data.

## 6.2 Test Suite

The Phase 9 enhancements grew the suite to **182 tests across 14 files**
(counted by AST over all `test_*.py` modules). All pass on the current
codebase (`venv/Scripts/python -m pytest -q` → `182 passed`). The
breakdown is:

| Module / Feature | Test file | Tests | Focus |
|------------------|-----------|-------|-------|
| Data pipeline | `test_pipeline.py` | 7 | Feature count, lag/rolling math, validate / dedupe / clip, train/test cutoff |
| Forecaster | `test_forecaster.py` | 8 | Baselines, ATC encoding, GridSearchCV, model save/load, evaluate metrics |
| Risk classifier | `test_risk_classifier.py` | 19 | DoS formula, all four tier boundaries, order qty, recursive 30-day loop, unknown-ATC raises, `load_atc_inventory` |
| Expiry advisor | `test_expiry_advisor.py` | 22 | Two-factor discount mapping (every quadrant), `units_at_risk`, `assess_batch` None-return paths, ordering |
| Expiry finance | `test_expiry_finance.py` | 13 | Value-at-risk, recovered revenue with overrides, write-off totals, per-ATC waste aggregation |
| Alert engine | `test_alert_engine.py` | 15 | Risk → alert mapping, expiry → alert mapping, severity assignment, idempotent refresh, acknowledge / get_all |
| Decomposition | `test_decomposition.py` | 5 | Output shape, NaN handling, short-series guard, period validation |
| Inventory KPI | `test_inventory_kpi.py` | 5 | Turnover formula, classification thresholds, zero-inventory guard |
| PO generator | `test_po_generator.py` | 14 | Supplier grouping, line totals, default-cost fallback, PDF bytes header, empty-input case |
| Database schema | `test_database.py` | 29 | Schema creation, seed row counts, idempotency, `inventory_batches` seed, `update_stock`, `add_batch` (7 paths including past-expiry warn), `recall_batch` (happy / unknown / idempotent), suppliers seed and ATC→supplier link, `add_supplier` (happy / empty / duplicate / negative-lead-time), `assign_supplier_to_atc` (happy / unknown-ATC / unknown-supplier) |
| Catalog helpers | `test_catalog.py` | 10 | `add_drug`, `add_atc_code`, duplicate / empty / unknown-FK guards |
| Flask API | `test_api.py` | 18 | All endpoints + 200 / 404 / 503 paths |
| Data ingestion | `test_ingest_data.py` | 11 | CSV normalisation, negative clipping, dedup, custom columns, auto-register |
| ATC registration | `test_register_atc.py` | 6 | Level inference, hierarchical validation |
| **Total** | | **182** | |

Coverage target is **80% on critical paths**. The forecaster, risk classifier,
expiry advisor, alert engine, and API routes each measure above 90 % line
coverage when running `pytest --cov=spis`. Uncovered lines are logging /
print statements and exception branches reached only on file-I/O failures.

## 6.3 Representative Unit Tests

### 6.3.1 Tier Boundaries

The four tier thresholds are tested at and immediately below their boundary
values. The current `TIER_CRITICAL / TIER_LOW / TIER_OK` constants are
asserted explicitly so that any future tuning forces a deliberate test
update:

```python
# tests/test_risk_classifier.py
def test_classify_risk_uses_constants():
    assert TIER_CRITICAL == 7.0
    assert TIER_LOW      == 14.0
    assert TIER_OK       == 90.0

def test_classify_risk_critical():
    assert classify_risk(0.0) == "CRITICAL"
    assert classify_risk(TIER_CRITICAL - 0.001) == "CRITICAL"

def test_classify_risk_low():
    assert classify_risk(TIER_CRITICAL)        == "LOW"
    assert classify_risk(TIER_LOW - 0.001)     == "LOW"

def test_classify_risk_ok():
    assert classify_risk(TIER_LOW)             == "OK"
    assert classify_risk(TIER_OK - 0.001)      == "OK"

def test_classify_risk_overstock():
    assert classify_risk(TIER_OK)              == "OVERSTOCK"
    assert classify_risk(1000.0)               == "OVERSTOCK"
```

### 6.3.2 Order Quantity Includes Safety Buffer

```python
def test_calculate_order_qty_includes_safety_buffer():
    no_buf   = calculate_order_qty(0.0, 100.0, 5.0, safety_days=0.0)
    with_buf = calculate_order_qty(0.0, 100.0, 5.0, safety_days=3.0)
    assert with_buf - no_buf == 15.0   # 5 units/day × 3 days
```

### 6.3.3 Expiry Discount Mapping

`test_expiry_advisor.py` covers every quadrant of the two-factor
(days × risk) matrix. Excerpts:

```python
def test_classify_discount_expired():
    pct, label, action = classify_discount(-1)
    assert (pct, label, action) == (0, "Expired", "write_off")

def test_classify_discount_cannot_dispense():
    pct, label, action = classify_discount(20)            # <30 days
    assert (pct, label, action) == (0, "Cannot Dispense", "return_to_supplier")

def test_classify_discount_no_action():
    pct, label, action = classify_discount(91)            # >90 days
    assert (pct, label, action) == (0, "OK", "none")
```

### 6.3.4 Feature Count Invariant

The pipeline must produce exactly 35 engineered features (plus the 3 original
columns). A test for this number means a future contributor adding a feature
cannot silently drift the model input matrix:

```python
def test_engineer_features_columns(small_daily_df):
    out = engineer_features(small_daily_df)
    assert len(out.columns) == 38     # 3 original + 35 features
    for f in ["ema_14", "lag_365", "season", "ema_ratio"]:
        assert f in out.columns
```

## 6.4 Integration Tests

### 6.4.1 Flask API via Test Client

`test_api.py` uses Flask's in-process test client; no socket is opened, so the
suite stays fast and CI-friendly. Each test runs against a fresh
`tmp_path`-rooted artifact directory built from a tiny in-memory XGBoost model
(`n_estimators=10`):

```python
def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json["status"] == "ok"

def test_risk_assessment_no_model(client_no_model):
    r = client_no_model.get("/api/v1/risk")
    assert r.status_code == 503
    assert "Model artifacts not loaded" in r.json["error"]

def test_forecast_unknown_atc(client):
    r = client.get("/api/v1/forecast/UNKNOWN")
    assert r.status_code == 404
```

### 6.4.2 Pipeline Train/Test Isolation

```python
def test_split_no_leakage():
    df = load_and_engineer(cutoff="2018-07-01")
    train, test = split_train_test(df, cutoff="2018-07-01")
    cutoff_dt = pd.Timestamp("2018-07-01")
    assert (train["date"] <  cutoff_dt).all()
    assert (test["date"]  >= cutoff_dt).all()
```

### 6.4.3 Alert Engine Idempotency

The alert engine has the subtlest integration behaviour because it writes to
disk. The corresponding test seeds CRITICAL/LOW assessments and expiry
offers, runs `refresh` once to populate the table, then asserts a second
call inserts zero new rows:

```python
def test_refresh_is_idempotent(tmp_db):
    inserted_first  = refresh(tmp_db, assessments=[critical_ra], offers=[])
    inserted_second = refresh(tmp_db, assessments=[critical_ra], offers=[])
    assert inserted_first  > 0
    assert inserted_second == 0
```

`alert_key_exists` is the underlying guard — same triple
`(alert_type, atc_code, batch_number)` with `acknowledged_at IS NULL`
counts as a duplicate.

### 6.4.4 Database Write Paths

`test_database.py` covers the three mutating helpers end-to-end against a
`tmp_path` SQLite database:

- `update_stock` — rejects negatives, updates `current_stock`, bumps
  `last_updated`.
- `add_batch` — inserts row, raises on duplicate `batch_number`, raises on
  invalid date / negative quantity, warns on past expiry, increments
  `atc_inventory.current_stock`.
- `recall_batch` — zeros the batch, sets `returned=1`, decrements aggregate
  stock with the `MAX(0, ...)` floor, appends a recall suffix to the
  `notes` column.

## 6.5 Error-Handling Tests

| ID | Scenario | Expected Behaviour |
|----|----------|--------------------|
| EH-001 | Negative quantity in ingest CSV | Clipped to 0.0 |
| EH-002 | Duplicate `(atc_code, date)` | Aggregated by `groupby().sum()` |
| EH-003 | Forecast for unknown ATC | API returns 404; `forecast_30_days` raises `ValueError` |
| EH-004 | Model artifacts missing | API returns 503 on `/risk` and `/forecast` |
| EH-005 | Zero daily demand | `days_of_stock == inf` → tier `OVERSTOCK`, `order_qty == 0` |
| EH-006 | First 7 days of an ATC's history (NaN `lag_7`) | Dropped in `split_train_test` |
| EH-007 | `forecast_30_days` on unknown ATC | `ValueError` with message |
| EH-008 | XGBoost returns small negative float | Clipped to 0.0 before being appended to the rolling history |
| EH-009 | Duplicate alert re-emitted | `alert_engine.refresh` skips it (idempotent) |
| EH-010 | Recall on unknown batch | `recall_batch` raises `ValueError` |
| EH-011 | `add_batch` with duplicate lot | Raises `ValueError("Batch number already exists: ...")` |
| EH-012 | Inventory turnover with zero current_stock | Reports `turnover == 0.0`, classification "Slow" |

## 6.6 Defects Found During Development

Selected defects, all fixed before the corresponding phase closed. Every fix
is accompanied by a regression test:

| Defect | Module | Fix |
|--------|--------|-----|
| `days_of_stock = inf` serialised as `"Infinity"` and broke JSON parsers | `api/routes.py` | `_ra_to_dict` replaces with `None` |
| Forecast loop held lag/rolling features constant, producing flat 30-day predictions | `risk_classifier.py` | Switched to recursive: append each prediction to a 365-day history buffer, recompute lag/rolling/EMA before the next step |
| Negative quantities in raw CSV reached the model | `pipeline.py` | `.clip(lower=0)` + EH-001 test |
| First 7 days of each ATC had NaN `lag_7`, crashed the train split | `pipeline.py` | `dropna(subset=["lag_7"])` in `split_train_test` |
| Tiny negative XGBoost predictions polluted the rolling history | `risk_classifier.py` | `max(0.0, pred)` per day before appending |
| Alerts duplicated on every dashboard refresh | `alert_engine.py` | `alert_key_exists` check + EH-009 test |
| `inventory_batches` lacked pharmacist-override columns; Page 3 edits had nowhere to land | `database.py` | `_migrate_schema` adds `applied_discount` and `returned` if missing |
| PO PDF crashed on non-Latin characters (e.g. supplier names with accents) | `po_generator.py` | `_safe()` encodes to latin-1 with `errors="replace"` before every `pdf.cell` call |
| Forecasting used Turkish holidays at serve time even though the pilot pharmacy is in Saudi | `risk_classifier.py` | Switched the live forecast loop to `holidays.SaudiArabia(...)`; training pipeline kept on `holidays.Turkey(...)` because the dataset itself is Turkish |

## 6.7 Test Infrastructure

- Fixtures live next to their test files; no global `conftest.py` so test
  ownership is local and the dependency graph between tests is obvious.
- The Flask API tests use a fresh `tmp_path` per test and never reuse the
  on-disk database used by the dashboard.
- A small `tiny_model` fixture (`n_estimators=10`) keeps the forecaster tests
  under a second total — anything larger lives in `scripts/train_model.py`,
  which is invoked manually.

Running the full suite locally:

```
py -3.11 -m pytest -q
```

Typical wall-clock time on a developer laptop is ~15 s. There are no
intermittent failures across the three independent runs performed for the
committee dossier.

---

# Chapter 7: Conclusion and Future Work

## 7.1 Summary

SPIS started as an empty repository in early Phase 1 and is, at the end of
Phase 9, a complete inventory-intelligence application:

- A reproducible SQLite database with eight tables, seeded from a real Kaggle
  pharmacy dataset (424,080 sales transactions over six years across eight
  ATC categories) and extended with batch-level expiry tracking, a directory
  of four real Saudi-market suppliers (Tamer Group, Banaja Holdings,
  Cigalah Group, Jamjoom Pharma) routable per-ATC, purchase-order history,
  and a notification log.
- A 35-feature time-series pipeline that splits cleanly along a 2019-01-01
  cutoff into 14,544 train rows and 2,248 test rows.
- A single XGBoost regressor — tuned with `TimeSeriesSplit` cross-validation
  across the production grid — that beats the moving-average baseline by ~3×
  on MAE (≈ 1.06 vs ≈ 2.89) and the naive baseline by ~4×.
- A four-tier risk classifier (`CRITICAL < 7d`, `LOW < 14d`, `OK < 90d`,
  `OVERSTOCK ≥ 90d`) calibrated for community-pharmacy lead times, with a
  deterministic order-quantity formula and a configurable safety buffer.
- A multi-page Streamlit dashboard (Overview plus eight pages) that reads
  model artifacts directly and ships with interactive history+forecast
  charts with P10–P90 bootstrap bands, in-app stock editing, batch receipt
  and recall, two-factor expiry-aware discount suggestions in SAR, a
  notification feed with sidebar filters, catalog management, an Analytics
  page with six panels (model accuracy, feature importance, ABC Pareto,
  seasonal decomposition, YoY growth, rolling trend) and a turnover KPI
  strip, and one-click supplier PO PDFs.
- A separate, well-tested Flask API as a sample external integration surface.
- A test suite of **182 tests** across 14 files, all passing, with 80%+
  coverage on every critical path.
- An IEEE-referenced graduation report (this document plus chapters 1–4).

## 7.2 Evaluation Against Objectives

| Objective (Chapter 1) | Implementation | Outcome |
|-----------------------|----------------|---------|
| Reproducible pharmacy database | `spis/data/database.py` with idempotent `init_db()` + `_migrate_schema()` | Achieved |
| End-to-end feature pipeline | `spis/data/pipeline.py`; 35 features, group-wise no-leak | Achieved |
| Demand forecaster | `spis/models/forecaster.py`; MAE ≈ 1.06, RMSE ≈ 2.29 | Achieved |
| Risk classification | `spis/models/risk_classifier.py`; four tiers (7 / 14 / 90 day boundaries) + order qty | Achieved |
| REST surface | `spis/api/`; 3 endpoints, 18 tests | Achieved |
| Interactive dashboard | `spis/dashboard/`; Overview + 8 pages incl. supplier management on Page 7 | Achieved |
| Expiry-aware discount system | `expiry_advisor.py`, `expiry_finance.py`, Page 3 | Achieved |
| Notifications | `alert_engine.py`, `alerts` table, Page 6 | Achieved |
| Operational PO output | `po_generator.py`, Page 8, fpdf2 PDFs in SAR | Achieved |
| Batch receipt & recall | `database.add_batch / recall_batch`, Page 5, stock_audit.csv | Achieved |
| Generalisable ingestion | `scripts/ingest_data.py`, `scripts/register_atc.py`, `catalog.py` | Achieved |
| Coverage ≥ 80% on critical paths | pytest + coverage gate | Achieved |

## 7.3 Evaluation Against Requirements

Every functional requirement (FR-1 … FR-6 in Chapter 3) is exercised by at
least one automated test, and the Phase 9 enhancements introduced four
additional behavioural requirements (expiry handling, alert idempotency,
turnover classification, supplier PO export) each backed by a dedicated test
file.

Non-functional requirements:

- **NFR-1 Performance**: full pipeline run on 16,848 daily rows completes in
  < 3 s on a developer laptop. Per-ATC 30-day forecast (30 XGBoost predictions
  plus per-day feature regeneration) finishes in under 500 ms.
- **NFR-2 Reliability**: 182 tests, 100 % pass rate, no flaky tests across
  three independent runs.
- **NFR-3 Scalability**: ingestion path is pharmacy-agnostic. Any new
  pharmacy can register N ATC codes through `register_atc.py` or the Manage
  Catalog page, feed CSVs through `ingest_data.py`, and retrain with a
  single `train_model.py` invocation.

## 7.4 Limitations

The limitations below are stated explicitly to scope the conclusions of
this report and to motivate the priorities in §7.5.

1. **Use of a public dataset.** Training and evaluation used a public
   Kaggle pharmaceutical sales dataset (424,080 transactions, 2014–2019,
   8 ATC categories) rather than data from an operational pharmacy
   partner. Public datasets capture aggregate sales behaviour but lack
   the prescription-level metadata, supplier records, and stock-movement
   logs that a live deployment would generate. Reported model accuracy
   therefore generalises to the dataset's characteristics, not to a
   specific pharmacy.

2. **Absence of real pharmacy integration.** The system has no live
   connection to a Point-of-Sale (POS) terminal, an Electronic Health
   Record (EHR), a supplier ordering portal, or a barcode/stock scanner.
   Sales are imported via CSV (`scripts/ingest_data.py`); stock updates
   are entered manually through the dashboard; the Flask REST API is
   intentionally read-only and does not push purchase orders or write
   back to any external system. SPIS therefore operates as a
   decision-support tool, not as an integrated procurement loop.

3. **Single-pharmacy limitation.** The forecaster was trained on one
   pharmacy's history. Seasonality and calendar effects are validated
   for that context only; the live forecast loop swaps in Saudi public
   holidays to align with the pilot site, but cross-pharmacy
   validation is required before commercial deployment. Risk-tier
   thresholds (`7 / 14 / 90` days) were calibrated against the seeded
   supplier lead times of this dataset and would need site-specific
   re-tuning.

4. **Lack of real-time forecasting.** Forecasts are produced in a batch
   off-line workflow: the user re-runs the pipeline
   (`run_pipeline.py` → `train_model.py`) to incorporate new sales.
   Lag, rolling, and EMA features depend on historical CSV data; without
   a continuous POS feed they become stale and forecast accuracy
   degrades. A real-time system would require streaming ingestion,
   incremental feature updates, and either online retraining or a
   scheduled re-training job.

5. **Limited expiry prediction.** The expiry advisor
   (`spis/models/expiry_advisor.py`) classifies discounts and write-off
   recommendations from `days_to_expiry` and `risk_ratio` but does **not**
   forecast which specific batches will expire before they are sold. It
   reasons from the current state of `inventory_batches` rather than
   from a probabilistic model of batch consumption. Drug-level (rather
   than ATC-category-level) sell-through forecasting would be required
   to predict the actual likelihood of write-off for a given batch.

6. **Single-warehouse stock model.** `atc_inventory` is a single
   snapshot. Multi-branch pharmacy chains would need per-location keys
   and a transfer-aware risk classifier.

7. **Read-only API.** The Flask surface is read-only by design. Stock
   edits, batch receipts, and recalls go through the dashboard's direct
   write path, not the API. A production deployment would need an
   authenticated `POST/PATCH` surface (see §7.5 future work item 6 and
   Chapter 5 §5.8 on security).

8. **NLP drug-name search was scoped, not delivered.** `spacy` and
   `scispacy` remain in `requirements.txt` because the Phase 9 plan
   included a drug-name NLP search, but it was deprioritised in favour
   of the operational features (alerts, POs, catalog management, batch
   receive / recall). The codebase currently has no NLP path.

## 7.5 Future Work

The priority order below is informed by what an evaluator or pharmacist
would most likely ask for next.

1. **Live POS ingestion.** Replace the CSV import with a continuous feed
   (e.g. a small Flask endpoint that receives POS events, batched into
   `sales`). Schedule weekly retraining so lag / rolling features stay
   representative.
2. **Probabilistic forecasts at training time.** The dashboard already
   shows a bootstrap P10–P90 band on Page 1, but the underlying model is
   still a point estimate. Replace `XGBRegressor` with quantile regression
   (`reg:quantileerror`) so the order-quantity formula can use the 90th
   percentile directly and remove the fixed `safety_days` constant.
3. **Per-drug forecasts.** Move from ATC-4 to per-SKU forecasting. Requires
   sparser-history modelling (hierarchical or transfer learning).
4. **NLP drug-name search.** Re-introduce the scoped scispacy search.
   `PhraseMatcher` over the `drugs` catalog with a `difflib` fallback when
   the scispacy model is not installed.
5. **Multi-branch deployment.** Add a `location_id` to `atc_inventory`,
   `inventory_batches`, and the API path, and extend the risk classifier to
   suggest inter-branch transfers before triggering an external PO.
6. **Authenticated API + mobile client.** Add API-key auth on the Flask
   surface and ship a thin mobile client that mirrors the alert feed for
   pharmacists on rotation.
7. **Refill reminders.** Subscribe a downstream patient-reminder service to
   the existing `alerts` table — `CRITICAL` events on chronic-medication
   ATC codes can be cross-referenced with a patient prescription database
   to warn patients before their next refill is at risk.

## 7.6 Reflections

**Saleh.** Owning the architecture taught me how much benefit comes from
keeping one source of truth per concept. The `RiskAssessment` dataclass,
the `_shared.py` cache helpers, the `FEATURE_COLS` list, and the
`_migrate_schema()` migration helper are each tiny pieces of code, but the
fact that every dashboard page and the Flask API run through them is what
made Phase 9 additions safe. The single highest-value design choice was
reading model artifacts directly from the dashboard — it kept Streamlit
sub-second and made the Flask API a clean optional surface rather than a
critical path.

**Nawaf.** Building the API factory and the test client harness made me
appreciate fail-fast design. Eager loading at startup means a deployment
with no model never serves a confused 500 — it serves a deliberate 503
with a message that tells you exactly which script to run. The 18 API
tests doubled as documentation of every error path.

**Mazen.** The test suite more than doubled during the project (from 75 to
182 tests across 14 files) and the later additions were the most valuable.
Alert idempotency, two-factor expiry classification, batch-recall semantics,
and PO generation each had a non-obvious failure mode that only a test
could pin down. The discipline of writing the test alongside the fix
turned each defect into a regression guard rather than a one-off patch.

**Ali.** The dashboard is where the project comes alive. Phase 8.5 split
the single page into multiple pages, and Phase 9 turned it from a viewer
into a tool — stock edits, batch receipts and recalls, discount
acknowledgements, alert acknowledgements, and PO PDFs all happen in-app.
Plotly + Streamlit's two-tier caching let me focus on the visuals without
ever measuring a render. The P10–P90 bootstrap band on Page 1 was the
single feature that made the forecast feel honest — it shows uncertainty
without hiding the point estimate. I would like to put this in front of a
pharmacist next.

---

## References

The references for this report are consolidated into a single IEEE-style
list at the end of the full Ch1-7 document, per committee guideline §IX
("a single Reference section for the whole report"). See
`docs/references_master.md` for the master list. New entries cited
above (Chen & Guestrin XGBoost, Pedregosa et al. scikit-learn, McKinney
pandas, Seabold & Perktold statsmodels, Ronacher Flask, Streamlit Inc.,
and Sommerville) are numbered [24] – [30] in that consolidated list and
extend the 23 entries inherited from the GP1 submission.
