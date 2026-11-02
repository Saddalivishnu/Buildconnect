import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import { useAuth } from '../App'
import { Link } from 'react-router-dom'

interface Project {
  id: number
  name: string
  demo: number
}

interface Allocation {
  material: string
  supplier_name: string
  quantity: number
  unit_price: number
  material_cost: number
  transport_cost: number
  delivery_days: number
  late_probability: number | null
  risk_evidence: string
  demo: boolean
}

interface PlanSummary {
  allocations: Allocation[]
  material_cost: number
  transport_cost: number
  total_estimated_cost: number
  shortage_penalty_estimate: number
  expected_late_delivery_risk: number | null
  estimated_delivery_days: number | null
  shortage_quantity: number
  budget_compliant: boolean
  feasible: boolean
  pareto_rank?: number
}

type Strategy = 'cheapest' | 'lowest_risk' | 'fastest' | 'weighted_risk_cost' | 'nsga_ii'
const strategies: { id: Strategy; label: string; desc: string }[] = [
  { id: 'cheapest', label: 'Cheapest Cost', desc: 'Minimizes total material & transport expenditure.' },
  { id: 'lowest_risk', label: 'Lowest Delivery Risk', desc: 'Prioritizes suppliers with lowest predicted delay probabilities.' },
  { id: 'fastest', label: 'Fastest Delivery', desc: 'Minimizes promised delivery turnaround days.' },
  { id: 'weighted_risk_cost', label: 'Balanced Risk/Cost', desc: 'Jointly balances unit price, logistics, and late delivery penalties.' },
  { id: 'nsga_ii', label: 'NSGA-II Pareto Frontier', desc: 'Multi-objective non-dominated trade-off between cost, lead-time, and risk.' },
]

export function ProcurementPage() {
  const { csrfToken } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState('')
  const [selected, setSelected] = useState<Strategy>('cheapest')
  const [alternatives, setAlternatives] = useState<Record<string, PlanSummary> | null>(null)
  const [planId, setPlanId] = useState<number | null>(null)
  const [planStatus, setPlanStatus] = useState('')
  const [orders, setOrders] = useState<number[]>([])
  const [transportRate, setTransportRate] = useState(0.02)
  const [shortagePenalty, setShortagePenalty] = useState(1500)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    api<{ projects: Project[] }>('/api/projects')
      .then(({ projects: list }) => {
        const own = list.filter((project) => project.demo === 0)
        setProjects(own)
        setProjectId(String(own[0]?.id ?? ''))
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load projects.'))
  }, [])

  async function compare() {
    if (!projectId) return
    setBusy(true)
    setError('')
    setMessage('')
    setAlternatives(null)
    setPlanId(null)
    setPlanStatus('')
    setOrders([])
    try {
      const response = await api<{ alternatives: Record<string, PlanSummary> }>('/api/procurement/optimize', {
        method: 'POST',
        body: JSON.stringify({
          project_id: Number(projectId),
          transport_rate_coefficient: transportRate,
          shortage_penalty: shortagePenalty,
        }),
      }, csrfToken)
      setAlternatives(response.alternatives)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to compare supplier quotations.')
    } finally {
      setBusy(false)
    }
  }

  async function savePlan() {
    if (!projectId) return
    setBusy(true)
    setError('')
    try {
      const response = await api<{ plan_id: number; status: string }>('/api/procurement/plans', {
        method: 'POST',
        body: JSON.stringify({
          project_id: Number(projectId),
          strategy: selected,
          transport_rate_coefficient: transportRate,
          shortage_penalty: shortagePenalty,
        }),
      }, csrfToken)
      setPlanId(response.plan_id)
      setPlanStatus(response.status)
      setMessage(`Plan #${response.plan_id} saved as proposed. Review allocations and approve before placing purchase orders.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to save the plan.')
    } finally {
      setBusy(false)
    }
  }

  async function decide(decision: 'approved' | 'rejected') {
    if (!planId) return
    setBusy(true)
    setError('')
    try {
      const response = await api<{ status: string }>(`/api/procurement/plans/${planId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      }, csrfToken)
      setPlanStatus(response.status)
      setMessage(decision === 'approved' ? 'Plan approved! You may now generate purchase orders.' : 'Plan rejected.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to record the decision.')
    } finally {
      setBusy(false)
    }
  }

  async function createOrders() {
    if (!planId) return
    setBusy(true)
    setError('')
    try {
      const response = await api<{ order_ids: number[] }>('/api/orders', {
        method: 'POST',
        body: JSON.stringify({ plan_id: planId }),
      }, csrfToken)
      setOrders(response.order_ids)
      setMessage(`Purchase orders generated successfully: PO #${response.order_ids.join(', PO #')}.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create purchase orders.')
    } finally {
      setBusy(false)
    }
  }

  const activePlan = alternatives ? alternatives[selected] : null

  return (
    <div className="space-y-6">
      <div className="page-heading flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Procurement Optimization & Decision Engine</h1>
          <p className="mt-1 text-sm text-slate-400">
            Compare 5 allocation strategies including NSGA-II Pareto trade-offs against live quotations, capacity, and deadlines.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/scenarios" className="btn-secondary text-xs">
            What-If Simulator →
          </Link>
          <Link to="/orders" className="btn-secondary text-xs">
            Manage Orders →
          </Link>
        </div>
      </div>

      {error && <p role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-red-200">{error}</p>}
      {message && <p role="status" className="rounded border border-emerald-700 bg-emerald-950/30 p-3 text-emerald-200">{message}</p>}

      <section className="card space-y-4">
        <h2 className="text-lg font-semibold">Optimization Configuration</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 items-end">
          <label className="text-sm">Target Project
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="form-control mt-1"
            >
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="text-sm">Transport Rate Coeff (₹/km·unit)
            <input
              type="number"
              step="0.005"
              min="0"
              value={transportRate}
              onChange={(e) => setTransportRate(Number(e.target.value))}
              className="form-control mt-1"
            />
          </label>
          <label className="text-sm">Shortage Penalty (₹/unit)
            <input
              type="number"
              step="100"
              min="0"
              value={shortagePenalty}
              onChange={(e) => setShortagePenalty(Number(e.target.value))}
              className="form-control mt-1"
            />
          </label>
          <button
            className="btn-primary"
            onClick={() => void compare()}
            disabled={!projectId || busy}
          >
            {busy ? 'Optimizing…' : 'Run Multi-Strategy Optimization'}
          </button>
        </div>
      </section>

      {/* Strategy selector tabs */}
      {alternatives && (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {strategies.map((strat) => {
              const plan = alternatives[strat.id]
              const isSelected = selected === strat.id
              return (
                <button
                  key={strat.id}
                  onClick={() => setSelected(strat.id)}
                  className={`rounded-xl border p-3 text-left transition-all flex-1 min-w-[200px] ${
                    isSelected
                      ? 'border-teal-500 bg-teal-950/50 text-slate-100 shadow-md ring-1 ring-teal-500'
                      : 'border-slate-700 bg-slate-800/60 text-slate-400 hover:border-slate-600'
                  }`}
                >
                  <div className="font-semibold text-sm text-slate-200">{strat.label}</div>
                  <div className="text-xs text-slate-400 mt-1 line-clamp-1">{strat.desc}</div>
                  {plan && (
                    <div className="mt-2 text-xs font-mono text-teal-300">
                      ₹{Math.round(plan.total_estimated_cost).toLocaleString()} · {plan.estimated_delivery_days ?? '—'} days
                    </div>
                  )}
                </button>
              )
            })}
          </div>

          {activePlan && (
            <article className="card space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-700/80 pb-4">
                <div>
                  <h3 className="text-xl font-bold text-slate-100">
                    {strategies.find(s => s.id === selected)?.label} Strategy
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {strategies.find(s => s.id === selected)?.desc}
                  </p>
                </div>
                <div className="flex gap-2">
                  {!planId ? (
                    <button
                      onClick={() => void savePlan()}
                      disabled={busy}
                      className="btn-primary text-xs"
                    >
                      Save As Proposed Plan
                    </button>
                  ) : planStatus === 'proposed' ? (
                    <div className="flex gap-2">
                      <button
                        onClick={() => void decide('approved')}
                        disabled={busy}
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
                      >
                        Approve Plan
                      </button>
                      <button
                        onClick={() => void decide('rejected')}
                        disabled={busy}
                        className="rounded-lg bg-rose-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-600"
                      >
                        Reject
                      </button>
                    </div>
                  ) : planStatus === 'approved' ? (
                    orders.length === 0 ? (
                      <button
                        onClick={() => void createOrders()}
                        disabled={busy}
                        className="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-amber-400"
                      >
                        Generate Purchase Orders
                      </button>
                    ) : (
                      <Link to="/orders" className="btn-secondary text-xs">
                        View Generated Orders ({orders.length}) →
                      </Link>
                    )
                  ) : (
                    <span className="text-xs text-rose-400">Plan Rejected</span>
                  )}
                </div>
              </div>

              {/* KPI Summary Cards */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-lg bg-slate-800/80 p-3">
                  <span className="text-xs text-slate-400 block">Total Estimated Cost</span>
                  <span className="text-xl font-bold text-teal-300 font-mono">
                    ₹{Math.round(activePlan.total_estimated_cost).toLocaleString()}
                  </span>
                  <span className="text-[11px] text-slate-400 block mt-0.5">
                    Material: ₹{Math.round(activePlan.material_cost).toLocaleString()} · Transport: ₹{Math.round(activePlan.transport_cost).toLocaleString()}
                  </span>
                </div>
                <div className="rounded-lg bg-slate-800/80 p-3">
                  <span className="text-xs text-slate-400 block">Estimated Delivery Lead Time</span>
                  <span className="text-xl font-bold text-slate-100 font-mono">
                    {activePlan.estimated_delivery_days ?? 'N/A'} <span className="text-sm font-normal text-slate-400">days</span>
                  </span>
                  <span className="text-[11px] text-slate-400 block mt-0.5">Longest promised transit branch</span>
                </div>
                <div className="rounded-lg bg-slate-800/80 p-3">
                  <span className="text-xs text-slate-400 block">Delivery Risk Indicator</span>
                  <span className="text-xl font-bold text-amber-400 font-mono">
                    {activePlan.expected_late_delivery_risk !== null
                      ? `${(activePlan.expected_late_delivery_risk * 100).toFixed(1)}%`
                      : 'N/A'}
                  </span>
                  <span className="text-[11px] text-slate-400 block mt-0.5">Predicted probability of delay</span>
                </div>
                <div className="rounded-lg bg-slate-800/80 p-3">
                  <span className="text-xs text-slate-400 block">Shortage / Feasibility</span>
                  <span className={`text-xl font-bold font-mono ${activePlan.shortage_quantity > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {activePlan.shortage_quantity > 0 ? `${activePlan.shortage_quantity} unmet` : '100% Fulfilled'}
                  </span>
                  <span className="text-[11px] text-slate-400 block mt-0.5">
                    {activePlan.budget_compliant ? 'Within project budget' : 'Exceeds budget cap'}
                  </span>
                </div>
              </div>

              {/* Allocations Table */}
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-left text-sm">
                  <thead className="text-slate-400">
                    <tr>
                      <th className="py-2">Allocated Supplier</th>
                      <th>Material</th>
                      <th>Allocated Qty</th>
                      <th>Unit Quote</th>
                      <th>Transport Est.</th>
                      <th>Promised Lead Time</th>
                      <th>Delay Risk</th>
                      <th>Data Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activePlan.allocations.map((alloc, i) => (
                      <tr key={i} className="border-t border-slate-700/60">
                        <td className="py-2.5 font-medium text-slate-200">{alloc.supplier_name}</td>
                        <td>{alloc.material}</td>
                        <td className="font-mono">{Number(alloc.quantity).toLocaleString()}</td>
                        <td className="font-mono">₹{Number(alloc.unit_price).toLocaleString()}</td>
                        <td className="font-mono">₹{Math.round(alloc.transport_cost).toLocaleString()}</td>
                        <td>{alloc.delivery_days} days</td>
                        <td>
                          {alloc.late_probability !== null ? (
                            <span className={alloc.late_probability > 0.3 ? 'text-rose-400' : 'text-emerald-400'}>
                              {(alloc.late_probability * 100).toFixed(0)}%
                            </span>
                          ) : '—'}
                        </td>
                        <td>
                          <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                            {alloc.risk_evidence || (alloc.demo ? 'Demo' : 'Real Quote')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          )}
        </section>
      )}
    </div>
  )
}
