import json
from typing import Dict, Any, List

DEFAULT_REGISTRY_MODELS: List[Dict[str, Any]] = [
    {
        "model_name": "Trend-Adjusted Naive",
        "model_version": "v1.0-frozen-alpha",
        "task_type": "price_forecast",
        "artifact_location": "outputs/forecasting/buildconnect_final_adaptive_results.csv",
        "feature_schema_version": "v1.0-univariate-lags",
        "preprocessing_config": {
            "scaling": "none",
            "differencing": "first_difference",
            "conformal_calibration_quantiles": "outputs/forecasting/buildconnect_conformal_results.csv",
        },
        "training_dataset_desc": "Official Indian Wholesale Price Index (WPI) for 20 construction materials.",
        "dataset_provenance": "REAL_WPI",
        "training_period": "2012-04 to 2021-03",
        "validation_period": "2021-04 to 2023-03",
        "test_period": "2023-04 to 2026-03",
        "frozen_parameters": {
            "decision_threshold_pct": 0.25,
            "conformal_confidence_levels": [0.80, 0.90, 0.95],
        },
        "deployment_status": "production_frozen",
        "documentation_reference": "documentation/compatibility_report.md#price-forecasting",
    },
    {
        "model_name": "ARIMA",
        "model_version": "v1.0-benchmark",
        "task_type": "price_forecast",
        "artifact_location": "models/buildconnect_models/arima/arima_opc_111.pkl",
        "feature_schema_version": "v1.0-arima-order-1-1-1",
        "preprocessing_config": {"differencing_order": 1},
        "training_dataset_desc": "Ordinary Portland Cement WPI Series.",
        "dataset_provenance": "REAL_WPI",
        "training_period": "2012-04 to 2023-03",
        "validation_period": "none",
        "test_period": "2023-04 to 2026-03",
        "frozen_parameters": {"p": 1, "d": 1, "q": 1},
        "deployment_status": "comparison_only",
        "documentation_reference": "documentation/compatibility_report.md#arima-benchmark",
    },
    {
        "model_name": "XGBoost Price Forecaster",
        "model_version": "v1.0-benchmark",
        "task_type": "price_forecast",
        "artifact_location": "models/buildconnect_models/xgboost/xgboost_opc.json",
        "feature_schema_version": "v1.0-lag-features",
        "preprocessing_config": {"lags": [1, 2, 3, 6, 12]},
        "training_dataset_desc": "WPI historical dataset with recursive lag feature extraction.",
        "dataset_provenance": "REAL_WPI",
        "training_period": "2012-04 to 2021-03",
        "validation_period": "2021-04 to 2023-03",
        "test_period": "2023-04 to 2026-03",
        "frozen_parameters": {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.05},
        "deployment_status": "comparison_only",
        "documentation_reference": "outputs/forecasting/buildconnect_xgboost_results.csv",
    },
    {
        "model_name": "LSTM Neural Forecaster",
        "model_version": "v1.0-experimental",
        "task_type": "price_forecast",
        "artifact_location": "models/buildconnect_models/lstm/lstm_opc.keras",
        "feature_schema_version": "v1.0-sequence-window",
        "preprocessing_config": {"window_size": 12, "feature_scaler": "lstm_feature_scaler.pkl"},
        "training_dataset_desc": "Normalized sequential WPI values for deep recurrent learning.",
        "dataset_provenance": "REAL_WPI",
        "training_period": "2012-04 to 2021-03",
        "validation_period": "2021-04 to 2023-03",
        "test_period": "2023-04 to 2026-03",
        "frozen_parameters": {"units": 64, "dropout": 0.2, "epochs": 50},
        "deployment_status": "comparison_only",
        "documentation_reference": "models/buildconnect_models/lstm/lstm_config.json",
    },
    {
        "model_name": "Supplier Delivery Risk Classifier",
        "model_version": "v1.0-experimental",
        "task_type": "supplier_risk",
        "artifact_location": "data/supplier/buildconnect_synthetic_supplier_orders.csv",
        "feature_schema_version": "v1.0-supplier-profile",
        "preprocessing_config": {
            "features": [
                "historical_delivery_success", "historical_avg_delay",
                "cancellation_rate", "distance_km", "availability_ratio", "supplier_rating"
            ]
        },
        "training_dataset_desc": "Synthetic supplier orders (10,000 observations) used for research feasibility.",
        "dataset_provenance": "SYNTHETIC_RESEARCH",
        "training_period": "Simulated 2024-2026",
        "validation_period": "none",
        "test_period": "none",
        "frozen_parameters": {"synthetic_risk_weights": [0.35, 0.20, 0.15, 0.10, 0.10, 0.10]},
        "deployment_status": "experimental",
        "documentation_reference": "data/supplier/buildconnect_supplier_shap_importance.csv",
    },
    {
        "model_name": "Heuristic Procurement Pareto Comparison",
        "model_version": "v1.1-heuristic-pareto",
        "task_type": "procurement_optimizer",
        "artifact_location": "backend/services/procurement_optimizer.py",
        "feature_schema_version": "v1.0-procurement-demands",
        "preprocessing_config": {"normalization": "min-max-bounds"},
        "training_dataset_desc": "Pareto comparison of four heuristic plans using live project requirements and quotes; not an NSGA-II search.",
        "dataset_provenance": "USER_ENTERED",
        "training_period": "Live execution",
        "validation_period": "none",
        "test_period": "none",
        "frozen_parameters": {
            "objectives": ["cost", "risk", "lead_time", "shortage"],
            "candidate_strategies": ["cheapest", "lowest_risk", "fastest", "weighted_risk_cost"],
            "default_allocation_strategy": "weighted_risk_cost",
        },
        "deployment_status": "production_frozen",
        "documentation_reference": "documentation/procurement_optimizer.md",
    },
]

def seed_model_registry(conn):
    """Ensure standard models are registered in model_registry table."""
    for m in DEFAULT_REGISTRY_MODELS:
        existing = conn.execute(
            "SELECT id FROM model_registry WHERE model_name = ? AND model_version = ?",
            (m["model_name"], m["model_version"]),
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO model_registry
                   (model_name, model_version, task_type, artifact_location,
                    feature_schema_version, preprocessing_config_json, training_dataset_desc,
                    dataset_provenance, training_period, validation_period, test_period,
                    frozen_parameters_json, deployment_status, documentation_reference)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    m["model_name"],
                    m["model_version"],
                    m["task_type"],
                    m["artifact_location"],
                    m["feature_schema_version"],
                    json.dumps(m["preprocessing_config"]),
                    m["training_dataset_desc"],
                    m["dataset_provenance"],
                    m["training_period"],
                    m["validation_period"],
                    m["test_period"],
                    json.dumps(m["frozen_parameters"]),
                    m["deployment_status"],
                    m["documentation_reference"],
                ),
            )
    conn.commit()
