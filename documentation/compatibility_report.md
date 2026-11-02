# BuildConnect AI compatibility report

## 1. Available research artifacts

### Real WPI data
- File: `data/wpi/BuildConnect_Construction_Materials_Final.csv`
- Shape: 3,380 monthly observations across 20 material categories
- Key columns: `date`, `material`, `wpi`, `material_group`, `month_sin`, `month_cos`, `wpi_lag_1`, `wpi_lag_3`, `wpi_lag_6`, `wpi_lag_12`, `wpi_roll_mean_3`, `wpi_roll_mean_6`, `wpi_roll_std_3`
- Compatibility: valid for material-level historical charts, trend analysis, and trend-adjusted forecast logic.

### Synthetic supplier-risk dataset
- File: `data/supplier/buildconnect_synthetic_supplier_orders.csv`
- Shape: 10,000 synthetic supplier/order records
- Key columns: supplier ID, material, quantity, distance, availability ratio, promised delivery days, rating, review count, verification flag, historical delivery success, average delay, cancellation rate, response time, price competitiveness, late probability, late delivery, actual delivery delay
- Compatibility: usable for experimental supplier risk scoring and demonstration workflows only. It must be labeled as synthetic and must not be represented as real order history.

### Forecast outputs and metadata
- `outputs/forecasting/buildconnect_final_adaptive_results.csv`: identifies the selected model per material and includes the chosen `alpha` values, validation metrics, and test metrics.
- `outputs/forecasting/buildconnect_conformal_results.csv`: contains calibration values, target coverage, interval widths, and coverage statistics for conformal intervals.
- `outputs/buy_wait/buildconnect_buy_wait_decisions.csv`: contains decision labels, expected movement, uncertainty, and `procurement_decision` outputs.
- `outputs/buy_wait/buildconnect_buy_wait_material_summary.csv`: summarizes average movement and uncertainty by material.
- Compatibility: these files are the primary source of truth for the frozen trend-adjusted rule and buy/wait logic.

### Model files
- `models/buildconnect_models/arima/arima_opc_111.pkl`: ARIMA artifact for a representative material (OPC)
- `models/buildconnect_models/lstm/lstm_opc.keras`: LSTM model for OPC
- `models/buildconnect_models/lstm/lstm_config.json`: configuration
- `models/buildconnect_models/lstm/lstm_feature_scaler.pkl`: feature scaler
- `models/buildconnect_models/lstm/lstm_target_scaler.pkl`: target scaler
- `models/buildconnect_models/xgboost/xgboost_opc.json`: XGBoost artifact
- `models/buildconnect_models/xgboost/xgboost_features.json`: feature order metadata
- Compatibility: available for experimental comparison, not for a universal operational pipeline without matching feature schema and material-specific packaging.

## 2. Missing or incompatible files

The package includes a list of expected artifacts that are absent from the delivered snapshot. The most important missing items are:

- No PostgreSQL/PostGIS schema or migration files were found.
- No authenticated application backend or frontend code existed in the original package.
- No ready-made supplier-risk classifier pipeline (for example logistic-regression artifacts or feature preprocessing files) was found.
- No production database seeding files or project records existed.
- No material catalogue service or `.env` configuration files existed in the project root.

## 3. Compatibility findings

### Supported
- Real WPI data is present and usable.
- Trend-adjusted Naive forecast logic is supported by saved material-specific `alpha` values.
- Conformal interval calibration outputs are available.
- Buy/wait decision support is supported by saved outputs.
- Synthetic supplier-risk data is available for low-evidence experimental scoring.
- Multi-material procurement outputs exist in Excel files and can be treated as report artifacts.

### Partial or experimental support
- ARIMA, XGBoost, and LSTM artifacts exist but are material-specific or configuration-dependent.
- XGBoost and LSTM pipelines are not universal and require matching schema validation before deployment.
- Supplier-risk classification is experimental because the project package does not include a persisted logistic regression model pipeline or feature-order artifact.
- NSGA-II results are represented as Pareto plots and output spreadsheets, but not as an implementation-ready optimizer pipeline.

### Unsupported without additional source files
- Production-ready PostgreSQL/PostGIS installation and migrations.
- Real supplier ERP or procurement history.
- Fully validated live supplier-risk classifier pipeline.
- Real customer reviews or real procurement-savings records.

## 4. Recommended implementation strategy

1. Use the WPI CSV and saved `alpha` values as the authoritative source for price forecasts.
2. Use the conformal calibration outputs for interval estimation and historical coverage reporting.
3. Treat all supplier-risk predictions as experimental, with explicit low-evidence warnings.
4. Build the backend and frontend around real data and metadata, while keeping demo data isolated from production user records.
5. Keep DB and API code robust enough to run against SQLite during development, with Postgres-compatible SQLAlchemy models and environment-based configuration for production.

## 5. Final compatibility verdict

The research package is compatible with a staged implementation of the BuildConnect AI platform, but it is not a complete application skeleton. The available artifacts can support the forecasting, uncertainty, buy/wait, and synthetic supplier-risk workflows; however, the project still requires the application code, database models, API layers, frontend, tests, and environment setup described in the BuildConnect AI master prompt.
