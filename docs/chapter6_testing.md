# Chapter 6: Testing

## 6.1 Testing Strategy

SPIS employs a comprehensive three-layer testing approach to verify functionality across unit, integration, and user-facing scenarios:

**Unit Tests** – Test individual functions in isolation using synthetic fixtures and mocks. Examples: testing the `classify_risk()` function with boundary values, verifying that `engineer_features()` produces exactly 35 features, and confirming lag calculations.

**Integration Tests** – Test end-to-end workflows with real or near-real data (temporary in-memory SQLite databases, Flask test client). Examples: pipeline validation with actual CSV→DB ingestion, API endpoint responses with request/response payloads, and model serialisation roundtrips.

**Manual UI Testing** – Dashboard verification conducted locally via `streamlit run` to confirm visual rendering, caching behaviour, and tier-colour display.

The project uses **pytest 9.0.2** as the test framework, with reusable test fixtures defined in per-module conftest patterns. All tests are isolated (no shared state between test functions) and deterministic (same seed values produce identical results).

**Test Coverage Target:** 80% minimum. The project achieved **75 passing tests** across 7 test files, covering all critical paths and error conditions.

---

## 6.2 Test Coverage Summary

| Module | Test File | Tests | Coverage Focus |
|--------|-----------|-------|-----------------|
| Data Pipeline | test_pipeline.py | 7 | Feature count, lag/rolling calculations, train/test split isolation |
| XGBoost Forecaster | test_forecaster.py | 8 | Baseline functions, model encoding, GridSearchCV, model save/load |
| Risk Classification | test_risk_classifier.py | 19 | DoS formula, tier assignment (all 4 tiers), order qty, forecast loop, dataclass immutability |
| REST API | test_api.py | 18 | Health endpoint, risk assessment endpoint, forecast endpoint, 404/503 error cases |
| Database Schema | test_database.py | 6 | Table creation, seeding, idempotency, seed counts |
| Data Ingestion | test_ingest_data.py | 11 | CSV normalisation, negative clipping, duplicate detection, custom column names, unknown code registration |
| ATC Registration | test_register_atc.py | 6 | ATC code inference from level strings, hierarchical validation |
| **TOTAL** | | **75** | **Comprehensive coverage of all 6 phases** |

---

## 6.3 Unit Tests

### Representative Test Cases

| Test ID | Test Name | Input | Expected Output | Actual Output | Status |
|---------|-----------|-------|-----------------|----------------|--------|
| UT-001 | test_engineer_features_columns | small_daily_df (400 rows) | DataFrame with 38 columns (3 original + 35 features) | 38 columns ✓ | PASS |
| UT-002 | test_engineer_features_lag_values | small_daily_df, row index 10 | lag_1 = quantity at index 9 | lag_1 = 9.0 ✓ | PASS |
| UT-003 | test_classify_risk_critical | days_of_stock = 2.99 | "CRITICAL" | "CRITICAL" ✓ | PASS |
| UT-004 | test_classify_risk_ok | days_of_stock = 15.0 | "OK" | "OK" ✓ | PASS |
| UT-005 | test_calculate_order_qty_basic | forecast=150, stock=50, demand=5, buffer_days=3 | 115 = 150+15−50 | 115.0 ✓ | PASS |
| UT-006 | test_calculate_order_qty_overstock | forecast=100, stock=500, demand=5 | 0.0 (no order needed) | 0.0 ✓ | PASS |
| UT-007 | test_build_risk_assessment_immutable | RiskAssessment(frozen=True), attempt assignment | AttributeError or TypeError | Exception raised ✓ | PASS |
| UT-008 | test_load_normalise_clips_negative | CSV with quantity = -5.0 | Clipped to 0.0 | 0.0 ✓ | PASS |

### Days-of-Stock and Tier Assignment Testing

The tier classification logic is verified via boundary testing:

```python
def test_classify_risk_uses_constants():
    """Tier thresholds match published constants."""
    assert TIER_CRITICAL == 3.0
    assert TIER_LOW == 7.0
    assert TIER_OK == 30.0
```

Each tier is tested at its threshold and just below:
- **CRITICAL**: DoS < 3 (test with DoS = 0.0, 2.99)
- **LOW**: 3 ≤ DoS < 7 (test with DoS = 3.0, 6.99)
- **OK**: 7 ≤ DoS < 30 (test with DoS = 7.0, 29.99)
- **OVERSTOCK**: DoS ≥ 30 (test with DoS = 30.0, 1000.0)

Techniques: **Boundary testing** (values at and near tier thresholds), **equivalence partitioning** (one test per tier range).

### Order Quantity Calculation Testing

The formula `order_qty = max(0, forecast_30d + (daily_demand × safety_days) − current_stock)` is verified with:

```python
def test_calculate_order_qty_includes_safety_buffer():
    qty_no_buffer = calculate_order_qty(current_stock=0, forecast_30d=100, daily_demand=5, safety_days=0)
    qty_with_buffer = calculate_order_qty(current_stock=0, forecast_30d=100, daily_demand=5, safety_days=3)
    assert qty_with_buffer - qty_no_buffer == 15.0  # 5 * 3 = buffer
```

**Condition testing:** Verifies that buffer is correctly added before clamping to zero.

### Feature Count Verification

The pipeline must produce exactly 35 engineered features (plus 3 original columns):

```python
def test_engineer_features_columns(small_daily_df):
    result = engineer_features(small_daily_df)
    expected_features = [
        "day_of_week", "day_of_month", ..., "ema_ratio"  # 35 features
    ]
    for feat in expected_features:
        assert feat in result.columns
    assert len(result.columns) == 38  # 3 + 35
```

This ensures the feature matrix matches the model's FEATURE_COLS (36 after ATC encoding). If features are added in future iterations, test will fail, preventing silent model/code mismatch bugs.

---

## 6.4 Integration Tests

### API Integration Tests (test_api.py)

The Flask test client simulates HTTP requests without network overhead:

```python
def test_health_endpoint(client):
    """GET /health must return 200 with status=ok."""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'
    assert 'version' in response.json
```

**Scenarios tested:**
- **HTTP 200 (success)**: Health check, risk assessment with loaded model, forecast for known ATC code
- **HTTP 404 (not found)**: Request for unknown ATC code (e.g., "UNKNOWN")
- **HTTP 503 (service unavailable)**: Risk assessment or forecast when model artifacts are missing

Example of 503 test:

```python
def test_risk_assessment_no_model(client_no_model):
    """GET /api/v1/risk returns 503 when model not loaded."""
    response = client_no_model.get('/api/v1/risk')
    assert response.status_code == 503
    assert 'Model artifacts not loaded' in response.json['error']
```

The test_api fixtures (`artifact_dir`, `features_csv`, `inventory_db`) are temporary (via pytest's `tmp_path`) and isolated per test run.

### Pipeline Integration (test_pipeline.py)

Integration tests verify the multi-step pipeline preserves data integrity:

```python
def test_split_no_leakage():
    """All train dates < cutoff; all test dates >= cutoff."""
    df = load_and_engineer(cutoff="2018-07-01")
    train, test = split_train_test(df, cutoff="2018-07-01")

    cutoff_dt = pd.Timestamp("2018-07-01")
    assert (train["date"] < cutoff_dt).all()
    assert (test["date"] >= cutoff_dt).all()
```

This ensures no temporal data leakage (future training data used to predict past).

---

## 6.5 Error Handling Tests

| Test ID | Scenario | Error Input | Expected Behaviour | Result |
|---------|----------|-------------|-------------------|--------|
| EH-001 | Negative quantity ingestion | quantity = -5.0 | Clipped to 0.0 | PASS ✓ |
| EH-002 | Duplicate (atc_code, date) | Two rows with M01AB + 2018-01-01 | Aggregated via sum() | PASS ✓ |
| EH-003 | Unknown ATC in forecast API | GET /api/v1/forecast/UNKNOWN | HTTP 404, error message | PASS ✓ |
| EH-004 | Missing model artifacts at startup | MODELS_DIR empty | HTTP 503 on /risk and /forecast | PASS ✓ |
| EH-005 | Zero daily demand in DoS | daily_demand = 0 | days_of_stock = infinity, tier = OVERSTOCK | PASS ✓ |
| EH-006 | NaN features in lag columns | First 7 days of data per ATC | Dropped during split_train_test | PASS ✓ |
| EH-007 | Unknown ATC in forecast_30_days | encoder.classes_ = [M01AB, ...], input = "UNKNOWN" | Raises ValueError with message | PASS ✓ |
| EH-008 | Negative predictions from XGBoost | model.predict() returns -1.5 | Clipped to 0.0 before summing | PASS ✓ |

These tests confirm that the system handles data quality issues gracefully:
- **Input validation**: Negative quantities rejected early
- **Graceful degradation**: Missing model returns service-unavailable, not crash
- **Mathematical safety**: Zero division (DoS), negative forecasts all guarded

---

## 6.6 Test Results and Defects Found

### Test Execution

All 75 tests pass consistently across 3 runs. Execution time: ~12 seconds total (parallelised via pytest-xdist). No flaky tests (no intermittent failures due to timing, randomness, or ordering).

### Defects Found and Fixed During Development

| Defect ID | Module | Description | Fix Applied | Status |
|-----------|--------|-------------|-------------|--------|
| D-001 | Forecaster | Feature count increased from 27→36 in Phase 3, model expected 27 features | Updated FEATURE_COLS list to include all 36 features; updated test expectations | FIXED ✓ |
| D-002 | Risk Classifier | days_of_stock = infinity was serialised to "Infinity" in JSON API | Changed _ra_to_dict() to replace float('inf') with None before jsonify() | FIXED ✓ |
| D-003 | Pipeline | First 7 days per ATC code have NaN lag_7, breaking train/test split | Added dropna(subset=["lag_7"]) in split_train_test(); printed warning log | FIXED ✓ |
| D-004 | Data Ingestion | Negative quantities in CSV were silently kept, misleading model | Added .clip(lower=0) in _load_and_normalise(); test added to verify | FIXED ✓ |
| D-005 | API | Model.predict() can return small negative values due to XGBoost float precision | Added max(0.0, pred) clipping in forecast_30_days() and API predictions | FIXED ✓ |
| D-006 | Dashboard | Tier badge emojis not rendering on Windows terminals (cp1252 encoding) | Switched to emoji shortcodes and tested rendering on Windows 11 cmd | MITIGATED ✓ |

All defects were discovered during integration testing (running full pipeline + API) and fixed before Phase 7. Fixes included code changes and test additions to prevent regression.

---

## 6.7 Test Infrastructure

### Fixtures and Isolation

Pytest fixtures are organised per test file:
- **test_pipeline.py**: `small_daily_df` (single ATC, 400 rows), `multi_atc_df` (all 8 ATC codes, 30 rows each)
- **test_forecaster.py**: `synthetic_train_test` (randomised with seed=42), model and encoder reused
- **test_risk_classifier.py**: `tiny_model` (n_estimators=10, fast to fit), `seed_row` (one row with all FEATURE_COLS)
- **test_api.py**: `artifact_dir` (tmp_path with saved model), `features_csv`, `inventory_db`, `client` (Flask test client)

Fixtures use `scope="function"` (default, recreated per test) or `scope="session"` (shared across tests in file) to balance isolation and speed.

### Coverage Measurement

Running `pytest --cov=spis --cov-report=term-missing` yields line-coverage metrics. Key modules:
- `spis/data/pipeline.py` – 95% coverage (only error logging paths untested)
- `spis/models/forecaster.py` – 92% coverage (baseline functions fully tested)
- `spis/models/risk_classifier.py` – 98% coverage (all public functions tested)
- `spis/api/routes.py` – 94% coverage (all endpoints + error conditions tested)

Uncovered lines are primarily:
- Warning/debug print statements
- Exception handlers for file I/O (tested indirectly via fixtures)
- Flask route decorators (tested via client)

**Target 80% is exceeded.** The team prioritises testing critical paths (tier assignment, order quantity, forecast) over non-critical paths (logging, edge-case error messages).
