import { useEffect, useState } from 'react'
import { api } from '../api'
import { Link } from 'react-router-dom'

interface MetricRow {
  material: string
  selected_model: string
  test_selected_MAE: number | null
  test_selected_RMSE: number | null
  'test_selected_MAPE_%': number | null
  'test_selected_sMAPE_%': number | null
  test_selected_R2: number | null
}

interface Evaluation {
  metrics: MetricRow[]
  dataset: string
  source_file: string
  warning: string
  status?: string
  reason?: string
}

export function ReportsPage() {
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<Evaluation>('/api/evaluation')
      .then(setEvaluation)
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load evaluation metrics.'))
  }, [])

  return (
    <div className="space-y-6">
      <div className="page-heading flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Reports & Model Evaluation</h1>
          <p className="mt-1 text-sm text-slate-400">
            Download generated forecasts, what-if scenarios, and recorded procurement outcomes with full provenance audit trails.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/research" className="btn-secondary text-xs">
            Open Research Dashboard →
          </Link>
          <Link to="/import" className="btn-secondary text-xs">
            Data Importer →
          </Link>
        </div>
      </div>

      {error && <p role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-red-200">{error}</p>}

      {/* Export Section */}
      <section className="card space-y-4">
        <h2 className="text-lg font-semibold">Audit & Data Exports</h2>
        <p className="text-sm text-slate-400">
          All exported records maintain strict data provenance tags (REAL_WPI, USER_ENTERED, REAL_TRANSACTION, SYNTHETIC_RESEARCH, DEMO).
        </p>
        <div className="flex flex-wrap gap-3 pt-1">
          <a className="btn-secondary text-xs" href="/api/reports/forecasts.csv" download>
            📥 Download Forecast History (CSV)
          </a>
          <a className="btn-secondary text-xs" href="/api/reports/orders.csv" download>
            📥 Download Order Outcomes (CSV)
          </a>
          <a className="btn-secondary text-xs" href="/api/reports/scenarios.csv" download>
            📥 Download Scenario Archive (CSV)
          </a>
          <a className="btn-secondary text-xs" href="/api/reports/evaluation.csv" download>
            📥 Download Holdout Metrics (CSV)
          </a>
        </div>
        <p className="text-xs text-slate-500">
          Exports are generated server-side directly from database records. WPI values are historical index numbers, never fabricated rupee prices.
        </p>
      </section>

      {/* Retrospective Model Evaluation Table */}
      <section className="card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">WPI Forecast Holdout Evaluation (Frozen Test Split)</h2>
          <span className="rounded bg-teal-950/60 border border-teal-800/80 px-2 py-0.5 text-xs text-teal-300">
            Validated Split
          </span>
        </div>

        {evaluation ? (
          <>
            <p className="text-sm text-slate-400">
              {evaluation.dataset} · Holdout artifact: <code className="text-xs text-teal-300">{evaluation.source_file}</code>
            </p>
            <p className="text-xs text-amber-300/90 bg-amber-950/30 border border-amber-900/60 p-2.5 rounded-lg">
              {evaluation.warning}
            </p>

            {evaluation.metrics.length > 0 && (
              <div className="max-h-[500px] overflow-auto rounded-lg border border-slate-700/80">
                <table className="w-full min-w-[850px] text-left text-sm">
                  <thead className="sticky top-0 bg-slate-800 text-slate-300">
                    <tr>
                      <th className="py-2.5 px-3">Material</th>
                      <th>Model Selected</th>
                      <th>MAE</th>
                      <th>RMSE</th>
                      <th>MAPE %</th>
                      <th>sMAPE %</th>
                      <th>R²</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evaluation.metrics.map((row) => (
                      <tr key={row.material} className="border-t border-slate-700/60 hover:bg-slate-800/40">
                        <td className="py-2.5 px-3 font-medium text-slate-200">{row.material}</td>
                        <td>
                          <span className="rounded bg-slate-800 px-2 py-0.5 text-xs font-mono text-teal-300">
                            {row.selected_model}
                          </span>
                        </td>
                        <td className="font-mono">{row.test_selected_MAE ?? '—'}</td>
                        <td className="font-mono">{row.test_selected_RMSE ?? '—'}</td>
                        <td className="font-mono">{row['test_selected_MAPE_%'] !== null ? `${row['test_selected_MAPE_%']}%` : '—'}</td>
                        <td className="font-mono">{row['test_selected_sMAPE_%'] !== null ? `${row['test_selected_sMAPE_%']}%` : '—'}</td>
                        <td className="font-mono">{row.test_selected_R2 ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {evaluation.status === 'unavailable' && (
              <p className="mt-3 text-slate-400">{evaluation.reason}</p>
            )}
          </>
        ) : (
          <p className="mt-4 animate-pulse text-slate-400">Loading retrospective evaluation metrics…</p>
        )}
      </section>

      <p className="text-xs text-slate-500">
        Time-series evaluations are locked to historical out-of-sample data. Unlabeled live contractor inputs are never mixed into holdout metrics.
      </p>
    </div>
  )
}
