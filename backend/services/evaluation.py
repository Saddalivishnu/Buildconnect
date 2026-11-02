import math
from typing import Dict, Any, List, Optional
import numpy as np

def evaluate_forecast_accuracy(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes standard time-series evaluation metrics for predictions against actual realized values:
    MAE, RMSE, MAPE, sMAPE, Interval Coverage, Average Width.
    """
    valid_pairs = [p for p in pairs if p.get("actual") is not None and p.get("predicted") is not None]
    if not valid_pairs:
        return {
            "status": "NO_GROUND_TRUTH",
            "sample_count": 0,
            "message": "No matched actual observations are available for the requested forecast window.",
        }

    actuals = np.array([float(p["actual"]) for p in valid_pairs])
    preds = np.array([float(p["predicted"]) for p in valid_pairs])
    n = len(actuals)

    mae = float(np.mean(np.abs(preds - actuals)))
    rmse = float(np.sqrt(np.mean((preds - actuals) ** 2)))

    # Safe MAPE avoiding division by zero
    non_zero = actuals != 0
    mape = float(np.mean(np.abs((actuals[non_zero] - preds[non_zero]) / actuals[non_zero])) * 100) if np.any(non_zero) else None

    # sMAPE
    denom = (np.abs(actuals) + np.abs(preds)) / 2.0
    valid_s = denom > 1e-6
    smape = float(np.mean(np.abs(preds[valid_s] - actuals[valid_s]) / denom[valid_s]) * 100) if np.any(valid_s) else None

    # Coverage for 80, 90, 95 intervals if present
    coverage_results = {}
    for cov_level in ("80", "90", "95"):
        hits = 0
        widths = []
        count_with_interval = 0
        for p in valid_pairs:
            intervals = p.get("intervals") or {}
            target_int = intervals.get(cov_level) or {}
            lower = target_int.get("lower")
            upper = target_int.get("upper")
            if lower is not None and upper is not None:
                count_with_interval += 1
                widths.append(upper - lower)
                if lower <= float(p["actual"]) <= upper:
                    hits += 1
        if count_with_interval > 0:
            coverage_results[f"coverage_{cov_level}"] = float(hits / count_with_interval)
            coverage_results[f"mean_width_{cov_level}"] = float(np.mean(widths))

    return {
        "status": "COMPUTED",
        "sample_count": n,
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape_pct": round(mape, 2) if mape is not None else None,
        "smape_pct": round(smape, 2) if smape is not None else None,
        "intervals": coverage_results,
    }

def evaluate_supplier_risk_model(conn) -> Dict[str, Any]:
    """
    Evaluates classification metrics on genuine recorded order delivery outcomes.
    If fewer than 10 genuine outcomes exist, returns INSUFFICIENT_REAL_LABELLED_DATA.
    """
    query = """
        SELECT ord.id, ord.supplier_id, ord.material, outcome.actual_delivery_date,
               outcome.final_paid_price, outcome.cancelled, outcome.delay_days,
               pred.predicted_late_probability
        FROM orders ord
        JOIN order_delivery_outcomes outcome ON outcome.order_id = ord.id
        LEFT JOIN supplier_risk_predictions pred ON pred.supplier_id = ord.supplier_id
        WHERE ord.demo = 0
    """
    records = conn.execute(query).fetchall()
    
    if len(records) < 10:
        return {
            "status": "INSUFFICIENT_REAL_LABELLED_DATA",
            "recorded_outcomes": len(records),
            "minimum_required_samples": 10,
            "message": "Real-world supplier risk evaluation requires at least 10 genuine recorded delivery outcomes. Synthetic benchmarks are never displayed as real performance.",
        }

    y_true = []
    y_prob = []
    for r in records:
        is_late = 1 if (r["cancelled"] == 1 or (r["delay_days"] or 0) > 0) else 0
        prob = r["predicted_late_probability"]
        if prob is not None:
            y_true.append(is_late)
            y_prob.append(float(prob))

    if len(y_prob) < 10:
        return {
            "status": "INSUFFICIENT_REAL_LABELLED_DATA",
            "matched_predictions_with_labels": len(y_prob),
            "message": "Fewer than 10 genuine orders had matched prediction scores at order time.",
        }

    y_true_arr = np.array(y_true)
    y_prob_arr = np.array(y_prob)
    y_pred_arr = (y_prob_arr >= 0.5).astype(int)

    tp = int(np.sum((y_pred_arr == 1) & (y_true_arr == 1)))
    fp = int(np.sum((y_pred_arr == 1) & (y_true_arr == 0)))
    tn = int(np.sum((y_pred_arr == 0) & (y_true_arr == 0)))
    fn = int(np.sum((y_pred_arr == 0) & (y_true_arr == 1)))

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float(2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    brier = float(np.mean((y_prob_arr - y_true_arr) ** 2))

    return {
        "status": "COMPUTED",
        "sample_size": len(y_true),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "brier_score": round(brier, 4),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "provenance": "REAL_TRANSACTION",
    }

def evaluate_procurement_outcomes(conn, project_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Compares recommended procurement plans with realized purchase order and delivery outcomes.
    """
    params = ()
    filter_clause = ""
    if project_id:
        filter_clause = "WHERE ord.project_id = ?"
        params = (project_id,)

    query = f"""
        SELECT ord.id, ord.project_id, ord.quantity, ord.quoted_unit_price,
               ord.promised_delivery_date, ord.status, ord.demo,
               outcome.actual_delivery_date, outcome.final_paid_price,
               outcome.actual_quantity_received, outcome.cancelled, outcome.delay_days
        FROM orders ord
        LEFT JOIN order_delivery_outcomes outcome ON outcome.order_id = ord.id
        {filter_clause}
        ORDER BY ord.id DESC
    """
    orders = conn.execute(query, params).fetchall()

    if not orders:
        return {
            "status": "NO_ORDERS",
            "message": "No purchase orders found for outcome evaluation.",
            "metrics": {},
        }

    total_orders = len(orders)
    delivered_orders = [o for o in orders if o["actual_delivery_date"] is not None]
    cancelled_orders = [o for o in orders if o["cancelled"] == 1]

    planned_spend = sum(float(o["quantity"]) * float(o["quoted_unit_price"]) for o in orders)
    realized_spend = sum(float(o["final_paid_price"]) for o in delivered_orders if o["final_paid_price"] is not None)

    avg_delay = np.mean([o["delay_days"] for o in delivered_orders if o["delay_days"] is not None]) if delivered_orders else 0.0

    return {
        "status": "COMPUTED",
        "total_orders_placed": total_orders,
        "completed_deliveries": len(delivered_orders),
        "cancellations": len(cancelled_orders),
        "planned_material_spend": round(planned_spend, 2),
        "realized_material_spend": round(realized_spend, 2),
        "cost_variance": round(realized_spend - planned_spend, 2) if delivered_orders else 0.0,
        "average_delivery_delay_days": round(float(avg_delay), 2),
        "provenance": "REAL_TRANSACTION",
    }
