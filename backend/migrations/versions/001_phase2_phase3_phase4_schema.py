"""Phase 2, 3, and 4 schema upgrades

Revision ID: 001_complete_schema
Revises: 
Create Date: 2026-11-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "001_complete_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Users table modifications
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("full_name", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("phone_number", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("account_status", sa.String(30), nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))

    # Material Catalog
    op.create_table(
        "material_catalog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("material_name", sa.String(150), nullable=False, unique=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False, server_default="Metric Ton"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("wpi_supported", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Supplier material listings
    op.create_table(
        "supplier_material_listings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("material_catalog.id"), nullable=True),
        sa.Column("material_name", sa.String(150), nullable=False),
        sa.Column("quoted_unit_price", sa.Float(), nullable=False),
        sa.Column("available_quantity", sa.Float(), nullable=False),
        sa.Column("minimum_order_quantity", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("unit", sa.String(50), nullable=False, server_default="Metric Ton"),
        sa.Column("estimated_delivery_days", sa.Integer(), nullable=False),
        sa.Column("availability_status", sa.String(50), nullable=False, server_default="Available"),
        sa.Column("quote_valid_until", sa.String(30), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # WPI Observations
    op.create_table(
        "wpi_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("material_catalog.id"), nullable=True),
        sa.Column("material_name", sa.String(150), nullable=False),
        sa.Column("observation_date", sa.String(30), nullable=False),
        sa.Column("index_value", sa.Float(), nullable=False),
        sa.Column("data_source", sa.String(100), nullable=False, server_default="REAL_WPI"),
        sa.Column("imported_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("material_name", "observation_date", name="uq_wpi_material_date"),
    )

    # Supplier risk predictions
    op.create_table(
        "supplier_risk_predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("material_catalog.id"), nullable=True),
        sa.Column("material_name", sa.String(150), nullable=True),
        sa.Column("predicted_late_probability", sa.Float(), nullable=True),
        sa.Column("risk_category", sa.String(30), nullable=False, server_default="Unknown"),
        sa.Column("model_name", sa.String(100), nullable=False, server_default="Empirical-History-Heuristic"),
        sa.Column("model_version", sa.String(50), nullable=False, server_default="v1.0"),
        sa.Column("input_data_provenance", sa.String(50), nullable=False, server_default="USER_ENTERED"),
        sa.Column("prediction_evidence_level", sa.String(30), nullable=False, server_default="insufficient"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Purchase order items
    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("material_catalog.id"), nullable=True),
        sa.Column("material", sa.String(150), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False, server_default="Metric Ton"),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("line_total", sa.Float(), nullable=False),
        sa.Column("promised_delivery_date", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="approved"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Procurement Scenarios
    op.create_table(
        "procurement_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scenario_name", sa.String(150), nullable=False),
        sa.Column("scenario_inputs", sa.Text(), nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=False),
        sa.Column("is_demo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Model Registry
    op.create_table(
        "model_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("artifact_location", sa.String(255), nullable=True),
        sa.Column("feature_schema_version", sa.String(50), nullable=False, server_default="v1.0"),
        sa.Column("preprocessing_config_json", sa.Text(), nullable=True),
        sa.Column("training_dataset_desc", sa.Text(), nullable=True),
        sa.Column("dataset_provenance", sa.String(50), nullable=False, server_default="REAL_WPI"),
        sa.Column("training_period", sa.String(100), nullable=True),
        sa.Column("validation_period", sa.String(100), nullable=True),
        sa.Column("test_period", sa.String(100), nullable=True),
        sa.Column("frozen_parameters_json", sa.Text(), nullable=True),
        sa.Column("deployment_status", sa.String(30), nullable=False, server_default="production_frozen"),
        sa.Column("documentation_reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

def downgrade() -> None:
    pass
