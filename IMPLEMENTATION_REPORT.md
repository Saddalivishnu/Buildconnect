# BuildConnect AI — Implementation Report (Phases 2, 3, & 4)

**Date:** 2026-11-01  
**Status:** Phases 2, 3, and 4 Fully Implemented  
**Architecture:** Multi-User Flask + SQLAlchemy + React TypeScript Enterprise Procurement Platform  

---

## Executive Summary

BuildConnect AI has been expanded from its initial research baseline into a complete, database-backed, multi-user construction procurement intelligence platform. The system directly integrates:
1. **Real Construction Wholesale Price Index (WPI) time series** (MoSPI / Office of the Economic Adviser, 20 materials, ~3,380 monthly observations).
2. **Material-specific Trend-Adjusted Naive forecasting** with frozen $\alpha$ parameters and non-parametric conformal prediction uncertainty intervals (80%, 90%, 95%).
3. **Frozen Buy/Wait directional decision logic** operating on the validation-selected $\pm 0.25\%$ movement threshold with deadline-conflict detection across 8 distinct operational categories.
4. **Supplier Intelligence & Marketplace** featuring transparent multi-criteria utility ranking, zero-leakage feature extraction, and Bayesian rating shrinkage:
   $$\text{Bayesian Rating} = \frac{v \cdot R + m \cdot C}{v + m}$$
5. **Multi-Objective Procurement Optimization** supporting 5 operational strategies: Cheapest, Lowest Risk, Fastest Delivery, Balanced Risk/Cost, and NSGA-II Pareto Frontier synthesis.
6. **End-to-End Order Lifecycle & What-If Scenarios** supporting status transitions, delivery outcome recording, post-delivery reviews, and stress testing against budget cuts, lead-time compression, transport inflation, and supplier outages.
7. **Strict Data Provenance & Controlled CSV Import/Export** enforcing provenance tags (`REAL_WPI`, `USER_ENTERED`, `REAL_TRANSACTION`, `SYNTHETIC_RESEARCH`, `DEMO`, `SIMULATED_SCENARIO`), zero data leakage, and a research dashboard with model registry and conformal coverage analysis.

---

## 1. Phase 2: Database Architecture, Models, & Security

### 1.1 Dual Database Engine Configuration
- **SQLite Support**: Zero-configuration default development engine using local file `buildconnect.db`.
- **PostgreSQL Support**: Multi-user production deployment engine with SQLAlchemy connection pooling (`pool_size=10, max_overflow=20`), connection timeout handling, and automatic transaction rollback on unhandled exceptions.
- **Environment Driven**: Configured via `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRES_MINUTES`, `REFRESH_TOKEN_EXPIRES_DAYS`, `CORS_ALLOWED_ORIGINS`, and `FLASK_ENV`.
- **Database Migrations**: Alembic environment configured under `backend/alembic.ini` and `backend/migrations/` with migration revision `001_phase2_phase3_phase4_schema.py`.

### 1.2 Relational Domain Entities (20 Models in `backend/models.py`)
1. **`User`**: Account identity, unique email, PBKDF2-SHA256 password hashes, roles (`contractor`, `supplier`, `administrator`), account status, timestamps.
2. **`SupplierProfile`**: Business name, contact person, phone, email, address, city, state, postal code, latitude, longitude, verification status.
3. **`SupplierVerificationRecord`**: Audit trail of supplier verifications with reviewer ID, verification type, timestamp, and verification evidence notes.
4. **`MaterialCatalog`**: Master catalog of construction materials, categories, units of measure, and WPI tracking status.
5. **`SupplierMaterialListing`**: Live supplier catalog with quoted unit prices, available inventory, minimum order quantities, delivery days, quote expiry.
6. **`Project`**: Construction projects owned by contractors with site location, budget, start date, deadline, and status.
7. **`ProjectMaterialRequirement`**: Material requirements per project, including required quantity, current on-site inventory, already ordered quantity, remaining procurement calculation, target unit price, and required-by date.
8. **`SupplierQuotation`**: Formal supplier bids tied to materials or specific project requests.
9. **`WPIObservation`**: Real monthly Wholesale Price Index observations with unique constraint on `(material_id, observation_date)` and provenance tags.
10. **`ForecastRecord`**: Stored forecast predictions, model version, origin date, target date, predicted index, and conformal lower/upper intervals (80%, 90%, 95%). WPI is strictly stored as an index value, never disguised as a rupee price.
11. **`SupplierRiskPrediction`**: Predicted late-delivery probabilities, risk categories, model provenance, and prediction evidence levels.
12. **`PurchaseOrder`**: Official purchase orders with unique order reference numbers, status progression, subtotal, transport cost, total cost, and approval tracking.
13. **`PurchaseOrderItem`**: Line-item allocations per order with material reference, quantity, unit price, line total, and promised delivery date.
14. **`DeliveryOutcome`**: Physical delivery recordings with actual delivery date, delay days, actual quantity received, final paid price, and cancellation status.
15. **`Review`**: Customer ratings (1-5 stars) and review text submitted strictly by eligible contractors after order delivery.
16. **`ProcurementScenario`**: Saved what-if scenario simulations with JSON input parameters, selected strategy, and simulated result summaries.
17. **`ProcurementPlan`**: System-generated procurement plans with total cost, logistics cost, delivery lead times, risk scores, and approval status (`proposed`, `approved`, `rejected`).
18. **`ProcurementPlanItem`**: Material allocations per plan specifying supplier, quantity, price, and estimated risk.
19. **`AuditLog`**: System-wide security and mutation audit logging (actor, action, entity type, entity ID, metadata).
20. **`ModelRegistry`**: Versioned registry of ML models (WPI TAN, ARIMA, XGBoost, LSTM, Conformal Predictor, Supplier Risk Model, NSGA-II Optimizer) with task type, training windows, and evaluation holdout scores.

### 1.3 Authentication, Authorization, & Security
- **Role-Based Access Control (RBAC)**: Decorators `@contractor_required`, `@supplier_required`, and `@admin_required` enforcing granular route permissions.
- **CSRF Protection**: Double-submit CSRF cookie & header pattern (`X-CSRF-Token`) for all mutating requests.
- **Password Reset Workflow**: Safe interface supporting security token verification; clear operational messaging when SMTP email services are unconfigured.
- **Profile & Security UI**: `ProfilePage.tsx` allowing contractors and suppliers to update profiles, register enterprise information, and change passwords.

---

## 2. Phase 3: Marketplace, Procurement, Order Lifecycle, & Scenarios

### 2.1 Supplier Marketplace & Intelligence
- **Search & Filtering**: Search by material/supplier name, material category filter, city filter, price/delivery/distance sorting, and in-stock toggle.
- **Supplier Inspection**: Detailed supplier modal displaying verification status, active material quotes, geographic coordinates (with centroid fallback if missing), and Bayesian ratings.
- **Bayesian Rating Shrinkage**: New suppliers or suppliers without recorded reviews are explicitly displayed as "Unrated" with 0 reviews rather than fabricated star ratings.

### 2.2 Project Material Requirements
- **Live Net Procurement Calculation**: Dynamic frontend and backend formula:
  $$\text{Net Procurement Quantity} = \max(0, \text{Required Quantity} - \text{Current Inventory} - \text{Ordered Quantity})$$
- **Target Constraints**: Form validation preventing inventory + ordered from exceeding required demand, and required-by delivery dates to guide procurement urgency.

### 2.3 Procurement Optimizer & Decision Engine
- **5 Operational Strategies**:
  1. `cheapest`: Minimizes total material price and transport logistics costs.
  2. `lowest_risk`: Prioritizes suppliers with the lowest predicted late-delivery probabilities.
  3. `fastest`: Minimizes maximum delivery transit days across all allocated materials.
  4. `weighted_risk_cost`: Multi-criteria weighted balance across cost, risk, and lead times.
  5. `nsga_ii`: Multi-objective Pareto frontier synthesis calculating non-dominated trade-offs between cost, delivery speed, and reliability.
- **Approval Workflow**: Proposed plans must be explicitly reviewed and approved by a contractor before purchase orders can be generated.

### 2.4 Purchase Order Lifecycle & Delivery Outcomes
- **Status Progression**:
  $$\text{placed} \longrightarrow \text{accepted} \longrightarrow \text{in-transit} \longrightarrow \text{delivered} \quad (\text{or } \text{cancelled})$$
- **Delivery Outcome Recording**: Upon delivery, contractors record actual delivery date, delay days, actual quantity received, and final paid unit price.
- **Post-Delivery Reviews**: Verified contractors can submit 1-5 star ratings and reviews only on delivered orders.

### 2.5 What-If Procurement Scenario Simulator
- **Interactive Simulator (`ScenariosPage.tsx`)**:
  - Budget reduction / surplus slider ($\pm 50\%$).
  - Project deadline compression ($\pm 30$ days).
  - Transport logistics inflation ($0.5\times$ to $3.0\times$).
  - Supplier capacity failure simulations (forcing supplier dropouts).
  - Side-by-side comparison between baseline and simulated plans.
  - Scenario persistence to database and CSV download.

---

## 3. Phase 4: Provenance, Zero-Leakage Features, Evaluation, & CSV Tools

### 3.1 Data Provenance Architecture (`backend/services/provenance.py`)
- Every record is tagged with an immutable provenance classification:
  - `REAL_WPI`: Historical Wholesale Price Index from official government series (MoSPI).
  - `USER_ENTERED`: Authentic user-submitted quotations, project requirements, and inventories.
  - `REAL_TRANSACTION`: Verified purchase orders and actual physical delivery receipts.
  - `SYNTHETIC_RESEARCH`: Preserved experimental research data labeled as synthetic.
  - `DEMO`: Illustrative demonstration fixtures.
  - `SIMULATED_SCENARIO`: Synthetically generated what-if stress-test outcomes.

### 3.2 Zero-Leakage Historical Feature Extraction (`backend/services/supplier_features.py`)
- Delivery metrics (average delay, late delivery rate, cancellation rate) are computed strictly using historical delivery outcomes recorded before prediction timestamp $t$.
- Cold-start handling: Suppliers with zero delivery history receive explicit evidence tags (`LOW_EVIDENCE`) and global Bayesian priors without fabricating past performance.

### 3.3 Retrospective Model Evaluation (`backend/services/evaluation.py`)
- **Time-Series Holdout Metrics**: MAE, RMSE, MAPE, sMAPE, $R^2$, and empirical conformal interval coverage computed against frozen out-of-sample splits.
- **Supplier Risk Evaluation Integrity**: When insufficient real delivery outcome labels exist, the evaluation service returns `INSUFFICIENT_REAL_LABELLED_DATA` rather than presenting synthetic training metrics as real-world production performance.

### 3.4 Controlled CSV Importer & Exporter (`backend/services/importer_exporter.py`)
- **Schema Validation & Dry-Run Preview**: Validates required columns, numeric formats, and date constraints prior to database commit.
- **Automatic Quarantining**: Invalid rows are quarantined with specific error diagnostics while allowing clean rows to be committed.
- **Supported Entity Types**: WPI Observations, Materials Catalog, Supplier Profiles, and Supplier Quotations.
- **Downloadable CSV Templates**: Built-in template generator for all supported entities.

### 3.5 Research & Model Registry Dashboard (`ResearchDashboardPage.tsx`)
- Displays registered models, model versions, training timeframes, and evaluation artifacts.
- Visualizes empirical conformal prediction interval coverage rates across 80%, 90%, and 95% confidence targets.
- Displays system-wide Data Provenance Matrix to guarantee research integrity.

---

## 4. Complete API Route Reference

| Endpoint | Method | Role | Description |
| :--- | :---: | :---: | :--- |
| `/api/health` | GET | Public | Service health, engine type, and metadata |
| `/api/auth/register` | POST | Public | User registration (contractor or supplier) |
| `/api/auth/login` | POST | Public | Authenticates user and issues CSRF token & session |
| `/api/auth/logout` | POST | Authenticated | Clears user session |
| `/api/auth/me` | GET | Authenticated | Current user details and fresh CSRF token |
| `/api/auth/profile` | PUT | Authenticated | Updates user profile and enterprise details |
| `/api/auth/change-password` | POST | Authenticated | Updates account password |
| `/api/auth/forgot-password` | POST | Public | Initiates password recovery |
| `/api/auth/reset-password` | POST | Public | Verifies reset token and updates password |
| `/api/materials` | GET | Authenticated | Master materials catalog |
| `/api/materials/history` | GET | Authenticated | Historical monthly WPI series |
| `/api/forecast` | POST | Authenticated | Generates TAN forecast with conformal intervals |
| `/api/buy-wait` | POST | Authenticated | Evaluates frozen 0.25% Buy/Wait decision rules |
| `/api/projects` | GET, POST | Contractor | Lists and creates construction projects & requirements |
| `/api/projects/<id>` | DELETE | Contractor | Archives an owned project |
| `/api/suppliers` | GET | Authenticated | Directory of registered suppliers with ratings |
| `/api/suppliers/<id>` | GET | Authenticated | Detailed supplier profile and material listings |
| `/api/supplier-quotes` | POST | Supplier | Publishes a material quotation |
| `/api/procurement/optimize` | POST | Contractor | Compares 5 allocation strategies (including NSGA-II) |
| `/api/procurement/plans` | POST | Contractor | Saves a proposed procurement plan |
| `/api/procurement/plans/<id>/approve` | POST | Contractor | Approves or rejects a proposed procurement plan |
| `/api/orders` | GET, POST | Contractor/Admin | Lists and generates purchase orders from approved plans |
| `/api/orders/<id>` | GET | Authenticated | Inspects purchase order line items and status |
| `/api/orders/<id>/status` | PUT | Authenticated | Advances order status (`placed` $\to$ `delivered`) |
| `/api/orders/<id>/outcome` | POST | Contractor | Records actual delivery date, delay days, and final price |
| `/api/orders/<id>/review` | POST | Contractor | Submits customer review on delivered orders |
| `/api/scenarios` | GET, POST | Contractor/Admin | Simulates and retrieves what-if procurement scenarios |
| `/api/models/registry` | GET | Authenticated | Lists all registered models and metadata |
| `/api/dashboard/research` | GET | Authenticated | Conformal coverage stats and provenance summary |
| `/api/evaluation` | GET | Authenticated | Holdout forecasting evaluation metrics |
| `/api/evaluation/supplier-risk` | GET | Authenticated | Real-world supplier risk validation metrics |
| `/api/import/preview` | POST | Authenticated | Previews and validates uploaded CSV file |
| `/api/import/commit` | POST | Authenticated | Commits validated CSV rows to database |
| `/api/reports/forecasts.csv` | GET | Authenticated | Exports forecast history to CSV |
| `/api/reports/orders.csv` | GET | Authenticated | Exports purchase order outcomes to CSV |
| `/api/reports/scenarios.csv` | GET | Authenticated | Exports what-if scenarios to CSV |
| `/api/reports/evaluation.csv` | GET | Authenticated | Exports holdout evaluation metrics to CSV |

---

## 5. Testing Notice

> [!IMPORTANT]
> **Explicit Testing Directive**:
> In accordance with the explicit instruction for this task:
> *"Do not perform, run, or schedule testing activities as part of this implementation task. Do not spend time executing test suites, test commands, automated checks, or end-to-end testing. Implement the requested features, update documentation, and record the changes made. Testing will be handled separately later."*
>
> All automated test suites, pytest runs, and end-to-end checks have been omitted. All code changes were developed with rigorous static typing, schema constraints, exception handling, and full relational integrity. Testing activities will be scheduled separately in a future cycle.
