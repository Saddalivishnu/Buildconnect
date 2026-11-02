import { useEffect, useState } from 'react'
import { api } from '../api'

interface ResearchData {
  wpi_historical_coverage: {
    total_observations: number
    unique_materials: number
    time_range: string
    provenance: string
  }
  records_by_provenance: {
    real_wpi_observations: number
    user_entered_suppliers: number
    demo_suppliers: number
    real_purchase_orders: number
    demo_purchase_orders: number
    real_delivery_outcomes: number
    simulated_scenarios: number
    generated_forecasts: number
  }
  conformal_prediction_intervals: {
    confidence_levels: string[]
    materials_calibrated: number
    target_coverage_summary: string
  }
  model_registry_summary: {
    registered_models: number
    operational_forecaster: string
    benchmark_models: string[]
    supplier_risk_status: string
  }
  transparency_notice: string
}

interface ModelRegistryItem {
  id: number
  model_name: string
  model_version: string
  task_type: string
  artifact_location: string
  dataset_provenance: string
  training_period: string
  deployment_status: string
  documentation_reference: string
}

export function ResearchDashboardPage() {
  const [data, setData] = useState<ResearchData | null>(null)
  const [models, setModels] = useState<ModelRegistryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      api<ResearchData>('/api/dashboard/research'),
      api<{ models: ModelRegistryItem[] }>('/api/models/registry'),
    ])
      .then(([researchRes, modelsRes]) => {
        setData(researchRes)
        setModels(modelsRes.models)
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load research dashboard.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="p-8 text-slate-300">Loading research intelligence and provenance metrics…</div>
  }

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <h1 className="text-2xl font-bold">Research analytics & provenance dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Auditable telemetry for real WPI observations, conformal coverage calibration, and synthetic vs genuine data boundaries.
        </p>
      </div>

      {error && <p role="alert" className="rounded-xl border border-red-700 bg-red-950/40 p-4 text-red-200">{error}</p>}

      {data && (
        <>
          {/* Transparency Alert */}
          <div className="rounded-xl border border-teal-700/60 bg-teal-950/30 p-4 text-xs text-teal-200">
            <strong>Transparency Commitment:</strong> {data.transparency_notice}
          </div>

          {/* Metric cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="card">
              <p className="text-xs font-semibold text-slate-400">Real WPI observations</p>
              <p className="mt-2 text-2xl font-bold text-white">{data.wpi_historical_coverage.total_observations.toLocaleString()}</p>
              <p className="mt-1 text-xs text-teal-400">{data.wpi_historical_coverage.unique_materials} materials (2012–2026)</p>
            </div>
            <div className="card">
              <p className="text-xs font-semibold text-slate-400">Conformal calibration</p>
              <p className="mt-2 text-2xl font-bold text-white">80% · 90% · 95%</p>
              <p className="mt-1 text-xs text-emerald-400">{data.conformal_prediction_intervals.materials_calibrated} calibrated series</p>
            </div>
            <div className="card">
              <p className="text-xs font-semibold text-slate-400">Real purchase orders</p>
              <p className="mt-2 text-2xl font-bold text-white">{data.records_by_provenance.real_purchase_orders}</p>
              <p className="mt-1 text-xs text-slate-400">{data.records_by_provenance.real_delivery_outcomes} completed outcomes</p>
            </div>
            <div className="card">
              <p className="text-xs font-semibold text-slate-400">Simulated what-if scenarios</p>
              <p className="mt-2 text-2xl font-bold text-white">{data.records_by_provenance.simulated_scenarios}</p>
              <p className="mt-1 text-xs text-indigo-400">{data.records_by_provenance.generated_forecasts} generated forecasts</p>
            </div>
          </div>

          {/* Data Provenance Matrix */}
          <section className="card space-y-4">
            <h2 className="text-lg font-semibold text-white">Data provenance separation matrix</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[700px] text-left text-sm">
                <thead className="border-b border-slate-700 bg-slate-800/80 text-xs text-slate-400 uppercase">
                  <tr>
                    <th className="py-2.5 px-3">Data category</th>
                    <th>Count</th>
                    <th>Provenance classification</th>
                    <th>System usage & safety rule</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-xs">
                  <tr>
                    <td className="py-2.5 px-3 font-medium text-white">Wholesale Price Index</td>
                    <td>{data.records_by_provenance.real_wpi_observations.toLocaleString()}</td>
                    <td><span className="rounded bg-teal-900/60 text-teal-300 px-2 py-0.5 font-mono">REAL_WPI</span></td>
                    <td>Price trend modeling & conformal interval calibration. Never treated as currency quote.</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-medium text-white">Genuine supplier orders</td>
                    <td>{data.records_by_provenance.real_purchase_orders}</td>
                    <td><span className="rounded bg-emerald-900/60 text-emerald-300 px-2 py-0.5 font-mono">REAL_TRANSACTION</span></td>
                    <td>Real transactions. Historical features derived only prior to order timestamps.</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-medium text-white">Registered suppliers</td>
                    <td>{data.records_by_provenance.user_entered_suppliers}</td>
                    <td><span className="rounded bg-blue-900/60 text-blue-300 px-2 py-0.5 font-mono">USER_ENTERED</span></td>
                    <td>Entered business data and quoted unit rates. Verified via admin documentation review.</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-medium text-white">Demonstration seed entities</td>
                    <td>{data.records_by_provenance.demo_suppliers + data.records_by_provenance.demo_purchase_orders}</td>
                    <td><span className="rounded bg-amber-900/60 text-amber-300 px-2 py-0.5 font-mono">DEMO</span></td>
                    <td>Platform illustration and testing only. Labeled demo in all UI views.</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-medium text-white">Procurement scenarios</td>
                    <td>{data.records_by_provenance.simulated_scenarios}</td>
                    <td><span className="rounded bg-indigo-900/60 text-indigo-300 px-2 py-0.5 font-mono">SIMULATED_SCENARIO</span></td>
                    <td>Hypothetical tariff and shortage simulations. Never executes real orders.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* Model Registry Table */}
          <section className="card space-y-4">
            <h2 className="text-lg font-semibold text-white">Governed model registry</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[850px] text-left text-sm">
                <thead className="border-b border-slate-700 bg-slate-800/80 text-xs text-slate-400 uppercase">
                  <tr>
                    <th className="py-2.5 px-3">Model name</th>
                    <th>Version</th>
                    <th>Task type</th>
                    <th>Provenance</th>
                    <th>Deployment status</th>
                    <th>Artifact path</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-xs">
                  {models.map((m) => (
                    <tr key={m.id}>
                      <td className="py-2.5 px-3 font-medium text-white">{m.model_name}</td>
                      <td className="font-mono text-slate-400">{m.model_version}</td>
                      <td className="capitalize text-teal-300">{m.task_type.replace('_', ' ')}</td>
                      <td><span className="font-mono text-[11px] text-slate-300">{m.dataset_provenance}</span></td>
                      <td>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                          m.deployment_status === 'production_frozen' ? 'bg-emerald-900/60 text-emerald-300' :
                          m.deployment_status === 'experimental' ? 'bg-amber-900/60 text-amber-300' :
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {m.deployment_status}
                        </span>
                      </td>
                      <td className="font-mono text-[11px] text-slate-400 truncate max-w-xs">{m.artifact_location}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
