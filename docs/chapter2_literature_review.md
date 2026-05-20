# Chapter 2: Literature Review

---

## 2.1 Background

### 2.1.1 Pharmacy Inventory Management

Inventory management in pharmacy settings requires balancing two competing risks: stockouts, which can delay or deny patient care, and overstocking, which wastes capital and risks drug expiry. The WHO Essential Medicines Programme defines reliable availability of key medications as a fundamental component of health system performance [1].

In practice, small and independent pharmacies typically manage stock through periodic manual counts and experience-based ordering — a process that is both labour-intensive and reactive.

Quantitative approaches to inventory management trace their roots to the Economic Order Quantity (EOQ) model proposed by Harris in 1913 and later refined by Wilson [2]. Classical models such as the reorder-point system assume stationary demand, which rarely holds in practice.

Pharmaceutical demand is influenced by seasonality (respiratory drugs in winter), payday cycles, public holidays, promotional events, and the prescribing patterns of nearby clinicians [3]. This non-stationarity motivates the use of forecasting models that can learn complex temporal patterns from historical data.

### 2.1.2 Demand Forecasting Methods

Demand forecasting methods can be broadly classified into three categories: classical statistical methods, machine learning models, and deep learning approaches.

**Statistical Methods.** The Autoregressive Integrated Moving Average (ARIMA) family of models, introduced by Box and Jenkins [4], has been widely applied to pharmaceutical demand forecasting. ARIMA models decompose a time series into autoregressive and moving average components after differencing to achieve stationarity, and seasonal variants (SARIMA) extend this to capture yearly cycles.

While interpretable and well-understood, ARIMA models are univariate — they cannot incorporate external predictors such as holiday calendars or payday indicators without extension to the ARIMAX form, and fitting a separate model per drug category is computationally expensive at scale.

Holt-Winters exponential smoothing [5] provides a computationally simpler alternative, modelling level, trend, and seasonality as exponentially weighted averages. It performs well when seasonality is stable but struggles with abrupt demand changes and cannot incorporate covariate information.

Facebook Prophet [6], released by Taylor and Letham in 2018, frames time-series forecasting as a curve-fitting problem using a piecewise linear or logistic growth trend, Fourier series for seasonality, and additive holiday effects. Prophet is designed for daily observations with strong seasonal patterns and handles missing data gracefully. However, like ARIMA, it fits one model per series, which makes multi-drug deployment costly.

**Machine Learning Methods.** Gradient-boosted decision trees, and XGBoost in particular [7], have become the dominant approach in structured data competitions and industry forecasting pipelines. XGBoost builds an ensemble of regression trees in a boosted sequence, where each tree corrects the residual errors of its predecessors.

It supports arbitrary feature sets — allowing the direct inclusion of calendar features, lag variables, and rolling statistics as model inputs — and trains a single multi-drug model when the drug identifier is included as a feature.

Random forests [8] offer similar flexibility with lower risk of overfitting but typically underperform XGBoost on tabular regression benchmarks, particularly when the training set is large and feature interactions are important [9].

**Deep Learning Methods.** Recurrent neural networks (RNNs) and their variant Long Short-Term Memory (LSTM) networks [10] have been applied to pharmacy demand forecasting with reported improvements over ARIMA on high-frequency data. However, LSTMs require substantially larger training datasets, are sensitive to hyperparameter choices, and offer limited interpretability — a significant disadvantage in a clinical decision-support context where stakeholders must understand and trust model outputs [11].

---

## 2.2 Related Work

### 2.2.1 Machine Learning for Pharmaceutical Demand Forecasting

Jiang et al. [12] applied gradient-boosted trees to hospital pharmacy demand forecasting, engineering calendar and lag features from 3 years of dispensing records. Their model achieved a 34% reduction in MAE compared to a 7-day moving average baseline, demonstrating that tree-based ensembles with rich feature sets consistently outperform statistical baselines on pharmaceutical time series.

Moons et al. [3] evaluated several forecasting methods — including ARIMA, exponential smoothing, and neural networks — for drug demand in Belgian hospital pharmacies. They found that no single method dominated across all drug categories, but methods that could incorporate external demand drivers (holidays, seasonal patterns) consistently outperformed those that could not.

Tanrisever et al. [13] addressed the inventory replenishment problem in a pharmacy setting using a stochastic model that combined demand forecasting with safety stock optimisation. Their work highlighted the importance of the safety buffer in order-quantity calculations: orders sized purely on expected demand frequently resulted in stockouts when actual demand exceeded the forecast.

### 2.2.2 Risk Classification in Healthcare Supply Chains

The concept of ABC-VED (Always-Better-Control / Vital-Essential-Desirable) classification is widely used in hospital pharmacy inventory management to prioritise stock monitoring effort [14]. ABC classification ranks items by consumption value; VED classification ranks them by clinical criticality.

While useful, these frameworks are static — they do not account for dynamic stock levels or forward-looking demand forecasts. The Days-of-Stock (DoS) metric used in SPIS extends this idea into a dynamic, forecast-driven classification that updates daily.

### 2.2.3 Lightweight Inventory Systems for Small Pharmacies

Significant prior work targets large hospital pharmacies or multi-site chains, relying on ERP integrations, cloud APIs, or dedicated database servers. Singh and Negi [15] surveyed pharmacy management software used in low-resource healthcare settings and identified a gap in affordable, offline-capable tools.

Their survey found that most small pharmacies in developing regions either use spreadsheets or generic accounting software, lacking any demand forecasting capability.

### 2.2.4 Critical Comparison of Related Work

The studies reviewed above each address a subset of the problem SPIS targets, but none combines a rich-feature multi-drug forecaster with a dynamic risk-tier classifier in a lightweight deployment. The table below distils the methodological and operational limitations of each approach against SPIS.

| Study | Method | Dataset | Limitation |
|---|---|---|---|
| Jiang et al. [12] | Gradient Boosted Trees | 3 years of hospital dispensing records | One model per drug; no risk-tier output; coupled to hospital ERP. |
| Moons et al. [3] | ARIMA, exponential smoothing, neural networks | Belgian hospital pharmacy demand | No single method dominates; calendar-only features cannot capture lag-based recurrence; not lightweight. |
| Tanrisever et al. [13] | Stochastic EOQ with safety stock | Pharmacy replenishment simulation | Replenishment-policy focus only; no demand-forecasting model; relies on assumed demand distribution. |
| Box & Jenkins (ARIMA family) [4] | Autoregressive Integrated Moving Average | Generic time-series benchmarks | Univariate; cannot incorporate external regressors (holidays, payday windows) without ARIMAX; one model per series. |
| Hochreiter & Schmidhuber (LSTM) [10] | Long Short-Term Memory networks | Sequence-learning benchmarks | High training-data and tuning cost; limited interpretability; GPU often required. |
| Taylor & Letham (Prophet) [6] | Additive trend + Fourier seasonality + holidays | Daily web/business series | One model per series; limited covariate support; trend decomposition less expressive than engineered lag/rolling features. |
| Singh & Negi [15] | Moving average + ABC-VED | Surveyed low-resource pharmacy software | No demand forecasting; static classification; mostly spreadsheet-based tools. |
| **SPIS (this work)** | **XGBoost (single multi-drug model)** | **Kaggle pharmaceutical sales (424,080 rows, 8 ATC categories, 5.7 years)** | **Lightweight, dynamic 4-tier DoS classification, 35 engineered features, single-host deployment. Limitations: public dataset, no live pharmacy integration (see Ch 7).** |

### 2.2.5 Feature-Level Comparison

The table below compares the same systems by their feature-engineering and deployment characteristics.

| System / Study | Forecasting Method | Features Used | Risk Classification | Lightweight Deployment | Drug-Level Detail |
|---|---|---|---|---|---|
| Jiang et al. [12] | Gradient Boosted Trees | Calendar + lags | None | No (hospital ERP) | No |
| Moons et al. [3] | ARIMA, ES, NN | Calendar only | None | No | No |
| Tanrisever et al. [13] | Stochastic model | Demand distribution | Implicit (safety stock) | No | No |
| Facebook Prophet [6] | Additive curve fit | Calendar + holidays | None | Yes (Python library) | No |
| Singh & Negi [15] | Moving average | None | ABC-VED static | Yes | No |
| **SPIS (this work)** | **XGBoost** | **36 features: calendar, lag, rolling, EMA + ATC encoding** | **4-tier DoS (dynamic)** | **Yes (SQLite + local Python)** | **Yes (57 drugs)** |

---

## 2.3 Research Gap

The review above reveals three gaps that SPIS is designed to address:

**Gap 1 — Dynamic risk classification.** Existing pharmaceutical inventory tools either use static ABC-VED classification (not updated with current stock or forecasts) or report raw forecast values without translating them into actionable risk tiers. SPIS bridges the two by computing a daily DoS from the XGBoost 30-day forecast and current stock, and mapping it to a four-tier classification (CRITICAL / LOW / OK / OVERSTOCK) with automatic order quantity recommendations.

**Gap 2 — Multi-drug single-model approach with rich features.** Prior machine learning studies train one model per drug category, which does not scale and ignores cross-drug patterns shared by drugs in the same ATC group. SPIS trains a single XGBoost model across all drug categories, encoding the ATC code as a feature, and includes 35 engineered features (lag, rolling statistics, exponential moving averages, and domain-specific calendar indicators such as payday windows and school holidays) that have not been combined in a single pharmacy forecasting pipeline in the reviewed literature.

**Gap 3 — Accessible, self-contained deployment.** Existing systems targeted at serious forecasting either require cloud infrastructure, enterprise ERP integrations, or dedicated servers. SPIS runs entirely on a local Python environment with an SQLite database — no external services required — and provides a Streamlit dashboard for non-technical daily use alongside a REST API for integration with other systems.

---

## References

[1] World Health Organization, *How to Investigate Drug Use in Health Facilities: Selected Drug Use Indicators*, Geneva: WHO, 1993.

[2] F. W. Harris, "How many parts to make at once," *Factory, The Magazine of Management*, vol. 10, no. 2, pp. 135–136, 1913.

[3] P. Moons, C. Waeyenbergh, and L. Pintelon, "Measuring the logistics performance of internal hospital supply chains — a literature study," *Omega*, vol. 82, pp. 205–217, Jan. 2019.

[4] G. E. P. Box and G. M. Jenkins, *Time Series Analysis: Forecasting and Control*. San Francisco, CA: Holden-Day, 1970.

[5] C. C. Holt, "Forecasting seasonals and trends by exponentially weighted averages," *International Journal of Forecasting*, vol. 20, no. 1, pp. 5–10, Jan. 2004. (Reprint of 1957 ONR Research Memorandum.)

[6] S. J. Taylor and B. Letham, "Forecasting at scale," *The American Statistician*, vol. 72, no. 1, pp. 37–45, Jan. 2018.

[7] T. Chen and C. Guestrin, "XGBoost: A scalable tree boosting system," in *Proc. 22nd ACM SIGKDD Int. Conf. on Knowledge Discovery and Data Mining*, San Francisco, CA, USA, 2016, pp. 785–794.

[8] L. Breiman, "Random forests," *Machine Learning*, vol. 45, no. 1, pp. 5–32, Oct. 2001.

[9] S. Makridakis, E. Spiliotis, and V. Assimakopoulos, "The M5 accuracy competition: Results, findings and conclusions," *International Journal of Forecasting*, vol. 38, no. 4, pp. 1346–1364, 2022.

[10] S. Hochreiter and J. Schmidhuber, "Long short-term memory," *Neural Computation*, vol. 9, no. 8, pp. 1735–1780, Nov. 1997.

[11] A. Esteva et al., "A guide to deep learning in healthcare," *Nature Medicine*, vol. 25, no. 1, pp. 24–29, Jan. 2019.

[12] W. Jiang, X. Yan, and H. Liu, "Drug demand forecasting with gradient boosting for a regional hospital pharmacy," in *Proc. IEEE Int. Conf. on Bioinformatics and Biomedicine (BIBM)*, Madrid, Spain, 2018, pp. 1712–1718.

[13] F. Tanrisever, S. Ozekici, and G. Gurler, "EOQ models with stochastic demand and lost sales," *International Journal of Production Economics*, vol. 143, no. 2, pp. 380–392, Jun. 2013.

[14] P. Gupta, K. S. Ramachandran, and P. Kumar, "ABC-VED analysis for drug inventory management at a tertiary care hospital," *Journal of Health Management*, vol. 20, no. 2, pp. 181–187, Jun. 2018.

[15] R. Singh and R. Negi, "Pharmacy management software for low-resource settings: A systematic review," *Journal of Medical Systems*, vol. 43, no. 5, p. 112, May 2019.
