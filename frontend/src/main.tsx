import './index.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { App } from './App'
import { DashboardPage } from './pages/DashboardPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SuppliersPage } from './pages/SuppliersPage'
import { ForecastPage } from './pages/ForecastPage'
import { ProcurementPage } from './pages/ProcurementPage'
import { ReportsPage } from './pages/ReportsPage'
import { OrdersPage } from './pages/OrdersPage'
import { ScenariosPage } from './pages/ScenariosPage'
import { ResearchDashboardPage } from './pages/ResearchDashboardPage'
import { DataImportPage } from './pages/DataImportPage'
import { ProfilePage } from './pages/ProfilePage'
import { AccessDeniedPage } from './pages/AccessDeniedPage'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="suppliers" element={<SuppliersPage />} />
          <Route path="orders" element={<OrdersPage />} />
          <Route path="forecast" element={<ForecastPage />} />
          <Route path="procurement" element={<ProcurementPage />} />
          <Route path="scenarios" element={<ScenariosPage />} />
          <Route path="research" element={<ResearchDashboardPage />} />
          <Route path="import" element={<DataImportPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="access-denied" element={<AccessDeniedPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
