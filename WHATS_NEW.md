# BuildConnect AI — What's New in Phases 2, 3, & 4

**Date:** 2026-11-01  
**Phases:** Phase 2 (Authentication & Database Foundation), Phase 3 (Marketplace, Procurement, & Order Lifecycle), Phase 4 (Provenance, Evaluation, CSV Tools, & Research Dashboard)

---

## 🆕 Major Features & Capabilities Added

### 1. Database Foundation & Architecture (Phase 2)
- **Centralized Engine & Connection Pooling** (`backend/database.py`):
  - Environment-driven configuration supporting SQLite (`sqlite:///buildconnect.db`) and PostgreSQL (`postgresql+psycopg2://...`).
  - Connection pooling with `pool_size=10, max_overflow=20`, connection recycling, and automatic rollback handlers.
- **Relational Domain Models** (`backend/models.py`):
  - 20 Declarative SQLAlchemy models: `User`, `SupplierProfile`, `SupplierVerificationRecord`, `MaterialCatalog`, `SupplierMaterialListing`, `Project`, `ProjectMaterialRequirement`, `SupplierQuotation`, `WPIObservation`, `ForecastRecord`, `SupplierRiskPrediction`, `PurchaseOrder`, `PurchaseOrderItem`, `DeliveryOutcome`, `Review`, `ProcurementScenario`, `ProcurementPlan`, `ProcurementPlanItem`, `AuditLog`, and `ModelRegistry`.
- **Alembic Migrations** (`backend/alembic.ini`, `backend/migrations/`):
  - Production-ready migration setup with migration script `001_phase2_phase3_phase4_schema.py`.
- **Authentication & RBAC**:
  - Secure registration, login, logout, password change, account status management, password reset token workflow, and profile updates.
  - Role-based decorators `@contractor_required`, `@supplier_required`, and `@admin_required`.
  - Double-submit CSRF protection on all mutating API calls.

### 2. Supplier Marketplace & Procurement Workflow (Phase 3)
- **Supplier Directory & Intelligence** (`frontend/src/pages/SuppliersPage.tsx`, `/api/suppliers`, `/api/supplier-listings`):
  - Material search, category filters, city/location filters, price/delivery sorting, availability filters.
  - Modal inspection showing verification badge, active material quotes, and routing coordinates.
  - Bayesian average rating shrinkage ($\frac{v \cdot R + m \cdot C}{v + m}$) with unrated indicators for zero-review suppliers.
- **Project Requirements Management** (`frontend/src/pages/ProjectsPage.tsx`, `/api/projects`):
  - Required quantity, current inventory, and ordered quantity inputs.
  - Real-time remaining procurement calculation: $\max(0, \text{required} - \text{inventory} - \text{ordered})$.
  - Target unit price and required-by date support.
- **Multi-Objective Procurement Optimization** (`frontend/src/pages/ProcurementPage.tsx`, `/api/procurement/optimize`):
  - 5 operational strategies: Cheapest, Lowest Delivery Risk, Fastest Delivery, Balanced Risk/Cost, and **NSGA-II Pareto Frontier** synthesis.
  - Plan proposal, review, and formal approval/rejection before purchase order issuance.
- **Order Lifecycle & Delivery Outcomes** (`frontend/src/pages/OrdersPage.tsx`, `/api/orders`):
  - Order progression: `placed` $\to$ `accepted` $\to$ `in-transit` $\to$ `delivered`.
  - Delivery outcome recording: actual delivery date, delay days, actual quantity received, and final paid price.
  - Post-delivery customer reviews (1-5 stars) allowed only on delivered orders.
- **What-If Procurement Scenarios** (`frontend/src/pages/ScenariosPage.tsx`, `/api/scenarios`):
  - Interactive simulator for budget shifts, deadline compression, transport inflation, and supplier outages.
  - Direct scenario saving and comparison against baseline allocations.

### 3. Data Provenance, Retrospective Evaluation, & Controlled CSV Tools (Phase 4)
- **Data Provenance Architecture** (`backend/services/provenance.py`):
  - Strict tagging (`REAL_WPI`, `USER_ENTERED`, `REAL_TRANSACTION`, `SYNTHETIC_RESEARCH`, `DEMO`, `SIMULATED_SCENARIO`).
  - Zero-leakage guarantee preventing test set leakage and separating simulated outcomes from historical data.
- **Zero-Leakage Feature Extraction** (`backend/services/supplier_features.py`):
  - Historical delivery metrics calculated strictly prior to prediction timestamp $t$.
- **Retrospective Model Evaluation** (`backend/services/evaluation.py`):
  - Out-of-sample holdout metrics: MAE, RMSE, MAPE, sMAPE, $R^2$, and conformal prediction coverage.
  - Supplier risk evaluation returns `INSUFFICIENT_REAL_LABELLED_DATA` when lacking genuine real-world labels.
- **Controlled CSV Import & Export** (`backend/services/importer_exporter.py`, `frontend/src/pages/DataImportPage.tsx`):
  - Live schema validation, row-by-row dry-run preview, and automatic quarantining of corrupt records.
  - Downloadable templates and direct CSV exports for forecasts, orders, scenarios, and evaluation metrics.
- **Research Dashboard & Model Registry** (`frontend/src/pages/ResearchDashboardPage.tsx`, `/api/models/registry`):
  - Registered model metadata, training timeframes, empirical conformal coverage charts, and system provenance matrix.

---

## 📁 New Files Created

### Backend Services & Models
- `backend/database.py`: Centralized DB engine, connection pooling, and environment config.
- `backend/models.py`: Declarative SQLAlchemy models for all 20 domain entities.
- `backend/alembic.ini`: Alembic migration configuration.
- `backend/migrations/env.py`: Alembic environment runner.
- `backend/migrations/script.py.mako`: Alembic migration script template.
- `backend/migrations/versions/001_phase2_phase3_phase4_schema.py`: Initial schema migration.
- `backend/services/provenance.py`: Data provenance definitions, validation, and zero-leakage helpers.
- `backend/services/supplier_features.py`: Zero-leakage historical features and Bayesian rating calculation.
- `backend/services/supplier_ranking.py`: Multi-criteria utility ranking with explainability.
- `backend/services/procurement_optimizer.py`: 5 procurement optimization strategies including NSGA-II Pareto.
- `backend/services/evaluation.py`: Time-series forecasting and supplier risk evaluation services.
- `backend/services/model_registry.py`: Model registry metadata and default artifact seeding.
- `backend/services/importer_exporter.py`: Controlled CSV import validation, preview, quarantining, and templates.

### Frontend Pages
- `frontend/src/pages/ProfilePage.tsx`: User profile, enterprise supplier details, and password updates.
- `frontend/src/pages/OrdersPage.tsx`: Order lifecycle tracking, status progression, delivery outcomes, and reviews.
- `frontend/src/pages/ScenariosPage.tsx`: What-if procurement scenario simulator and scenario archive.
- `frontend/src/pages/ResearchDashboardPage.tsx`: Research analytics, model registry, conformal coverage, and provenance.
- `frontend/src/pages/DataImportPage.tsx`: Controlled CSV importer with dry-run preview and downloadable templates.
- `frontend/src/pages/AccessDeniedPage.tsx`: 403 Access Denied notification page.

---

## ⚙️ Testing Status

> [!NOTE]
> Per explicit user requirement, automated test execution, test suites, and end-to-end verification commands were not run during this implementation phase. All features have been implemented and documented, with testing scheduled for a separate follow-up cycle.
