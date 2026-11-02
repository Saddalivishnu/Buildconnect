from datetime import datetime, date
from typing import Dict, Any, List, Optional
import numpy as np

def compute_bayesian_rating(raw_rating: Optional[float], review_count: int, prior_mean: float = 4.0, prior_weight: int = 5) -> float:
    """
    Bayesian average rating calculation:
    weighted_rating = (v * R + m * C) / (v + m)
    where:
      v = review_count
      R = raw_rating
      m = prior_weight (default 5 reviews)
      C = prior_mean (default 4.0)
    This prevents suppliers with 1 review of 5.0 from outranking established suppliers with 50 reviews of 4.8.
    """
    if raw_rating is None or review_count <= 0:
        return float(prior_mean)
    return float((review_count * raw_rating + prior_weight * prior_mean) / (review_count + prior_weight))

def extract_leakage_safe_supplier_features(
    conn,
    supplier_id: int,
    prediction_time: Optional[datetime] = None,
    current_quote: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate historical features for a supplier using only records strictly preceding prediction_time.
    Ensures zero target leakage.
    """
    if prediction_time is None:
        prediction_time = datetime.utcnow()
    
    cutoff_iso = prediction_time.isoformat()

    # Query all completed orders with outcomes recorded prior to cutoff
    query = """
        SELECT ord.id AS order_id, ord.quantity, ord.quoted_unit_price, ord.promised_delivery_date,
               ord.created_at, outcome.actual_delivery_date, outcome.final_paid_price,
               outcome.cancelled, outcome.delay_days, outcome.created_at AS outcome_time
        FROM orders ord
        JOIN order_delivery_outcomes outcome ON outcome.order_id = ord.id
        WHERE ord.supplier_id = ?
          AND ord.demo = 0
          AND outcome.created_at < ?
        ORDER BY outcome.created_at ASC
    """
    historical_outcomes = conn.execute(query, (supplier_id, cutoff_iso)).fetchall()
    total_prior_orders = len(historical_outcomes)

    # Determine evidence level
    if total_prior_orders < 3:
        evidence_level = "insufficient"
    elif total_prior_orders < 10:
        evidence_level = "low"
    elif total_prior_orders < 25:
        evidence_level = "moderate"
    else:
        evidence_level = "high"

    # Query supplier profile details
    supplier_row = conn.execute(
        "SELECT id, name, rating, review_count, verified, availability FROM suppliers WHERE id = ?",
        (supplier_id,)
    ).fetchone()
    
    raw_rating = float(supplier_row["rating"]) if supplier_row and supplier_row["rating"] is not None else 4.0
    review_count = int(supplier_row["review_count"]) if supplier_row and supplier_row["review_count"] else 0
    bayesian_rating = compute_bayesian_rating(raw_rating, review_count)

    if total_prior_orders == 0:
        return {
            "supplier_id": supplier_id,
            "total_orders": 0,
            "evidence_level": evidence_level,
            "delivery_success_rate": None,
            "average_delay_days": None,
            "cancellation_rate": None,
            "fulfillment_rate": None,
            "raw_rating": raw_rating,
            "review_count": review_count,
            "bayesian_rating": bayesian_rating,
            "is_verified": bool(supplier_row["verified"]) if supplier_row else False,
            "warning": "New supplier with zero recorded genuine prior order outcomes. Historical risk features are unavailable.",
        }

    cancelled_count = sum(1 for row in historical_outcomes if row["cancelled"] == 1)
    delayed_count = sum(1 for row in historical_outcomes if row["cancelled"] == 0 and (row["delay_days"] or 0) > 0)
    on_time_count = sum(1 for row in historical_outcomes if row["cancelled"] == 0 and (row["delay_days"] or 0) <= 0)
    
    delivery_success_rate = on_time_count / total_prior_orders
    cancellation_rate = cancelled_count / total_prior_orders
    
    delays = [row["delay_days"] for row in historical_outcomes if row["delay_days"] is not None and row["cancelled"] == 0]
    avg_delay_days = float(np.mean(delays)) if delays else 0.0

    return {
        "supplier_id": supplier_id,
        "total_orders": total_prior_orders,
        "evidence_level": evidence_level,
        "delivery_success_rate": float(delivery_success_rate),
        "late_rate": float(1.0 - delivery_success_rate),
        "average_delay_days": float(avg_delay_days),
        "cancellation_rate": float(cancellation_rate),
        "raw_rating": raw_rating,
        "review_count": review_count,
        "bayesian_rating": bayesian_rating,
        "is_verified": bool(supplier_row["verified"]) if supplier_row else False,
        "warning": None if evidence_level in {"moderate", "high"} else f"Limited evidence ({total_prior_orders} orders recorded).",
    }
