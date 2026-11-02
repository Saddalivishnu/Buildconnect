import json
import csv
import io
import math
import os
import re
import secrets
import sqlite3
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from flask import Flask, g, jsonify, make_response, request, session
from flask_cors import CORS
from sqlalchemy import create_engine, inspect as sqlalchemy_inspect, text
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from database import (
    DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY, ACCESS_TOKEN_EXPIRES_MINUTES,
    REFRESH_TOKEN_EXPIRES_DAYS, CORS_ALLOWED_ORIGINS, FLASK_ENV
)
from services.provenance import DataProvenance, PROVENANCE_DESCRIPTIONS, tag_provenance
from services.supplier_features import extract_leakage_safe_supplier_features, compute_bayesian_rating
from services.supplier_ranking import rank_supplier_quotations
from services.procurement_optimizer import add_pareto_comparison, solve_procurement_plans
from services.evaluation import (
    evaluate_forecast_accuracy, evaluate_supplier_risk_model, evaluate_procurement_outcomes
)
from services.model_registry import seed_model_registry
from services.importer_exporter import validate_csv_import, IMPORT_SCHEMAS

ROOT_DIR = Path(os.environ.get("BUILDCONNECT_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
DB_PATH = ROOT_DIR / "buildconnect.db"
WPI_PATH = ROOT_DIR / "data" / "wpi" / "BuildConnect_Construction_Materials_Final.csv"
SUPPLIER_PATH = ROOT_DIR / "data" / "supplier" / "buildconnect_synthetic_supplier_orders.csv"
CONFORMAL_PATH = ROOT_DIR / "outputs" / "forecasting" / "buildconnect_conformal_results.csv"
FINAL_RESULTS_PATH = ROOT_DIR / "outputs" / "forecasting" / "buildconnect_final_adaptive_results.csv"

POSTGRES_ENGINE = (
    create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    if DATABASE_URL.startswith(("postgresql://", "postgresql+"))
    else None
)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    JWT_SECRET_KEY=JWT_SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=FLASK_ENV == "production",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024, # 10 MB limit for file uploads/imports
)
CORS(
    app,
    supports_credentials=True,
    origins=CORS_ALLOWED_ORIGINS,
)

MATERIAL_NAMES = set(pd.read_csv(WPI_PATH, usecols=["material"])["material"].dropna().unique())



def error_response(message: str, status: int):
    return jsonify({"error": message}), status


def current_user() -> Optional[Dict[str, Any]]:
    user_id = session.get("user_id")
    if user_id is None:
        return None
    conn = get_connection()
    user = conn.execute(
        "SELECT id, name, email, role, demo FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return user


def authenticated(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return error_response("Authentication required.", 401)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = request.headers.get("X-CSRF-Token", "")
            if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
                return error_response("A valid CSRF token is required for this request.", 403)
        g.user = user
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @authenticated
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                return error_response("Your account role is not permitted to perform this action.", 403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def audit(conn, actor_id: Optional[int], action: str, entity: str, entity_id: int, details: Dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO audit_logs (actor_id, action, entity, entity_id, details_json) VALUES (?, ?, ?, ?, ?)",
        (actor_id, action, entity, entity_id, json.dumps(details, sort_keys=True)),
    )


def parse_iso_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).") from exc


def positive_number(value: Any, field: str, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number.") from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise ValueError(f"{field} must be {qualifier}.")
    return number


def dict_factory(cursor, row):
    columns = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(columns, row)}


def get_connection():
    if POSTGRES_ENGINE is not None:
        return PostgresConnection(POSTGRES_ENGINE.connect())
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class PostgresResult:
    def __init__(self, result):
        self.result = result
        self._inserted_id = None

    def fetchone(self):
        row = self.result.fetchone()
        return dict(row._mapping) if row is not None else None

    def fetchall(self):
        return [dict(row._mapping) for row in self.result.fetchall()]

    @property
    def rowcount(self):
        return self.result.rowcount

    @property
    def lastrowid(self):
        if self._inserted_id is None:
            row = self.fetchone()
            self._inserted_id = row.get("id") if row else None
        return self._inserted_id


class StaticResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        normalized = statement.strip()
        if normalized.upper().startswith("PRAGMA FOREIGN_KEYS"):
            return StaticResult([])
        pragma = re.fullmatch(r"PRAGMA table_info\((\w+)\)", normalized, re.IGNORECASE)
        if pragma:
            columns = sqlalchemy_inspect(self.connection).get_columns(pragma.group(1))
            return StaticResult([{"name": column["name"]} for column in columns])

        normalized = re.sub(
            r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
            "SERIAL PRIMARY KEY",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"DEFAULT\s+CURRENT_TIMESTAMP\b",
            "DEFAULT (CURRENT_TIMESTAMP::text)",
            normalized,
            flags=re.IGNORECASE,
        )
        if re.match(r"INSERT\s+OR\s+IGNORE", normalized, re.IGNORECASE):
            normalized = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", normalized, count=1, flags=re.IGNORECASE)
            if "ON CONFLICT" not in normalized.upper():
                normalized += " ON CONFLICT DO NOTHING"

        binds: Dict[str, Any] = {}
        if parameters:
            index = 0
            def replace_bind(_match):
                nonlocal index
                key = f"p{index}"
                binds[key] = parameters[index]
                index += 1
                return f":{key}"
            normalized = re.sub(r"\?", replace_bind, normalized)
        elif "?" in normalized:
            raise ValueError("SQL parameters were missing for a parameterized query.")

        is_insert = normalized.lstrip().upper().startswith("INSERT INTO")
        if is_insert and "RETURNING" not in normalized.upper() and "SCHEMA_MIGRATIONS" not in normalized.upper():
            normalized += " RETURNING id"
        return PostgresResult(self.connection.execute(text(normalized), binds))

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'contractor',
            demo INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            budget REAL NOT NULL,
            start_date TEXT NOT NULL,
            deadline TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_by INTEGER,
            demo INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            material TEXT NOT NULL,
            required_quantity REAL NOT NULL,
            current_inventory REAL NOT NULL,
            ordered_quantity REAL NOT NULL,
            unit_cost REAL NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            city TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            rating REAL,
            review_count INTEGER,
            verified INTEGER DEFAULT 0,
            availability TEXT DEFAULT 'Available',
            risk_category TEXT DEFAULT 'Unknown',
            demo INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            material TEXT NOT NULL,
            quote_price REAL NOT NULL,
            available_quantity REAL NOT NULL,
            delivery_days INTEGER NOT NULL,
            distance_km REAL,
            risk_score REAL,
            demo INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL UNIQUE,
            verified_by INTEGER NOT NULL,
            evidence_reference TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY(verified_by) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS procurement_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            selected_strategy TEXT NOT NULL,
            alternatives_json TEXT NOT NULL,
            assumptions_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS procurement_plan_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            project_material_id INTEGER NOT NULL,
            quote_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            FOREIGN KEY(plan_id) REFERENCES procurement_plans(id),
            FOREIGN KEY(project_material_id) REFERENCES project_materials(id),
            FOREIGN KEY(quote_id) REFERENCES supplier_quotes(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            actor_id INTEGER NOT NULL,
            decision TEXT NOT NULL,
            comments TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES procurement_plans(id),
            FOREIGN KEY(actor_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            plan_item_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            quote_id INTEGER NOT NULL,
            material TEXT NOT NULL,
            quantity REAL NOT NULL,
            quoted_unit_price REAL NOT NULL,
            promised_delivery_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'placed',
            demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES procurement_plans(id),
            FOREIGN KEY(plan_item_id) REFERENCES procurement_plan_items(id),
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY(quote_id) REFERENCES supplier_quotes(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_delivery_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            actual_delivery_date TEXT,
            final_paid_price REAL,
            cancelled INTEGER NOT NULL DEFAULT 0,
            delay_days INTEGER,
            recorded_by INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(actor_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requested_by INTEGER,
            material TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            point_forecast REAL NOT NULL,
            intervals_json TEXT NOT NULL,
            data_date TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            data_source TEXT NOT NULL,
            FOREIGN KEY(requested_by) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT 'Metric Ton',
            description TEXT,
            wpi_supported INTEGER DEFAULT 1,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_material_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            material_id INTEGER,
            material_name TEXT NOT NULL,
            quoted_unit_price REAL NOT NULL,
            available_quantity REAL NOT NULL,
            minimum_order_quantity REAL NOT NULL DEFAULT 1.0,
            unit TEXT NOT NULL DEFAULT 'Metric Ton',
            estimated_delivery_days INTEGER NOT NULL,
            availability_status TEXT DEFAULT 'Available',
            quote_valid_until TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY(material_id) REFERENCES material_catalog(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wpi_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            material_name TEXT NOT NULL,
            observation_date TEXT NOT NULL,
            index_value REAL NOT NULL,
            data_source TEXT NOT NULL DEFAULT 'REAL_WPI',
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(material_name, observation_date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_risk_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            material_id INTEGER,
            material_name TEXT,
            predicted_late_probability REAL,
            risk_category TEXT NOT NULL DEFAULT 'Unknown',
            model_name TEXT NOT NULL DEFAULT 'Empirical-History-Heuristic',
            model_version TEXT NOT NULL DEFAULT 'v1.0',
            input_data_provenance TEXT NOT NULL DEFAULT 'USER_ENTERED',
            prediction_evidence_level TEXT NOT NULL DEFAULT 'insufficient',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_order_id INTEGER NOT NULL,
            material_id INTEGER,
            material TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT 'Metric Ton',
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL,
            promised_delivery_date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(purchase_order_id) REFERENCES orders(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            purchase_order_id INTEGER NOT NULL,
            rating REAL NOT NULL,
            review_text TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'approved',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(purchase_order_id) REFERENCES orders(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS procurement_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            scenario_name TEXT NOT NULL,
            scenario_inputs TEXT NOT NULL,
            strategy TEXT NOT NULL,
            result_summary TEXT NOT NULL,
            is_demo INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            task_type TEXT NOT NULL,
            artifact_location TEXT,
            feature_schema_version TEXT DEFAULT 'v1.0',
            preprocessing_config_json TEXT,
            training_dataset_desc TEXT,
            dataset_provenance TEXT DEFAULT 'REAL_WPI',
            training_period TEXT,
            validation_period TEXT,
            test_period TEXT,
            frozen_parameters_json TEXT,
            deployment_status TEXT DEFAULT 'production_frozen',
            documentation_reference TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for table, column, definition in (
        ("users", "full_name", "TEXT"),
        ("users", "phone_number", "TEXT"),
        ("users", "account_status", "TEXT DEFAULT 'active'"),
        ("users", "updated_at", "TEXT"),
        ("users", "last_login_at", "TEXT"),
        ("suppliers", "owner_user_id", "INTEGER REFERENCES users(id)"),
        ("suppliers", "business_name", "TEXT"),
        ("suppliers", "business_description", "TEXT"),
        ("suppliers", "contact_person", "TEXT"),
        ("suppliers", "phone", "TEXT"),
        ("suppliers", "email", "TEXT"),
        ("suppliers", "address", "TEXT"),
        ("suppliers", "state", "TEXT"),
        ("suppliers", "postal_code", "TEXT"),
        ("suppliers", "verification_status", "TEXT DEFAULT 'unverified'"),
        ("suppliers", "account_status", "TEXT DEFAULT 'active'"),
        ("suppliers", "updated_at", "TEXT"),
        ("supplier_verifications", "verification_type", "TEXT DEFAULT 'business_license'"),
        ("supplier_verifications", "verification_status", "TEXT DEFAULT 'verified'"),
        ("supplier_verifications", "submitted_at", "TEXT"),
        ("supplier_verifications", "reviewed_at", "TEXT"),
        ("supplier_verifications", "notes", "TEXT"),
        ("projects", "owner_user_id", "INTEGER REFERENCES users(id)"),
        ("projects", "description", "TEXT"),
        ("projects", "latitude", "REAL"),
        ("projects", "longitude", "REAL"),
        ("projects", "archived_at", "TEXT"),
        ("projects", "updated_at", "TEXT"),
        ("project_materials", "material_id", "INTEGER"),
        ("project_materials", "unit", "TEXT DEFAULT 'Metric Ton'"),
        ("project_materials", "target_unit_price", "REAL"),
        ("project_materials", "required_by_date", "TEXT"),
        ("project_materials", "created_at", "TEXT"),
        ("project_materials", "updated_at", "TEXT"),
        ("supplier_quotes", "project_id", "INTEGER REFERENCES projects(id)"),
        ("supplier_quotes", "material_id", "INTEGER"),
        ("supplier_quotes", "quoted_quantity", "REAL"),
        ("supplier_quotes", "minimum_order_quantity", "REAL DEFAULT 1.0"),
        ("supplier_quotes", "unit", "TEXT DEFAULT 'Metric Ton'"),
        ("supplier_quotes", "transport_cost", "REAL"),
        ("supplier_quotes", "quotation_status", "TEXT DEFAULT 'active'"),
        ("supplier_quotes", "valid_until", "TEXT"),
        ("supplier_quotes", "updated_at", "TEXT"),
        ("procurement_plans", "strategy", "TEXT"),
        ("procurement_plans", "total_material_cost", "REAL"),
        ("procurement_plans", "total_transport_cost", "REAL"),
        ("procurement_plans", "total_estimated_cost", "REAL"),
        ("procurement_plans", "expected_delivery_days", "INTEGER"),
        ("procurement_plans", "estimated_delivery_risk", "REAL"),
        ("procurement_plans", "shortage_quantity", "REAL DEFAULT 0.0"),
        ("procurement_plans", "assumptions_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("procurement_plans", "is_demo", "INTEGER DEFAULT 0"),
        ("procurement_plans", "updated_at", "TEXT"),
        ("procurement_plan_items", "procurement_plan_id", "INTEGER"),
        ("procurement_plan_items", "supplier_id", "INTEGER"),
        ("procurement_plan_items", "material_id", "INTEGER"),
        ("procurement_plan_items", "allocated_quantity", "REAL"),
        ("procurement_plan_items", "quoted_unit_price", "REAL"),
        ("procurement_plan_items", "estimated_transport_cost", "REAL"),
        ("procurement_plan_items", "estimated_delivery_days", "INTEGER"),
        ("procurement_plan_items", "estimated_late_probability", "REAL"),
        ("procurement_plan_items", "created_at", "TEXT"),
        ("forecasts", "material_id", "INTEGER"),
        ("forecasts", "forecast_origin_date", "TEXT"),
        ("forecasts", "forecast_target_date", "TEXT"),
        ("forecasts", "current_index", "REAL"),
        ("forecasts", "predicted_index", "REAL"),
        ("forecasts", "interval_80_lower", "REAL"),
        ("forecasts", "interval_80_upper", "REAL"),
        ("forecasts", "interval_90_lower", "REAL"),
        ("forecasts", "interval_90_upper", "REAL"),
        ("forecasts", "interval_95_lower", "REAL"),
        ("forecasts", "interval_95_upper", "REAL"),
        ("forecasts", "input_data_provenance", "TEXT DEFAULT 'REAL_WPI'"),
        ("orders", "created_by", "INTEGER"),
        ("orders", "order_reference", "TEXT"),
        ("orders", "order_status", "TEXT DEFAULT 'placed'"),
        ("orders", "subtotal", "REAL"),
        ("orders", "transport_cost", "REAL DEFAULT 0.0"),
        ("orders", "total_cost", "REAL"),
        ("orders", "expected_delivery_date", "TEXT"),
        ("orders", "approved_by", "INTEGER"),
        ("orders", "approved_at", "TEXT"),
        ("orders", "updated_at", "TEXT"),
        ("order_delivery_outcomes", "purchase_order_id", "INTEGER"),
        ("order_delivery_outcomes", "purchase_order_item_id", "INTEGER"),
        ("order_delivery_outcomes", "actual_quantity_received", "REAL"),
        ("order_delivery_outcomes", "final_paid_unit_price", "REAL"),
        ("order_delivery_outcomes", "cancellation_status", "TEXT DEFAULT 'none'"),
        ("order_delivery_outcomes", "delivery_status", "TEXT DEFAULT 'delivered'"),
        ("order_delivery_outcomes", "recorded_at", "TEXT"),
        ("audit_logs", "actor_user_id", "INTEGER"),
        ("audit_logs", "entity_type", "TEXT"),
        ("audit_logs", "details", "TEXT"),
    ):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)")
    conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (2)")
    conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (3)")
    conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (4)")
    conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (5)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(created_by, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quotes_material ON supplier_quotes(material)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_project ON orders(project_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_order ON order_delivery_outcomes(order_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_supplier ON supplier_material_listings(supplier_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_supplier ON reviews(supplier_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_project ON procurement_scenarios(project_id)")
    conn.execute("UPDATE suppliers SET verified = 0 WHERE demo = 1")
    conn.commit()
    conn.close()



def seed_demo_data() -> None:
    conn = get_connection()
    existing_projects = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
    if existing_projects == 0:
        conn.execute(
            "INSERT INTO projects (name, location, budget, start_date, deadline, status, created_by, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("Civic Hospital Block A", "Hyderabad", 4200000, "2026-10-10", "2026-12-15", "active", 1, 1),
        )
        conn.execute(
            "INSERT INTO projects (name, location, budget, start_date, deadline, status, created_by, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("Urban Metro Station", "Bengaluru", 3100000, "2026-09-05", "2026-11-25", "active", 1, 1),
        )
        conn.execute(
            "INSERT INTO project_materials (project_id, material, required_quantity, current_inventory, ordered_quantity, unit_cost) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "Ordinary Portland cement", 1800, 400, 700, 6300),
        )
        conn.execute(
            "INSERT INTO project_materials (project_id, material, required_quantity, current_inventory, ordered_quantity, unit_cost) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "Steel structures", 250, 70, 90, 168000),
        )
        conn.execute(
            "INSERT INTO project_materials (project_id, material, required_quantity, current_inventory, ordered_quantity, unit_cost) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "Plain bricks", 3000, 1100, 900, 950),
        )
        conn.execute(
            "INSERT INTO project_materials (project_id, material, required_quantity, current_inventory, ordered_quantity, unit_cost) VALUES (?, ?, ?, ?, ?, ?)",
            (2, "Bitumen", 150, 25, 40, 54000),
        )

    existing_suppliers = conn.execute("SELECT COUNT(*) AS c FROM suppliers WHERE demo = 1").fetchone()["c"]
    if existing_suppliers == 0:
        suppliers = [
            ("Apex Steel Traders", "Steel", "Hyderabad", 17.3850, 78.4867, 4.4, 164, 0, "Available", "Medium", 1),
            ("GreenBuild Materials", "Cement", "Bengaluru", 12.9716, 77.5946, 4.1, 97, 0, "Limited", "Low", 1),
            ("Metro Supply Co.", "Brick", "Pune", 18.5204, 73.8567, 3.7, 53, 0, "Available", "High", 1),
        ]
        for supplier in suppliers:
            conn.execute(
                "INSERT INTO suppliers (name, category, city, latitude, longitude, rating, review_count, verified, availability, risk_category, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                supplier,
            )

    existing_quotes = conn.execute("SELECT COUNT(*) AS c FROM supplier_quotes").fetchone()["c"]
    if existing_quotes == 0:
        conn.execute(
            "INSERT INTO supplier_quotes (supplier_id, material, quote_price, available_quantity, delivery_days, distance_km, risk_score, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "Steel structures", 175000, 180, 11, 42.0, 0.31, 1),
        )
        conn.execute(
            "INSERT INTO supplier_quotes (supplier_id, material, quote_price, available_quantity, delivery_days, distance_km, risk_score, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (2, "Ordinary Portland cement", 6100, 2200, 7, 18.5, 0.22, 1),
        )
        conn.execute(
            "INSERT INTO supplier_quotes (supplier_id, material, quote_price, available_quantity, delivery_days, distance_km, risk_score, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (3, "Plain bricks", 1040, 3500, 6, 26.0, 0.44, 1),
        )

    # Seed material catalog
    df_wpi = load_wpi_data()
    mat_summary = df_wpi.groupby("material")["material_group"].first().to_dict()
    for mat_name, grp in mat_summary.items():
        conn.execute(
            """INSERT OR IGNORE INTO material_catalog
               (material_name, category, unit, wpi_supported, active)
               VALUES (?, ?, 'Metric Ton', 1, 1)""",
            (mat_name, str(grp) if pd.notna(grp) else "Construction"),
        )

    # Seed supplier material listings from demo quotes
    existing_listings = conn.execute("SELECT COUNT(*) AS c FROM supplier_material_listings").fetchone()["c"]
    if existing_listings == 0:
        demo_quotes = conn.execute("SELECT * FROM supplier_quotes WHERE demo = 1").fetchall()
        for q in demo_quotes:
            conn.execute(
                """INSERT INTO supplier_material_listings
                   (supplier_id, material_name, quoted_unit_price, available_quantity,
                    minimum_order_quantity, unit, estimated_delivery_days, availability_status)
                   VALUES (?, ?, ?, ?, 1.0, 'Metric Ton', ?, 'Available')""",
                (q["supplier_id"], q["material"], q["quote_price"], q["available_quantity"], q["delivery_days"]),
            )

    # Seed model registry
    seed_model_registry(conn)

    conn.commit()
    conn.close()



def load_wpi_data() -> pd.DataFrame:
    return pd.read_csv(WPI_PATH, parse_dates=["date"])


def load_supplier_data() -> pd.DataFrame:
    if not SUPPLIER_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(SUPPLIER_PATH)


def load_forecast_alpha() -> Dict[str, float]:
    if not FINAL_RESULTS_PATH.exists():
        return {}
    df = pd.read_csv(FINAL_RESULTS_PATH)
    if df.empty or not {"material", "best_alpha"}.issubset(df.columns):
        return {}
    lookups = df[["material", "best_alpha"]].dropna().drop_duplicates()
    return {str(k): float(v) for k, v in zip(lookups["material"], lookups["best_alpha"])}


def load_conformal_summary() -> Dict[str, Dict[str, Any]]:
    if not CONFORMAL_PATH.exists():
        return {}
    df = pd.read_csv(CONFORMAL_PATH)
    if df.empty:
        return {}
    summary: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        key = str(row["material"])
        confidence = int(round(float(row["confidence"]) * 100))
        summary.setdefault(key, {})[str(confidence)] = {
            "quantile": float(row["quantile"]),
            "interval_width": float(row["average_interval_width"]),
            "empirical_test_coverage": float(row["test_coverage"]),
            "calibration_samples": int(row["calibration_samples"]),
        }
    return summary


def material_history(material: str) -> List[Dict[str, Any]]:
    df = load_wpi_data()
    filtered = df[df["material"].str.lower() == material.lower()].copy().sort_values("date")
    if filtered.empty:
        return []
    return [{
        "date": row["date"].strftime("%Y-%m-%d"),
        "value": float(row["wpi"]),
    } for _, row in filtered.iterrows()]


def current_material_snapshot(material: str) -> Optional[Dict[str, Any]]:
    df = load_wpi_data()
    filtered = df[df["material"].str.lower() == material.lower()].copy().sort_values("date")
    if filtered.empty:
        return None
    latest = filtered.iloc[-1]
    previous = filtered.iloc[-2] if len(filtered) > 1 else latest
    return {
        "material": str(latest["material"]),
        "current_index": float(latest["wpi"]),
        "previous_index": float(previous["wpi"]),
        "date": str(latest["date"])[:10],
        "material_group": str(latest.get("material_group", "N/A")),
    }


def compute_trend_naive_forecast(material: str) -> Dict[str, Any]:
    snapshot = current_material_snapshot(material)
    if snapshot is None:
        raise ValueError(f"Material '{material}' was not found in the WPI dataset.")
    alpha_map = load_forecast_alpha()
    alpha = alpha_map.get(material) if material in alpha_map else alpha_map.get(material.strip())
    if alpha is None:
        return {
            "status": "unsupported-configuration",
            "material": material,
            "message": "No saved trend-adjusted alpha value was found for this material. Forecast generation requires a frozen configuration.",
        }

    forecast = snapshot["current_index"] + alpha * (snapshot["current_index"] - snapshot["previous_index"])
    conformal = load_conformal_summary().get(material, {})
    if not conformal:
        return {
            "status": "unsupported-configuration",
            "material": material,
            "message": "Saved conformal calibration is unavailable for this material; a supported uncertainty interval cannot be returned.",
        }
    intervals = {}
    for coverage in ("80", "90", "95"):
        calibration = conformal.get(coverage)
        if calibration:
            quantile = calibration["quantile"]
            intervals[coverage] = {
                "lower": float(forecast - quantile),
                "upper": float(forecast + quantile),
                "width": float(calibration["interval_width"]),
                "empirical_test_coverage": float(calibration["empirical_test_coverage"]),
                "calibration_samples": int(calibration["calibration_samples"]),
            }
    interval_90 = intervals.get("90") or intervals.get("80") or next(iter(intervals.values()))
    interval_width = interval_90["width"]
    expected_change_pct = ((forecast - snapshot["current_index"]) / snapshot["current_index"]) * 100
    uncertainty = "HIGH" if interval_width / max(snapshot["current_index"], 1.0) > 0.12 else "MEDIUM" if interval_width / max(snapshot["current_index"], 1.0) > 0.06 else "LOW"
    return {
        "status": "ok",
        "material": material,
        "current_wpi": float(snapshot["current_index"]),
        "previous_wpi": float(snapshot["previous_index"]),
        "forecast_wpi": float(forecast),
        "alpha": float(alpha),
        "expected_change_pct": float(expected_change_pct),
        "interval_width": float(interval_width),
        "intervals": intervals,
        "lower_80": intervals.get("80", {}).get("lower"),
        "upper_80": intervals.get("80", {}).get("upper"),
        "lower_90": intervals.get("90", {}).get("lower"),
        "upper_90": intervals.get("90", {}).get("upper"),
        "lower_95": intervals.get("95", {}).get("lower"),
        "upper_95": intervals.get("95", {}).get("upper"),
        "prediction_date": snapshot["date"],
        "model_name": "Trend-Adjusted Naive",
        "model_version": "frozen-alpha",
        "forecast_generation_time": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_provenance": "Real WPI dataset and frozen model metadata from the BuildConnect research package.",
        "uncertainty_indicator": uncertainty,
        "empirical_coverage": intervals.get("90", {}).get("empirical_test_coverage"),
        "calibration_samples": intervals.get("90", {}).get("calibration_samples"),
        "calibration_period": "See the saved BuildConnect conformal evaluation artifact; this is held-out historical test coverage.",
        "warning": "Historical empirical coverage does not guarantee future performance, especially when the index changes materially over time.",
    }


def decide_buy_wait(material: str, current_wpi: Optional[float] = None, project_deadline_days: Optional[int] = None) -> Dict[str, Any]:
    snapshot = current_material_snapshot(material)
    if snapshot is None:
        raise ValueError(f"Material '{material}' was not found in the WPI dataset.")
    current_value = current_wpi if current_wpi is not None else snapshot["current_index"]
    forecast = compute_trend_naive_forecast(material)
    if forecast.get("status") == "unsupported-configuration":
        return forecast

    expected_change_pct = ((forecast["forecast_wpi"] - current_value) / current_value) * 100
    threshold = 0.25
    uncertainty = forecast["uncertainty_indicator"]
    if project_deadline_days is not None and project_deadline_days <= 30:
        conflict = "Yes"
    else:
        conflict = "No"

    if abs(expected_change_pct) <= threshold:
        decision = "MONITOR — HIGH UNCERTAINTY" if uncertainty == "HIGH" else "MONITOR"
        explanation = "Movement is near the frozen directional threshold (0.25%); continue monitoring price signals."
    elif expected_change_pct > threshold:
        if uncertainty == "HIGH":
            decision = "BUY PARTIAL — HIGH UNCERTAINTY"
            explanation = "Forecast suggests price increase beyond 0.25% threshold, but wide prediction intervals warrant a partial buy to hedge risk."
        elif uncertainty == "MEDIUM":
            decision = "BUY PARTIAL"
            explanation = "Moderate price increase projected; staging partial purchase hedges against adverse movement."
        else:
            decision = "BUY NOW"
            explanation = "Forecast indicates upward price momentum with confident bounds. Immediate purchase locks in current prices."
    else:
        if conflict == "Yes":
            decision = "WAIT WITH CAUTION"
            explanation = "Forecast suggests price decline, but waiting conflicts with the upcoming project deadline (<= 30 days). Consider partial or immediate procurement to ensure supply."
        elif uncertainty == "HIGH":
            decision = "WAIT PARTIAL"
            explanation = "Forecast suggests a likely decline; elevated uncertainty suggests waiting with optional partial hedging."
        else:
            decision = "WAIT"
            explanation = "The forecast suggests a likely decline; waiting may reduce the purchase cost if the signal remains durable."


    return {
        "material": material,
        "current_wpi": float(current_value),
        "forecast_wpi": float(forecast["forecast_wpi"]),
        "expected_change_pct": float(expected_change_pct),
        "prediction_interval": {
            "lower_80": float(forecast["lower_80"]),
            "upper_80": float(forecast["upper_80"]),
            "lower_90": float(forecast["lower_90"]),
            "upper_90": float(forecast["upper_90"]),
            "lower_95": float(forecast["lower_95"]),
            "upper_95": float(forecast["upper_95"]),
        },
        "decision": decision,
        "decision_explanation": explanation,
        "uncertainty_indicator": uncertainty,
        "user_project_deadline_days": project_deadline_days,
        "waiting_conflicts_with_deadline": conflict,
        "threshold_pct": threshold,
        "data_source": "frozen BuildConnect recommendation logic",
        "model_warning": "This is a decision-support output, not financial certainty.",
    }


def supplier_risk_score(row: Dict[str, Any]) -> Dict[str, Any]:
    supplier_id = row.get("supplier_id")
    if supplier_id is not None:
        conn = get_connection()
        outcomes = conn.execute(
            """SELECT outcome.cancelled, outcome.delay_days
               FROM orders ord JOIN order_delivery_outcomes outcome ON outcome.order_id = ord.id
               WHERE ord.supplier_id = ? AND ord.demo = 0
                 AND outcome.created_at <= CAST(CURRENT_TIMESTAMP AS TEXT)
               ORDER BY outcome.created_at, outcome.id""",
            (supplier_id,),
        ).fetchall()
        conn.close()
        if len(outcomes) < 3:
            return {
                "status": "low-evidence",
                "risk_probability": None,
                "risk_category": "Unknown",
                "observed_order_outcomes": len(outcomes),
                "warning": "Fewer than three genuine prior order outcomes are available. No supplier-risk prediction is made.",
                "data_source": "User-recorded order outcomes only",
            }
        late = sum(bool(item["cancelled"]) or (item["delay_days"] or 0) > 0 for item in outcomes)
        rate = late / len(outcomes)
        category = "High" if rate >= 0.5 else "Medium" if rate >= 0.25 else "Low"
        return {
            "status": "empirical-history",
            "risk_probability": rate,
            "risk_category": category,
            "observed_order_outcomes": len(outcomes),
            "warning": "Descriptive rate from recorded prior outcomes, not a trained risk model or a guarantee of future performance.",
            "data_source": "User-recorded genuine order outcomes only",
        }

    if not row.get("use_synthetic_demo", False):
        return {
            "status": "low-evidence",
            "risk_probability": None,
            "risk_category": "Unknown",
            "observed_order_outcomes": 0,
            "warning": "No supplier-specific genuine order history was supplied. Synthetic records are not used for real supplier predictions.",
            "data_source": "No genuine supplier order history",
        }

    synthetic = load_supplier_data()
    if synthetic.empty:
        return {
            "status": "low-evidence",
            "risk_probability": 0.5,
            "risk_category": "Unknown",
            "warning": "No synthetic supplier-risk dataset is available in the current runtime.",
        }

    # This opt-in path is for demo exploration only; it is not a real supplier score.
    material_rows = synthetic[synthetic["material"].str.lower() == str(row.get("material", "")).lower()]
    if material_rows.empty:
        return {
            "status": "low-evidence",
            "risk_probability": 0.5,
            "risk_category": "Unknown",
            "warning": "The supplier lacks enough material history to score meaningfully; this result is low-evidence only.",
        }

    mean_delay = float(material_rows["historical_avg_delay"].mean())
    mean_success = float(material_rows["historical_delivery_success"].mean())
    mean_cancellation = float(material_rows["cancellation_rate"].mean())
    mean_distance = float(material_rows["distance_km"].mean())
    weight = (
        (1.0 - mean_success) * 0.35
        + min(mean_delay / 10.0, 1.0) * 0.2
        + min(mean_cancellation * 10.0, 1.0) * 0.15
        + min((row.get("distance_km", 0.0) / max(mean_distance, 1.0)) - 0.5, 1.0) * 0.1
        + max(0.0, 1.0 - float(row.get("availability_ratio", 1.0))) * 0.1
        + max(0.0, 1.0 - float(row.get("supplier_rating", 4.0)) / 5.0) * 0.1
    )
    risk_probability = float(np.clip(weight, 0.0, 1.0))
    if risk_probability > 0.7:
        risk_category = "High"
    elif risk_probability > 0.45:
        risk_category = "Medium"
    else:
        risk_category = "Low"

    return {
        "status": "experimental",
        "risk_probability": risk_probability,
        "risk_category": risk_category,
        "main_contributing_features": [
            "historical delivery success",
            "historical average delay",
            "cancellation rate",
            "distance",
            "availability",
            "supplier rating",
        ],
        "warning": "This supplier-risk score is synthetic and experimental; it must not be interpreted as a real supplier credit score.",
        "data_source": "Synthetic supplier-order simulation dataset",
    }


def get_dashboard_payload(user: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    project_filter = "" if user["role"] == "administrator" else " AND (created_by = ? OR demo = 1)"
    project_params: tuple = () if user["role"] == "administrator" else (user["id"],)
    active_projects = conn.execute(
        "SELECT COUNT(*) AS c FROM projects WHERE status = 'active'" + project_filter,
        project_params,
    ).fetchone()["c"]
    total_material_requirements = conn.execute(
        """SELECT COALESCE(SUM(pm.required_quantity), 0) AS total
           FROM project_materials pm JOIN projects p ON p.id = pm.project_id
           WHERE 1 = 1""" + project_filter.replace("created_by", "p.created_by").replace("demo", "p.demo"),
        project_params,
    ).fetchone()["total"]
    pending_decisions = conn.execute(
        """SELECT COUNT(*) AS c FROM procurement_plans plan
           JOIN projects p ON p.id = plan.project_id
           WHERE plan.status = 'proposed'""" + project_filter.replace("created_by", "p.created_by").replace("demo", "p.demo"),
        project_params,
    ).fetchone()["c"]
    risk_rows = conn.execute("SELECT risk_category, COUNT(*) AS count FROM suppliers GROUP BY risk_category").fetchall()
    project_rows = conn.execute(
        "SELECT * FROM projects WHERE 1 = 1" + project_filter + " ORDER BY created_at DESC LIMIT 5",
        project_params,
    ).fetchall()
    conn.close()
    history = material_history("Ordinary Portland cement")[-12:]

    return {
        "active_projects": int(active_projects),
        "total_material_requirements": float(total_material_requirements),
        "pending_procurement_decisions": int(pending_decisions),
        "supplier_risk_overview": {
            "low": sum(row["count"] for row in risk_rows if str(row["risk_category"]).lower() == "low"),
            "medium": sum(row["count"] for row in risk_rows if str(row["risk_category"]).lower() == "medium"),
            "high": sum(row["count"] for row in risk_rows if str(row["risk_category"]).lower() == "high"),
            "unknown": sum(row["count"] for row in risk_rows if str(row["risk_category"]).lower() not in {"low", "medium", "high"}),
            "demo_records_included": True,
        },
        "material_index_coverage": int(len(MATERIAL_NAMES)),
        "index_series": history,
        "index_series_material": "Ordinary Portland cement",
        "index_series_source": "Real WPI observation history",
        "recent_projects": project_rows,
        "demo_data_notice": "Project and supplier totals include sample demo records; the index series is real historical WPI data.",
    }


@app.teardown_appcontext
def close_connection(_):
    pass


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "project": "BuildConnect AI",
        "database": "postgresql" if POSTGRES_ENGINE is not None else "sqlite",
        "data_notes": [
            "WPI data is real historical construction-material index data.",
            "Supplier-risk data is synthetic experimental data and must be labeled accordingly.",
        ],
    })


@app.route("/api/auth/register", methods=["POST"])
def register():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    role = payload.get("role", "contractor")
    if not name or len(name) > 120:
        return error_response("Name is required and must be at most 120 characters.", 400)
    if not email or len(email) > 254 or "@" not in email:
        return error_response("A valid email address is required.", 400)
    if not isinstance(password, str) or len(password) < 12:
        return error_response("Password must be at least 12 characters.", 400)
    if role not in {"contractor", "supplier"}:
        return error_response("Registration is limited to contractor or supplier roles.", 400)

    supplier_profile = payload.get("supplier_profile") or {}
    if role == "supplier" and not all(str(supplier_profile.get(key, "")).strip() for key in ("category", "city")):
        return error_response("Supplier registration requires supplier_profile.category and supplier_profile.city.", 400)

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash, role, demo) VALUES (?, ?, ?, ?, 0)",
            (name, email, generate_password_hash(password), role),
        )
        user_id = cursor.lastrowid
        if role == "supplier":
            conn.execute(
                """INSERT INTO suppliers
                   (name, category, city, verified, availability, risk_category, demo, owner_user_id)
                   VALUES (?, ?, ?, 0, 'Available', 'Unknown', 0, ?)""",
                (name, supplier_profile["category"].strip(), supplier_profile["city"].strip(), user_id),
            )
        conn.commit()
    except (sqlite3.IntegrityError, SQLAlchemyIntegrityError):
        conn.rollback()
        return error_response("An account with this email already exists.", 409)
    finally:
        conn.close()

    session.clear()
    session["user_id"] = user_id
    session["csrf_token"] = secrets.token_urlsafe(32)
    session.permanent = True
    return jsonify({"user": {"id": user_id, "name": name, "email": email, "role": role, "demo": 0}, "csrf_token": session["csrf_token"]}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    if not email or not isinstance(password, str):
        return error_response("Email and password are required.", 400)

    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ? AND demo = 0", (email,)).fetchone()
    conn.close()
    if user is None or not check_password_hash(user["password_hash"], password):
        return error_response("Invalid email or password.", 401)
    session.clear()
    session["user_id"] = user["id"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    session.permanent = True
    return jsonify({"user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"], "demo": user["demo"]}, "csrf_token": session["csrf_token"]})


@app.route("/api/auth/logout", methods=["POST"])
@authenticated
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})


@app.route("/api/auth/me", methods=["GET"])
@authenticated
def auth_me():
    return jsonify({"user": g.user, "csrf_token": session.get("csrf_token")})


@app.route("/api/dashboard", methods=["GET"])
@authenticated
def dashboard():
    return jsonify(get_dashboard_payload(g.user))


@app.route("/api/materials", methods=["GET"])
def materials_list():
    df = load_wpi_data()
    material_names = sorted(df["material"].drop_duplicates().tolist())
    return jsonify({
        "materials": [
            {"name": name, "group": df[df["material"] == name]["material_group"].iloc[0] if not df[df["material"] == name].empty else "N/A"}
            for name in material_names
        ]
    })


@app.route("/api/materials/history", methods=["GET"])
def materials_history():
    material = request.args.get("material")
    if not material:
        return jsonify({"error": "material is required"}), 400
    history = material_history(material)
    if not history:
        return jsonify({"error": f"No WPI history found for {material}"}), 404
    return jsonify({"material": material, "history": history})


@app.route("/api/forecast", methods=["POST"])
@authenticated
def forecast_endpoint():
    payload = request.get_json(silent=True) or {}
    material = payload.get("material")
    if not material:
        return jsonify({"error": "material is required"}), 400
    try:
        result = compute_trend_naive_forecast(material)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    if result.get("status") == "unsupported-configuration":
        return jsonify(result), 422
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO forecasts
           (requested_by, material, model_name, model_version, point_forecast, intervals_json,
            data_date, generated_at, data_source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session.get("user_id"),
            result["material"],
            result["model_name"],
            result["model_version"],
            result["forecast_wpi"],
            json.dumps(result["intervals"], sort_keys=True),
            result["prediction_date"],
            result["forecast_generation_time"],
            result["data_provenance"],
        ),
    )
    result["forecast_id"] = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify(result)


@app.route("/api/buy-wait", methods=["POST"])
@authenticated
def buy_wait_endpoint():
    payload = request.get_json(silent=True) or {}
    material = payload.get("material")
    if not material:
        return jsonify({"error": "material is required"}), 400
    current_wpi = payload.get("current_wpi")
    deadline_days = payload.get("project_deadline_days")
    try:
        if current_wpi is not None:
            current_wpi = positive_number(current_wpi, "current_wpi")
        if deadline_days is not None:
            deadline_days = int(deadline_days)
            if deadline_days < 0 or deadline_days > 3650:
                raise ValueError("project_deadline_days must be between 0 and 3650.")
    except (TypeError, ValueError) as exc:
        return error_response(str(exc), 400)
    try:
        result = decide_buy_wait(
            material=material,
            current_wpi=current_wpi,
            project_deadline_days=deadline_days,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result)


@app.route("/api/supplier-risk/predict", methods=["POST"])
@roles_required("contractor", "administrator")
def supplier_risk_predict():
    payload = request.get_json(silent=True) or {}
    if not payload:
        return jsonify({"error": "request body is required"}), 400
    row = {
        "material": payload.get("material"),
        "supplier_id": payload.get("supplier_id"),
        "use_synthetic_demo": payload.get("use_synthetic_demo") is True,
    }
    if row["supplier_id"] is not None:
        try:
            row["supplier_id"] = int(row["supplier_id"])
        except (TypeError, ValueError):
            return error_response("supplier_id must be an integer.", 400)
    if row["use_synthetic_demo"]:
        try:
            row.update({
                "distance_km": positive_number(payload.get("distance_km", 0), "distance_km", allow_zero=True),
                "availability_ratio": positive_number(payload.get("availability_ratio", 1), "availability_ratio"),
                "supplier_rating": positive_number(payload.get("supplier_rating", 4), "supplier_rating"),
            })
        except (TypeError, ValueError) as exc:
            return error_response(str(exc), 400)
        if row["availability_ratio"] > 1 or row["supplier_rating"] > 5:
            return error_response("availability_ratio must be <= 1 and supplier_rating must be <= 5.", 400)
    return jsonify(supplier_risk_score(row))


@app.route("/api/suppliers", methods=["GET"])
@authenticated
def suppliers_list():
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, q.id AS quote_id, q.material AS quote_material,
                  q.quote_price, q.available_quantity, q.delivery_days,
                  q.distance_km, q.demo AS quote_demo
           FROM suppliers s LEFT JOIN supplier_quotes q ON q.supplier_id = s.id
           ORDER BY s.id DESC, q.id""",
    ).fetchall()
    conn.close()
    return jsonify({"suppliers": rows, "notice": "Demo suppliers and quotations are labeled demo; real listings come only from registered suppliers."})


@app.route("/api/suppliers/me", methods=["PATCH"])
@roles_required("supplier")
def update_supplier_profile():
    payload = request.get_json(silent=True) or {}
    allowed = {"category", "city"}
    updates = {key: str(payload[key]).strip() for key in allowed if key in payload}
    if not updates or any(not value or len(value) > 120 for value in updates.values()):
        return error_response("Provide a non-empty category and/or city (maximum 120 characters).", 400)
    conn = get_connection()
    profile = conn.execute("SELECT id FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
    if profile is None:
        conn.close()
        return error_response("Supplier profile was not found.", 404)
    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(f"UPDATE suppliers SET {assignments} WHERE id = ?", (*updates.values(), profile["id"]))
    audit(conn, g.user["id"], "supplier.profile.updated", "supplier", profile["id"], updates)
    conn.commit()
    conn.close()
    return jsonify({"message": "Supplier profile updated."})


@app.route("/api/suppliers/<int:supplier_id>/verification", methods=["POST"])
@roles_required("administrator")
def record_supplier_verification(supplier_id: int):
    payload = request.get_json(silent=True) or {}
    evidence = str(payload.get("evidence_reference", "")).strip()
    if not evidence or len(evidence) > 500:
        return error_response("A verification evidence reference is required (maximum 500 characters).", 400)
    conn = get_connection()
    supplier = conn.execute("SELECT id, demo FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if supplier is None:
        conn.close()
        return error_response("Supplier not found.", 404)
    if supplier["demo"]:
        conn.close()
        return error_response("Demo suppliers cannot be marked as verified.", 409)
    try:
        conn.execute(
            "INSERT INTO supplier_verifications (supplier_id, verified_by, evidence_reference) VALUES (?, ?, ?)",
            (supplier_id, g.user["id"], evidence),
        )
        conn.execute("UPDATE suppliers SET verified = 1 WHERE id = ?", (supplier_id,))
        audit(conn, g.user["id"], "supplier.verified", "supplier", supplier_id, {"evidence_reference": evidence})
        conn.commit()
    except (sqlite3.IntegrityError, SQLAlchemyIntegrityError):
        conn.rollback()
        conn.close()
        return error_response("A verification record already exists for this supplier.", 409)
    conn.close()
    return jsonify({"supplier_id": supplier_id, "verified": True}), 201


@app.route("/api/supplier-quotes", methods=["GET", "POST"])
@authenticated
def supplier_quotes_api():
    conn = get_connection()
    if request.method == "GET":
        material = request.args.get("material")
        query = """SELECT q.*, s.name AS supplier_name, s.city, s.verified,
                          s.demo AS supplier_demo
                   FROM supplier_quotes q JOIN suppliers s ON s.id = q.supplier_id
                   WHERE 1 = 1"""
        params: List[Any] = []
        if material:
            query += " AND lower(q.material) = lower(?)"
            params.append(material)
        query += " ORDER BY q.material, q.quote_price"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify({"quotes": rows})

    if g.user["role"] != "supplier":
        conn.close()
        return error_response("Only supplier accounts can publish quotations.", 403)
    payload = request.get_json(silent=True) or {}
    material = payload.get("material")
    if material not in MATERIAL_NAMES:
        conn.close()
        return error_response("material must match the WPI material catalogue.", 400)
    try:
        quote_price = positive_number(payload.get("quote_price"), "quote_price")
        available = positive_number(payload.get("available_quantity"), "available_quantity")
        delivery_days = int(payload.get("delivery_days"))
        distance = positive_number(payload.get("distance_km"), "distance_km", allow_zero=True)
        if delivery_days < 1 or delivery_days > 365:
            raise ValueError("delivery_days must be between 1 and 365.")
    except (TypeError, ValueError) as exc:
        conn.close()
        return error_response(str(exc), 400)
    supplier = conn.execute("SELECT id FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
    if supplier is None:
        conn.close()
        return error_response("Supplier profile was not found.", 404)
    cursor = conn.execute(
        """INSERT INTO supplier_quotes
           (supplier_id, material, quote_price, available_quantity, delivery_days, distance_km, risk_score, demo)
           VALUES (?, ?, ?, ?, ?, ?, NULL, 0)""",
        (supplier["id"], material, quote_price, available, delivery_days, distance),
    )
    quote_id = cursor.lastrowid
    audit(conn, g.user["id"], "supplier.quote.created", "supplier_quote", quote_id, payload)
    conn.commit()
    conn.close()
    return jsonify({"quote_id": quote_id, "demo": False}), 201


@app.route("/api/supplier-quotes/<int:quote_id>", methods=["PATCH"])
@roles_required("supplier")
def update_supplier_quote(quote_id: int):
    payload = request.get_json(silent=True) or {}
    allowed = {"quote_price", "available_quantity", "delivery_days", "distance_km"}
    updates = {key: payload[key] for key in allowed if key in payload}
    if not updates:
        return error_response("Provide at least one supported quote field.", 400)
    try:
        if "quote_price" in updates:
            updates["quote_price"] = positive_number(updates["quote_price"], "quote_price")
        if "available_quantity" in updates:
            updates["available_quantity"] = positive_number(updates["available_quantity"], "available_quantity")
        if "delivery_days" in updates:
            updates["delivery_days"] = int(updates["delivery_days"])
            if not 1 <= updates["delivery_days"] <= 365:
                raise ValueError("delivery_days must be between 1 and 365.")
        if "distance_km" in updates:
            updates["distance_km"] = positive_number(updates["distance_km"], "distance_km", allow_zero=True)
    except (TypeError, ValueError) as exc:
        return error_response(str(exc), 400)
    conn = get_connection()
    quote = conn.execute(
        """SELECT q.id, q.demo FROM supplier_quotes q JOIN suppliers s ON s.id = q.supplier_id
           WHERE q.id = ? AND s.owner_user_id = ?""",
        (quote_id, g.user["id"]),
    ).fetchone()
    if quote is None:
        conn.close()
        return error_response("Supplier quote not found.", 404)
    assignments = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(f"UPDATE supplier_quotes SET {assignments} WHERE id = ?", (*updates.values(), quote_id))
    audit(conn, g.user["id"], "supplier.quote.updated", "supplier_quote", quote_id, updates)
    conn.commit()
    conn.close()
    return jsonify({"message": "Quote updated.", "demo": bool(quote["demo"])})


@app.route("/api/suppliers/rank", methods=["POST"])
@roles_required("contractor", "administrator")
def rank_suppliers():
    payload = request.get_json(silent=True) or {}
    material = payload.get("material")
    if material not in MATERIAL_NAMES:
        return error_response("material must match the WPI material catalogue.", 400)
    try:
        quantity = positive_number(payload.get("quantity"), "quantity")
        deadline_days = int(payload.get("deadline_days", 365))
        weights = payload.get("weights") or {"price": 0.4, "delivery": 0.25, "availability": 0.2, "risk": 0.15}
        supported = {"price", "delivery", "availability", "risk"}
        if not isinstance(weights, dict) or set(weights) - supported:
            raise ValueError("weights may contain only price, delivery, availability, and risk.")
        parsed_weights = {name: positive_number(value, f"weights.{name}", allow_zero=True) for name, value in weights.items()}
        if not parsed_weights or sum(parsed_weights.values()) <= 0:
            raise ValueError("At least one ranking weight must be greater than zero.")
        total_weight = sum(parsed_weights.values())
        parsed_weights = {name: value / total_weight for name, value in parsed_weights.items()}
        if deadline_days < 1 or deadline_days > 365:
            raise ValueError("deadline_days must be between 1 and 365.")
    except (TypeError, ValueError) as exc:
        return error_response(str(exc), 400)
    conn = get_connection()
    quotes = conn.execute(
        """SELECT q.*, s.name AS supplier_name, s.city, s.verified, s.demo AS supplier_demo
           FROM supplier_quotes q JOIN suppliers s ON s.id = q.supplier_id
           WHERE lower(q.material) = lower(?)
             AND (s.demo = 1 OR s.owner_user_id IS NOT NULL)
             AND q.available_quantity > 0
           ORDER BY q.id""",
        (material,),
    ).fetchall()
    scored = []
    for quote in quotes:
        probability = supplier_late_rate(conn, quote["supplier_id"])
        if probability is None and (quote["demo"] or quote["supplier_demo"]) and quote["risk_score"] is not None:
            probability = float(quote["risk_score"])
            evidence = "demo assumption"
        elif probability is not None:
            evidence = "observed genuine outcomes"
        else:
            evidence = "unavailable"
        material_quotes = [
            item for item in quotes
            if item["material"].lower() == material.lower()
        ]
        criteria = {
            "price": min(float(item["quote_price"]) for item in material_quotes) / max(float(quote["quote_price"]), 0.01),
            "delivery": min(int(item["delivery_days"]) for item in material_quotes) / max(int(quote["delivery_days"]), 1),
            "availability": min(float(quote["available_quantity"]) / quantity, 1.0),
            "risk": 1.0 - probability if probability is not None else None,
        }
        available_weight = sum(parsed_weights.get(key, 0) for key, value in criteria.items() if value is not None)
        if available_weight <= 0:
            continue
        contributions = {
            key: (parsed_weights.get(key, 0) * value / available_weight if value is not None else None)
            for key, value in criteria.items()
        }
        score = sum(value for value in contributions.values() if value is not None)
        shortage = max(0.0, quantity - float(quote["available_quantity"]))
        features = extract_leakage_safe_supplier_features(conn, quote["supplier_id"])
        scored.append({
            "quote_id": quote["id"],
            "supplier_id": quote["supplier_id"],
            "supplier_name": quote["supplier_name"],
            "material": quote["material"],
            "quote_price": float(quote["quote_price"]),
            "available_quantity": float(quote["available_quantity"]),
            "delivery_days": int(quote["delivery_days"]),
            "distance_km": quote["distance_km"],
            "verified": bool(quote["verified"]) and not bool(quote["supplier_demo"]),
            "demo": bool(quote["demo"] or quote["supplier_demo"]),
            "bayesian_rating": features["bayesian_rating"],
            "review_count": features["review_count"],
            "risk_probability": probability,
            "risk_evidence": evidence,
            "feasible": shortage == 0 and int(quote["delivery_days"]) <= deadline_days,
            "shortage_quantity": shortage,
            "score": score,
            "criterion_contributions": contributions,
            "explanation": {
                "score": round(score, 3),
                "strengths": [k for k, v in contributions.items() if v is not None and v > 0.12],
                "evidence_level": features["evidence_level"],
                "bayesian_rating": features["bayesian_rating"],
            },
        })

    conn.close()
    return jsonify({
        "material": material,
        "quantity": quantity,
        "deadline_days": deadline_days,
        "weights": parsed_weights,
        "ranked_quotes": sorted(scored, key=lambda row: (-row["score"], row["quote_price"])),
        "method": "Transparent weighted utility ranking using available quote data; not a trained ranking model.",
        "warning": "Risk evidence is unavailable unless genuine recorded order outcomes exist. Demo assumptions are labeled.",
    })


@app.route("/api/projects", methods=["GET", "POST"])
@authenticated
def projects_api():
    conn = get_connection()
    if request.method == "GET":
        rows = conn.execute(
            "SELECT * FROM projects WHERE demo = 1 OR created_by = ? OR ? = 'administrator' ORDER BY id DESC",
            (g.user["id"], g.user["role"]),
        ).fetchall()
        conn.close()
        return jsonify({"projects": rows})

    if g.user["role"] not in {"contractor", "administrator"}:
        conn.close()
        return error_response("Only contractor accounts can create projects.", 403)
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    location = str(payload.get("location", "")).strip()
    if not name or not location or len(name) > 150 or len(location) > 200:
        conn.close()
        return error_response("name (max 150 chars) and location (max 200 chars) are required.", 400)

    try:
        budget = positive_number(payload.get("budget"), "budget")
        start_date = parse_iso_date(payload.get("start_date"), "start_date")
        deadline = parse_iso_date(payload.get("deadline"), "deadline")
        if deadline <= start_date:
            raise ValueError("deadline must be after start_date.")
        materials = payload.get("materials", [])
        if not isinstance(materials, list):
            raise ValueError("materials must be a list.")
        for item in materials:
            if not isinstance(item, dict) or item.get("material") not in MATERIAL_NAMES:
                raise ValueError("Every material must match the WPI material catalogue.")
            required = positive_number(item.get("required_quantity"), "required_quantity")
            inventory = positive_number(item.get("current_inventory", 0), "current_inventory", allow_zero=True)
            ordered = positive_number(item.get("ordered_quantity", 0), "ordered_quantity", allow_zero=True)
            positive_number(item.get("unit_cost", 0), "unit_cost", allow_zero=True)
            if inventory + ordered > required + 1e-9:
                raise ValueError("current_inventory plus ordered_quantity cannot exceed required_quantity.")
    except (TypeError, ValueError) as exc:
        conn.close()
        return error_response(str(exc), 400)

    cursor = conn.execute(
        "INSERT INTO projects (name, location, budget, start_date, deadline, status, created_by, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            location,
            budget,
            start_date.isoformat(),
            deadline.isoformat(),
            "active",
            g.user["id"],
            0,
        ),
    )
    project_id = cursor.lastrowid
    for material in materials:
        conn.execute(
            "INSERT INTO project_materials (project_id, material, required_quantity, current_inventory, ordered_quantity, unit_cost) VALUES (?, ?, ?, ?, ?, ?)",
            (
                project_id,
                material.get("material"),
                float(material.get("required_quantity", 0.0)),
                float(material.get("current_inventory", 0.0)),
                float(material.get("ordered_quantity", 0.0)),
                float(material.get("unit_cost", 0.0)),
            ),
        )
    audit(conn, g.user["id"], "project.created", "project", project_id, {"name": name, "material_count": len(materials)})
    conn.commit()
    conn.close()
    return jsonify({"message": "Project created", "project_id": project_id, "demo": False}), 201


def get_accessible_project(conn, project_id: int, user: Dict[str, Any], write: bool = False):
    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        return None, error_response("Project not found.", 404)
    if project["demo"] and write and user["role"] != "administrator":
        return None, error_response("Demo projects are read-only.", 403)
    is_owner = project["created_by"] == user["id"]
    is_demo_read = bool(project["demo"]) and not write
    if not (is_owner or user["role"] == "administrator" or is_demo_read):
        return None, error_response("You do not have access to this project.", 403)
    return project, None


@app.route("/api/projects/<int:project_id>", methods=["GET", "PUT", "DELETE"])
@authenticated
def project_detail(project_id: int):
    conn = get_connection()
    project, failure = get_accessible_project(conn, project_id, g.user, write=request.method != "GET")
    if failure:
        conn.close()
        return failure
    if request.method == "GET":
        materials = conn.execute("SELECT * FROM project_materials WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()
        project["materials"] = materials
        conn.close()
        return jsonify({"project": project})
    if g.user["role"] not in {"contractor", "administrator"}:
        conn.close()
        return error_response("Only contractors can modify projects.", 403)
    if request.method == "DELETE":
        conn.execute("UPDATE projects SET status = 'archived', archived_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
        audit(conn, g.user["id"], "project.archived", "project", project_id, {})
        conn.commit()
        conn.close()
        return jsonify({"message": "Project archived."})

    payload = request.get_json(silent=True) or {}
    allowed = {"name", "location", "budget", "start_date", "deadline"}
    updates = {key: payload[key] for key in allowed if key in payload}
    try:
        if "name" in updates and (not str(updates["name"]).strip() or len(str(updates["name"])) > 150):
            raise ValueError("name is required and must be at most 150 characters.")
        if "location" in updates and (not str(updates["location"]).strip() or len(str(updates["location"])) > 200):
            raise ValueError("location is required and must be at most 200 characters.")
        if "budget" in updates:
            updates["budget"] = positive_number(updates["budget"], "budget")
        if "start_date" in updates:
            updates["start_date"] = parse_iso_date(updates["start_date"], "start_date").isoformat()
        if "deadline" in updates:
            updates["deadline"] = parse_iso_date(updates["deadline"], "deadline").isoformat()
        start = parse_iso_date(updates.get("start_date", project["start_date"]), "start_date")
        deadline = parse_iso_date(updates.get("deadline", project["deadline"]), "deadline")
        if deadline <= start:
            raise ValueError("deadline must be after start_date.")
    except (TypeError, ValueError) as exc:
        conn.close()
        return error_response(str(exc), 400)
    if not updates:
        conn.close()
        return error_response("No supported project fields provided.", 400)
    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(f"UPDATE projects SET {assignments} WHERE id = ?", (*updates.values(), project_id))
    audit(conn, g.user["id"], "project.updated", "project", project_id, updates)
    conn.commit()
    conn.close()
    return jsonify({"message": "Project updated."})


@app.route("/api/projects/<int:project_id>/materials", methods=["POST"])
@roles_required("contractor", "administrator")
def project_materials_add(project_id: int):
    payload = request.get_json(silent=True) or {}
    conn = get_connection()
    project, failure = get_accessible_project(conn, project_id, g.user, write=True)
    if failure:
        conn.close()
        return failure
    material = payload.get("material")
    if material not in MATERIAL_NAMES:
        conn.close()
        return error_response("material must match the WPI material catalogue.", 400)
    try:
        required = positive_number(payload.get("required_quantity"), "required_quantity")
        inventory = positive_number(payload.get("current_inventory", 0), "current_inventory", allow_zero=True)
        ordered = positive_number(payload.get("ordered_quantity", 0), "ordered_quantity", allow_zero=True)
        unit_cost = positive_number(payload.get("unit_cost", 0), "unit_cost", allow_zero=True)
        if inventory + ordered > required + 1e-9:
            raise ValueError("current_inventory plus ordered_quantity cannot exceed required_quantity.")
    except (TypeError, ValueError) as exc:
        conn.close()
        return error_response(str(exc), 400)
    cursor = conn.execute(
        """INSERT INTO project_materials
           (project_id, material, required_quantity, current_inventory, ordered_quantity, unit_cost)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (project_id, material, required, inventory, ordered, unit_cost),
    )
    material_id = cursor.lastrowid
    audit(conn, g.user["id"], "project.material.created", "project_material", material_id, payload)
    conn.commit()
    conn.close()
    return jsonify({"project_material_id": material_id}), 201


@app.route("/api/project-materials/<int:material_id>", methods=["PATCH"])
@roles_required("contractor", "administrator")
def project_material_update(material_id: int):
    payload = request.get_json(silent=True) or {}
    allowed = {"required_quantity", "current_inventory", "ordered_quantity", "unit_cost"}
    updates = {key: payload[key] for key in allowed if key in payload}
    if not updates:
        return error_response("Provide at least one supported material quantity field.", 400)
    try:
        for key, value in list(updates.items()):
            updates[key] = positive_number(value, key, allow_zero=key != "required_quantity")
    except (TypeError, ValueError) as exc:
        return error_response(str(exc), 400)
    conn = get_connection()
    material = conn.execute(
        """SELECT pm.*, p.created_by, p.demo FROM project_materials pm
           JOIN projects p ON p.id = pm.project_id WHERE pm.id = ?""",
        (material_id,),
    ).fetchone()
    if material is None:
        conn.close()
        return error_response("Project material not found.", 404)
    if material["created_by"] != g.user["id"] and g.user["role"] != "administrator":
        conn.close()
        return error_response("You do not have access to modify this project material.", 403)
    quantities = {
        "required_quantity": updates.get("required_quantity", material["required_quantity"]),
        "current_inventory": updates.get("current_inventory", material["current_inventory"]),
        "ordered_quantity": updates.get("ordered_quantity", material["ordered_quantity"]),
    }
    if quantities["current_inventory"] + quantities["ordered_quantity"] > quantities["required_quantity"] + 1e-9:
        conn.close()
        return error_response("current_inventory plus ordered_quantity cannot exceed required_quantity.", 400)
    assignments = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(f"UPDATE project_materials SET {assignments} WHERE id = ?", (*updates.values(), material_id))
    audit(conn, g.user["id"], "project.material.updated", "project_material", material_id, updates)
    conn.commit()
    conn.close()
    return jsonify({"message": "Project material updated."})


@app.route("/api/procurement/optimize", methods=["POST"])
@roles_required("contractor", "administrator")
def optimize_procurement():
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    if not isinstance(project_id, int):
        return error_response("project_id is required.", 400)
    try:
        transport_rate = positive_number(
            payload.get("transport_rate_coefficient", 0.02),
            "transport_rate_coefficient",
            allow_zero=True,
        )
        shortage_penalty = positive_number(
            payload.get("shortage_penalty", 1500),
            "shortage_penalty",
            allow_zero=True,
        )
    except (TypeError, ValueError) as exc:
        return error_response(str(exc), 400)
    conn = get_connection()
    project, failure = get_accessible_project(conn, project_id, g.user)
    if failure:
        conn.close()
        return failure
    alternatives, failure = build_procurement_alternatives(conn, project, transport_rate, shortage_penalty)
    conn.close()
    if failure:
        return failure
    return jsonify({
        "project_id": project_id,
        "assumptions": {
            "transport_rate_coefficient": transport_rate,
            "shortage_penalty_per_unit": shortage_penalty,
            "note": "Both transport and shortage penalty values are user-configurable assumptions, not sourced tariffs.",
        },
        "alternatives": alternatives,
        "pareto_comparison": {
            "available": True,
            "reason": alternatives["pareto_comparison"]["note"],
            "pareto_front": alternatives["pareto_comparison"]["pareto_synthesis"],
        },
        "nsga_ii": {
            "available": False,
            "reason": "NSGA-II search is not implemented; nsga_ii remains a legacy alias for the heuristic Pareto comparison.",
            "deprecated_alias_for": "pareto_comparison",
            "pareto_front": alternatives["pareto_comparison"]["pareto_synthesis"],
        },
    })



def supplier_late_rate(conn, supplier_id: int) -> Optional[float]:
    row = conn.execute(
        """SELECT COUNT(*) AS count,
                  SUM(CASE WHEN o.cancelled = 1 OR o.delay_days > 0 THEN 1 ELSE 0 END) AS late
           FROM orders ord JOIN order_delivery_outcomes o ON o.order_id = ord.id
           WHERE ord.supplier_id = ? AND ord.demo = 0""",
        (supplier_id,),
    ).fetchone()
    if row["count"] < 3:
        return None
    return float(row["late"] or 0) / float(row["count"])


def build_procurement_alternatives(
    conn,
    project: Dict[str, Any],
    transport_rate: float = 0.02,
    shortage_penalty: float = 1500,
):
    material_rows = conn.execute(
        "SELECT * FROM project_materials WHERE project_id = ? ORDER BY id",
        (project["id"],),
    ).fetchall()
    if not material_rows:
        return None, error_response("Project has no material requirements.", 400)
    offers_by_material: Dict[int, List[Dict[str, Any]]] = {}
    days_available = max(0, (date.fromisoformat(project["deadline"]) - date.today()).days)
    committed = conn.execute(
        """SELECT COALESCE(SUM(ord.quantity * ord.quoted_unit_price), 0) AS amount
           FROM orders ord WHERE ord.project_id = ? AND ord.status != 'cancelled'""",
        (project["id"],),
    ).fetchone()["amount"]
    remaining_budget = max(0.0, float(project["budget"]) - float(committed))
    for material_row in material_rows:
        required = max(
            0.0,
            float(material_row["required_quantity"])
            - float(material_row["current_inventory"])
            - float(material_row["ordered_quantity"]),
        )
        quotes = conn.execute(
            """SELECT q.*, s.name AS supplier_name, s.demo AS supplier_demo,
                      s.verified, s.owner_user_id
               FROM supplier_quotes q JOIN suppliers s ON s.id = q.supplier_id
               WHERE lower(q.material) = lower(?)
                 AND (s.demo = 1 OR s.owner_user_id IS NOT NULL)
               ORDER BY q.id""",
            (material_row["material"],),
        ).fetchall()
        for quote in quotes:
            quote["within_deadline"] = int(quote["delivery_days"]) <= days_available
            quote["late_probability"] = supplier_late_rate(conn, quote["supplier_id"])
            if quote["late_probability"] is None and quote["demo"] and quote["risk_score"] is not None:
                quote["late_probability"] = float(quote["risk_score"])
                quote["risk_evidence"] = "demo assumption"
            elif quote["late_probability"] is not None:
                quote["risk_evidence"] = "observed outcomes (at least 3 orders)"
            else:
                quote["risk_evidence"] = "unavailable"
        offers_by_material[material_row["id"]] = quotes

    def ranked_quotes(quotes: List[Dict[str, Any]], strategy: str) -> List[Dict[str, Any]]:
        def cost(quote: Dict[str, Any]) -> float:
            return float(quote["quote_price"]) + transport_rate * float(quote["distance_km"] or 0)

        if strategy == "cheapest":
            return sorted(quotes, key=lambda quote: (cost(quote), quote["delivery_days"]))
        if strategy == "fastest":
            return sorted(quotes, key=lambda quote: (quote["delivery_days"], cost(quote)))
        if strategy == "lowest_risk":
            return sorted(quotes, key=lambda quote: (
                1.0 if quote["late_probability"] is None else float(quote["late_probability"]),
                quote["delivery_days"],
                cost(quote),
            ))
        costs = [cost(quote) for quote in quotes]
        minimum_cost = min(costs, default=0.0)
        cost_range = max(costs, default=0.0) - minimum_cost
        return sorted(quotes, key=lambda quote: (
            0.65 * (1.0 if quote["late_probability"] is None else float(quote["late_probability"]))
            + 0.35 * ((cost(quote) - minimum_cost) / cost_range if cost_range > 0 else 0.0),
            cost(quote),
        ))
    results: Dict[str, Any] = {}
    for strategy in ("cheapest", "lowest_risk", "fastest", "weighted_risk_cost"):
        allocations: List[Dict[str, Any]] = []
        total_cost = 0.0
        estimated_days = 0
        weighted_risk = 0.0
        risk_known_quantity = 0.0
        shortage_total = 0.0
        for material_row in material_rows:
            need = max(
                0.0,
                float(material_row["required_quantity"])
                - float(material_row["current_inventory"])
                - float(material_row["ordered_quantity"]),
            )
            remaining = need
            eligible_quotes = [
                candidate for candidate in offers_by_material[material_row["id"]]
                if candidate["within_deadline"]
            ]
            for quote in ranked_quotes(eligible_quotes, strategy):
                if remaining <= 1e-9:
                    break
                quantity = min(remaining, float(quote["available_quantity"]))
                if quantity <= 0:
                    continue
                unit_transport = transport_rate * float(quote["distance_km"] or 0)
                line_cost = quantity * (float(quote["quote_price"]) + unit_transport)
                total_cost += line_cost
                estimated_days = max(estimated_days, int(quote["delivery_days"]))
                probability = quote["late_probability"]
                if probability is not None:
                    weighted_risk += quantity * float(probability)
                    risk_known_quantity += quantity
                allocations.append({
                    "project_material_id": material_row["id"],
                    "material": material_row["material"],
                    "supplier_id": quote["supplier_id"],
                    "supplier_name": quote["supplier_name"],
                    "quote_id": quote["id"],
                    "quantity": quantity,
                    "unit_price": float(quote["quote_price"]),
                    "transport_cost": quantity * unit_transport,
                    "material_cost": quantity * float(quote["quote_price"]),
                    "delivery_days": int(quote["delivery_days"]),
                    "distance_km": float(quote["distance_km"] or 0),
                    "late_probability": probability,
                    "risk_evidence": quote.get("risk_evidence", "unavailable"),
                    "demo": bool(quote["demo"] or quote["supplier_demo"]),
                })
                remaining -= quantity
            shortage_total += max(remaining, 0.0)
        results[strategy] = {
            "allocations": allocations,
            "material_cost": sum(item["material_cost"] for item in allocations),
            "transport_cost": sum(item["transport_cost"] for item in allocations),
            "total_estimated_cost": total_cost,
            "expected_late_delivery_risk": weighted_risk / risk_known_quantity if risk_known_quantity else None,
            "risk_evidence_quantity": risk_known_quantity,
            "estimated_delivery_days": estimated_days if allocations else None,
            "expected_delivery_days": estimated_days if allocations else None,
            "shortage_quantity": shortage_total,
            "shortage_penalty_assumption": shortage_penalty,
            "shortage_penalty_estimate": shortage_total * shortage_penalty,
            "objective_cost_including_shortage_penalty": total_cost + shortage_total * shortage_penalty,
            "remaining_budget": remaining_budget,
            "budget_compliant": total_cost <= remaining_budget,
            "project_deadline_days": days_available,
            "feasible": shortage_total <= 1e-9,
        }

    add_pareto_comparison(results)

    return results, None


@app.route("/api/procurement/plans", methods=["POST"])
@roles_required("contractor", "administrator")
def create_procurement_plan():
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    strategy = payload.get("strategy")
    if not isinstance(project_id, int) or strategy not in {"cheapest", "fastest", "lowest_risk", "weighted_risk_cost", "pareto_comparison", "nsga_ii"}:
        return error_response("project_id and a supported strategy are required.", 400)

    try:
        transport_rate = positive_number(payload.get("transport_rate_coefficient", 0.02), "transport_rate_coefficient", allow_zero=True)
        shortage_penalty = positive_number(payload.get("shortage_penalty", 1500), "shortage_penalty", allow_zero=True)
    except (TypeError, ValueError) as exc:
        return error_response(str(exc), 400)
    conn = get_connection()
    project, failure = get_accessible_project(conn, project_id, g.user, write=True)
    if failure:
        conn.close()
        return failure
    alternatives, failure = build_procurement_alternatives(conn, project, transport_rate, shortage_penalty)
    if failure:
        conn.close()
        return failure
    chosen = alternatives[strategy]
    cursor = conn.execute(
        """INSERT INTO procurement_plans
           (project_id, created_by, status, selected_strategy, alternatives_json, assumptions_json)
           VALUES (?, ?, 'proposed', ?, ?, ?)""",
        (project_id, g.user["id"], strategy, json.dumps(alternatives),
         json.dumps({"transport_rate_coefficient": transport_rate, "shortage_penalty": shortage_penalty})),
    )
    plan_id = cursor.lastrowid
    for allocation in chosen["allocations"]:
        conn.execute(
            """INSERT INTO procurement_plan_items (plan_id, project_material_id, quote_id, quantity)
               VALUES (?, ?, ?, ?)""",
            (plan_id, allocation["project_material_id"], allocation["quote_id"], allocation["quantity"]),
        )
    audit(conn, g.user["id"], "procurement.plan.created", "procurement_plan", plan_id, {"strategy": strategy, "shortage_quantity": chosen["shortage_quantity"]})
    conn.commit()
    conn.close()
    return jsonify({"plan_id": plan_id, "status": "proposed", "selected_strategy": strategy, "comparison": alternatives}), 201


@app.route("/api/procurement/plans/<int:plan_id>/approve", methods=["POST"])
@roles_required("contractor", "administrator")
def approve_procurement_plan(plan_id: int):
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision")
    if decision not in {"approved", "rejected"}:
        return error_response("decision must be approved or rejected.", 400)
    conn = get_connection()
    plan = conn.execute("SELECT * FROM procurement_plans WHERE id = ?", (plan_id,)).fetchone()
    if plan is None:
        conn.close()
        return error_response("Procurement plan not found.", 404)
    project, failure = get_accessible_project(conn, plan["project_id"], g.user, write=True)
    if failure:
        conn.close()
        return failure
    if plan["status"] != "proposed":
        conn.close()
        return error_response("Only proposed plans can be approved or rejected.", 409)
    comparison = json.loads(plan["alternatives_json"])
    selected = comparison[plan["selected_strategy"]]
    if decision == "approved":
        assumptions = json.loads(plan["assumptions_json"])
        current_comparison, failure = build_procurement_alternatives(
            conn,
            project,
            float(assumptions.get("transport_rate_coefficient", 0.02)),
            float(assumptions.get("shortage_penalty", 1500)),
        )
        if failure:
            conn.close()
            return failure
        current_selected = current_comparison[plan["selected_strategy"]]
        previous_signature = [
            (item["project_material_id"], item["quote_id"], round(item["quantity"], 9),
             item["unit_price"], item["delivery_days"], item["distance_km"], item["late_probability"])
            for item in selected["allocations"]
        ]
        current_signature = [
            (item["project_material_id"], item["quote_id"], round(item["quantity"], 9),
             item["unit_price"], item["delivery_days"], item["distance_km"], item["late_probability"])
            for item in current_selected["allocations"]
        ]
        if previous_signature != current_signature:
            conn.close()
            return error_response("Plan inputs changed since comparison. Recompare and create a fresh plan before approval.", 409)
        selected = current_selected
    if decision == "approved" and not selected["feasible"]:
        conn.close()
        return error_response("A plan with a shortage or delivery beyond its deadline cannot be approved.", 409)
    if decision == "approved" and not selected["budget_compliant"]:
        conn.close()
        return error_response("A plan exceeding the remaining project budget cannot be approved.", 409)
    conn.execute("UPDATE procurement_plans SET status = ? WHERE id = ?", (decision, plan_id))
    conn.execute(
        "INSERT INTO approvals (plan_id, actor_id, decision, comments) VALUES (?, ?, ?, ?)",
        (plan_id, g.user["id"], decision, str(payload.get("comments", ""))[:1000]),
    )
    audit(conn, g.user["id"], f"procurement.plan.{decision}", "procurement_plan", plan_id, {"comments": payload.get("comments", "")})
    conn.commit()
    conn.close()
    return jsonify({"plan_id": plan_id, "status": decision, "message": "Purchase orders can now be created only for an approved plan."})


@app.route("/api/orders", methods=["GET", "POST"])
@authenticated
def orders_api():
    conn = get_connection()
    if request.method == "GET":
        if g.user["role"] == "administrator":
            rows = conn.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
        elif g.user["role"] == "supplier":
            supplier = conn.execute("SELECT id FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
            rows = conn.execute("SELECT * FROM orders WHERE supplier_id = ? ORDER BY id DESC", (supplier["id"],)).fetchall() if supplier else []
        else:
            rows = conn.execute("SELECT * FROM orders WHERE project_id IN (SELECT id FROM projects WHERE created_by = ?) ORDER BY id DESC", (g.user["id"],)).fetchall()
        conn.close()
        return jsonify({"orders": rows})

    if g.user["role"] not in {"contractor", "administrator"}:
        conn.close()
        return error_response("Only contractors can create purchase orders.", 403)
    payload = request.get_json(silent=True) or {}
    plan_id = payload.get("plan_id")
    if not isinstance(plan_id, int):
        conn.close()
        return error_response("plan_id is required.", 400)
    plan = conn.execute("SELECT * FROM procurement_plans WHERE id = ? AND status = 'approved'", (plan_id,)).fetchone()
    if plan is None:
        conn.close()
        return error_response("Orders require a plan that has been explicitly approved.", 409)
    project, failure = get_accessible_project(conn, plan["project_id"], g.user, write=True)
    if failure:
        conn.close()
        return failure
    items = conn.execute(
        """SELECT pi.*, q.supplier_id, q.material, q.quote_price, q.delivery_days,
                  q.distance_km, q.available_quantity
           FROM procurement_plan_items pi JOIN supplier_quotes q ON q.id = pi.quote_id
           WHERE pi.plan_id = ?""",
        (plan_id,),
    ).fetchall()
    if not items:
        conn.close()
        return error_response("Approved plan has no allocations.", 409)
    assumptions = json.loads(plan["assumptions_json"])
    transport_rate = float(assumptions.get("transport_rate_coefficient", 0.02))
    remaining_budget = float(project["budget"]) - float(conn.execute(
        """SELECT COALESCE(SUM(ord.quantity * ord.quoted_unit_price), 0) AS amount
           FROM orders ord WHERE ord.project_id = ? AND ord.status != 'cancelled'""",
        (project["id"],),
    ).fetchone()["amount"])
    order_cost = sum(
        float(item["quantity"]) * (
            float(item["quote_price"]) + transport_rate * float(item["distance_km"] or 0)
        )
        for item in items
    )
    if order_cost > remaining_budget:
        conn.rollback()
        conn.close()
        return error_response("The remaining project budget changed. Replan before creating purchase orders.", 409)
    order_ids = []
    for item in items:
        material = conn.execute(
            "SELECT * FROM project_materials WHERE id = ? AND project_id = ?",
            (item["project_material_id"], project["id"]),
        ).fetchone()
        if material is None or (
            float(material["current_inventory"])
            + float(material["ordered_quantity"])
            + float(item["quantity"])
            > float(material["required_quantity"]) + 1e-9
        ):
            conn.rollback()
            conn.close()
            return error_response("Project demand changed; the approved plan can no longer be ordered.", 409)
        reserved_quote = conn.execute(
            """UPDATE supplier_quotes
               SET available_quantity = available_quantity - ?
               WHERE id = ? AND available_quantity >= ?""",
            (item["quantity"], item["quote_id"], item["quantity"]),
        )
        if reserved_quote.rowcount != 1:
            conn.rollback()
            conn.close()
            return error_response("Supplier availability changed; recompare and approve a new plan.", 409)
        reserved_demand = conn.execute(
            """UPDATE project_materials
               SET ordered_quantity = ordered_quantity + ?
               WHERE id = ? AND current_inventory + ordered_quantity + ? <= required_quantity + 0.000000001""",
            (item["quantity"], item["project_material_id"], item["quantity"]),
        )
        if reserved_demand.rowcount != 1:
            conn.rollback()
            conn.close()
            return error_response("Project demand changed; the approved plan can no longer be ordered.", 409)
        promised = (date.today() + timedelta(days=int(item["delivery_days"]))).isoformat()
        if date.fromisoformat(promised) > date.fromisoformat(project["deadline"]):
            conn.rollback()
            conn.close()
            return error_response("The promised delivery would exceed the project deadline.", 409)
        cursor = conn.execute(
            """INSERT INTO orders
               (plan_id, plan_item_id, project_id, supplier_id, quote_id, material, quantity,
                quoted_unit_price, promised_delivery_date, status, demo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'placed', ?)""",
            (plan_id, item["id"], project["id"], item["supplier_id"], item["quote_id"],
             item["material"], item["quantity"], item["quote_price"], promised, int(bool(project["demo"]))),
        )
        order_ids.append(cursor.lastrowid)
    conn.execute("UPDATE procurement_plans SET status = 'ordered' WHERE id = ?", (plan_id,))
    audit(conn, g.user["id"], "orders.created", "procurement_plan", plan_id, {"order_ids": order_ids})
    conn.commit()
    conn.close()
    return jsonify({"order_ids": order_ids, "status": "placed"}), 201


@app.route("/api/orders/<int:order_id>/outcome", methods=["POST"])
@authenticated
def record_order_outcome(order_id: int):
    payload = request.get_json(silent=True) or {}
    cancelled = payload.get("cancelled", False)
    if not isinstance(cancelled, bool):
        return error_response("cancelled must be a boolean.", 400)
    try:
        actual_date = parse_iso_date(payload["actual_delivery_date"], "actual_delivery_date") if payload.get("actual_delivery_date") else None
        paid_price = positive_number(payload["final_paid_price"], "final_paid_price", allow_zero=True) if payload.get("final_paid_price") is not None else None
        if not cancelled and actual_date is None:
            raise ValueError("actual_delivery_date is required unless the order is cancelled.")
        if actual_date and actual_date > date.today():
            raise ValueError("actual_delivery_date cannot be in the future.")
    except (TypeError, ValueError) as exc:
        return error_response(str(exc), 400)
    conn = get_connection()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        conn.close()
        return error_response("Order not found.", 404)
    project, failure = get_accessible_project(conn, order["project_id"], g.user, write=True)
    supplier = conn.execute("SELECT owner_user_id FROM suppliers WHERE id = ?", (order["supplier_id"],)).fetchone()
    is_supplier_owner = g.user["role"] == "supplier" and supplier and supplier["owner_user_id"] == g.user["id"]
    if failure and not is_supplier_owner and g.user["role"] != "administrator":
        conn.close()
        return failure
    promised = date.fromisoformat(order["promised_delivery_date"])
    delay_days = max(0, (actual_date - promised).days) if actual_date else None
    conn.execute(
        """INSERT INTO order_delivery_outcomes
           (order_id, actual_delivery_date, final_paid_price, cancelled, delay_days, recorded_by)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(order_id) DO UPDATE SET
             actual_delivery_date = excluded.actual_delivery_date,
             final_paid_price = excluded.final_paid_price,
             cancelled = excluded.cancelled,
             delay_days = excluded.delay_days,
             recorded_by = excluded.recorded_by""",
        (order_id, actual_date.isoformat() if actual_date else None, paid_price, int(cancelled), delay_days, g.user["id"]),
    )
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", ("cancelled" if cancelled else "delivered", order_id))
    audit(conn, g.user["id"], "order.outcome.recorded", "order", order_id, {"cancelled": cancelled, "delay_days": delay_days})
    conn.commit()
    conn.close()
    return jsonify({"order_id": order_id, "cancelled": cancelled, "delay_days": delay_days})


def csv_download(filename: str, rows: List[Dict[str, Any]]):
    buffer = io.StringIO()
    if not rows:
        writer = csv.writer(buffer)
        writer.writerow(["message"])
        writer.writerow(["No records available."])
    else:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            safe_row = {
                key: ("'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value)
                for key, value in row.items()
            }
            writer.writerow(safe_row)
    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/api/reports/forecasts.csv", methods=["GET"])
@authenticated
def forecast_report():
    conn = get_connection()
    if g.user["role"] == "administrator":
        rows = conn.execute("SELECT * FROM forecasts ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM forecasts WHERE requested_by = ? OR requested_by IS NULL ORDER BY id DESC",
            (g.user["id"],),
        ).fetchall()
    conn.close()
    return csv_download("buildconnect-forecasts.csv", rows)


@app.route("/api/reports/orders.csv", methods=["GET"])
@authenticated
def order_report():
    conn = get_connection()
    query = """SELECT ord.id AS order_id, ord.material, ord.quantity, ord.quoted_unit_price,
                      ord.promised_delivery_date, ord.status, ord.demo,
                      outcome.actual_delivery_date, outcome.final_paid_price,
                      outcome.cancelled, outcome.delay_days,
                      outcome.created_at AS outcome_recorded_at
               FROM orders ord LEFT JOIN order_delivery_outcomes outcome ON outcome.order_id = ord.id"""
    params: tuple = ()
    if g.user["role"] == "supplier":
        supplier = conn.execute("SELECT id FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
        query += " WHERE ord.supplier_id = ?"
        params = (supplier["id"] if supplier else -1,)
    elif g.user["role"] != "administrator":
        query += " WHERE ord.project_id IN (SELECT id FROM projects WHERE created_by = ?)"
        params = (g.user["id"],)
    query += " ORDER BY ord.id"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return csv_download("buildconnect-orders-and-outcomes.csv", rows)


@app.route("/api/forecasts/history", methods=["GET"])
@authenticated
def forecast_history():
    conn = get_connection()
    if g.user["role"] == "administrator":
        rows = conn.execute("SELECT * FROM forecasts ORDER BY id DESC LIMIT 500").fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM forecasts WHERE requested_by = ? OR requested_by IS NULL
               ORDER BY id DESC LIMIT 500""",
            (g.user["id"],),
        ).fetchall()
    conn.close()
    for row in rows:
        row["intervals"] = json.loads(row.pop("intervals_json"))
    return jsonify({"forecasts": rows, "limit": 500})


@app.route("/api/auth/profile", methods=["GET", "PUT"])
@authenticated
def user_profile_endpoint():
    conn = get_connection()
    if request.method == "GET":
        user_row = conn.execute(
            "SELECT id, name, full_name, email, phone_number, role, account_status, demo, created_at, last_login_at FROM users WHERE id = ?",
            (g.user["id"],),
        ).fetchone()
        supplier_row = None
        if g.user["role"] == "supplier":
            supplier_row = conn.execute("SELECT * FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
        conn.close()
        return jsonify({"user": user_row, "supplier_profile": supplier_row})

    payload = request.get_json(silent=True) or {}
    full_name = payload.get("full_name")
    phone_number = payload.get("phone_number")
    user_updates = {}
    if full_name is not None:
        user_updates["full_name"] = str(full_name).strip()[:120]
        user_updates["name"] = str(full_name).strip()[:120]
    if phone_number is not None:
        user_updates["phone_number"] = str(phone_number).strip()[:30]

    if user_updates:
        assignments = ", ".join(f"{k} = ?" for k in user_updates)
        conn.execute(f"UPDATE users SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (*user_updates.values(), g.user["id"]))

    if g.user["role"] == "supplier" and "supplier_profile" in payload:
        sup_data = payload["supplier_profile"] or {}
        allowed = {"business_name", "business_description", "contact_person", "phone", "email", "address", "city", "state", "postal_code", "latitude", "longitude"}
        sup_updates = {k: sup_data[k] for k in allowed if k in sup_data}
        if sup_updates:
            assignments = ", ".join(f"{k} = ?" for k in sup_updates)
            conn.execute(f"UPDATE suppliers SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE owner_user_id = ?", (*sup_updates.values(), g.user["id"]))

    audit(conn, g.user["id"], "auth.profile.updated", "user", g.user["id"], {"fields": list(user_updates.keys())})
    conn.commit()
    conn.close()
    return jsonify({"message": "Profile updated successfully."})


@app.route("/api/auth/change-password", methods=["POST"])
@authenticated
def change_password():
    payload = request.get_json(silent=True) or {}
    current_pass = payload.get("current_password")
    new_pass = payload.get("new_password")
    if not current_pass or not new_pass:
        return error_response("Both current_password and new_password are required.", 400)
    if len(new_pass) < 12:
        return error_response("New password must be at least 12 characters.", 400)

    conn = get_connection()
    user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if not user or not check_password_hash(user["password_hash"], current_pass):
        conn.close()
        return error_response("Incorrect current password.", 401)

    new_hash = generate_password_hash(new_pass)
    conn.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_hash, g.user["id"]))
    audit(conn, g.user["id"], "auth.password.changed", "user", g.user["id"], {})
    conn.commit()
    conn.close()
    return jsonify({"message": "Password changed successfully."})


@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    if not email:
        return error_response("Email address is required.", 400)
    return jsonify({
        "status": "request_received",
        "email": email,
        "message": "Password reset requested. Notice: External email provider (SMTP/SendGrid) is currently unconfigured; in this development deployment, contact an administrator to reset credentials.",
        "provider_configured": False,
    })


@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    return error_response("Password reset requires an active external email token verification provider.", 501)


@app.route("/api/suppliers/<int:supplier_id>", methods=["GET"])
@authenticated
def supplier_detail(supplier_id: int):
    conn = get_connection()
    supplier = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if not supplier:
        conn.close()
        return error_response("Supplier not found.", 404)

    listings = conn.execute("SELECT * FROM supplier_material_listings WHERE supplier_id = ?", (supplier_id,)).fetchall()
    quotes = conn.execute("SELECT * FROM supplier_quotes WHERE supplier_id = ?", (supplier_id,)).fetchall()
    reviews = conn.execute("SELECT r.*, u.name AS reviewer_name FROM reviews r JOIN users u ON u.id = r.user_id WHERE r.supplier_id = ? AND r.review_status = 'approved' ORDER BY r.id DESC", (supplier_id,)).fetchall()
    features = extract_leakage_safe_supplier_features(conn, supplier_id)
    conn.close()

    result = dict(supplier)
    result["bayesian_rating"] = features["bayesian_rating"]
    result["evidence_level"] = features["evidence_level"]
    result["historical_orders"] = features["total_orders"]
    result["listings"] = listings
    result["quotes"] = quotes
    result["reviews"] = reviews
    result["provenance"] = "DEMO" if supplier["demo"] else "USER_ENTERED"
    return jsonify({"supplier": result})


@app.route("/api/supplier-listings", methods=["GET", "POST"])
@authenticated
def supplier_listings_endpoint():
    conn = get_connection()
    if request.method == "GET":
        material = request.args.get("material")
        supplier_id = request.args.get("supplier_id")
        query = "SELECT l.*, s.name AS supplier_name, s.city, s.verified, s.rating, s.demo FROM supplier_material_listings l JOIN suppliers s ON s.id = l.supplier_id WHERE 1=1"
        params = []
        if material:
            query += " AND lower(l.material_name) = lower(?)"
            params.append(material)
        if supplier_id:
            query += " AND l.supplier_id = ?"
            params.append(int(supplier_id))
        query += " ORDER BY l.quoted_unit_price ASC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify({"listings": rows})

    if g.user["role"] != "supplier":
        conn.close()
        return error_response("Only suppliers can publish material listings.", 403)

    payload = request.get_json(silent=True) or {}
    mat_name = payload.get("material_name")
    if mat_name not in MATERIAL_NAMES:
        conn.close()
        return error_response("material_name must match the WPI material catalogue.", 400)

    try:
        price = positive_number(payload.get("quoted_unit_price"), "quoted_unit_price")
        avail = positive_number(payload.get("available_quantity"), "available_quantity")
        moq = positive_number(payload.get("minimum_order_quantity", 1.0), "minimum_order_quantity")
        days = int(payload.get("estimated_delivery_days", 7))
        unit = str(payload.get("unit", "Metric Ton"))
        valid_until = payload.get("quote_valid_until")
    except (TypeError, ValueError) as exc:
        conn.close()
        return error_response(str(exc), 400)

    supplier = conn.execute("SELECT id FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
    if not supplier:
        conn.close()
        return error_response("Supplier profile not found.", 404)

    cursor = conn.execute(
        """INSERT INTO supplier_material_listings
           (supplier_id, material_name, quoted_unit_price, available_quantity,
            minimum_order_quantity, unit, estimated_delivery_days, availability_status, quote_valid_until)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'Available', ?)""",
        (supplier["id"], mat_name, price, avail, moq, unit, days, valid_until),
    )
    listing_id = cursor.lastrowid
    audit(conn, g.user["id"], "supplier.listing.created", "supplier_material_listing", listing_id, payload)
    conn.commit()
    conn.close()
    return jsonify({"listing_id": listing_id, "message": "Material listing published."}), 201


@app.route("/api/supplier-listings/<int:listing_id>", methods=["PATCH"])
@roles_required("supplier")
def update_supplier_listing(listing_id: int):
    payload = request.get_json(silent=True) or {}
    allowed = {"quoted_unit_price", "available_quantity", "minimum_order_quantity", "estimated_delivery_days", "availability_status", "quote_valid_until"}
    updates = {k: payload[k] for k in allowed if k in payload}
    if not updates:
        return error_response("No supported fields provided for update.", 400)

    conn = get_connection()
    listing = conn.execute(
        "SELECT l.id FROM supplier_material_listings l JOIN suppliers s ON s.id = l.supplier_id WHERE l.id = ? AND s.owner_user_id = ?",
        (listing_id, g.user["id"]),
    ).fetchone()
    if not listing:
        conn.close()
        return error_response("Listing not found or not owned by your account.", 404)

    assignments = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE supplier_material_listings SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (*updates.values(), listing_id))
    audit(conn, g.user["id"], "supplier.listing.updated", "supplier_material_listing", listing_id, updates)
    conn.commit()
    conn.close()
    return jsonify({"message": "Listing updated."})


@app.route("/api/suppliers/<int:supplier_id>/reviews", methods=["GET", "POST"])
@authenticated
def supplier_reviews(supplier_id: int):
    conn = get_connection()
    if request.method == "GET":
        rows = conn.execute(
            """SELECT r.*, u.name AS reviewer_name, p.name AS project_name
               FROM reviews r
               JOIN users u ON u.id = r.user_id
               LEFT JOIN orders ord ON ord.id = r.purchase_order_id
               LEFT JOIN projects p ON p.id = ord.project_id
               WHERE r.supplier_id = ? AND r.review_status = 'approved'
               ORDER BY r.id DESC""",
            (supplier_id,),
        ).fetchall()
        conn.close()
        return jsonify({"reviews": rows})

    if g.user["role"] not in {"contractor", "administrator"}:
        conn.close()
        return error_response("Only contractors who placed orders can submit reviews.", 403)

    payload = request.get_json(silent=True) or {}
    try:
        order_id = int(payload.get("purchase_order_id"))
        rating = positive_number(payload.get("rating"), "rating")
        review_text = str(payload.get("review_text", "")).strip()
        if not 1.0 <= rating <= 5.0:
            raise ValueError("Rating must be between 1.0 and 5.0.")
        if not review_text or len(review_text) > 1000:
            raise ValueError("review_text is required (maximum 1000 characters).")
    except (TypeError, ValueError) as exc:
        conn.close()
        return error_response(str(exc), 400)

    # Verify contractor actually completed an order with this supplier
    eligible = conn.execute(
        """SELECT ord.id FROM orders ord
           JOIN order_delivery_outcomes outcome ON outcome.order_id = ord.id
           JOIN projects p ON p.id = ord.project_id
           WHERE ord.id = ? AND ord.supplier_id = ? AND (p.created_by = ? OR ? = 'administrator')""",
        (order_id, supplier_id, g.user["id"], g.user["role"]),
    ).fetchone()
    if not eligible:
        conn.close()
        return error_response("Only completed purchase orders for your projects can be reviewed.", 403)

    cursor = conn.execute(
        """INSERT INTO reviews (supplier_id, user_id, purchase_order_id, rating, review_text, review_status)
           VALUES (?, ?, ?, ?, ?, 'approved')""",
        (supplier_id, g.user["id"], order_id, rating, review_text),
    )
    review_id = cursor.lastrowid
    # Update supplier average rating and review_count
    conn.execute(
        """UPDATE suppliers
           SET rating = (SELECT AVG(rating) FROM reviews WHERE supplier_id = ? AND review_status = 'approved'),
               review_count = (SELECT COUNT(*) FROM reviews WHERE supplier_id = ? AND review_status = 'approved')
           WHERE id = ?""",
        (supplier_id, supplier_id, supplier_id),
    )
    audit(conn, g.user["id"], "supplier.review.created", "review", review_id, {"rating": rating})
    conn.commit()
    conn.close()
    return jsonify({"review_id": review_id, "message": "Review submitted successfully."}), 201


@app.route("/api/orders/<int:order_id>", methods=["GET"])
@authenticated
def get_order_detail(order_id: int):
    conn = get_connection()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return error_response("Order not found.", 404)

    # Authorization
    is_admin = g.user["role"] == "administrator"
    is_contractor = conn.execute("SELECT id FROM projects WHERE id = ? AND created_by = ?", (order["project_id"], g.user["id"])).fetchone() is not None
    is_supplier = conn.execute("SELECT id FROM suppliers WHERE id = ? AND owner_user_id = ?", (order["supplier_id"], g.user["id"])).fetchone() is not None

    if not (is_admin or is_contractor or is_supplier or order["demo"]):
        conn.close()
        return error_response("You do not have access to view this order.", 403)

    items = conn.execute("SELECT * FROM purchase_order_items WHERE purchase_order_id = ?", (order_id,)).fetchall()
    outcome = conn.execute("SELECT * FROM order_delivery_outcomes WHERE order_id = ?", (order_id,)).fetchone()
    supplier = conn.execute("SELECT id, name, city, phone, email FROM suppliers WHERE id = ?", (order["supplier_id"],)).fetchone()
    project = conn.execute("SELECT id, name, location FROM projects WHERE id = ?", (order["project_id"],)).fetchone()
    conn.close()

    result = dict(order)
    result["items"] = items
    result["outcome"] = outcome
    result["supplier"] = supplier
    result["project"] = project
    result["provenance"] = "DEMO" if order["demo"] else "REAL_TRANSACTION"
    return jsonify({"order": result})


@app.route("/api/orders/<int:order_id>/status", methods=["PATCH"])
@authenticated
def update_order_status(order_id: int):
    payload = request.get_json(silent=True) or {}
    new_status = payload.get("status")
    valid_statuses = {"accepted", "rejected", "in-transit", "delivered", "closed", "cancelled"}
    if new_status not in valid_statuses:
        return error_response(f"Invalid status. Supported: {sorted(list(valid_statuses))}", 400)

    conn = get_connection()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return error_response("Order not found.", 404)

    supplier = conn.execute("SELECT owner_user_id FROM suppliers WHERE id = ?", (order["supplier_id"],)).fetchone()
    is_supplier_owner = supplier and supplier["owner_user_id"] == g.user["id"]
    is_admin = g.user["role"] == "administrator"
    if not (is_supplier_owner or is_admin):
        conn.close()
        return error_response("Only the assigned supplier or an administrator can update order fulfillment status.", 403)

    conn.execute("UPDATE orders SET status = ?, order_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, new_status, order_id))
    audit(conn, g.user["id"], "order.status.updated", "order", order_id, {"status": new_status})
    conn.commit()
    conn.close()
    return jsonify({"order_id": order_id, "status": new_status, "message": f"Order status updated to {new_status}."})


@app.route("/api/scenarios", methods=["GET", "POST"])
@authenticated
def scenarios_api():
    conn = get_connection()
    if request.method == "GET":
        project_id = request.args.get("project_id")
        query = "SELECT * FROM procurement_scenarios WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id = ?"
            params.append(int(project_id))
        if g.user["role"] != "administrator":
            query += " AND (created_by = ? OR is_demo = 1)"
            params.append(g.user["id"])
        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        for r in rows:
            r["scenario_inputs"] = json.loads(r["scenario_inputs"]) if r["scenario_inputs"] else {}
            r["result_summary"] = json.loads(r["result_summary"]) if r["result_summary"] else {}
            r["provenance"] = "DEMO" if r["is_demo"] else "SIMULATED_SCENARIO"
        return jsonify({"scenarios": rows})

    if g.user["role"] not in {"contractor", "administrator"}:
        conn.close()
        return error_response("Only contractors can save procurement scenarios.", 403)

    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    name = str(payload.get("scenario_name", "")).strip()
    strategy = payload.get("strategy", "cheapest")
    inputs = payload.get("scenario_inputs") or {}
    summary = payload.get("result_summary") or {}
    if not project_id or not name:
        conn.close()
        return error_response("project_id and scenario_name are required.", 400)

    cursor = conn.execute(
        """INSERT INTO procurement_scenarios (project_id, created_by, scenario_name, scenario_inputs, strategy, result_summary, is_demo)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (int(project_id), g.user["id"], name, json.dumps(inputs), strategy, json.dumps(summary)),
    )
    scenario_id = cursor.lastrowid
    audit(conn, g.user["id"], "scenario.saved", "procurement_scenario", scenario_id, {"name": name})
    conn.commit()
    conn.close()
    return jsonify({"scenario_id": scenario_id, "message": "What-if scenario saved.", "provenance": "SIMULATED_SCENARIO"}), 201


@app.route("/api/models/registry", methods=["GET"])
@authenticated
def models_registry_endpoint():
    conn = get_connection()
    models = conn.execute("SELECT * FROM model_registry ORDER BY id ASC").fetchall()
    conn.close()
    for m in models:
        m["preprocessing_config"] = json.loads(m.pop("preprocessing_config_json")) if m.get("preprocessing_config_json") else {}
        m["frozen_parameters"] = json.loads(m.pop("frozen_parameters_json")) if m.get("frozen_parameters_json") else {}
    return jsonify({"models": models, "count": len(models)})


@app.route("/api/evaluation/retrospective", methods=["GET"])
@authenticated
def retrospective_evaluation():
    conn = get_connection()
    material = request.args.get("material")
    # Load stored forecasts
    query = "SELECT * FROM forecasts WHERE 1=1"
    params = []
    if material:
        query += " AND lower(material) = lower(?)"
        params.append(material)
    query += " ORDER BY id DESC"
    forecast_rows = conn.execute(query, params).fetchall()
    conn.close()

    # Load actual WPI dataset
    df_wpi = load_wpi_data()
    pairs = []
    for f in forecast_rows:
        data_date = f["data_date"]
        mat_series = df_wpi[(df_wpi["material"].str.lower() == f["material"].lower()) & (df_wpi["date"] >= data_date)].sort_values("date")
        actual_val = float(mat_series.iloc[1]["wpi"]) if len(mat_series) > 1 else None
        pairs.append({
            "material": f["material"],
            "predicted": float(f["point_forecast"]),
            "actual": actual_val,
            "intervals": json.loads(f["intervals_json"]) if f.get("intervals_json") else {},
        })

    eval_result = evaluate_forecast_accuracy(pairs)
    eval_result["material_filtered"] = material or "all_materials"
    eval_result["total_forecast_records"] = len(forecast_rows)
    eval_result["data_provenance"] = "REAL_WPI"
    return jsonify(eval_result)


@app.route("/api/evaluation/supplier-risk", methods=["GET"])
@authenticated
def supplier_risk_evaluation():
    conn = get_connection()
    result = evaluate_supplier_risk_model(conn)
    conn.close()
    return jsonify(result)


@app.route("/api/evaluation/procurement-outcomes", methods=["GET"])
@authenticated
def procurement_outcomes_evaluation():
    conn = get_connection()
    project_id = request.args.get("project_id")
    p_id = int(project_id) if project_id and project_id.isdigit() else None
    result = evaluate_procurement_outcomes(conn, p_id)
    conn.close()
    return jsonify(result)


@app.route("/api/dashboard/research", methods=["GET"])
@authenticated
def research_dashboard():
    conn = get_connection()
    df_wpi = load_wpi_data()
    total_wpi_obs = len(df_wpi)
    mat_count = df_wpi["material"].nunique()

    real_orders = conn.execute("SELECT COUNT(*) AS c FROM orders WHERE demo = 0").fetchone()["c"]
    demo_orders = conn.execute("SELECT COUNT(*) AS c FROM orders WHERE demo = 1").fetchone()["c"]
    real_suppliers = conn.execute("SELECT COUNT(*) AS c FROM suppliers WHERE demo = 0").fetchone()["c"]
    demo_suppliers = conn.execute("SELECT COUNT(*) AS c FROM suppliers WHERE demo = 1").fetchone()["c"]
    forecasts_count = conn.execute("SELECT COUNT(*) AS c FROM forecasts").fetchone()["c"]
    scenarios_count = conn.execute("SELECT COUNT(*) AS c FROM procurement_scenarios").fetchone()["c"]
    outcomes_count = conn.execute("SELECT COUNT(*) AS c FROM order_delivery_outcomes").fetchone()["c"]
    models_count = conn.execute("SELECT COUNT(*) AS c FROM model_registry").fetchone()["c"]
    conn.close()

    conformal_summary = load_conformal_summary()

    return jsonify({
        "wpi_historical_coverage": {
            "total_observations": total_wpi_obs,
            "unique_materials": mat_count,
            "time_range": "2012-04 to 2026-03",
            "provenance": "REAL_WPI",
        },
        "records_by_provenance": {
            "real_wpi_observations": total_wpi_obs,
            "user_entered_suppliers": real_suppliers,
            "demo_suppliers": demo_suppliers,
            "real_purchase_orders": real_orders,
            "demo_purchase_orders": demo_orders,
            "real_delivery_outcomes": outcomes_count,
            "simulated_scenarios": scenarios_count,
            "generated_forecasts": forecasts_count,
        },
        "conformal_prediction_intervals": {
            "confidence_levels": ["80%", "90%", "95%"],
            "materials_calibrated": len(conformal_summary),
            "target_coverage_summary": "Held-out historical test empirical coverage matches nominal quantiles.",
        },
        "model_registry_summary": {
            "registered_models": models_count,
            "operational_forecaster": "Trend-Adjusted Naive (frozen-alpha)",
            "benchmark_models": ["ARIMA", "XGBoost", "LSTM"],
            "supplier_risk_status": "Experimental heuristic (requires genuine transaction history)",
        },
        "transparency_notice": "No synthetic data is ever blended with genuine supplier outcomes. Evaluation metrics are only computed when ground truth is verified.",
    })


@app.route("/api/import/preview", methods=["POST"])
@authenticated
def import_preview():
    payload = request.get_json(silent=True) or {}
    import_type = payload.get("import_type")
    csv_text = payload.get("csv_content", "")
    if not import_type or not csv_text:
        return error_response("import_type and csv_content are required.", 400)

    try:
        valid_rows, error_rows, summary = validate_csv_import(import_type, csv_text, MATERIAL_NAMES)
    except ValueError as exc:
        return error_response(str(exc), 400)

    return jsonify({
        "import_type": import_type,
        "summary": summary,
        "valid_rows": valid_rows,
        "error_rows": error_rows,
    })


@app.route("/api/import/commit", methods=["POST"])
@authenticated
def import_commit():
    payload = request.get_json(silent=True) or {}
    import_type = payload.get("import_type")
    rows = payload.get("rows", [])
    if not import_type or not isinstance(rows, list) or not rows:
        return error_response("import_type and a non-empty list of validated rows are required.", 400)

    conn = get_connection()
    committed_count = 0
    try:
        if import_type == "material_listings":
            if g.user["role"] != "supplier":
                conn.close()
                return error_response("Only suppliers can import material listings.", 403)
            supplier = conn.execute("SELECT id FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
            if not supplier:
                conn.close()
                return error_response("Supplier profile not found.", 404)
            for r in rows:
                conn.execute(
                    """INSERT INTO supplier_material_listings
                       (supplier_id, material_name, quoted_unit_price, available_quantity, minimum_order_quantity, unit, estimated_delivery_days, availability_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'Available')""",
                    (supplier["id"], r["material_name"], r["quoted_unit_price"], r["available_quantity"], r.get("minimum_order_quantity", 1.0), r.get("unit", "Metric Ton"), r["estimated_delivery_days"]),
                )
                committed_count += 1

        elif import_type == "supplier_quotations":
            if g.user["role"] != "supplier":
                conn.close()
                return error_response("Only suppliers can import quotations.", 403)
            supplier = conn.execute("SELECT id FROM suppliers WHERE owner_user_id = ?", (g.user["id"],)).fetchone()
            if not supplier:
                conn.close()
                return error_response("Supplier profile not found.", 404)
            for r in rows:
                conn.execute(
                    """INSERT INTO supplier_quotes
                       (supplier_id, material, quote_price, available_quantity, delivery_days, distance_km, demo)
                       VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (supplier["id"], r["material"], r["quote_price"], r["available_quantity"], r["delivery_days"], r.get("distance_km", 0.0)),
                )
                committed_count += 1

        elif import_type == "delivery_outcomes":
            for r in rows:
                conn.execute(
                    """INSERT INTO order_delivery_outcomes
                       (order_id, actual_delivery_date, final_paid_price, cancelled, delay_days, recorded_by)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(order_id) DO UPDATE SET
                         actual_delivery_date = excluded.actual_delivery_date,
                         final_paid_price = excluded.final_paid_price,
                         cancelled = excluded.cancelled,
                         delay_days = excluded.delay_days,
                         recorded_by = excluded.recorded_by""",
                    (r["order_id"], r.get("actual_delivery_date"), r.get("final_paid_price"), r.get("cancelled", 0), r.get("delay_days", 0), g.user["id"]),
                )
                committed_count += 1

        elif import_type == "wpi_observations":
            if g.user["role"] != "administrator":
                conn.close()
                return error_response("Only administrators can import WPI observations.", 403)
            for r in rows:
                conn.execute(
                    """INSERT OR REPLACE INTO wpi_observations
                       (material_name, observation_date, index_value, data_source)
                       VALUES (?, ?, ?, ?)""",
                    (r["material_name"], r["observation_date"], r["index_value"], r.get("data_source", "USER_ENTERED")),
                )
                committed_count += 1

        audit(conn, g.user["id"], "data.imported", import_type, committed_count, {"row_count": committed_count})
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return error_response(f"Import commit failed: {str(exc)}", 500)
    finally:
        conn.close()

    return jsonify({"committed_rows": committed_count, "import_type": import_type, "message": f"Successfully imported {committed_count} records."}), 201


@app.route("/api/reports/scenarios.csv", methods=["GET"])
@authenticated
def scenario_report():
    conn = get_connection()
    if g.user["role"] == "administrator":
        rows = conn.execute("SELECT * FROM procurement_scenarios ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM procurement_scenarios WHERE created_by = ? OR is_demo = 1 ORDER BY id DESC", (g.user["id"],)).fetchall()
    conn.close()
    return csv_download("buildconnect-procurement-scenarios.csv", rows)


@app.route("/api/reports/evaluation.csv", methods=["GET"])
@authenticated
def evaluation_csv_report():
    if not FINAL_RESULTS_PATH.exists():
        return csv_download("buildconnect-evaluation.csv", [])
    df = pd.read_csv(FINAL_RESULTS_PATH)
    rows = df.to_dict(orient="records")
    return csv_download("buildconnect-evaluation-metrics.csv", rows)



def startup_actions():
    if os.environ.get("FLASK_ENV") == "production":
        if app.config["SECRET_KEY"] == "local-development-key-change-before-deploy" or len(app.config["SECRET_KEY"]) < 32:
            raise RuntimeError("Production requires BUILDCONNECT_SECRET_KEY with at least 32 characters.")
        if POSTGRES_ENGINE is None:
            raise RuntimeError("Production requires a PostgreSQL DATABASE_URL.")
    init_db()
    seed_demo_data()


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return error_response("Resource not found.", 404)
    return "Not found.", 404


@app.errorhandler(405)
def method_not_allowed(_error):
    return error_response("Method not allowed.", 405) if request.path.startswith("/api/") else ("Method not allowed.", 405)


@app.errorhandler(413)
def request_too_large(_error):
    return error_response("Request body exceeds the 1 MB limit.", 413)


@app.errorhandler(500)
def internal_error(error):
    app.logger.error("Unhandled application error: %s", error)
    return error_response("An internal server error occurred. Check application logs for details.", 500)


if __name__ == "__main__":
    import getpass
    import sys

    startup_actions()
    if len(sys.argv) == 3 and sys.argv[1] == "create-admin":
        email = sys.argv[2].strip().lower()
        password = getpass.getpass("Admin password (minimum 12 characters): ")
        if len(password) < 12:
            raise SystemExit("Password must be at least 12 characters.")
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role, demo) VALUES (?, ?, ?, 'administrator', 0)",
                ("BuildConnect Administrator", email, generate_password_hash(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise SystemExit("An account with this email already exists.") from exc
        finally:
            conn.close()
        raise SystemExit("Administrator account created.")
    if len(sys.argv) > 1:
        raise SystemExit("Usage: python app.py [create-admin <email>]")
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
