import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ApiError, api } from '../api'
import { useAuth } from '../App'
import { Link } from 'react-router-dom'

interface Material {
  name: string
  group: string
}

interface Forecast {
  status: string
  material: string
  current_wpi: number
  forecast_wpi: number
  expected_change_pct: number
  alpha: number
  prediction_date: string
  forecast_generation_time: string
  model_name: string
  model_version: string
  data_provenance: string
  intervals: Record<string, { lower: number; upper: number; width: number; empirical_test_coverage: number; calibration_samples: number }>
  warning: string
}

interface Decision {
  decision: string
  decision_category?: string
  decision_explanation: string
  expected_change_pct: number
  uncertainty_indicator: string
  waiting_conflicts_with_deadline: string
  provenance?: string
}

interface Observation {
  date: string
  value: number
}

function getDecisionStyle(cat?: string, dec?: string) {
  const text = (cat || dec || '').toUpperCase()
  if (text.includes('PRICE_RISING_CONFIDENT')) return 'border-emerald-500 bg-emerald-950/40 text-emerald-300'
  if (text.includes('DEADLINE_NEAR')) return 'border-rose-500 bg-rose-950/40 text-rose-300'
  if (text.includes('PRICE_FALLING_FAVORABLE')) return 'border-sky-500 bg-sky-950/40 text-sky-300'
  if (text.includes('UNCERTAIN')) return 'border-amber-500 bg-amber-950/40 text-amber-300'
  if (text.includes('STABLE')) return 'border-indigo-500 bg-indigo-950/40 text-indigo-300'
  return 'border-slate-600 bg-slate-800 text-slate-200'
}

export function ForecastPage() {
  const { csrfToken } = useAuth()
  const [materials, setMaterials] = useState<Material[]>([])
  const [material, setMaterial] = useState('')
  const [history, setHistory] = useState<Observation[]>([])
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const [decision, setDecision] = useState<Decision | null>(null)
  const [deadline, setDeadline] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api<{ materials: Material[] }>('/api/materials')
      .then((data) => {
        setMaterials(data.materials)
        setMaterial(data.materials[0]?.name ?? '')
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load materials.'))
  }, [])

  useEffect(() => {
    if (!material) return
    api<{ history: Observation[] }>(`/api/materials/history?material=${encodeURIComponent(material)}`)
      .then((data) => setHistory(data.history))
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load WPI history.'))
  }, [material])

  async function generate() {
    setLoading(true)
    setError('')
    setForecast(null)
    setDecision(null)
    try {
      const result = await api<Forecast>('/api/forecast', { method: 'POST', body: JSON.stringify({ material }) }, csrfToken)
      setForecast(result)
      const deadlineDays = deadline ? Math.ceil((new Date(`${deadline}T00:00:00`).getTime() - Date.now()) / 86400000) : undefined
      const recommendation = await api<Decision>('/api/buy-wait', {
        method: 'POST',
        body: JSON.stringify({ material, project_deadline_days: deadlineDays }),
      }, csrfToken)
      setDecision(recommendation)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to generate the forecast.')
    } finally {
      setLoading(false)
    }
  }

  const latestDate = history[history.length - 1]?.date

  return (
    <div className="space-y-6">
      <div className="page-heading flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Material Price Intelligence & Decision Engine</h1>
          <p className="mt-1 text-sm text-slate-400">
            Real monthly WPI history, conformal prediction uncertainty intervals, and frozen Buy/Wait directional rules.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/scenarios" className="btn-secondary text-xs">
            What-If Scenarios →
          </Link>
          <Link to="/research" className="btn-secondary text-xs">
            Conformal Coverage →
          </Link>
        </div>
      </div>

      <section className="card flex flex-wrap items-end gap-4">
        <label className="min-w-64 flex-1 text-sm">Material Catalog
          <select value={material} onChange={(event) => setMaterial(event.target.value)} className="form-control mt-1">
            {materials.map((item) => <option key={item.name} value={item.name}>{item.name} · {item.group}</option>)}
          </select>
        </label>
        <label className="text-sm">Project Delivery Deadline (Optional)
          <input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} className="form-control mt-1" />
        </label>
        <button className="btn-primary" onClick={() => void generate()} disabled={!material || loading}>
          {loading ? 'Evaluating Model…' : 'Generate Forecast & Buy/Wait Decision'}
        </button>
      </section>

      {error && <p role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-red-200">{error}</p>}

      {/* Historical Trend Chart */}
      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">Real Monthly Wholesale Price Index (WPI) History</h2>
            <span className="text-xs text-teal-400 font-mono">Provenance: REAL_WPI · MoSPI / Office of the Economic Adviser</span>
          </div>
          {latestDate && <span className="text-sm text-slate-400">Latest observation: {latestDate}</span>}
        </div>
        <div className="chart-container mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#94a3b8" tick={{ fontSize: 10 }} minTickGap={40} />
              <YAxis stroke="#94a3b8" domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
                formatter={(val: any) => [`${Number(val).toFixed(2)} Index`, 'WPI Observation']}
              />
              <Line name="WPI index" dataKey="value" type="monotone" stroke="#14b8a6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Results grid */}
      {forecast && (
        <section className="grid gap-6 lg:grid-cols-2">
          <article className="card space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Next Observation Forecast</h2>
              <span className="rounded bg-teal-950/70 border border-teal-800 px-2 py-0.5 text-xs text-teal-300">
                PROVENANCE: FORECAST_RECORD
              </span>
            </div>
            <p className="text-4xl font-bold text-teal-300 font-mono">
              {forecast.forecast_wpi.toFixed(2)} <span className="text-base font-normal text-slate-400">WPI</span>
            </p>
            <p className="text-sm text-slate-300">
              Current index: <span className="font-mono">{forecast.current_wpi.toFixed(2)}</span> · Expected movement:{' '}
              <span className={`font-mono font-semibold ${forecast.expected_change_pct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                {forecast.expected_change_pct >= 0 ? '+' : ''}{forecast.expected_change_pct.toFixed(3)}%
              </span>
            </p>
            <p className="text-xs text-slate-400">
              Model: {forecast.model_name} · Version {forecast.model_version} · Frozen α = {forecast.alpha}
            </p>
            <p className="text-xs text-slate-400">
              As of {forecast.prediction_date} · Computed at {new Date(forecast.forecast_generation_time).toLocaleString()}
            </p>
            <p className="text-xs text-slate-400">{forecast.data_provenance}</p>

            {/* Conformal intervals */}
            <div className="space-y-2 border-t border-slate-700/80 pt-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Conformal Uncertainty Prediction Intervals
              </span>
              {Object.entries(forecast.intervals).map(([level, interval]) => (
                <div key={level} className="rounded-lg bg-slate-800/80 p-2 text-xs flex justify-between items-center">
                  <span className="font-semibold text-slate-300">{level}% Interval</span>
                  <span className="font-mono text-teal-300">
                    [{interval.lower.toFixed(2)} — {interval.upper.toFixed(2)}]
                  </span>
                  <span className="text-slate-400">
                    Width: {interval.width.toFixed(2)} | Holdout coverage: {(interval.empirical_test_coverage * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
            <p className="text-xs text-amber-200/90">{forecast.warning}</p>
          </article>

          {decision && (
            <article className={`card space-y-4 border ${getDecisionStyle(decision.decision_category, decision.decision)}`}>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-100">Buy / Wait Directional Recommendation</h2>
                <span className="rounded bg-slate-900/60 px-2 py-0.5 text-xs font-mono font-semibold">
                  Rule Threshold: ±0.25%
                </span>
              </div>

              <div className="rounded-xl bg-slate-900/60 p-4 border border-slate-700/60">
                <p className="text-2xl font-bold font-mono tracking-tight">{decision.decision}</p>
                <p className="mt-2 text-sm text-slate-300 leading-relaxed">{decision.decision_explanation}</p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-lg bg-slate-900/40 p-2.5">
                  <span className="text-slate-400 block">Uncertainty State:</span>
                  <span className="font-semibold text-sm mt-0.5 block">{decision.uncertainty_indicator}</span>
                </div>
                <div className="rounded-lg bg-slate-900/40 p-2.5">
                  <span className="text-slate-400 block">Deadline Conflict:</span>
                  <span className={`font-semibold text-sm mt-0.5 block ${decision.waiting_conflicts_with_deadline === 'Yes' ? 'text-rose-400' : 'text-slate-200'}`}>
                    {deadline ? decision.waiting_conflicts_with_deadline : 'No deadline provided'}
                  </span>
                </div>
              </div>

              {decision.waiting_conflicts_with_deadline === 'Yes' && (
                <div className="rounded-lg border border-rose-700 bg-rose-950/60 p-3 text-xs text-rose-200">
                  ⚠️ <strong>Urgency Warning:</strong> Even though the price forecast suggests favorable waiting, waiting conflicts with the target project deadline ({deadline}). Immediate procurement is recommended to prevent project stoppage penalties.
                </div>
              )}

              <p className="text-[11px] text-slate-400 border-t border-slate-700/60 pt-2">
                Decisions are research-oriented mathematical guidelines; not financial guarantees. Purchases are never committed automatically.
              </p>
            </article>
          )}
        </section>
      )}
    </div>
  )
}
