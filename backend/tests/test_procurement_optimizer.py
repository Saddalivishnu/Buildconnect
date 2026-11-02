"""Optimizer regressions using a disposable, in-memory database only."""

import sqlite3
from datetime import date, timedelta

import pytest

from services.procurement_optimizer import add_pareto_comparison, solve_procurement_plans


@pytest.fixture
def procurement_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE project_materials (
            id INTEGER PRIMARY KEY, project_id INTEGER, material TEXT,
            required_quantity REAL, current_inventory REAL, ordered_quantity REAL
        );
        CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY, name TEXT, demo INTEGER,
            verified INTEGER, owner_user_id INTEGER
        );
        CREATE TABLE supplier_quotes (
            id INTEGER PRIMARY KEY, supplier_id INTEGER, material TEXT,
            quote_price REAL, available_quantity REAL, delivery_days INTEGER,
            distance_km REAL, risk_score REAL, demo INTEGER
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY, supplier_id INTEGER, project_id INTEGER,
            quantity REAL, quoted_unit_price REAL, status TEXT, demo INTEGER
        );
        CREATE TABLE order_delivery_outcomes (
            order_id INTEGER, cancelled INTEGER, delay_days INTEGER
        );
        INSERT INTO project_materials VALUES (1, 1, 'Cement', 1, 0, 0);
        """
    )
    yield conn
    conn.close()


def add_quote(conn, supplier_id, price, delivery_days, risk):
    conn.execute(
        "INSERT INTO suppliers VALUES (?, ?, 1, 0, NULL)",
        (supplier_id, f"Demo supplier {supplier_id}"),
    )
    conn.execute(
        "INSERT INTO supplier_quotes VALUES (?, ?, 'Cement', ?, 1, ?, 0, ?, 1)",
        (supplier_id, supplier_id, price, delivery_days, risk),
    )


def solve(conn):
    plans, error = solve_procurement_plans(
        conn,
        {
            "id": 1,
            "budget": 1000,
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert error is None
    return plans


@pytest.mark.parametrize("competing_risk", [0.2, None])
def test_zero_risk_remains_a_pareto_tradeoff(procurement_db, competing_risk):
    # Same cost: the first quote trades slower delivery for evidenced zero risk.
    add_quote(procurement_db, 1, price=100, delivery_days=2, risk=0.0)
    add_quote(procurement_db, 2, price=100, delivery_days=1, risk=competing_risk)

    plans = solve(procurement_db)

    assert plans["lowest_risk"]["expected_late_delivery_risk"] == 0.0
    assert plans["fastest"]["expected_late_delivery_risk"] == competing_risk
    front = {
        plan["strategy"]: plan
        for plan in plans["pareto_comparison"]["pareto_front_solutions"]
    }
    assert {"lowest_risk", "fastest"} <= front.keys()
    assert front["lowest_risk"]["expected_late_delivery_risk"] == 0.0


def test_same_day_delivery_remains_a_pareto_tradeoff(procurement_db):
    # A higher price buys same-day delivery at the same risk level.
    add_quote(procurement_db, 1, price=110, delivery_days=0, risk=0.2)
    add_quote(procurement_db, 2, price=100, delivery_days=1, risk=0.2)

    plans = solve(procurement_db)

    assert plans["fastest"]["expected_delivery_days"] == 0
    front = {
        plan["strategy"]: plan
        for plan in plans["pareto_comparison"]["pareto_front_solutions"]
    }
    assert {"cheapest", "fastest"} <= front.keys()
    assert front["fastest"]["expected_delivery_days"] == 0


def test_unavailable_quotes_preserve_missing_risk_and_delivery(procurement_db):
    plans = solve(procurement_db)

    comparison = plans["pareto_comparison"]
    assert comparison["allocations"] == []
    assert comparison["expected_late_delivery_risk"] is None
    assert comparison["expected_delivery_days"] is None
    assert comparison["shortage_quantity"] == 1
    assert comparison["feasible"] is False


def test_legacy_strategy_alias_preserves_procurement_result(procurement_db):
    add_quote(procurement_db, 1, price=100, delivery_days=2, risk=0.0)

    plans = solve(procurement_db)

    canonical = plans["pareto_comparison"]
    legacy = plans["nsga_ii"]
    assert canonical["strategy"] == "pareto_comparison"
    assert legacy["strategy"] == "nsga_ii"
    for field in (
        "allocations", "total_estimated_cost", "expected_late_delivery_risk",
        "expected_delivery_days", "shortage_quantity", "feasible",
        "pareto_front_solutions",
    ):
        assert legacy[field] == canonical[field]


def test_pareto_front_excludes_dominated_plans_and_preserves_equal_candidates():
    # Same price, lead time and shortage: evidenced zero risk wins over positive
    # or unknown risk, while two equal zero-risk candidates both remain valid.
    plans = {
        strategy: {
            "total_estimated_cost": 100,
            "expected_late_delivery_risk": risk,
            "estimated_delivery_days": 0,
            "shortage_quantity": 0,
            "feasible": True,
        }
        for strategy, risk in (
            ("cheapest", None),
            ("lowest_risk", 0.0),
            ("fastest", 0.2),
            ("weighted_risk_cost", 0.0),
        )
    }

    add_pareto_comparison(plans)

    assert {
        point["strategy"]
        for point in plans["pareto_comparison"]["pareto_front_solutions"]
    } == {"lowest_risk", "weighted_risk_cost"}
