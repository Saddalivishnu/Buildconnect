import { FormEvent, useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import { useAuth } from '../App'
import { Link } from 'react-router-dom'

interface SupplierRecord {
  id: number
  name: string
  category: string
  city: string
  demo: number
  verified: number
  quote_id: number | null
  quote_material: string | null
  quote_price: number | null
  available_quantity: number | null
  delivery_days: number | null
  distance_km: number | null
  quote_demo: number | null
  contact_person?: string
  phone?: string
  email?: string
  address?: string
  state?: string
  latitude?: number | null
  longitude?: number | null
  average_rating?: number | null
  review_count?: number
}

interface MaterialRecord {
  name: string
}

export function SuppliersPage() {
  const { user, csrfToken } = useAuth()
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([])
  const [materials, setMaterials] = useState<MaterialRecord[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  // Filters & sorting
  const [searchTerm, setSearchTerm] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('ALL')
  const [cityFilter, setCityFilter] = useState('ALL')
  const [availabilityOnly, setAvailabilityOnly] = useState(false)
  const [sortBy, setSortBy] = useState<'price_asc' | 'delivery_asc' | 'distance_asc' | 'name'>('price_asc')

  // Selected supplier modal for detail view
  const [selectedSupplier, setSelectedSupplier] = useState<SupplierRecord | null>(null)

  async function load() {
    try {
      const [directory, catalogue] = await Promise.all([
        api<{ suppliers: SupplierRecord[] }>('/api/suppliers'),
        api<{ materials: MaterialRecord[] }>('/api/materials'),
      ])
      setSuppliers(directory.suppliers)
      setMaterials(catalogue.materials)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load supplier data.')
    }
  }

  useEffect(() => { void load() }, [])

  async function publishQuote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    setBusy(true)
    setError('')
    setMessage('')
    const values = new FormData(form)
    try {
      await api('/api/supplier-quotes', {
        method: 'POST',
        body: JSON.stringify({
          material: values.get('material'),
          quote_price: Number(values.get('quote_price')),
          available_quantity: Number(values.get('available_quantity')),
          delivery_days: Number(values.get('delivery_days')),
          distance_km: Number(values.get('distance_km')),
        }),
      }, csrfToken)
      form.reset()
      setMessage('Quotation published and visible in the marketplace.')
      await load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to publish quotation.')
    } finally {
      setBusy(false)
    }
  }

  // Derive categories and cities for dropdown filters
  const categories = Array.from(new Set(suppliers.map(s => s.category).filter(Boolean)))
  const cities = Array.from(new Set(suppliers.map(s => s.city).filter(Boolean)))

  // Filter and sort listings
  const filtered = suppliers.filter((item) => {
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      const matchName = item.name.toLowerCase().includes(q)
      const matchMat = (item.quote_material || '').toLowerCase().includes(q)
      const matchCat = (item.category || '').toLowerCase().includes(q)
      if (!matchName && !matchMat && !matchCat) return false
    }
    if (categoryFilter !== 'ALL' && item.category !== categoryFilter) return false
    if (cityFilter !== 'ALL' && item.city !== cityFilter) return false
    if (availabilityOnly && (!item.available_quantity || item.available_quantity <= 0)) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === 'price_asc') {
      return (a.quote_price ?? 999999) - (b.quote_price ?? 999999)
    }
    if (sortBy === 'delivery_asc') {
      return (a.delivery_days ?? 999) - (b.delivery_days ?? 999)
    }
    if (sortBy === 'distance_asc') {
      return (a.distance_km ?? 9999) - (b.distance_km ?? 9999)
    }
    return a.name.localeCompare(b.name)
  })

  return (
    <div className="space-y-6">
      <div className="page-heading flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Supplier Marketplace & Intelligence</h1>
          <p className="mt-1 text-sm text-slate-400">
            Compare verified supplier listings, quoted prices, Bayesian quality ratings, and delivery terms. WPI is an index, not a quoted price.
          </p>
        </div>
        <Link to="/orders" className="btn-secondary text-sm">
          View Active Purchase Orders →
        </Link>
      </div>

      {error && <p role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-red-200">{error}</p>}
      {message && <p role="status" className="rounded border border-emerald-700 bg-emerald-950/30 p-3 text-emerald-200">{message}</p>}

      {user.role === 'supplier' && (
        <form onSubmit={publishQuote} className="card space-y-4">
          <h2 className="text-lg font-semibold">Publish a New Quotation</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <label className="text-sm">Material
              <select required name="material" className="form-control">
                {materials.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
              </select>
            </label>
            <label className="text-sm">Unit quote (₹/unit)<input required name="quote_price" type="number" min="0.01" step="any" className="form-control" /></label>
            <label className="text-sm">Available quantity<input required name="available_quantity" type="number" min="0.01" step="any" className="form-control" /></label>
            <label className="text-sm">Promised delivery (days)<input required name="delivery_days" type="number" min="1" max="365" className="form-control" /></label>
            <label className="text-sm">Distance (km, entered)<input required name="distance_km" type="number" min="0" step="any" className="form-control" /></label>
          </div>
          <p className="text-xs text-slate-400">Distance is supplier-entered. New listings are unverified unless validated by an administrator.</p>
          <button className="btn-primary" disabled={busy}>{busy ? 'Publishing…' : 'Publish quote'}</button>
        </form>
      )}

      {/* Search, Filter & Sort Controls */}
      <section className="card space-y-4">
        <h2 className="text-lg font-semibold">Directory Search & Filters</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="text-xs text-slate-400">Search Material / Supplier</label>
            <input
              type="text"
              placeholder="e.g. Cement, Steel, Supplier"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="form-control text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">Material Category</label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="form-control text-sm"
            >
              <option value="ALL">All Categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400">City / Location</label>
            <select
              value={cityFilter}
              onChange={(e) => setCityFilter(e.target.value)}
              className="form-control text-sm"
            >
              <option value="ALL">All Cities</option>
              {cities.map((city) => <option key={city} value={city}>{city}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400">Sort By</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="form-control text-sm"
            >
              <option value="price_asc">Price: Lowest first</option>
              <option value="delivery_asc">Delivery: Fastest first</option>
              <option value="distance_asc">Distance: Nearest first</option>
              <option value="name">Supplier Name (A-Z)</option>
            </select>
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={availabilityOnly}
                onChange={(e) => setAvailabilityOnly(e.target.checked)}
                className="rounded border-slate-700 bg-slate-800 text-teal-500 focus:ring-0"
              />
              In-stock only (&gt; 0 qty)
            </label>
          </div>
        </div>
      </section>

      {/* Directory Listings Table */}
      <section className="card">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Available Supplier Quotations ({sorted.length})</h2>
          <span className="text-xs text-slate-400">Showing filtered results</span>
        </div>

        {sorted.length === 0 ? (
          <p className="mt-4 text-slate-400">No supplier quotations match your filter criteria.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-slate-400">
                <tr>
                  <th className="py-2">Supplier</th>
                  <th>Material</th>
                  <th>Unit Quote</th>
                  <th>Available Qty</th>
                  <th>Delivery</th>
                  <th>Location / Distance</th>
                  <th>Bayesian Rating</th>
                  <th>Provenance</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((item, idx) => (
                  <tr key={`${item.id}-${item.quote_id || idx}`} className="border-t border-slate-700 hover:bg-slate-800/40">
                    <td className="py-3">
                      <button
                        onClick={() => setSelectedSupplier(item)}
                        className="font-medium text-teal-400 hover:underline text-left"
                      >
                        {item.name}
                      </button>
                      <div className="text-xs text-slate-400">{item.category}</div>
                    </td>
                    <td>{item.quote_material || 'General Supply'}</td>
                    <td className="font-mono">{item.quote_price !== null ? `₹${Number(item.quote_price).toLocaleString()}` : '—'}</td>
                    <td>{item.available_quantity !== null ? Number(item.available_quantity).toLocaleString() : '—'}</td>
                    <td>{item.delivery_days !== null ? `${item.delivery_days} days` : '—'}</td>
                    <td>
                      {item.city}
                      {item.distance_km !== null ? ` · ${item.distance_km} km` : ''}
                    </td>
                    <td>
                      {item.review_count && item.review_count > 0 ? (
                        <span className="inline-flex items-center gap-1 font-semibold text-amber-400">
                          ★ {(item.average_rating || 0).toFixed(1)}
                          <span className="text-xs font-normal text-slate-400">({item.review_count})</span>
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500 italic">Unrated</span>
                      )}
                    </td>
                    <td>
                      {item.demo || item.quote_demo ? (
                        <span className="rounded bg-blue-900/60 px-2 py-0.5 text-xs text-blue-200">Demo</span>
                      ) : (
                        <span className="text-xs text-emerald-300">Enterprise</span>
                      )}
                      {item.verified === 1 && !item.demo && (
                        <span className="ml-1 rounded bg-teal-900/60 px-1.5 py-0.5 text-[10px] text-teal-200">Verified</span>
                      )}
                    </td>
                    <td>
                      <button
                        onClick={() => setSelectedSupplier(item)}
                        className="rounded bg-slate-700 px-2.5 py-1 text-xs hover:bg-slate-600"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Supplier Detail Modal */}
      {selectedSupplier && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="max-w-xl w-full rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-xl font-bold text-slate-100">{selectedSupplier.name}</h3>
                <p className="text-sm text-slate-400">{selectedSupplier.category} · {selectedSupplier.city}</p>
              </div>
              <button
                onClick={() => setSelectedSupplier(null)}
                className="text-slate-400 hover:text-slate-200 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-slate-800/60 p-3">
                  <p className="text-xs text-slate-400">Verification Status</p>
                  <p className="font-semibold mt-0.5">
                    {selectedSupplier.verified ? '✓ Verified Partner' : 'Unverified Listing'}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-800/60 p-3">
                  <p className="text-xs text-slate-400">Bayesian Average Rating</p>
                  <p className="font-semibold mt-0.5">
                    {selectedSupplier.review_count && selectedSupplier.review_count > 0
                      ? `★ ${(selectedSupplier.average_rating || 0).toFixed(2)} (${selectedSupplier.review_count} reviews)`
                      : 'No customer reviews recorded yet'}
                  </p>
                </div>
              </div>

              <div className="rounded-lg bg-slate-800/60 p-3 space-y-1">
                <p className="text-xs text-slate-400">Active Quoted Material</p>
                <p className="font-semibold text-teal-300">
                  {selectedSupplier.quote_material || 'No active material quoted'}
                </p>
                {selectedSupplier.quote_price !== null && (
                  <p className="text-xs text-slate-300">
                    Price: ₹{Number(selectedSupplier.quote_price).toLocaleString()} | Available Qty: {Number(selectedSupplier.available_quantity).toLocaleString()} | Promised Delivery: {selectedSupplier.delivery_days} days
                  </p>
                )}
              </div>

              <div className="rounded-lg bg-slate-800/60 p-3">
                <p className="text-xs text-slate-400">Geographic Routing & Coordinates</p>
                {selectedSupplier.latitude && selectedSupplier.longitude ? (
                  <p className="text-xs font-mono text-slate-300 mt-1">
                    Lat: {selectedSupplier.latitude.toFixed(4)}, Long: {selectedSupplier.longitude.toFixed(4)}
                  </p>
                ) : (
                  <p className="text-xs text-slate-400 mt-1 italic">
                    Coordinates not registered. Using city-level centroid estimate ({selectedSupplier.city || 'Regional Center'}). Distance: {selectedSupplier.distance_km ?? 'N/A'} km.
                  </p>
                )}
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3 border-t border-slate-800 pt-4">
              <button
                onClick={() => setSelectedSupplier(null)}
                className="btn-secondary text-xs"
              >
                Close
              </button>
              {user.role === 'contractor' && (
                <Link
                  to="/procurement"
                  className="btn-primary text-xs"
                >
                  Allocate in Procurement Plan →
                </Link>
              )}
            </div>
          </div>
        </div>
      )}

      <p className="text-xs text-slate-500">
        Supplier ratings are calculated strictly via Bayesian mean shrinkage over validated purchase order delivery reviews. Unreviewed suppliers remain unrated.
      </p>
    </div>
  )
}
