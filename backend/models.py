from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    full_name = Column(String(120), nullable=True)
    email = Column(String(254), nullable=False, unique=True, index=True)
    password_hash = Column(String(256), nullable=False)
    phone_number = Column(String(30), nullable=True)
    role = Column(String(30), nullable=False, default="contractor") # contractor, supplier, administrator
    account_status = Column(String(30), nullable=False, default="active") # active, suspended, pending
    demo = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "full_name": self.full_name or self.name,
            "email": self.email,
            "phone_number": self.phone_number,
            "role": self.role,
            "account_status": self.account_status,
            "demo": self.demo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


class SupplierProfile(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(150), nullable=False)
    business_name = Column(String(150), nullable=True)
    business_description = Column(Text, nullable=True)
    category = Column(String(120), nullable=False)
    contact_person = Column(String(120), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(254), nullable=True)
    address = Column(String(255), nullable=True)
    city = Column(String(120), nullable=False, index=True)
    state = Column(String(120), nullable=True)
    postal_code = Column(String(30), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    rating = Column(Float, nullable=True, default=4.0)
    review_count = Column(Integer, nullable=False, default=0)
    verified = Column(Integer, nullable=False, default=0)
    verification_status = Column(String(30), nullable=False, default="unverified") # unverified, pending, verified, rejected
    availability = Column(String(50), nullable=False, default="Available")
    risk_category = Column(String(30), nullable=False, default="Unknown")
    account_status = Column(String(30), nullable=False, default="active")
    demo = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "name": self.name,
            "business_name": self.business_name or self.name,
            "business_description": self.business_description or "",
            "category": self.category,
            "contact_person": self.contact_person or "",
            "phone": self.phone or "",
            "email": self.email or "",
            "address": self.address or "",
            "city": self.city,
            "state": self.state or "",
            "postal_code": self.postal_code or "",
            "latitude": self.latitude,
            "longitude": self.longitude,
            "rating": self.rating,
            "review_count": self.review_count,
            "verified": self.verified,
            "verification_status": self.verification_status,
            "availability": self.availability,
            "risk_category": self.risk_category,
            "account_status": self.account_status,
            "demo": self.demo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SupplierVerificationRecord(Base):
    __tablename__ = "supplier_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, unique=True, index=True)
    verification_type = Column(String(50), nullable=False, default="business_license")
    verification_status = Column(String(30), nullable=False, default="verified") # pending, verified, rejected
    evidence_reference = Column(Text, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, default=datetime.utcnow)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "verification_type": self.verification_type,
            "verification_status": self.verification_status,
            "evidence_reference": self.evidence_reference,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "notes": self.notes,
        }


class MaterialCatalog(Base):
    __tablename__ = "material_catalog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_name = Column(String(150), nullable=False, unique=True, index=True)
    category = Column(String(100), nullable=False, index=True)
    unit = Column(String(50), nullable=False, default="Metric Ton")
    description = Column(Text, nullable=True)
    wpi_supported = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "material_name": self.material_name,
            "category": self.category,
            "unit": self.unit,
            "description": self.description,
            "wpi_supported": self.wpi_supported,
            "active": self.active,
        }


class SupplierMaterialListing(Base):
    __tablename__ = "supplier_material_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True, index=True)
    material_name = Column(String(150), nullable=False, index=True)
    quoted_unit_price = Column(Float, nullable=False)
    available_quantity = Column(Float, nullable=False)
    minimum_order_quantity = Column(Float, nullable=False, default=1.0)
    unit = Column(String(50), nullable=False, default="Metric Ton")
    estimated_delivery_days = Column(Integer, nullable=False)
    availability_status = Column(String(50), nullable=False, default="Available")
    quote_valid_until = Column(String(30), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "material_id": self.material_id,
            "material_name": self.material_name,
            "quoted_unit_price": self.quoted_unit_price,
            "available_quantity": self.available_quantity,
            "minimum_order_quantity": self.minimum_order_quantity,
            "unit": self.unit,
            "estimated_delivery_days": self.estimated_delivery_days,
            "availability_status": self.availability_status,
            "quote_valid_until": self.quote_valid_until,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(200), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    budget = Column(Float, nullable=False)
    start_date = Column(String(30), nullable=False)
    deadline = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default="active") # active, archived, completed
    demo = Column(Integer, nullable=False, default=0)
    archived_at = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id or self.created_by,
            "created_by": self.created_by or self.owner_user_id,
            "name": self.name,
            "description": self.description or "",
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "budget": self.budget,
            "start_date": self.start_date,
            "deadline": self.deadline,
            "status": self.status,
            "demo": self.demo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProjectMaterialRequirement(Base):
    __tablename__ = "project_materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True, index=True)
    material = Column(String(150), nullable=False, index=True)
    required_quantity = Column(Float, nullable=False)
    current_inventory = Column(Float, nullable=False, default=0.0)
    ordered_quantity = Column(Float, nullable=False, default=0.0)
    unit = Column(String(50), nullable=False, default="Metric Ton")
    unit_cost = Column(Float, nullable=False, default=0.0)
    target_unit_price = Column(Float, nullable=True)
    required_by_date = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        remaining = max(0.0, float(self.required_quantity) - float(self.current_inventory) - float(self.ordered_quantity))
        return {
            "id": self.id,
            "project_id": self.project_id,
            "material_id": self.material_id,
            "material": self.material,
            "required_quantity": self.required_quantity,
            "current_inventory": self.current_inventory,
            "ordered_quantity": self.ordered_quantity,
            "remaining_quantity": remaining,
            "unit": self.unit,
            "unit_cost": self.unit_cost,
            "target_unit_price": self.target_unit_price,
            "required_by_date": self.required_by_date,
        }


class SupplierQuotation(Base):
    __tablename__ = "supplier_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True, index=True)
    material = Column(String(150), nullable=False, index=True)
    quote_price = Column(Float, nullable=False)
    quoted_quantity = Column(Float, nullable=True)
    available_quantity = Column(Float, nullable=False)
    minimum_order_quantity = Column(Float, nullable=False, default=1.0)
    unit = Column(String(50), nullable=False, default="Metric Ton")
    delivery_days = Column(Integer, nullable=False)
    transport_cost = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    quotation_status = Column(String(30), nullable=False, default="active") # active, expired, withdrawn
    valid_until = Column(String(30), nullable=True)
    demo = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "project_id": self.project_id,
            "material_id": self.material_id,
            "material": self.material,
            "quote_price": self.quote_price,
            "quoted_unit_price": self.quote_price,
            "quoted_quantity": self.quoted_quantity or self.available_quantity,
            "available_quantity": self.available_quantity,
            "minimum_order_quantity": self.minimum_order_quantity,
            "unit": self.unit,
            "delivery_days": self.delivery_days,
            "promised_delivery_days": self.delivery_days,
            "transport_cost": self.transport_cost,
            "distance_km": self.distance_km,
            "risk_score": self.risk_score,
            "quotation_status": self.quotation_status,
            "valid_until": self.valid_until,
            "demo": self.demo,
        }


class WPIObservation(Base):
    __tablename__ = "wpi_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True, index=True)
    material_name = Column(String(150), nullable=False, index=True)
    observation_date = Column(String(30), nullable=False, index=True)
    index_value = Column(Float, nullable=False)
    data_source = Column(String(100), nullable=False, default="REAL_WPI")
    imported_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("material_name", "observation_date", name="uq_wpi_material_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "material_id": self.material_id,
            "material_name": self.material_name,
            "observation_date": self.observation_date,
            "index_value": self.index_value,
            "data_source": self.data_source,
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
        }


class ForecastRecord(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True, index=True)
    material = Column(String(150), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=False)
    forecast_origin_date = Column(String(30), nullable=True)
    forecast_target_date = Column(String(30), nullable=True)
    current_index = Column(Float, nullable=True)
    predicted_index = Column(Float, nullable=True)
    point_forecast = Column(Float, nullable=False)
    interval_80_lower = Column(Float, nullable=True)
    interval_80_upper = Column(Float, nullable=True)
    interval_90_lower = Column(Float, nullable=True)
    interval_90_upper = Column(Float, nullable=True)
    interval_95_lower = Column(Float, nullable=True)
    interval_95_upper = Column(Float, nullable=True)
    intervals_json = Column(Text, nullable=False)
    data_date = Column(String(30), nullable=False)
    generated_at = Column(String(50), nullable=False)
    data_source = Column(String(100), nullable=False)
    input_data_provenance = Column(String(50), nullable=False, default="REAL_WPI")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "requested_by": self.requested_by,
            "material": self.material,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "current_index": self.current_index or self.point_forecast,
            "point_forecast": self.point_forecast,
            "predicted_index": self.predicted_index or self.point_forecast,
            "interval_80": {"lower": self.interval_80_lower, "upper": self.interval_80_upper},
            "interval_90": {"lower": self.interval_90_lower, "upper": self.interval_90_upper},
            "interval_95": {"lower": self.interval_95_lower, "upper": self.interval_95_upper},
            "data_date": self.data_date,
            "generated_at": self.generated_at,
            "data_source": self.data_source,
            "input_data_provenance": self.input_data_provenance,
        }


class SupplierRiskPrediction(Base):
    __tablename__ = "supplier_risk_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True)
    material_name = Column(String(150), nullable=True)
    predicted_late_probability = Column(Float, nullable=True)
    risk_category = Column(String(30), nullable=False, default="Unknown") # Low, Medium, High, Unknown
    model_name = Column(String(100), nullable=False, default="Empirical-History-Heuristic")
    model_version = Column(String(50), nullable=False, default="v1.0")
    input_data_provenance = Column(String(50), nullable=False, default="USER_ENTERED")
    prediction_evidence_level = Column(String(30), nullable=False, default="insufficient") # insufficient, low, moderate, high
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "material_name": self.material_name,
            "predicted_late_probability": self.predicted_late_probability,
            "risk_category": self.risk_category,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "input_data_provenance": self.input_data_provenance,
            "prediction_evidence_level": self.prediction_evidence_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PurchaseOrder(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("procurement_plans.id"), nullable=False, index=True)
    plan_item_id = Column(Integer, ForeignKey("procurement_plan_items.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("supplier_quotes.id"), nullable=False)
    order_reference = Column(String(100), nullable=True, unique=True, index=True)
    material = Column(String(150), nullable=False)
    quantity = Column(Float, nullable=False)
    quoted_unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=True)
    transport_cost = Column(Float, nullable=True, default=0.0)
    total_cost = Column(Float, nullable=True)
    promised_delivery_date = Column(String(30), nullable=False)
    expected_delivery_date = Column(String(30), nullable=True)
    order_status = Column(String(30), nullable=False, default="placed") # placed, accepted, rejected, in-transit, delivered, cancelled, closed
    status = Column(String(30), nullable=False, default="placed")
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    demo = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        line_subtotal = self.subtotal or (self.quantity * self.quoted_unit_price)
        total = self.total_cost or (line_subtotal + (self.transport_cost or 0.0))
        return {
            "id": self.id,
            "order_reference": self.order_reference or f"PO-{self.id:05d}",
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "created_by": self.created_by,
            "supplier_id": self.supplier_id,
            "quote_id": self.quote_id,
            "material": self.material,
            "quantity": self.quantity,
            "quoted_unit_price": self.quoted_unit_price,
            "subtotal": line_subtotal,
            "transport_cost": self.transport_cost or 0.0,
            "total_cost": total,
            "promised_delivery_date": self.promised_delivery_date,
            "expected_delivery_date": self.expected_delivery_date or self.promised_delivery_date,
            "order_status": self.order_status or self.status,
            "status": self.status,
            "demo": self.demo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True)
    material = Column(String(150), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False, default="Metric Ton")
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    promised_delivery_date = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "purchase_order_id": self.purchase_order_id,
            "material": self.material,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "line_total": self.line_total,
            "promised_delivery_date": self.promised_delivery_date,
        }


class DeliveryOutcome(Base):
    __tablename__ = "order_delivery_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True, index=True)
    purchase_order_id = Column(Integer, nullable=True)
    purchase_order_item_id = Column(Integer, nullable=True)
    actual_delivery_date = Column(String(30), nullable=True)
    actual_quantity_received = Column(Float, nullable=True)
    final_paid_price = Column(Float, nullable=True)
    final_paid_unit_price = Column(Float, nullable=True)
    cancelled = Column(Integer, nullable=False, default=0)
    cancellation_status = Column(String(30), nullable=False, default="none") # none, contractor_cancelled, supplier_rejected
    delivery_status = Column(String(30), nullable=False, default="pending") # on_time, delayed, cancelled, partial
    delay_days = Column(Integer, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "actual_delivery_date": self.actual_delivery_date,
            "actual_quantity_received": self.actual_quantity_received,
            "final_paid_price": self.final_paid_price,
            "final_paid_unit_price": self.final_paid_unit_price,
            "cancelled": self.cancelled,
            "cancellation_status": self.cancellation_status,
            "delivery_status": self.delivery_status,
            "delay_days": self.delay_days,
            "recorded_by": self.recorded_by,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    purchase_order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    rating = Column(Float, nullable=False)
    review_text = Column(Text, nullable=False)
    review_status = Column(String(30), nullable=False, default="approved") # approved, pending_moderation, rejected
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "user_id": self.user_id,
            "purchase_order_id": self.purchase_order_id,
            "rating": self.rating,
            "review_text": self.review_text,
            "review_status": self.review_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProcurementScenario(Base):
    __tablename__ = "procurement_scenarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scenario_name = Column(String(150), nullable=False)
    scenario_inputs = Column(Text, nullable=False) # JSON
    strategy = Column(String(50), nullable=False)
    result_summary = Column(Text, nullable=False) # JSON
    is_demo = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "project_id": self.project_id,
            "created_by": self.created_by,
            "scenario_name": self.scenario_name,
            "scenario_inputs": json.loads(self.scenario_inputs) if self.scenario_inputs else {},
            "strategy": self.strategy,
            "result_summary": json.loads(self.result_summary) if self.result_summary else {},
            "is_demo": self.is_demo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProcurementPlan(Base):
    __tablename__ = "procurement_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="proposed") # draft, proposed, submitted, approved, rejected, ordered, closed
    selected_strategy = Column(String(50), nullable=False)
    strategy = Column(String(50), nullable=True)
    total_material_cost = Column(Float, nullable=True)
    total_transport_cost = Column(Float, nullable=True)
    total_estimated_cost = Column(Float, nullable=True)
    expected_delivery_days = Column(Integer, nullable=True)
    estimated_delivery_risk = Column(Float, nullable=True)
    shortage_quantity = Column(Float, nullable=True, default=0.0)
    alternatives_json = Column(Text, nullable=False)
    assumptions_json = Column(Text, nullable=False, default="{}")
    is_demo = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "project_id": self.project_id,
            "created_by": self.created_by,
            "status": self.status,
            "selected_strategy": self.selected_strategy,
            "strategy": self.strategy or self.selected_strategy,
            "total_material_cost": self.total_material_cost,
            "total_transport_cost": self.total_transport_cost,
            "total_estimated_cost": self.total_estimated_cost,
            "expected_delivery_days": self.expected_delivery_days,
            "estimated_delivery_risk": self.estimated_delivery_risk,
            "shortage_quantity": self.shortage_quantity,
            "alternatives": json.loads(self.alternatives_json) if self.alternatives_json else {},
            "assumptions": json.loads(self.assumptions_json) if self.assumptions_json else {},
            "is_demo": self.is_demo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProcurementPlanItem(Base):
    __tablename__ = "procurement_plan_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("procurement_plans.id"), nullable=False, index=True)
    procurement_plan_id = Column(Integer, nullable=True)
    project_material_id = Column(Integer, ForeignKey("project_materials.id"), nullable=False)
    quote_id = Column(Integer, ForeignKey("supplier_quotes.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    material_id = Column(Integer, ForeignKey("material_catalog.id"), nullable=True)
    allocated_quantity = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    quoted_unit_price = Column(Float, nullable=True)
    estimated_transport_cost = Column(Float, nullable=True)
    estimated_delivery_days = Column(Integer, nullable=True)
    estimated_late_probability = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "project_material_id": self.project_material_id,
            "quote_id": self.quote_id,
            "supplier_id": self.supplier_id,
            "allocated_quantity": self.allocated_quantity or self.quantity,
            "quantity": self.quantity,
            "quoted_unit_price": self.quoted_unit_price,
            "estimated_transport_cost": self.estimated_transport_cost,
            "estimated_delivery_days": self.estimated_delivery_days,
            "estimated_late_probability": self.estimated_late_probability,
        }


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_user_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False, index=True)
    entity = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=False, index=True)
    details_json = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        details_val = self.details_json or self.details or "{}"
        try:
            parsed = json.loads(details_val)
        except Exception:
            parsed = {"raw": details_val}
        return {
            "id": self.id,
            "actor_id": self.actor_id or self.actor_user_id,
            "action": self.action,
            "entity": self.entity or self.entity_type,
            "entity_id": self.entity_id,
            "details": parsed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False, index=True)
    model_version = Column(String(50), nullable=False)
    task_type = Column(String(50), nullable=False) # price_forecast, supplier_risk, ranking, procurement_optimizer
    artifact_location = Column(String(255), nullable=True)
    feature_schema_version = Column(String(50), nullable=False, default="v1.0")
    preprocessing_config_json = Column(Text, nullable=True)
    training_dataset_desc = Column(Text, nullable=True)
    dataset_provenance = Column(String(50), nullable=False, default="REAL_WPI") # REAL_WPI, SYNTHETIC_RESEARCH
    training_period = Column(String(100), nullable=True)
    validation_period = Column(String(100), nullable=True)
    test_period = Column(String(100), nullable=True)
    frozen_parameters_json = Column(Text, nullable=True)
    deployment_status = Column(String(30), nullable=False, default="production_frozen") # production_frozen, experimental, comparison_only
    documentation_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "task_type": self.task_type,
            "artifact_location": self.artifact_location,
            "feature_schema_version": self.feature_schema_version,
            "preprocessing_config": json.loads(self.preprocessing_config_json) if self.preprocessing_config_json else {},
            "training_dataset_desc": self.training_dataset_desc,
            "dataset_provenance": self.dataset_provenance,
            "training_period": self.training_period,
            "validation_period": self.validation_period,
            "test_period": self.test_period,
            "frozen_parameters": json.loads(self.frozen_parameters_json) if self.frozen_parameters_json else {},
            "deployment_status": self.deployment_status,
            "documentation_reference": self.documentation_reference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
