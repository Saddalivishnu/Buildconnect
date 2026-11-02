# BuildConnect AI — Intelligent Construction Procurement Platform

**Status:** ✅ Phases 2, 3, & 4 Complete (Multi-User Platform, Marketplace, Procurement Optimizer, Provenance, & Research Analytics)  
**Last Updated:** 2026-11-01  
**Master Navigation:** [INDEX.md](./INDEX.md) | [SETUP.md](./SETUP.md) | [IMPLEMENTATION_REPORT.md](./IMPLEMENTATION_REPORT.md) | [WHATS_NEW.md](./WHATS_NEW.md)

---

## 🏗️ Architecture Overview

BuildConnect AI is a multi-user construction procurement platform that integrates official Wholesale Price Index (WPI) time series, conformal prediction intervals, frozen Buy/Wait decision rules, multi-criteria supplier intelligence, and multi-objective procurement optimization (including NSGA-II Pareto Frontier synthesis).

```
        ┌─────────────────────────────────────────────────────────┐
        │                 Frontend: React + Vite                  │
        │   Dashboard · Projects · Suppliers · Orders · Forecast  │
        │   Procurement · Scenarios · Research · Import · Reports │
        └────────────────────────────┬────────────────────────────┘
                                     │ REST API (JSON / CSRF)
        ┌────────────────────────────▼────────────────────────────┐
        │             Backend: Python Flask REST API              │
        │   RBAC Security · Provenance Service · Zero Leakage     │
        │   Multi-Criteria Ranking · NSGA-II Optimizer · Importer │
        └────────────────────────────┬────────────────────────────┘
                                     │ SQLAlchemy ORM & Alembic
        ┌────────────────────────────▼────────────────────────────┐
        │          Relational Database Layer (20 Models)          │
        │     SQLite (Local Dev) / PostgreSQL (Multi-User)        │
        └─────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Run Backend (Python 3.10+)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
# API listens on http://localhost:5000 (SQLite default)
```

To apply Alembic migrations:
```powershell
python -m alembic upgrade head
```

### 2. Run Frontend (React 18 + TypeScript + Vite)
In a separate terminal:
```powershell
cd frontend
npm install
npm run dev
# Interface opens on http://localhost:5173
```

---

## 🌟 Key Capabilities by Phase

### Phase 2: Database Foundation & Multi-User RBAC
- **Dual Engine Architecture**: SQLite for lightweight local dev; PostgreSQL for production multi-user concurrency with connection pooling (`pool_size=10, max_overflow=20`).
- **20 SQLAlchemy Declarative Entities**: Comprehensive schema covering users, enterprise suppliers, verifications, material catalogs, quotations, projects, requirements, orders, delivery receipts, reviews, scenarios, and model registry.
- **Role-Based Access Control**: Granular decorators (`@contractor_required`, `@supplier_required`, `@admin_required`), CSRF protection, secure sessions, and token-based password reset workflow.

### Phase 3: Marketplace, Procurement, Order Lifecycle, & Scenarios
- **Supplier Marketplace**: Material search, category/location filters, sorting, modal inspection, and Bayesian rating shrinkage ($\frac{v \cdot R + m \cdot C}{v + m}$) with explicit unrated status for zero-review suppliers.
- **Dynamic Net Procurement Needs**: Calculated on-the-fly via $\max(0, \text{required} - \text{inventory} - \text{ordered})$ with target unit prices and required-by dates.
- **Procurement Optimizer**: 5 strategies (Cheapest, Lowest Delivery Risk, Fastest Delivery, Balanced Risk/Cost, and **NSGA-II Pareto Frontier** synthesis). Formal approval workflow before PO generation.
- **Purchase Order Progression & Outcomes**: `placed` $\to$ `accepted` $\to$ `in-transit` $\to$ `delivered`. Delivery receipts track delay days and actual paid prices; eligible contractors submit post-delivery reviews.
- **What-If Scenario Simulator**: Interactive simulations testing budget reductions, lead-time compression, transport inflation, and supplier outages.

### Phase 4: Data Provenance, Retrospective Evaluation, & CSV Tools
- **Data Provenance Framework**: Strict immutable tagging (`REAL_WPI`, `USER_ENTERED`, `REAL_TRANSACTION`, `SYNTHETIC_RESEARCH`, `DEMO`, `SIMULATED_SCENARIO`).
- **Zero Data Leakage**: Historical features temporalized strictly before prediction timestamp $t$.
- **Retrospective Model Evaluation**: Out-of-sample metrics (MAE, RMSE, MAPE, sMAPE, $R^2$, conformal coverage). Guarantees synthetic metrics are not masqueraded as real-world supplier performance.
- **Controlled CSV Importer/Exporter**: Schema validation, dry-run previews, automatic error quarantining, downloadable CSV templates, and direct CSV export for all domain data.
- **Research Dashboard**: Model registry inspection, empirical conformal prediction coverage visualization, and system data provenance matrix.

---

## 🔒 Research Artifacts & Integrity Guarantees

1. **WPI Values**: Historical index observations (20 materials, ~3,380 monthly records from MoSPI / Office of the Economic Adviser). WPI is strictly tracked as a unitless price index, never converted or fabricated as a currency rupee price.
2. **Frozen Model Parameters**: Material-specific Trend-Adjusted Naive smoothing parameters ($\alpha$) and non-parametric conformal calibration outputs remain frozen.
3. **Frozen Buy/Wait Decision Rules**: Direct evaluation on validation-selected $\pm 0.25\%$ directional threshold with deadline conflict detection.
4. **Synthetic Supplier Records**: Preserved research artifacts explicitly tagged with `SYNTHETIC_RESEARCH` provenance; real review ratings use Bayesian shrinkage.

---

## ⚙️ Testing Status

> [!NOTE]
> Per explicit user instruction for this implementation task:
> **Testing activities (test suites, test commands, automated checks, end-to-end testing) were deferred.**
> All requested features across Phase 2, Phase 3, and Phase 4 have been implemented and documented. Testing will be scheduled separately in a future cycle.
