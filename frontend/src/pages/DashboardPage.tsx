import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { api } from '../api'

interface DashboardData {
  active_projects: number
  total_material_requirements: number
  pending_procurement_decisions: number
  supplier_risk_overview: { low: number; medium: number; high: number }
  material_index_coverage: number
  recent_projects: Array<{ id: number; name: string; location: string }>
  demo_data_notice: string
  index_series: Array<{ date: string; value: number }>
  index_series_material: string
  index_series_source: string
}

export function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<DashboardData>('/api/dashboard')
      .then((data) => {
        setDashboard(data)
        setLoading(false)
      })
      .catch((err) => {
        console.error('Dashboard fetch failed:', err)
        setError('Failed to load dashboard data')
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="grid gap-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="card h-32 animate-pulse bg-slate-700" />
        ))}
      </div>
    )
  }

  if (error || !dashboard) {
    return <div className="card bg-red-900/20 p-6 text-red-300">{error || 'Failed to load dashboard'}</div>
  }

  return (
    <div className="space-y-6">
      <div className="status-panel p-4 text-sm text-cyan-100">
        <strong className="mr-1 text-teal-200">Data provenance:</strong>{dashboard.demo_data_notice}
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <div className="card">
          <p className="text-sm font-medium text-slate-400">Active Projects</p>
          <p className="mt-2 text-3xl font-bold text-teal-400">{dashboard.active_projects}</p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-slate-400">Material Requirements (units)</p>
          <p className="mt-2 text-3xl font-bold text-teal-400">{dashboard.total_material_requirements.toLocaleString()}</p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-slate-400">Pending Decisions</p>
          <p className="mt-2 text-3xl font-bold text-amber-400">{dashboard.pending_procurement_decisions}</p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-slate-400">Materials Indexed</p>
          <p className="mt-2 text-3xl font-bold text-emerald-400">{dashboard.material_index_coverage}</p>
        </div>
      </div>

      {/* Supplier Risk Overview */}
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-100">Supplier Risk Overview</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-lg bg-emerald-900/20 p-4 text-center">
            <p className="text-sm text-slate-400">Low Risk</p>
            <p className="mt-2 text-2xl font-bold text-emerald-400">{dashboard.supplier_risk_overview.low}</p>
          </div>
          <div className="rounded-lg bg-amber-900/20 p-4 text-center">
            <p className="text-sm text-slate-400">Medium Risk</p>
            <p className="mt-2 text-2xl font-bold text-amber-400">{dashboard.supplier_risk_overview.medium}</p>
          </div>
          <div className="rounded-lg bg-red-900/20 p-4 text-center">
            <p className="text-sm text-slate-400">High Risk</p>
            <p className="mt-2 text-2xl font-bold text-red-400">{dashboard.supplier_risk_overview.high}</p>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-100">Materials Indexed Over Time</h2>
        <div className="chart-container mt-4">
          <p className="mb-2 text-sm text-slate-400">{dashboard.index_series_material} · {dashboard.index_series_source}. WPI is an index, not a supplier price.</p>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={dashboard.index_series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#94a3b8" tick={{ fontSize: 11 }} />
              <YAxis stroke="#94a3b8" domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Legend />
              <Line name="WPI" type="monotone" dataKey="value" stroke="#14b8a6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent Projects */}
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-100">Recent Projects</h2>
        <div className="mt-4 space-y-2">
          {dashboard.recent_projects && dashboard.recent_projects.length > 0 ? (
            dashboard.recent_projects.map((proj) => (
              <div key={proj.id} className="flex items-center justify-between border-b border-slate-700 pb-2 last:border-0">
                <div>
                  <p className="font-medium text-slate-100">{proj.name}</p>
                  <p className="text-sm text-slate-400">{proj.location}</p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-slate-400">No recent projects</p>
          )}
        </div>
      </div>
    </div>
  )
}
