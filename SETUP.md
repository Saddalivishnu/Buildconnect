# BuildConnect AI: Setup, Architecture, and Operational Guide

BuildConnect AI is a database-backed, multi-user construction procurement intelligence platform integrating real Wholesale Price Index (WPI) time-series forecasting, conformal uncertainty estimation, frozen Buy/Wait decision rules, multi-criteria supplier intelligence, and multi-objective procurement optimization (including NSGA-II Pareto synthesis).

---

## 1. System Requirements

- **Python**: Python 3.10+ and `pip`
- **Node.js**: Node.js 18+ and `npm`
- **Database Engine**:
  - **Development / Demonstration**: SQLite (default, zero-configuration local file `buildconnect.db`)
  - **Multi-user / Production Deployment**: PostgreSQL 14+ (optional PostGIS for spatial coordinates)

---

## 2. Environment Configuration

Copy `.env.example` to `.env` in the project root or configure shell environment variables:

```bash
cp .env.example .env
```

### Environment Variables Reference

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///buildconnect.db` (or `postgresql+psycopg2://user:password@localhost:5432/buildconnect`) |
| `SECRET_KEY` | Session signing secret (minimum 32 chars) | `buildconnect-dev-session-secret-change-in-production` |
| `JWT_SECRET_KEY` | JWT token signing key | `buildconnect-jwt-secret-key-change-in-production` |
| `ACCESS_TOKEN_EXPIRES_MINUTES` | Access token lifespan | `60` |
| `REFRESH_TOKEN_EXPIRES_DAYS` | Refresh token lifespan | `30` |
| `CORS_ALLOWED_ORIGINS` | Permitted origins | `http://localhost:5173,http://127.0.0.1:5173` |
| `FLASK_ENV` | Runtime environment | `development` (use `production` for secure cookies) |

---

## 3. Local Development (SQLite Default)

The default configuration requires no external database server credentials.

### Backend Setup (PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

The Flask API starts on `http://localhost:5000`.

### Database Initialization & Migrations

Alembic migrations are configured under `backend/alembic.ini` and `backend/migrations/`.
To apply database migrations to your database:

```powershell
cd backend
python -m alembic upgrade head
```

### Administrative User Provisioning

Administrator accounts cannot be self-registered from the public web interface. To create an initial administrator:

```powershell
cd backend
python app.py create-admin admin@buildconnect.ai
# Enter a secure password (at least 12 characters) when prompted.
```

### Frontend Setup (PowerShell)

In a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite will proxy API requests directly to `http://localhost:5000`.

---

## 4. Multi-User PostgreSQL Deployment

To deploy BuildConnect AI with PostgreSQL:

1. Create a PostgreSQL database (e.g. `buildconnect_db`).
2. Set the `DATABASE_URL` environment variable:
   ```bash
   DATABASE_URL=postgresql+psycopg2://bc_user:StrongPassword@localhost:5432/buildconnect_db
   ```
3. Run Alembic migrations to apply all 20 relational entities:
   ```powershell
   cd backend
   python -m alembic upgrade head
   ```
4. Start the application under Gunicorn or standard WSGI:
   ```powershell
   python app.py
   ```
   Connection pooling is enabled by default with `pool_size=10`, `max_overflow=20`, and automatic transaction rollback on failed requests.

---

## 5. Architectural Modules & Navigation

| Route | View | Capabilities |
| :--- | :--- | :--- |
| `/` | **Overview Dashboard** | KPI overview, active projects summary, recent quotations |
| `/projects` | **Project Requirements** | Net procurement calculation `max(0, required - inventory - ordered)`, target unit prices, required-by dates |
| `/suppliers` | **Supplier Marketplace** | Directory search, category/location filters, price/delivery sorting, Bayesian ratings, coordinates/fallback |
| `/orders` | **Order Lifecycle** | Order tracking, status progression (`placed -> accepted -> in-transit -> delivered`), delivery outcomes, customer reviews |
| `/forecast` | **Price Intelligence** | Monthly WPI history, conformal prediction uncertainty intervals, 8 frozen Buy/Wait decision states |
| `/procurement` | **Procurement Optimizer** | 5 allocation strategies (`cheapest`, `lowest_risk`, `fastest`, `weighted_risk_cost`, `nsga_ii` Pareto frontier) |
| `/scenarios` | **What-If Simulator** | Interactive simulation of budget shocks, delivery compression, transport hikes, and supplier outages |
| `/research` | **Research Dashboard** | Model registry, data provenance matrix, empirical conformal test coverage, and holdout benchmarks |
| `/import` | **Controlled CSV Import** | Live schema validation, row-by-row dry-run preview, automatic quarantining of corrupt records, and downloadable CSV templates |
| `/reports` | **Reports & Audit** | Direct CSV export for forecasts, purchase orders, what-if scenarios, and holdout evaluation metrics |
| `/profile` | **Profile & Enterprise** | User profile, supplier business credentials, verified status, and password update |

---

## 6. Testing Notice

> [!NOTE]
> **Testing Status**:
> As explicitly requested for this implementation task, automated test execution, test suite runs, and end-to-end verification commands were not scheduled or executed. All database models, service layers, API endpoints, and frontend user interfaces have been fully implemented, wired, and documented. Verification and automated testing will be conducted separately.
