import { FormEvent, useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import { useAuth } from '../App'
import { Link } from 'react-router-dom'

interface MaterialOption {
  name: string
  group: string
}

interface ProjectRequirement {
  material: string
  required_quantity: number
  current_inventory: number
  ordered_quantity: number
  remaining_quantity?: number
  unit_cost?: number
  required_by_date?: string
}

interface Project {
  id: number
  name: string
  location: string
  budget: number
  start_date: string
  deadline: string
  status: string
  demo: number
  materials?: ProjectRequirement[]
}

export function ProjectsPage() {
  const { csrfToken } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [materials, setMaterials] = useState<MaterialOption[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  // Live calculation helpers for project creation form
  const [formRequiredQty, setFormRequiredQty] = useState<number>(1000)
  const [formInventoryQty, setFormInventoryQty] = useState<number>(0)
  const [formOrderedQty, setFormOrderedQty] = useState<number>(0)

  const remainingQty = Math.max(0, formRequiredQty - formInventoryQty - formOrderedQty)

  async function load() {
    try {
      const [projectData, materialData] = await Promise.all([
        api<{ projects: Project[] }>('/api/projects'),
        api<{ materials: MaterialOption[] }>('/api/materials'),
      ])
      setProjects(projectData.projects)
      setMaterials(materialData.materials)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load project data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    setBusy(true)
    setError('')
    setMessage('')
    const values = new FormData(event.currentTarget)
    const material = String(values.get('material'))
    const req = Number(values.get('required_quantity'))
    const inv = Number(values.get('current_inventory') || 0)
    const ord = Number(values.get('ordered_quantity') || 0)
    const targetPrice = Number(values.get('target_unit_price') || 0)
    const reqBy = String(values.get('required_by_date') || values.get('deadline'))

    if (inv + ord > req) {
      setError('Current inventory plus already ordered quantity cannot exceed total required quantity.')
      setBusy(false)
      return
    }

    try {
      const result = await api<{ project_id: number }>('/api/projects', {
        method: 'POST',
        body: JSON.stringify({
          name: values.get('name'),
          location: values.get('location'),
          budget: Number(values.get('budget')),
          start_date: values.get('start_date'),
          deadline: values.get('deadline'),
          materials: [{
            material,
            required_quantity: req,
            current_inventory: inv,
            ordered_quantity: ord,
            unit_cost: targetPrice,
            required_by_date: reqBy,
          }],
        }),
      }, csrfToken)
      setMessage(`Project created (ID ${result.project_id}). Net remaining requirement to procure: ${Math.max(0, req - inv - ord).toLocaleString()} units.`)
      form.reset()
      setFormRequiredQty(1000)
      setFormInventoryQty(0)
      setFormOrderedQty(0)
      await load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to create the project.')
    } finally {
      setBusy(false)
    }
  }

  async function archiveProject(project: Project) {
    if (project.demo) return
    setError('')
    try {
      await api(`/api/projects/${project.id}`, { method: 'DELETE' }, csrfToken)
      await load()
      setMessage(`${project.name} archived.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to archive project.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="page-heading flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Construction Projects & Requirements</h1>
          <p className="mt-1 text-sm text-slate-400">
            Define site requirements, existing inventory, and unfulfilled material demand.
          </p>
        </div>
        <Link to="/procurement" className="btn-secondary text-sm">
          Plan Allocations →
        </Link>
      </div>

      {error && <p role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-red-200">{error}</p>}
      {message && <p role="status" className="rounded border border-emerald-700 bg-emerald-950/30 p-3 text-emerald-200">{message}</p>}

      <form onSubmit={createProject} className="card space-y-4">
        <h2 className="text-lg font-semibold">Define New Project Requirement</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-sm">Project name
            <input required name="name" maxLength={150} className="form-control" placeholder="e.g. Metro Station Block B" />
          </label>
          <label className="text-sm">Site Location
            <input required name="location" maxLength={200} className="form-control" placeholder="e.g. Pune City Sector 4" />
          </label>
          <label className="text-sm">Total Budget (₹)
            <input required name="budget" type="number" min="0.01" step="0.01" className="form-control" placeholder="e.g. 5000000" />
          </label>
          <label className="text-sm">Start Date
            <input required name="start_date" type="date" className="form-control" />
          </label>
          <label className="text-sm">Project Deadline
            <input required name="deadline" type="date" className="form-control" />
          </label>
          <label className="text-sm">Required-by Date
            <input name="required_by_date" type="date" className="form-control" title="Material delivery target date" />
          </label>
          <label className="text-sm">Material Spec
            <select required name="material" className="form-control">
              {materials.map((item) => <option key={item.name} value={item.name}>{item.name} ({item.group})</option>)}
            </select>
          </label>
          <label className="text-sm">Required Total Quantity
            <input
              required
              name="required_quantity"
              type="number"
              min="0.001"
              step="any"
              value={formRequiredQty}
              onChange={(e) => setFormRequiredQty(Number(e.target.value))}
              className="form-control"
            />
          </label>
          <label className="text-sm">Current On-Site Inventory
            <input
              required
              name="current_inventory"
              type="number"
              min="0"
              step="any"
              value={formInventoryQty}
              onChange={(e) => setFormInventoryQty(Number(e.target.value))}
              className="form-control"
            />
          </label>
          <label className="text-sm">Already Ordered Quantity
            <input
              required
              name="ordered_quantity"
              type="number"
              min="0"
              step="any"
              value={formOrderedQty}
              onChange={(e) => setFormOrderedQty(Number(e.target.value))}
              className="form-control"
            />
          </label>
          <label className="text-sm">Target Unit Price (₹, optional)
            <input name="target_unit_price" type="number" min="0" step="any" defaultValue="0" className="form-control" placeholder="Max acceptable unit cost" />
          </label>

          <div className="rounded-xl border border-teal-800/60 bg-teal-950/30 p-3 flex flex-col justify-center">
            <span className="text-xs text-teal-400 font-medium">Net Procurement Need:</span>
            <span className="text-xl font-bold text-teal-200 mt-1 font-mono">
              {remainingQty.toLocaleString()} units
            </span>
            <span className="text-[11px] text-slate-400 mt-0.5">
              = max(0, {formRequiredQty} - {formInventoryQty} - {formOrderedQty})
            </span>
          </div>
        </div>

        <p className="text-xs text-slate-400">
          Target unit price and required-by dates guide multi-criteria supplier ranking and procurement optimization.
        </p>
        <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Create Project & Requirement'}</button>
      </form>

      <section className="card">
        <h2 className="text-lg font-semibold">Active Projects ({projects.length})</h2>
        {loading ? (
          <p className="mt-4 animate-pulse text-slate-400">Loading projects…</p>
        ) : projects.length === 0 ? (
          <p className="mt-4 text-slate-400">No projects yet. Create one above to initiate procurement optimization.</p>
        ) : (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {projects.map((project) => (
              <article key={project.id} className="rounded-xl border border-slate-700 bg-slate-800/40 p-5 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-100">{project.name}</h3>
                    <p className="text-xs text-slate-400">{project.location} · Deadline: {project.deadline}</p>
                  </div>
                  {project.demo === 1 ? (
                    <span className="rounded bg-blue-900/60 px-2 py-0.5 text-xs text-blue-200">Demo</span>
                  ) : (
                    <button className="text-xs text-red-300 hover:text-red-200" onClick={() => void archiveProject(project)}>
                      Archive
                    </button>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs text-slate-300">
                  <div className="rounded bg-slate-900/60 p-2">
                    <span className="text-slate-400 block">Total Budget:</span>
                    <span className="font-semibold text-sm">₹{Number(project.budget).toLocaleString()}</span>
                  </div>
                  <div className="rounded bg-slate-900/60 p-2">
                    <span className="text-slate-400 block">Status:</span>
                    <span className="font-semibold text-sm capitalize">{project.status}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between border-t border-slate-700/60 pt-3">
                  <span className="text-xs text-slate-400">Start Date: {project.start_date}</span>
                  <Link
                    to="/procurement"
                    className="text-xs font-semibold text-teal-400 hover:underline"
                  >
                    Optimize Procurement →
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
