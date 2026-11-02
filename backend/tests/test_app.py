from datetime import date, timedelta
from uuid import uuid4

import pytest

from app import app, startup_actions


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "DB_PATH", tmp_path / "buildconnect-test.db")
    startup_actions()
    app.config["TESTING"] = True
    return app.test_client()


def register(client, role="contractor"):
    email = f"{uuid4().hex}@example.test"
    body = {
        "name": "Test User",
        "email": email,
        "password": "correct-horse-battery",
        "role": role,
    }
    if role == "supplier":
        body["supplier_profile"] = {"category": "Cement", "city": "Hyderabad"}
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201
    return response.get_json()


def csrf(response):
    return {"X-CSRF-Token": response["csrf_token"]}


def test_health_and_real_wpi_routes(client):
    assert client.get("/api/health").status_code == 200
    materials = client.get("/api/materials").get_json()["materials"]
    assert len(materials) >= 20
    history = client.get("/api/materials/history?material=Ordinary%20Portland%20cement")
    assert history.status_code == 200
    assert history.get_json()["history"]


def test_forecast_intervals_and_buy_wait_use_saved_artifacts(client):
    auth = register(client)
    response = client.post(
        "/api/forecast",
        headers=csrf(auth),
        json={"material": "Ordinary Portland cement"},
    )
    assert response.status_code == 200
    forecast = response.get_json()
    assert forecast["status"] == "ok"
    assert forecast["model_name"] == "Trend-Adjusted Naive"
    assert forecast["alpha"] == pytest.approx(0.15)
    assert forecast["intervals"]["90"]["calibration_samples"] > 0
    assert forecast["forecast_id"]

    decision_response = client.post(
        "/api/buy-wait",
        headers=csrf(auth),
        json={"material": "Ordinary Portland cement"},
    )
    assert decision_response.status_code == 200
    decision = decision_response.get_json()
    assert decision["threshold_pct"] == 0.25
    assert decision["decision_explanation"]


def test_supplier_risk_does_not_apply_synthetic_history_to_real_supplier(client):
    auth = register(client)
    result_response = client.post(
        "/api/supplier-risk/predict",
        headers=csrf(auth),
        json={"material": "Steel structures"},
    )
    assert result_response.status_code == 200
    result = result_response.get_json()
    assert result["status"] == "low-evidence"
    assert result["risk_probability"] is None
    assert "Synthetic records are not used" in result["warning"]

    demo = client.post(
        "/api/supplier-risk/predict",
        headers=csrf(auth),
        json={"material": "Steel structures", "use_synthetic_demo": True, "distance_km": 40, "availability_ratio": 0.9, "supplier_rating": 4},
    ).get_json()
    assert demo["status"] == "experimental"
    assert "synthetic" in demo["warning"].lower()


def test_registration_login_role_permissions_and_password_hash(client):
    account = register(client)
    assert account["user"]["role"] == "contractor"
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/projects").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers=csrf(account)).status_code == 200
    assert client.get("/api/projects").status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": account["user"]["email"], "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    assert login.get_json()["user"]["id"] == account["user"]["id"]

    import sqlite3
    from app import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    stored = conn.execute("SELECT password_hash FROM users WHERE id = ?", (account["user"]["id"],)).fetchone()[0]
    conn.close()
    assert stored != "correct-horse-battery"

    bad_role = client.post(
        "/api/auth/register",
        json={"name": "Admin", "email": f"{uuid4().hex}@example.test", "password": "correct-horse-battery", "role": "administrator"},
    )
    assert bad_role.status_code == 400


def test_mutating_authenticated_endpoints_require_csrf_and_project_ownership(client):
    owner = register(client)
    stranger_client = app.test_client()
    stranger = register(stranger_client)
    payload = {
        "name": "Private project",
        "location": "Pune",
        "budget": 1000,
        "start_date": date.today().isoformat(),
        "deadline": (date.today() + timedelta(days=20)).isoformat(),
        "materials": [],
    }
    missing_csrf = client.post("/api/projects", json=payload)
    assert missing_csrf.status_code == 403
    created = client.post("/api/projects", headers=csrf(owner), json=payload)
    assert created.status_code == 201
    project_id = created.get_json()["project_id"]
    assert stranger_client.get(f"/api/projects/{project_id}").status_code == 403
    assert stranger_client.put(
        f"/api/projects/{project_id}",
        headers=csrf(stranger),
        json={"name": "Takeover"},
    ).status_code == 403


def test_supplier_can_publish_quotes_but_cannot_create_projects(client):
    supplier_auth = register(client, "supplier")
    quote = client.post(
        "/api/supplier-quotes",
        headers=csrf(supplier_auth),
        json={
            "material": "Ordinary Portland cement",
            "quote_price": 6200,
            "available_quantity": 100,
            "delivery_days": 3,
            "distance_km": 4,
        },
    )
    assert quote.status_code == 201
    quote_id = quote.get_json()["quote_id"]
    assert client.patch(
        f"/api/supplier-quotes/{quote_id}",
        headers=csrf(supplier_auth),
        json={"available_quantity": 120},
    ).status_code == 200
    assert client.post(
        "/api/projects",
        headers=csrf(supplier_auth),
        json={"name": "Forbidden", "location": "City", "budget": 100, "start_date": "2026-10-01", "deadline": "2026-12-01"},
    ).status_code == 403


def test_only_administrator_can_verify_real_suppliers(client):
    supplier_auth = register(client, "supplier")
    import sqlite3
    from werkzeug.security import generate_password_hash
    from app import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    supplier_id = conn.execute(
        "SELECT id FROM suppliers WHERE owner_user_id = ?",
        (supplier_auth["user"]["id"],),
    ).fetchone()[0]
    admin_email = f"{uuid4().hex}@example.test"
    admin_password = "correct-horse-battery"
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role, demo) VALUES (?, ?, ?, 'administrator', 0)",
        ("Test Administrator", admin_email, generate_password_hash(admin_password)),
    )
    conn.commit()
    demo_supplier_id = conn.execute(
        "SELECT id FROM suppliers WHERE demo = 1 ORDER BY id LIMIT 1"
    ).fetchone()[0]
    conn.close()

    contractor = app.test_client()
    contractor_auth = register(contractor)
    endpoint = f"/api/suppliers/{supplier_id}/verification"
    assert contractor.post(
        endpoint,
        headers=csrf(contractor_auth),
        json={"evidence_reference": "vendor-check-123"},
    ).status_code == 403

    admin = app.test_client()
    login = admin.post(
        "/api/auth/login",
        json={"email": admin_email, "password": admin_password},
    )
    assert login.status_code == 200
    admin_auth = login.get_json()
    verified = admin.post(
        endpoint,
        headers=csrf(admin_auth),
        json={"evidence_reference": "vendor-check-123"},
    )
    assert verified.status_code == 201
    assert verified.get_json()["verified"] is True
    assert admin.post(
        f"/api/suppliers/{demo_supplier_id}/verification",
        headers=csrf(admin_auth),
        json={"evidence_reference": "demo-check"},
    ).status_code == 409


def test_project_plan_approval_order_and_outcome_lifecycle(client):
    contractor = register(client)
    supplier = app.test_client()
    supplier_auth = register(supplier, "supplier")
    quote = supplier.post(
        "/api/supplier-quotes",
        headers=csrf(supplier_auth),
        json={
            "material": "Cement superfine",
            "quote_price": 100,
            "available_quantity": 20,
            "delivery_days": 2,
            "distance_km": 5,
        },
    )
    assert quote.status_code == 201

    project = client.post(
        "/api/projects",
        headers=csrf(contractor),
        json={
            "name": "Test construction project",
            "location": "Chennai",
            "budget": 5000,
            "start_date": date.today().isoformat(),
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
            "materials": [
                {"material": "Cement superfine", "required_quantity": 10, "current_inventory": 0, "ordered_quantity": 0, "unit_cost": 0},
            ],
        },
    )
    assert project.status_code == 201
    project_id = project.get_json()["project_id"]
    details = client.get(f"/api/projects/{project_id}").get_json()["project"]
    material_id = details["materials"][0]["id"]
    assert details["materials"][0]["required_quantity"] == 10

    assert client.patch(
        f"/api/project-materials/{material_id}",
        headers=csrf(contractor),
        json={"current_inventory": 2},
    ).status_code == 200

    ranking = client.post(
        "/api/suppliers/rank",
        headers=csrf(contractor),
        json={"material": "Cement superfine", "quantity": 8, "deadline_days": 30},
    )
    assert ranking.status_code == 200
    ranked = ranking.get_json()["ranked_quotes"]
    assert any(row["supplier_name"] == "Test User" and row["feasible"] for row in ranked)

    comparison = client.post(
        "/api/procurement/optimize",
        headers=csrf(contractor),
        json={"project_id": project_id},
    )
    assert comparison.status_code == 200
    plan_response = client.post(
        "/api/procurement/plans",
        headers=csrf(contractor),
        json={"project_id": project_id, "strategy": "cheapest"},
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.get_json()["plan_id"]
    assert client.post(
        "/api/orders",
        headers=csrf(contractor),
        json={"plan_id": plan_id},
    ).status_code == 409
    approval = client.post(
        f"/api/procurement/plans/{plan_id}/approve",
        headers=csrf(contractor),
        json={"decision": "approved", "comments": "Reviewed"},
    )
    assert approval.status_code == 200
    created_orders = client.post(
        "/api/orders",
        headers=csrf(contractor),
        json={"plan_id": plan_id},
    )
    assert created_orders.status_code == 201
    order_id = created_orders.get_json()["order_ids"][0]
    outcome = client.post(
        f"/api/orders/{order_id}/outcome",
        headers=csrf(contractor),
        json={"actual_delivery_date": date.today().isoformat(), "final_paid_price": 1010},
    )
    assert outcome.status_code == 200
    assert outcome.get_json()["delay_days"] == 0
    assert client.post(
        "/api/orders",
        headers=csrf(contractor),
        json={"plan_id": plan_id},
    ).status_code == 409

    report = client.get("/api/reports/orders.csv")
    assert report.status_code == 200
    assert b"actual_delivery_date" in report.data
    assert client.get("/api/forecasts/history").status_code == 200


def test_plan_is_rejected_if_project_demand_changes_before_approval(client):
    contractor = register(client)
    supplier = app.test_client()
    supplier_auth = register(supplier, "supplier")
    quote_response = supplier.post(
        "/api/supplier-quotes",
        headers=csrf(supplier_auth),
        json={
            "material": "Cement superfine",
            "quote_price": 100,
            "available_quantity": 20,
            "delivery_days": 2,
            "distance_km": 5,
        },
    )
    assert quote_response.status_code == 201
    project = client.post(
        "/api/projects",
        headers=csrf(contractor),
        json={
            "name": "Stale-plan test",
            "location": "Chennai",
            "budget": 5000,
            "start_date": date.today().isoformat(),
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
            "materials": [
                {"material": "Cement superfine", "required_quantity": 10, "current_inventory": 0, "ordered_quantity": 0, "unit_cost": 0},
            ],
        },
    )
    plan = client.post(
        "/api/procurement/plans",
        headers=csrf(contractor),
        json={"project_id": project.get_json()["project_id"], "strategy": "cheapest"},
    )
    assert plan.status_code == 201
    project_material = client.get(
        f"/api/projects/{project.get_json()['project_id']}"
    ).get_json()["project"]["materials"][0]
    assert client.patch(
        f"/api/project-materials/{project_material['id']}",
        headers=csrf(contractor),
        json={"current_inventory": 10},
    ).status_code == 200
    approval = client.post(
        f"/api/procurement/plans/{plan.get_json()['plan_id']}/approve",
        headers=csrf(contractor),
        json={"decision": "approved"},
    )
    assert approval.status_code == 409
    assert "changed since comparison" in approval.get_json()["error"]


def test_invalid_project_and_quantity_overallocation_are_rejected(client):
    contractor = register(client)
    response = client.post(
        "/api/projects",
        headers=csrf(contractor),
        json={
            "name": "Invalid project",
            "location": "City",
            "budget": 10,
            "start_date": "2026-11-01",
            "deadline": "2026-10-01",
            "materials": [],
        },
    )
    assert response.status_code == 400
    assert "deadline" in response.get_json()["error"]


@pytest.mark.parametrize("strategy", ["pareto_comparison", "nsga_ii"])
def test_pareto_comparison_and_legacy_alias_support_order_lifecycle(client, strategy):
    contractor = register(client)
    supplier = app.test_client()
    supplier_auth = register(supplier, "supplier")
    quote_response = supplier.post(
        "/api/supplier-quotes",
        headers=csrf(supplier_auth),
        json={
            "material": "Cement superfine",
            "quote_price": 100,
            "available_quantity": 20,
            "delivery_days": 2,
            "distance_km": 5,
        },
    )
    assert quote_response.status_code == 201
    quote_id = quote_response.get_json()["quote_id"]
    project_response = client.post(
        "/api/projects",
        headers=csrf(contractor),
        json={
            "name": f"Pareto compatibility {uuid4().hex}",
            "location": "Chennai",
            "budget": 5000,
            "start_date": date.today().isoformat(),
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
            "materials": [
                {
                    "material": "Cement superfine",
                    "required_quantity": 10,
                    "current_inventory": 0,
                    "ordered_quantity": 0,
                    "unit_cost": 0,
                },
            ],
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.get_json()["project_id"]

    comparison_response = client.post(
        "/api/procurement/optimize",
        headers=csrf(contractor),
        json={"project_id": project_id},
    )
    assert comparison_response.status_code == 200
    comparison = comparison_response.get_json()
    alternatives = comparison["alternatives"]
    assert set(alternatives) == {
        "cheapest", "lowest_risk", "fastest", "weighted_risk_cost",
        "pareto_comparison", "nsga_ii",
    }
    assert comparison["pareto_comparison"]["available"] is True
    assert comparison["nsga_ii"]["available"] is False
    canonical = alternatives["pareto_comparison"]
    assert canonical["strategy"] == "pareto_comparison"
    assert "heuristic" in canonical["note"].lower()
    assert canonical["pareto_synthesis"]
    assert canonical["pareto_front_solutions"]
    assert canonical["allocations"][0]["quote_id"] == quote_id
    assert canonical["allocations"][0]["quantity"] == 10
    legacy = alternatives["nsga_ii"]
    assert legacy["strategy"] == "nsga_ii"
    assert legacy["deprecated_alias_for"] == "pareto_comparison"
    assert legacy["allocations"] == canonical["allocations"]
    assert legacy["pareto_front_solutions"] == canonical["pareto_front_solutions"]

    plan_response = client.post(
        "/api/procurement/plans",
        headers=csrf(contractor),
        json={"project_id": project_id, "strategy": strategy},
    )
    assert plan_response.status_code == 201
    plan = plan_response.get_json()
    assert plan["selected_strategy"] == strategy
    plan_id = plan["plan_id"]
    assert client.post(
        "/api/orders",
        headers=csrf(contractor),
        json={"plan_id": plan_id},
    ).status_code == 409
    approval_response = client.post(
        f"/api/procurement/plans/{plan_id}/approve",
        headers=csrf(contractor),
        json={"decision": "approved"},
    )
    assert approval_response.status_code == 200
    orders_response = client.post(
        "/api/orders",
        headers=csrf(contractor),
        json={"plan_id": plan_id},
    )
    assert orders_response.status_code == 201
    assert len(orders_response.get_json()["order_ids"]) == 1
    orders = client.get("/api/orders").get_json()["orders"]
    created_order = next(row for row in orders if row["id"] == orders_response.get_json()["order_ids"][0])
    assert created_order["quote_id"] == quote_id
    assert created_order["quantity"] == 10
