from datetime import date, datetime
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

HEURISTIC_STRATEGIES = ("cheapest", "lowest_risk", "fastest", "weighted_risk_cost")


def add_pareto_comparison(results: Dict[str, Any]) -> None:
    """Compare the four heuristic plans; this is not an NSGA-II search."""
    def objectives(plan):
        risk = plan["expected_late_delivery_risk"]
        delivery = plan.get("estimated_delivery_days", plan.get("expected_delivery_days"))
        return (
            plan["total_estimated_cost"],
            1.0 if risk is None else risk,
            float("inf") if delivery is None else delivery,
            plan["shortage_quantity"],
        )

    points = []
    front = []
    for strategy in HEURISTIC_STRATEGIES:
        plan = results[strategy]
        point = {
            "strategy": strategy,
            "total_estimated_cost": plan["total_estimated_cost"],
            "expected_late_delivery_risk": plan["expected_late_delivery_risk"],
            "estimated_delivery_days": plan.get("estimated_delivery_days", plan.get("expected_delivery_days")),
            "shortage_quantity": plan["shortage_quantity"],
            "feasible": plan["feasible"],
        }
        point["expected_delivery_days"] = point["estimated_delivery_days"]
        points.append(point)
        values = objectives(plan)
        dominated = any(
            all(other <= value for other, value in zip(objectives(results[candidate]), values))
            and any(other < value for other, value in zip(objectives(results[candidate]), values))
            for candidate in HEURISTIC_STRATEGIES
            if candidate != strategy
        )
        if not dominated:
            front.append(point)

    note = (
        "Pareto comparison of four heuristic allocation plans, not an NSGA-II search or a global optimum. "
        "The default allocation is the balanced risk/cost plan; review the nondominated alternatives before approval. "
        "For comparison only, unknown risk is treated as 1.0 and unknown delivery time as unbounded; "
        "reported missing values remain null."
    )
    comparison = dict(results["weighted_risk_cost"])
    comparison.update({
        "strategy": "pareto_comparison",
        "method": "heuristic_pareto_comparison",
        "allocation_strategy": "weighted_risk_cost",
        "pareto_front_solutions": front,
        "pareto_synthesis": {
            "candidate_strategies": list(HEURISTIC_STRATEGIES),
            "tradeoff_points": points,
            "nondominated_strategies": [point["strategy"] for point in front],
            "objective_note": note,
        },
        "note": note,
    })
    results["pareto_comparison"] = comparison
    # Existing saved plans and API clients can continue using the old identifier.
    results["nsga_ii"] = {
        **comparison,
        "strategy": "nsga_ii",
        "deprecated_alias_for": "pareto_comparison",
    }


def calculate_supplier_late_prob(conn, supplier_id: int, demo_score: Optional[float] = None) -> Tuple[Optional[float], str]:
    """Calculate empirical late rate or return demo benchmark."""
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN o.cancelled = 1 OR o.delay_days > 0 THEN 1 ELSE 0 END) AS late
           FROM orders ord JOIN order_delivery_outcomes o ON o.order_id = ord.id
           WHERE ord.supplier_id = ? AND ord.demo = 0""",
        (supplier_id,),
    ).fetchone()
    count = row["total"] if row else 0
    if count >= 3:
        rate = float(row["late"] or 0) / float(count)
        return rate, f"empirical history ({count} orders)"
    if demo_score is not None:
        return float(demo_score), "synthetic research benchmark"
    return None, "insufficient history"

def solve_procurement_plans(
    conn,
    project: Dict[str, Any],
    transport_rate: float = 0.02,
    shortage_penalty: float = 1500.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Dict[str, Any], int]]]:
    """
    Computes four heuristic procurement alternatives and their Pareto comparison:
    1. cheapest
    2. lowest_risk
    3. fastest
    4. weighted_risk_cost
    5. pareto_comparison (nsga_ii is a legacy compatibility alias)
    """
    material_rows = conn.execute(
        "SELECT * FROM project_materials WHERE project_id = ? ORDER BY id",
        (project["id"],),
    ).fetchall()

    if not material_rows:
        return None, ({"error": "Project has no material requirements."}, 400)

    try:
        deadline_date = date.fromisoformat(project["deadline"])
        days_available = max(0, (deadline_date - date.today()).days)
    except Exception:
        days_available = 365

    committed_spend = conn.execute(
        """SELECT COALESCE(SUM(ord.quantity * ord.quoted_unit_price), 0) AS total
           FROM orders ord WHERE ord.project_id = ? AND ord.status != 'cancelled'""",
        (project["id"],),
    ).fetchone()["total"]
    remaining_budget = max(0.0, float(project["budget"]) - float(committed_spend))

    # Retrieve candidate quotes per requirement
    candidates_by_mat: Dict[int, List[Dict[str, Any]]] = {}
    for mat in material_rows:
        remaining_needed = max(
            0.0,
            float(mat["required_quantity"])
            - float(mat["current_inventory"])
            - float(mat["ordered_quantity"]),
        )
        quotes = conn.execute(
            """SELECT q.*, s.name AS supplier_name, s.demo AS supplier_demo,
                      s.verified, s.owner_user_id
               FROM supplier_quotes q
               JOIN suppliers s ON s.id = q.supplier_id
               WHERE lower(q.material) = lower(?)
                 AND (s.demo = 1 OR s.owner_user_id IS NOT NULL)
                 AND q.available_quantity > 0
               ORDER BY q.id""",
            (mat["material"],),
        ).fetchall()

        enriched = []
        for q in quotes:
            q_dict = dict(q)
            q_dict["within_deadline"] = int(q_dict["delivery_days"]) <= days_available
            late_prob, evidence = calculate_supplier_late_prob(
                conn,
                q_dict["supplier_id"],
                float(q_dict["risk_score"]) if q_dict.get("risk_score") is not None else None
            )
            q_dict["late_probability"] = late_prob
            q_dict["risk_evidence"] = evidence
            enriched.append(q_dict)
        candidates_by_mat[mat["id"]] = enriched

    def evaluate_strategy_allocation(strategy: str) -> Dict[str, Any]:
        allocations = []
        total_material_cost = 0.0
        total_transport_cost = 0.0
        max_delivery_days = 0
        total_risk_weighted = 0.0
        risk_quantity_accounted = 0.0
        total_shortage = 0.0

        for mat in material_rows:
            needed = max(
                0.0,
                float(mat["required_quantity"])
                - float(mat["current_inventory"])
                - float(mat["ordered_quantity"]),
            )
            if needed <= 1e-9:
                continue

            available_quotes = [q for q in candidates_by_mat[mat["id"]] if q["within_deadline"]]
            if not available_quotes:
                total_shortage += needed
                continue

            def sort_key(q: Dict[str, Any]):
                delivered_cost = float(q["quote_price"]) + transport_rate * float(q["distance_km"] or 0)
                risk = 1.0 if q["late_probability"] is None else float(q["late_probability"])
                lead = int(q["delivery_days"])
                if strategy == "cheapest":
                    return (delivered_cost, lead, risk)
                elif strategy == "fastest":
                    return (lead, delivered_cost, risk)
                elif strategy == "lowest_risk":
                    return (risk, lead, delivered_cost)
                else: # weighted_risk_cost
                    return (0.6 * delivered_cost + 0.4 * (risk * 10000), lead)

            sorted_quotes = sorted(available_quotes, key=sort_key)
            unfilled = needed

            for q in sorted_quotes:
                if unfilled <= 1e-9:
                    break
                alloc_qty = min(unfilled, float(q["available_quantity"]))
                if alloc_qty <= 0:
                    continue

                unit_transport = transport_rate * float(q["distance_km"] or 0)
                mat_cost = alloc_qty * float(q["quote_price"])
                trans_cost = alloc_qty * unit_transport

                total_material_cost += mat_cost
                total_transport_cost += trans_cost
                max_delivery_days = max(max_delivery_days, int(q["delivery_days"]))

                if q["late_probability"] is not None:
                    total_risk_weighted += alloc_qty * float(q["late_probability"])
                    risk_quantity_accounted += alloc_qty

                allocations.append({
                    "project_material_id": mat["id"],
                    "material": mat["material"],
                    "supplier_id": q["supplier_id"],
                    "supplier_name": q["supplier_name"],
                    "quote_id": q["id"],
                    "quantity": alloc_qty,
                    "unit_price": float(q["quote_price"]),
                    "material_cost": mat_cost,
                    "transport_cost": trans_cost,
                    "total_line_cost": mat_cost + trans_cost,
                    "delivery_days": int(q["delivery_days"]),
                    "distance_km": float(q["distance_km"] or 0),
                    "late_probability": q["late_probability"],
                    "risk_evidence": q["risk_evidence"],
                    "demo": bool(q["demo"] or q["supplier_demo"]),
                })
                unfilled -= alloc_qty

            total_shortage += max(0.0, unfilled)

        total_est_cost = total_material_cost + total_transport_cost
        avg_risk = (total_risk_weighted / risk_quantity_accounted) if risk_quantity_accounted > 0 else None

        return {
            "strategy": strategy,
            "allocations": allocations,
            "material_cost": total_material_cost,
            "transport_cost": total_transport_cost,
            "total_estimated_cost": total_est_cost,
            "expected_delivery_days": max_delivery_days if allocations else None,
            "estimated_delivery_days": max_delivery_days if allocations else None,
            "expected_late_delivery_risk": avg_risk,
            "estimated_delivery_risk": avg_risk,
            "shortage_quantity": total_shortage,
            "shortage_penalty_assumption": shortage_penalty,
            "shortage_penalty_estimate": total_shortage * shortage_penalty,
            "objective_cost_including_shortage_penalty": total_est_cost + total_shortage * shortage_penalty,
            "remaining_budget": remaining_budget,
            "budget_compliant": total_est_cost <= remaining_budget,
            "project_deadline_days": days_available,
            "feasible": (total_shortage <= 1e-9) and (total_est_cost <= remaining_budget),
        }

    results: Dict[str, Any] = {}
    for strat in HEURISTIC_STRATEGIES:
        results[strat] = evaluate_strategy_allocation(strat)

    add_pareto_comparison(results)

    return results, None
