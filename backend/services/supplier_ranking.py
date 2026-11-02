from typing import Dict, Any, List, Optional
from services.supplier_features import extract_leakage_safe_supplier_features

DEFAULT_RANKING_WEIGHTS: Dict[str, float] = {
    "price": 0.35,
    "delivery_speed": 0.20,
    "availability": 0.15,
    "risk_reliability": 0.15,
    "supplier_reputation": 0.10,
    "verification": 0.05,
}

def rank_supplier_quotations(
    conn,
    material: str,
    required_quantity: float,
    deadline_days: int = 365,
    transport_rate_coefficient: float = 0.02,
    custom_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Evaluates and ranks supplier quotes transparently using multi-criteria weighted utility.
    """
    weights = dict(DEFAULT_RANKING_WEIGHTS)
    if custom_weights:
        for k, v in custom_weights.items():
            if k in weights and isinstance(v, (int, float)) and v >= 0:
                weights[k] = float(v)
    
    total_w = sum(weights.values())
    if total_w <= 0:
        weights = dict(DEFAULT_RANKING_WEIGHTS)
        total_w = sum(weights.values())
    weights = {k: v / total_w for k, v in weights.items()}

    # Retrieve all quotes for this material
    quotes = conn.execute(
        """SELECT q.*, s.name AS supplier_name, s.category, s.city, s.verified, s.rating,
                  s.review_count, s.demo AS supplier_demo, s.owner_user_id
           FROM supplier_quotes q
           JOIN suppliers s ON s.id = q.supplier_id
           WHERE lower(q.material) = lower(?)
             AND (s.demo = 1 OR s.owner_user_id IS NOT NULL)
             AND q.available_quantity > 0
           ORDER BY q.id""",
        (material,),
    ).fetchall()

    if not quotes:
        return {
            "material": material,
            "required_quantity": required_quantity,
            "deadline_days": deadline_days,
            "weights": weights,
            "ranked_quotes": [],
            "explanation": "No available supplier quotations found for this material.",
        }

    # Pre-calculate min/max for normalization
    prices = [float(q["quote_price"]) + transport_rate_coefficient * float(q["distance_km"] or 0) for q in quotes]
    delivery_times = [int(q["delivery_days"]) for q in quotes]
    min_price = min(prices)
    max_price = max(prices)
    min_delivery = min(delivery_times)
    max_delivery = max(delivery_times)

    scored_items: List[Dict[str, Any]] = []

    for q in quotes:
        supplier_id = q["supplier_id"]
        features = extract_leakage_safe_supplier_features(conn, supplier_id)
        
        # Calculate delivered price (quote price + estimated transport)
        effective_price = float(q["quote_price"]) + transport_rate_coefficient * float(q["distance_km"] or 0)
        
        # 1. Price score (lower price is better: 1.0 for min_price, scaling down)
        price_score = min_price / max(effective_price, 0.01)

        # 2. Delivery speed score (fewer days is better)
        delivery_score = min_delivery / max(int(q["delivery_days"]), 1)

        # 3. Availability score (can they fulfill the requirement?)
        avail_ratio = min(1.0, float(q["available_quantity"]) / max(required_quantity, 1e-6))
        availability_score = avail_ratio

        # 4. Risk & Reliability score
        # Use genuine historical delivery success rate if evidence >= low, otherwise demo score or neutral with warning
        if features["evidence_level"] in {"moderate", "high"} and features["delivery_success_rate"] is not None:
            risk_score = features["delivery_success_rate"]
            risk_evidence = f"Historical success ({features['total_orders']} orders: {features['delivery_success_rate']:.1%})"
            estimated_late_prob = 1.0 - features["delivery_success_rate"]
        elif features["evidence_level"] == "low" and features["delivery_success_rate"] is not None:
            risk_score = 0.5 * features["delivery_success_rate"] + 0.5 * 0.7 # regress to neutral
            risk_evidence = f"Limited history ({features['total_orders']} orders)"
            estimated_late_prob = 1.0 - features["delivery_success_rate"]
        elif (q["demo"] or q["supplier_demo"]) and q["risk_score"] is not None:
            risk_score = 1.0 - float(q["risk_score"])
            risk_evidence = "Demo simulation benchmark"
            estimated_late_prob = float(q["risk_score"])
        else:
            risk_score = 0.5 # Neutral score for unproven supplier
            risk_evidence = "Insufficient genuine history"
            estimated_late_prob = None

        # 5. Reputation score (Bayesian average rating out of 5)
        reputation_score = min(1.0, max(0.0, features["bayesian_rating"] / 5.0))

        # 6. Verification score
        is_verified = bool(q["verified"]) and not bool(q["supplier_demo"])
        verification_score = 1.0 if is_verified else 0.0

        # Weighted total
        contributions = {
            "price": weights["price"] * price_score,
            "delivery_speed": weights["delivery_speed"] * delivery_score,
            "availability": weights["availability"] * availability_score,
            "risk_reliability": weights["risk_reliability"] * risk_score,
            "supplier_reputation": weights["supplier_reputation"] * reputation_score,
            "verification": weights["verification"] * verification_score,
        }
        composite_score = sum(contributions.values())

        # Feasibility check
        within_deadline = int(q["delivery_days"]) <= deadline_days
        shortage = max(0.0, required_quantity - float(q["available_quantity"]))
        is_feasible = within_deadline and shortage <= 1e-9

        # Structured explanation
        pros = []
        cons = []
        if price_score > 0.85:
            pros.append("Highly competitive delivered price")
        elif price_score < 0.6:
            cons.append("Higher unit or transport cost compared to peers")

        if within_deadline:
            pros.append(f"Meets deadline ({q['delivery_days']} days vs {deadline_days} days limit)")
        else:
            cons.append(f"Exceeds required deadline ({q['delivery_days']} days promised)")

        if avail_ratio >= 1.0:
            pros.append("Full requirement quantity available")
        else:
            cons.append(f"Capacity shortage of {shortage:,.1f} units")

        if is_verified:
            pros.append("Verified enterprise supplier credentials")
        else:
            cons.append("Unverified supplier documentation")

        explanation = {
            "summary": f"Ranked with composite utility score of {composite_score:.3f}.",
            "strengths": pros,
            "limitations": cons,
            "contributions": contributions,
            "risk_evidence_level": features["evidence_level"],
            "risk_evidence_description": risk_evidence,
        }

        scored_items.append({
            "quote_id": q["id"],
            "supplier_id": q["supplier_id"],
            "supplier_name": q["supplier_name"],
            "city": q["city"],
            "material": q["material"],
            "quote_price": float(q["quote_price"]),
            "effective_delivered_price": effective_price,
            "available_quantity": float(q["available_quantity"]),
            "delivery_days": int(q["delivery_days"]),
            "distance_km": q["distance_km"],
            "verified": is_verified,
            "demo": bool(q["demo"] or q["supplier_demo"]),
            "bayesian_rating": features["bayesian_rating"],
            "review_count": features["review_count"],
            "risk_probability": estimated_late_prob,
            "risk_evidence": risk_evidence,
            "feasible": is_feasible,
            "shortage_quantity": shortage,
            "score": composite_score,
            "criterion_contributions": contributions,
            "explanation": explanation,
        })

    # Sort descending by composite score, then by delivered price
    ranked = sorted(scored_items, key=lambda x: (-x["score"], x["effective_delivered_price"]))

    return {
        "material": material,
        "quantity": required_quantity,
        "deadline_days": deadline_days,
        "weights": weights,
        "ranked_quotes": ranked,
        "method": "Multi-criteria weighted utility normalization with Bayesian rating and leakage-safe history",
        "warning": "Risk estimates reflect recorded order history or benchmark simulations. Never treat scores as credit ratings.",
    }
