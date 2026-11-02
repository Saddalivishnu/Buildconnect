import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../App'

interface Project {
  id: number
  name: string
  budget: number
  deadline: string
  demo: number
}

interface Scenario {
  id: number
  project_id: number
  scenario_name: string
  strategy: string
  scenario_inputs: Record<string, unknown>
  result_summary: Record<string, unknown>
  created_at: string
  provenance: string
}

interface SimulationResult {
  strategy: string
  material_cost: number
  transport_cost: number
  total_estimated_cost: number
  expected_delivery_days: number | null
  expected_late_delivery_risk: number | null
  shortage_quantity: number
  budget_compliant: boolean
  feasible: boolean
}

export function ScenariosPage() {
  const { csrfToken } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | ''>('')
  const [strategy, setStrategy] = useState('weighted_risk_cost')
  const [transportRate, setTransportRate] = useState(0.02)
  const [shortagePenalty, setShortagePenalty] = useState(1500)
  const [scenarioName, setScenarioName] = useState('')
  const [simulation, setSimulation] = useState<Record<string, SimulationResult> | null>(null)
  const [savedScenarios, setSavedScenarios] = useState<Scenario[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadData() {
    try {
      const [projData, scenData] = await Promise.all([
        api<{ projects: Project[] }>('/api/projects'),
        api<{ scenarios: Scenario[] }>('/api/scenarios'),
      ])
      setProjects(projData.projects)
      if (projData.projects.length > 0 && !projectId) {
        setProjectId(projData.projects[0].id)
      }
      setSavedScenarios(scenData.scenarios)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load scenario data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  async function runSimulation() {
    if (!projectId) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const res = await api<{ alternatives: Record<string, SimulationResult> }>('/api/procurement/optimize', {
        method: 'POST',
        body: JSON.stringify({
          project_id: Number(projectId),
          transport_rate_coefficient: transportRate,
          shortage_penalty: shortagePenalty,
        }),
      }, csrfToken)
      setSimulation(res.alternatives)
      setMessage('Simulation updated with live market quotes and assumption parameters.')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Failed to run scenario simulation.')
    } finally {
      setBusy(false)
    }
  }

  async function saveScenario() {
    if (!projectId || !scenarioName.trim() || !simulation) return
    setBusy(true)
    setError('')
    try {
      const chosen = simulation[strategy] || simulation['cheapest']
      await api('/api/scenarios', {
        method: 'POST',
        body: JSON.stringify({
          project_id: Number(projectId),
          scenario_name: scenarioName.trim(),
          strategy,
          scenario_inputs: {
            transport_rate_coefficient: transportRate,
            shortage_penalty: shortagePenalty,
            strategy,
          },
          result_summary: chosen,
        }),
      }, csrfToken)
      setMessage(`Scenario "${scenarioName}" saved.`)
      setScenarioName('')
      await loadData()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to save scenario.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <h1 className="text-2xl font-bold">What-if procurement simulator</h1>
        <p className="mt-1 text-sm text-slate-400">
          Simulate supply chain outcomes by adjusting transport tariffs, shortage penalties, and procurement strategies.
        </p>
      </div>

      {error && <p role="alert" className="rounded-xl border border-red-700 bg-red-950/40 p-4 text-red-200">{error}</p>}
      {message && <p role="status" className="rounded-xl border border-emerald-700 bg-emerald-950/40 p-4 text-emerald-200">{message}</p>}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Scenario Controls */}
        <section className="card space-y-4">
          <h2 className="text-lg font-semibold text-white">Scenario parameters</h2>
          <label className="block text-sm">Select project
            <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))} className="form-control mt-1">
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name} · Budget: ₹{p.budget.toLocaleString()}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm">Optimization strategy
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="form-control mt-1">
              <option value="cheapest">Cheapest feasible</option>
              <option value="lowest_risk">Lowest delivery risk</option>
              <option value="fastest">Fastest lead time</option>
              <option value="weighted_risk_cost">Weighted cost & risk compromise</option>
              <option value="nsga_ii">NSGA-II Pareto multi-objective compromise</option>
            </select>
          </label>

          <label className="block text-sm">Transport tariff (₹ / km / unit)
            <input type="number" step="0.005" min="0" value={transportRate} onChange={(e) => setTransportRate(Number(e.target.value))} className="form-control mt-1" />
            <span className="text-[11px] text-slate-400">Configurable assumption; not a certified carrier tariff.</span>
          </label>

          <label className="block text-sm">Shortage penalty (₹ / unfulfilled unit)
            <input type="number" step="100" min="0" value={shortagePenalty} onChange={(e) => setShortagePenalty(Number(e.target.value))} className="form-control mt-1" />
            <span className="text-[11px] text-slate-400">Simulated penalty for contractor delay damages.</span>
          </label>

          <button onClick={runSimulation} className="btn-primary w-full" disabled={busy || !projectId}>
            {busy ? 'Simulating…' : 'Run scenario simulation'}
          </button>
        </section>

        {/* Simulation Output */}
        <section className="card lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">Simulated outcomes</h2>
            <span className="rounded-full bg-indigo-950/70 border border-indigo-700/60 px-3 py-1 text-xs text-indigo-300 font-mono">
              PROVENANCE: SIMULATED_SCENARIO
            </span>
          </div>

          {simulation ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-4">
                {Object.entries(simulation).map(([key, res]) => (
                  <div
                    key={key}
                    onClick={() => setStrategy(key)}
                    className={`cursor-pointer rounded-xl border p-3 transition ${
                      strategy === key
                        ? 'border-teal-500 bg-teal-950/30'
                        : 'border-slate-700 bg-slate-800/40 hover:border-slate-600'
                    }`}
                  >
                    <p className="text-xs font-semibold text-slate-400 capitalize">{key.replace('_', ' ')}</p>
                    <p className="mt-1 text-base font-bold text-white">₹{res.total_estimated_cost.toLocaleString()}</p>
                    <p className="text-xs text-slate-400">Lead time: {res.expected_delivery_days ?? 'N/A'} days</p>
                    {res.shortage_quantity > 0 ? (
                      <span className="mt-1 inline-block text-[11px] font-bold text-red-400">Shortage: {res.shortage_quantity}</span>
                    ) : (
                      <span className="mt-1 inline-block text-[11px] font-bold text-emerald-400">Feasible ✓</span>
                    )}
                  </div>
                ))}
              </div>

              {/* Save Scenario Form */}
              <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 space-y-3">
                <h3 className="text-sm font-semibold text-white">Save this simulated scenario</h3>
                <div className="flex gap-2">
                  <input
                    value={scenarioName}
                    onChange={(e) => setScenarioName(e.target.value)}
                    placeholder="e.g. Q4 Monsoon Cement Hike (+15% tariff assumption)"
                    className="form-control flex-1"
                  />
                  <button onClick={saveScenario} className="btn-secondary whitespace-nowrap" disabled={busy || !scenarioName.trim()}>
                    Save scenario
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <p className="py-12 text-center text-sm text-slate-400">
              Select parameters and click "Run scenario simulation" to preview cost and delivery trade-offs.
            </p>
          )}
        </section>
      </div>

      {/* Saved Scenarios List */}
      <section className="card space-y-4">
        <h2 className="text-lg font-semibold text-white">Saved scenarios repository</h2>
        {savedScenarios.length === 0 ? (
          <p className="text-sm text-slate-400">No saved scenarios yet. Use the simulator above to save what-if comparisons.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className="border-b border-slate-700 text-xs text-slate-400 uppercase">
                <tr>
                  <th className="py-2">Scenario name</th>
                  <th>Strategy</th>
                  <th>Inputs</th>
                  <th>Simulated total</th>
                  <th>Saved date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {savedScenarios.map((s) => {
                  const summary = s.result_summary as any
                  return (
                    <tr key={s.id}>
                      <td className="py-2.5 font-medium text-white">{s.scenario_name}</td>
                      <td className="capitalize text-teal-300">{s.strategy}</td>
                      <td className="text-xs text-slate-400 font-mono">
                        tariff: {String((s.scenario_inputs as any).transport_rate_coefficient || 0.02)}
                      </td>
                      <td className="font-semibold text-emerald-400">
                        {summary?.total_estimated_cost ? `₹${Number(summary.total_estimated_cost).toLocaleString()}` : 'N/A'}
                      </td>
                      <td className="text-xs text-slate-400">{s.created_at?.slice(0, 10)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
