import { FormEvent, useState } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../App'

interface ImportSummary {
  total_rows: number
  valid_count: number
  error_count: number
  message?: string
  preview_sample?: Record<string, unknown>[]
}

interface RowError {
  row_number: number
  raw_data: Record<string, unknown>
  errors: string[]
}

export function DataImportPage() {
  const { csrfToken } = useAuth()
  const [importType, setImportType] = useState('material_listings')
  const [csvContent, setCsvContent] = useState('')
  const [summary, setSummary] = useState<ImportSummary | null>(null)
  const [validRows, setValidRows] = useState<Record<string, unknown>[]>([])
  const [errorRows, setErrorRows] = useState<RowError[]>([])
  const [loading, setLoading] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const templateSamples: Record<string, string> = {
    material_listings: `material_name,quoted_unit_price,available_quantity,minimum_order_quantity,unit,estimated_delivery_days
Ordinary Portland cement,6200,1500,50,Metric Ton,7
Steel structures,172000,120,5,Metric Ton,14
Plain bricks,1020,5000,500,Metric Ton,5`,
    supplier_quotations: `material,quote_price,available_quantity,delivery_days,distance_km
Ordinary Portland cement,6150,800,6,22.5
Bitumen,53500,60,10,35.0`,
    delivery_outcomes: `order_id,actual_delivery_date,final_paid_price,cancelled,delay_days
1,2026-10-18,6100,0,0
2,2026-10-25,175000,0,2`,
    wpi_observations: `material_name,observation_date,index_value,data_source
Ordinary Portland cement,2026-04-01,185.4,REAL_WPI
Steel structures,2026-04-01,210.2,REAL_WPI`,
  }

  function loadTemplate(type: string) {
    setImportType(type)
    setCsvContent(templateSamples[type] || '')
    setSummary(null)
    setValidRows([])
    setErrorRows([])
    setError('')
    setMessage('')
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const text = await file.text()
    setCsvContent(text)
    setSummary(null)
    setValidRows([])
    setErrorRows([])
  }

  async function previewValidation(e: FormEvent) {
    e.preventDefault()
    if (!csvContent.trim()) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const res = await api<{
        summary: ImportSummary
        valid_rows: Record<string, unknown>[]
        error_rows: RowError[]
      }>('/api/import/preview', {
        method: 'POST',
        body: JSON.stringify({ import_type: importType, csv_content: csvContent }),
      }, csrfToken)
      setSummary(res.summary)
      setValidRows(res.valid_rows)
      setErrorRows(res.error_rows)
      if (res.summary.error_count > 0) {
        setError(`Validation detected ${res.summary.error_count} row errors. Review quarantined rows below.`)
      } else {
        setMessage(`All ${res.summary.valid_count} rows passed validation. You can now commit the import.`)
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Import validation failed.')
    } finally {
      setLoading(false)
    }
  }

  async function commitImport() {
    if (!validRows.length) return
    setCommitting(true)
    setError('')
    setMessage('')
    try {
      const res = await api<{ message: string; committed_rows: number }>('/api/import/commit', {
        method: 'POST',
        body: JSON.stringify({ import_type: importType, rows: validRows }),
      }, csrfToken)
      setMessage(res.message)
      setSummary(null)
      setValidRows([])
      setErrorRows([])
      setCsvContent('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Failed to commit import records.')
    } finally {
      setCommitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <h1 className="text-2xl font-bold">Controlled data import</h1>
        <p className="mt-1 text-sm text-slate-400">
          Upload and validate CSV records with pre-commit inspection. Invalid records are quarantined with diagnostic errors.
        </p>
      </div>

      {error && <p role="alert" className="rounded-xl border border-red-700 bg-red-950/40 p-4 text-red-200">{error}</p>}
      {message && <p role="status" className="rounded-xl border border-emerald-700 bg-emerald-950/40 p-4 text-emerald-200">{message}</p>}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Import Setup Form */}
        <section className="card space-y-4">
          <h2 className="text-lg font-semibold text-white">Import configuration</h2>
          <label className="block text-sm">Data entity type
            <select value={importType} onChange={(e) => loadTemplate(e.target.value)} className="form-control mt-1">
              <option value="material_listings">Supplier material listings</option>
              <option value="supplier_quotations">Supplier quotations</option>
              <option value="delivery_outcomes">Historical delivery outcomes</option>
              <option value="wpi_observations">Official WPI index observations (Admin)</option>
            </select>
          </label>

          <label className="block text-sm">Upload CSV file
            <input type="file" accept=".csv,text/csv" onChange={handleFileUpload} className="form-control mt-1 text-xs file:mr-2 file:rounded-md file:border-0 file:bg-slate-700 file:py-1 file:px-2 file:text-xs file:text-white" />
          </label>

          <button
            type="button"
            onClick={() => loadTemplate(importType)}
            className="text-xs text-teal-400 underline hover:text-teal-300"
          >
            Insert sample CSV template for this type
          </button>
        </section>

        {/* CSV Editor & Action */}
        <section className="card lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">CSV payload editor</h2>
            <span className="text-xs text-slate-400">Strict schema validation active</span>
          </div>

          <form onSubmit={previewValidation} className="space-y-4">
            <textarea
              rows={10}
              required
              value={csvContent}
              onChange={(e) => setCsvContent(e.target.value)}
              placeholder="Paste comma-separated CSV rows including header line..."
              className="form-control font-mono text-xs leading-relaxed"
            />

            <div className="flex justify-end gap-3">
              <button type="submit" className="btn-primary" disabled={loading || !csvContent.trim()}>
                {loading ? 'Validating schema…' : 'Validate & preview records'}
              </button>
            </div>
          </form>
        </section>
      </div>

      {/* Validation Summary & Preview */}
      {summary && (
        <section className="card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-700 pb-4">
            <div>
              <h2 className="text-lg font-bold text-white">Validation summary</h2>
              <p className="text-xs text-slate-400">
                Total rows parsed: {summary.total_rows} · Valid: {summary.valid_count} · Quarantined errors: {summary.error_count}
              </p>
            </div>
            {summary.valid_count > 0 && (
              <button onClick={commitImport} className="btn-primary" disabled={committing}>
                {committing ? 'Committing…' : `Commit ${summary.valid_count} valid records`}
              </button>
            )}
          </div>

          {/* Valid sample */}
          {validRows.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase text-emerald-400">Valid rows preview ({validRows.length} ready)</h3>
              <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/60 p-2">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-800">
                      {Object.keys(validRows[0] || {}).map((k) => <th key={k} className="py-1 px-2">{k}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {validRows.slice(0, 5).map((row, i) => (
                      <tr key={i} className="border-b border-slate-800/40">
                        {Object.values(row).map((val, j) => <td key={j} className="py-1 px-2 text-slate-300">{String(val)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Error rows */}
          {errorRows.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase text-red-400">Quarantined rows ({errorRows.length} issues)</h3>
              <div className="space-y-2">
                {errorRows.map((err, i) => (
                  <div key={i} className="rounded-lg border border-red-900/60 bg-red-950/30 p-3 text-xs text-red-200">
                    <p className="font-semibold">Row #{err.row_number}: {err.errors.join(' · ')}</p>
                    <p className="mt-1 font-mono text-[11px] text-slate-400">{JSON.stringify(err.raw_data)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
