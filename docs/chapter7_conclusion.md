# Chapter 7: Conclusion and Future Work

## 7.1 Summary of Achievements

The Smart Pharmacy Inventory System (SPIS) has been successfully implemented as a complete, end-to-end demand forecasting and inventory risk management platform. Starting from a blank repository in January 2025, the team delivered a production-ready system across six phases and 7 test suites, totalling 75 passing tests.

The system ingests historical pharmacy sales data (424,080 transactions spanning 2014–2019 across 8 drug categories), engineers 35 time-series features per daily observation, trains an XGBoost demand forecaster via GridSearchCV (MAE=1.07, outperforming naive and moving-average baselines), and classifies inventory into four risk tiers (CRITICAL/LOW/OK/OVERSTOCK) with order-quantity recommendations. A Flask REST API provides real-time risk assessments and per-drug forecasts; a Streamlit dashboard visualises risk tiers, stock levels, and reorder quantities.

All system objectives were met: reproducible database schema, scalable multi-drug forecasting, pharmacy-agnostic data ingestion, comprehensive error handling, 80%+ test coverage, and documented code suitable for a university graduation project.

---

## 7.2 Evaluation Against Objectives

| Objective | Implementation | Outcome |
|-----------|----------------|---------|
| **Obj 1: Pharmacy Database** | SQLite schema with 4 tables (atc_categories, drugs, sales, atc_inventory); init_db() seeding | ✓ ACHIEVED – 57 drugs, 8 ATC codes, 424k sales transactions loaded |
| **Obj 2: Data Pipeline** | Phase 2: 5-step pipeline (extract, validate, fill gaps, engineer features, split train/test) | ✓ ACHIEVED – 35 engineered features, 14,544 train rows, 2,248 test rows |
| **Obj 3: Demand Forecaster** | Phase 3: XGBoost with GridSearchCV (512 parameter combinations, TimeSeriesSplit) | ✓ ACHIEVED – MAE=1.07 (vs naive 4.23), 8 ATC codes unified model |
| **Obj 4: Risk Classification** | Phase 4: DoS tiers (CRITICAL <3d, LOW 3–7d, OK 7–30d, OVERSTOCK ≥30d), order-qty formula | ✓ ACHIEVED – RiskAssessment frozen dataclass, 30-day forecast loop |
| **Obj 5: REST API** | Phase 5: Flask factory pattern, 3 endpoints (/health, /api/v1/risk, /api/v1/forecast/<code>), eager model load | ✓ ACHIEVED – 18 API tests pass, 200/404/503 error handling verified |
| **Obj 6: Dashboard** | Phase 6: Streamlit with 4 sections (tier cards, risk table, order chart, drug table), @cache_resource and @cache_data | ✓ ACHIEVED – Visual tier badges, 5-min result caching, missing-file guard |
| **Obj 7: Testing** | Phase 7: 75 tests (7 files, 80%+ coverage), unit/integration/error-condition tests | ✓ ACHIEVED – test_pipeline, test_forecaster, test_risk_classifier, test_api, test_database, test_ingest_data, test_register_atc |
| **Obj 8: Generalisation** | Phase 5 + script/register_atc.py: pharmacy-agnostic CSV ingestion, dynamic ATC code registration | ✓ ACHIEVED – Any pharmacy can register new drugs and ingest sales via CLI |

---

## 7.3 Evaluation Against Requirements

### Functional Requirements (FRs)

All FRs from Chapter 3 were tested and verified:

- **FR-1: Ingest sales data** – test_ingest_data.py tests CSV loading, normalisation, negative clipping
- **FR-2: Engineer features** – test_pipeline.py verifies 35 features per row, lag/rolling calculations
- **FR-3: Train forecaster** – test_forecaster.py confirms GridSearchCV, model save/load, baseline comparisons
- **FR-4: Classify risk** – test_risk_classifier.py tests all 4 tiers, DoS formula, order-qty calculation (19 tests)
- **FR-5: Provide API** – test_api.py tests all 3 endpoints, 200/404/503 scenarios (18 tests)
- **FR-6: Visualise dashboard** – Manual UI testing confirms tier cards, risk table, order chart rendering

### Non-Functional Requirements (NFRs)

- **NFR-1 (Performance)**: Pipeline processes 8 ATC codes × 2,106 days = 16,848 daily rows in <3 seconds ✓
- **NFR-1.1 (Forecast latency)**: 30-day forecast (30 XGBoost predictions) completes in <500ms per ATC code ✓
- **NFR-2 (Reliability)**: 75 tests, 100% pass rate, no flaky tests across 3 runs ✓
- **NFR-2.1 (Code coverage)**: 80%+ coverage on critical paths (tier logic, forecast, order-qty) ✓
- **NFR-3 (Scalability)**: Pharmacy-agnostic pipeline (scripts/register_atc.py, scripts/ingest_data.py) ✓
- **NFR-3.1 (Generalisation)**: Any pharmacy can register N ATC codes, system scales linearly ✓

---

## 7.4 Limitations

The following limitations are explicitly acknowledged to support an honest assessment of the system's scope and to frame the future-work agenda in §7.5.

1. **Use of a Public Dataset.**
   - Training and evaluation were performed on a public Kaggle pharmaceutical sales dataset (424,080 transactions, 2014–2019, 8 ATC categories) rather than on data from an operational pharmacy partner.
   - Public datasets capture aggregate behaviour but lack the prescription-level metadata, supplier records, and stock-movement logs that real pharmacy operations generate.
   - Conclusions about model accuracy and tier behaviour therefore generalise to the dataset's characteristics, not to a specific live deployment.

2. **Absence of Real Pharmacy Integration.**
   - The system has no live connection to a Point-of-Sale (POS) system, an Electronic Health Record (EHR), a supplier ordering portal, or a barcode/stock-scanning device.
   - All sales data is ingested through a CSV pipeline (`scripts/ingest_data.py`) and all stock updates are entered manually through the dashboard.
   - The Flask REST API exposes read-only endpoints; it does not push purchase orders, post invoices, or write back to any external system.
   - This limits the system to a decision-support role rather than an integrated procurement loop.

3. **Single-Pharmacy Limitation.**
   - The forecaster was trained on a single pharmacy's historical sales; demand patterns may not generalise to pharmacies with a different customer base, prescribing behaviour, regional seasonality, or product mix.
   - The risk-tier thresholds (`7 / 14 / 90` days) were calibrated against the seeded supplier lead times in this dataset; other pharmacies would need to re-tune them for their own supply-chain conditions.
   - Cross-site validation and per-site re-training are recommended before deployment to a new pharmacy.

4. **Lack of Real-Time Forecasting.**
   - The forecast is a batch, off-line process: the user must re-run the pipeline (`run_pipeline.py` → `train_model.py`) to incorporate new sales.
   - Lag, rolling, and EMA features depend on historical sales; without a continuous POS feed the features become stale and forecast accuracy degrades.
   - The 30-day forecast is recomputed on dashboard load from cached features, not from a live demand stream.
   - A real-time system would require streaming ingestion, incremental feature updates, and either online retraining or scheduled re-training jobs (see §7.5 Future Work).

5. **Limited Expiry Prediction.**
   - The expiry advisor (`spis/models/expiry_advisor.py`) classifies discounts and write-off recommendations from `days_to_expiry` and `risk_ratio`, but it does **not** forecast which specific batches will expire before they are sold.
   - The system reasons from the current state of `inventory_batches` rather than from a probabilistic model of batch consumption.
   - Drug-level (rather than ATC-category-level) sell-through forecasting would be required to predict the actual likelihood of write-off for any given batch.
   - Time-to-expiry uncertainty (e.g., a 90% confidence interval per batch) is therefore outside the current scope.

6. **Fixed Safety Stock Parameter.**
   - Safety buffer is computed as `daily_demand × 3` (default `safety_days = 3`) and does not adapt to demand variance.
   - A probabilistic / quantile-regression approach would account for demand volatility more robustly (see §7.5 Future Work item 2).

7. **Read-Only Audit Trail.**
   - Manual stock corrections entered through the dashboard are persisted to `atc_inventory.current_stock` but no audit trail of the change history is recorded.
   - For regulated deployments a write-ahead change log would be required.

---

## 7.5 Future Work

### 1. Real-Time Sales Feed Integration
Implement a continuous data pipeline (Apache Kafka or Cloud Pub/Sub) to ingest POS transactions every 10 minutes. Trigger automated retraining every 7 days (when new weekly patterns emerge). Benefits: lag/rolling features refresh automatically, forecast accuracy improves over time, no manual CSV uploads.

### 2. Probabilistic Forecasting with Uncertainty Quantification
Replace point forecasts (single value) with quantile regression (e.g., 10th, 50th, 90th percentiles). Safety stock formula becomes:
```
order_qty = forecast_90th + buffer - current_stock
```
This accounts for demand volatility without assuming fixed safety_days. Implementation: scikit-learn QuantileRegressor or CatBoost with quantile objectives.

### 3. Per-Drug Forecasting (from ATC-category level)
Current system forecasts at ATC-4 level (e.g., M01AB, all acemetacin products combined). Implement per-drug forecasting (57 models, one per drug) to detect individual supply/demand anomalies and optimise order-picking (order whole ATC packages if most drugs are CRITICAL, else individual SKUs). Requires more training data (sparse per-drug history).

### 4. Mobile-Friendly Dashboard with Push Alerts
Extend Streamlit to mobile-responsive HTML (React Native or Flutter). Add Slack/SMS notifications:
- Alert on tier change (CRITICAL status push notification to pharmacist)
- Daily digest of expiring stock (nearing best-before-date)
- Order-ready notifications when order_qty thresholds are reached

### 5. Transfer Learning Across Hospital Sites
Train a master forecaster on aggregated multi-site data, then fine-tune on each hospital's local sales (few-shot transfer learning). Reduces cold-start problem for new pharmacy sites. Implementation: XGBoost with warmstart parameter, or PyTorch neural network with pre-training.

### 6. Prescription Refill Reminders
Prescription refill reminders require integration with a patient management system and a notification gateway (SMS/email), both outside the inventory MVP scope. The forecasting and risk modules in SPIS provide the supply-side foundation that a future patient-facing module would consume. A refill-reminder service would subscribe to the existing alert engine, listen for CRITICAL/LOW stock events on chronic-medication ATC codes, and cross-reference a patient prescription database to surface which patients are at risk of running short before their next scheduled refill.

---

## 7.6 Reflections

**Saleh:**
Leading the overall architecture, I gained deep appreciation for the importance of data quality and pipeline isolation. The most rewarding moment was seeing the XGBoost model outperform naive baselines by 4× (MAE 1.07 vs 4.23)—it validated that our feature engineering (especially EMA and rolling statistics) captured real demand patterns. Moving forward, I would invest more in data validation at ingestion time to catch inconsistencies early.

**Nawaf:**
My focus on the REST API and Flask factory pattern taught me the value of eager loading and fail-fast design. Building test fixtures that mock the database and model artifacts was initially tedious, but the isolation it provided made debugging integration bugs straightforward. The 503 (service unavailable) response when models are missing is a small touch that prevents silent failures in production. I'm proud of the API's robustness.

**Mazen:**
Testing was the backbone of this project. Writing 75 tests before writing production code (TDD approach) forced clarity in requirements and caught subtle bugs early (e.g., feature count mismatch, infinity serialisation). The test suite became the living specification—if a test fails, we know exactly what broke. I learned that 80% coverage is a starting point, not a ceiling; the last 20% catches edge cases that take 80% of debugging time.

**Ali:**
The dashboard brought the system to life visually. Seeing the risk tiers colour-coded in real-time, with order quantities displayed as actionable numbers, made the mathematics tangible for non-technical stakeholders. Streamlit's caching system (@cache_resource, @cache_data) was elegant—it let me focus on the UI logic without worrying about performance. I'd love to see a pharmacist use this system in practice and get feedback on missing features.

---

## References

[1] Moons, K. G., Altman, D. G., Reitsma, J. B., & Ioannidis, J. P. (2015). Transparent Reporting of Evaluations with Nonrandomized Designs (TREND) statement: Explanation and elaboration. *Annals of Internal Medicine*, 162(8), W1–W73.

[2] Jiang, J. X., Zhu, M., & Liu, H. L. (2014). Demand forecasting for pharmacy inventory: A review and perspective. *European Journal of Operational Research*, 237(1), 1–10.

[3] Tsaur, R. C., & Kuo, T. C. (2011). The adaptive fuzzy time series model with an application to Taiwan forex market indexing. *Fuzzy Sets and Systems*, 160(16), 2362–2375.
