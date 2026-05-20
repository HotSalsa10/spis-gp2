# Chapter 1: Introduction

---

## 1.1 Background

Pharmacies are a critical link in the healthcare supply chain. Maintaining adequate stock of medications directly affects patient safety — a stockout of a pain reliever or anxiolytic can have immediate clinical consequences, while overstocking ties up capital and risks drug expiry.

For independent and small-chain pharmacies, inventory management is typically performed manually: a pharmacist or storekeeper inspects shelves, estimates demand from experience, and places orders based on intuition. This process is error-prone, time-consuming, and cannot adapt quickly to seasonal demand shifts, holiday periods, or unusual consumption patterns.

Modern enterprise pharmacy systems — such as those offered by large hospital networks — include demand forecasting and inventory optimisation as built-in features. However, these platforms are prohibitively expensive for single-site or small-chain pharmacies.

There is a clear gap in accessible, lightweight tools that apply machine learning techniques to pharmacy-scale inventory data without requiring cloud infrastructure, specialised hardware, or large IT teams.

Machine learning, and gradient-boosted tree models in particular, have demonstrated strong performance on time-series demand forecasting tasks across retail and healthcare domains [1][2]. When combined with a systematic feature engineering pipeline, such models can capture complex temporal patterns — weekly seasonality, holiday effects, payday cycles — that simple statistical baselines miss.

The output of such a model, framed as a risk classification and order recommendation, gives pharmacy staff actionable daily guidance rather than raw numbers.

---

## 1.2 Problem Definition

This project addresses the following core problem:

> **A single-site pharmacy has no systematic, data-driven mechanism to predict future drug demand, assess current inventory risk, or generate order recommendations — forcing staff to rely on manual judgement and reactive restocking.**

The specific deficiencies that motivate this work are:

1. **No demand forecasting.** Staff estimate future consumption based on experience rather than historical data, leading to both stockouts and unnecessary surplus.
2. **No risk classification.** There is no formal method to prioritise which drugs require immediate attention. A drug with two days of stock remaining is treated the same as one with a two-month surplus.
3. **No automated order quantities.** When restocking is needed, the quantity ordered is determined ad hoc rather than derived from a 30-day demand forecast with a safety buffer.
4. **No scalable tooling.** Any solution must be lightweight (local execution, no cloud dependency) and adaptable to pharmacies other than the one whose data was used to develop the system.

---

## 1.3 Aims and Objectives

### Aim

To design, implement, and evaluate a Smart Pharmacy Inventory System (SPIS) that uses historical sales data and machine learning to provide daily inventory risk assessment and order recommendations for pharmacy drug stock.

### Objectives

1. **Data Ingestion** — Build an automated pipeline to ingest historical sales data (in standard long-format CSV) into a structured SQLite database, supporting arbitrary drug categories (ATC codes).

2. **Feature Engineering** — Implement a reproducible pipeline that derives 35 time-series features from raw daily sales data, including calendar indicators, lag variables, rolling statistics, and exponential moving averages.

3. **Demand Forecasting** — Train an XGBoost gradient-boosted model and evaluate it against two baselines (naïve lag-1 and 7-day moving average), targeting a Mean Absolute Error (MAE) below 2.0 units per day.

4. **Risk Classification** — Classify each drug category into one of four inventory risk tiers (CRITICAL, LOW, OK, OVERSTOCK) based on days-of-stock calculated from the 30-day demand forecast.

5. **Order Recommendations** — Generate a recommended order quantity for each drug category that covers the next 30 days of forecasted demand plus a configurable safety buffer.

6. **REST API** — Expose the forecasting and risk assessment logic via a Flask REST API with three endpoints: health check, full risk assessment, and per-drug 30-day forecast.

7. **Dashboard** — Deliver a single-page Streamlit dashboard that presents summary tier counts, a detailed risk table, and order quantity charts, suitable for daily use by pharmacy staff.

8. **Testing** — Achieve comprehensive automated test coverage across all system components with a minimum of 75 passing unit and integration tests.

---

## 1.4 Project Timeline

The project was executed across two semesters (GP1 and GP2) with the following phase structure:

| Phase | Description | Deliverable |
|-------|-------------|-------------|
| 1 | Repository setup, database schema, drug catalog, data ingestion | `inventory.db`, `scripts/ingest_kaggle.py` |
| 2 | Data pipeline and feature engineering | `features_daily.csv`, `train.csv`, `test.csv` |
| 3 | XGBoost demand forecasting model | `xgboost_forecaster.joblib`, `metrics.json` |
| 4 | Risk classification and order recommendations | `spis/models/risk_classifier.py` |
| 5 | Flask REST API | `spis/api/`, 3 endpoints |
| 6 | Streamlit dashboard | `spis/dashboard/app.py` |
| 7 | Expanded testing suite | 75 automated tests |
| 8 | GP Report | This document |

---

## 1.5 Team

| Member | Role |
|--------|------|
| Saleh  | Lead developer — ML pipeline, model training, API |
| Nawaf  | Data engineering — ingestion, feature pipeline, database |
| Mazen  | Backend — Flask API, risk classifier, testing |
| Ali    | Frontend — Streamlit dashboard, documentation |

---

## References

[1] T. Chen and C. Guestrin, "XGBoost: A Scalable Tree Boosting System," in *Proc. 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, San Francisco, CA, USA, 2016, pp. 785–794.

[2] A. Fildes, K. Nikolopoulos, S. F. Crone, and A. A. Syntetos, "Forecasting and operational research: A review," *Journal of the Operational Research Society*, vol. 59, no. 9, pp. 1150–1172, Sep. 2008.
