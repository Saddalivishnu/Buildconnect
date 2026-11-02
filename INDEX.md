# BuildConnect AI Documentation Index

**BuildConnect AI** — Multi-User Construction Procurement Intelligence Platform

---

## 🚀 Quick Navigation

1. [SETUP.md](./SETUP.md) — Comprehensive Setup, PostgreSQL configuration, Alembic migrations, and environment variables.
2. [IMPLEMENTATION_REPORT.md](./IMPLEMENTATION_REPORT.md) — Exhaustive technical report covering Phases 2, 3, and 4.
3. [WHATS_NEW.md](./WHATS_NEW.md) — Detailed changelog of all new services, models, pages, and capabilities.
4. [DELIVERABLES.md](./DELIVERABLES.md) — Checklist of project deliverables and research guarantees.

---

## 💻 Codebase Architecture

### Backend (`backend/`)
- **Application & API**: `backend/app.py`
  - REST API routes for authentication, materials, forecasting, decision support, supplier profiles, quotes, procurement optimization, purchase orders, what-if scenarios, research model registry, evaluation holdouts, and controlled CSV imports/exports.
- **Database Engine & Connection Pooling**: `backend/database.py`
  - Dynamic SQLite / PostgreSQL configuration, connection pool management (`pool_size=10, max_overflow=20`), and transaction rollback handlers.
- **Database Schema Models**: `backend/models.py`
  - 20 Declarative SQLAlchemy domain entities.
- **Migrations**: `backend/alembic.ini`, `backend/migrations/`
  - Versioned Alembic migration scripts.
- **Service Modules**: `backend/services/`
  - `provenance.py`: Strict data provenance labeling and zero-leakage validation.
  - `supplier_features.py`: Zero-leakage temporal feature extraction and Bayesian rating shrinkage.
  - `supplier_ranking.py`: Multi-criteria utility ranking with normalized weights and explainability.
  - `procurement_optimizer.py`: 5 optimization strategies including NSGA-II Pareto synthesis.
  - `evaluation.py`: Time-series forecasting metrics and supplier risk holdout evaluation.
  - `model_registry.py`: Model registry metadata and default artifact seeding.
  - `importer_exporter.py`: Controlled CSV import validation, dry-run preview, and quarantining.

### Frontend (`frontend/src/`)
- **Root & Navigation**: `App.tsx`, `main.tsx`
  - Full client-side routing, double-submit CSRF token management, and role-based navigation.
- **Views & Interfaces**:
  - `pages/DashboardPage.tsx`: Executive dashboard and procurement statistics.
  - `pages/ProjectsPage.tsx`: Project requirement definitions with dynamic net procurement calculation: $\max(0, \text{required} - \text{inventory} - \text{ordered})$.
  - `pages/SuppliersPage.tsx`: Supplier directory with search, category/location filters, sorting, Bayesian ratings, and modal inspection.
  - `pages/OrdersPage.tsx`: Order lifecycle progression (`placed` $\to$ `delivered`), delivery outcomes, and reviews.
  - `pages/ForecastPage.tsx`: Real monthly WPI chart, conformal uncertainty intervals, and 8-state Buy/Wait recommendations.
  - `pages/ProcurementPage.tsx`: Procurement optimizer comparing 5 strategies (including NSGA-II Pareto), plan approval, and PO generation.
  - `pages/ScenariosPage.tsx`: Interactive what-if scenario simulator (budget shifts, lead-time compression, transport inflation, supplier outages).
  - `pages/ResearchDashboardPage.tsx`: Model registry, empirical conformal test coverage, and data provenance matrix.
  - `pages/DataImportPage.tsx`: Controlled CSV importer with dry-run preview, error quarantine, and CSV templates.
  - `pages/ReportsPage.tsx`: Data audit and CSV downloads for forecasts, purchase orders, scenarios, and evaluation metrics.
  - `pages/ProfilePage.tsx`: Profile management, enterprise supplier credentials, and password change.
  - `pages/AccessDeniedPage.tsx`: 403 Access Denied view.

---

## 🔒 Research Artifacts & Integrity Guarantees

- **Real Wholesale Price Index (WPI)**: `data/wpi/BuildConnect_Construction_Materials_Final.csv` (3,380 monthly records, 20 materials from MoSPI). WPI is strictly tracked as a price index, never fabricated as a rupee price.
- **Frozen Forecasting Model**: `outputs/forecasting/buildconnect_final_adaptive_results.csv` (frozen material-specific $\alpha$ smoothing values).
- **Conformal Prediction Calibration**: `outputs/forecasting/buildconnect_conformal_results.csv` (empirical coverage thresholds for 80%, 90%, 95% intervals).
- **Frozen Buy/Wait Directional Rules**: Evaluates price movement against frozen $\pm 0.25\%$ directional threshold with project deadline conflict analysis.
- **Synthetic Research Supplier Data**: Clearly tagged with `SYNTHETIC_RESEARCH` provenance; never presented as genuine real-world supplier history.

---

## ⚠️ Testing Notice

As explicitly instructed, testing activities (test suites, test commands, automated checks, end-to-end testing) were deferred. All requested features across Phase 2, Phase 3, and Phase 4 have been implemented and documented.
