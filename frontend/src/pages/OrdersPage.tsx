import { FormEvent, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../App'

interface OrderOutcome {
  actual_delivery_date: string | null
  final_paid_price: number | null
  cancelled: number
  delay_days: number | null
  cancellation_status?: string
}

interface PurchaseOrder {
  id: number
  order_reference?: string
  plan_id: number
  project_id: number
  supplier_id: number
  material: string
  quantity: number
  quoted_unit_price: number
  subtotal?: number
  transport_cost?: number
  total_cost?: number
  promised_delivery_date: string
  expected_delivery_date?: string
  status: string
  order_status?: string
  demo: number
  created_at: string
  outcome?: OrderOutcome | null
}

export function OrdersPage() {
  const { user, csrfToken } = useAuth()
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  // Outcome recording modal state
  const [selectedOrder, setSelectedOrder] = useState<PurchaseOrder | null>(null)
  const [outcomeDate, setOutcomeDate] = useState(new Date().toISOString().slice(0, 10))
  const [outcomePrice, setOutcomePrice] = useState('')
  const [outcomeCancelled, setOutcomeCancelled] = useState(false)

  // Review state
  const [reviewOrder, setReviewOrder] = useState<PurchaseOrder | null>(null)
  const [rating, setRating] = useState(5)
  const [reviewText, setReviewText] = useState('')

  async function loadOrders() {
    try {
      const data = await api<{ orders: PurchaseOrder[] }>('/api/orders')
      setOrders(data.orders)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load orders.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadOrders()
  }, [])

  async function updateStatus(orderId: number, newStatus: string) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await api(`/api/orders/${orderId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus }),
      }, csrfToken)
      setMessage(`Order #${orderId} marked as ${newStatus}.`)
      await loadOrders()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to update order status.')
    } finally {
      setBusy(false)
    }
  }

  async function submitOutcome(event: FormEvent) {
    event.preventDefault()
    if (!selectedOrder) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const body: Record<string, unknown> = {
        cancelled: outcomeCancelled,
      }
      if (!outcomeCancelled) {
        body.actual_delivery_date = outcomeDate
      }
      if (outcomePrice) {
        body.final_paid_price = Number(outcomePrice)
      }
      await api(`/api/orders/${selectedOrder.id}/outcome`, {
        method: 'POST',
        body: JSON.stringify(body),
      }, csrfToken)
      setMessage(`Delivery outcome recorded for Order #${selectedOrder.id}.`)
      setSelectedOrder(null)
      await loadOrders()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to record delivery outcome.')
    } finally {
      setBusy(false)
    }
  }

  async function submitReview(event: FormEvent) {
    event.preventDefault()
    if (!reviewOrder) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await api(`/api/suppliers/${reviewOrder.supplier_id}/reviews`, {
        method: 'POST',
        body: JSON.stringify({
          purchase_order_id: reviewOrder.id,
          rating,
          review_text: reviewText,
        }),
      }, csrfToken)
      setMessage(`Review submitted for Supplier #${reviewOrder.supplier_id}.`)
      setReviewOrder(null)
      setReviewText('')
      await loadOrders()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to submit review.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <h1 className="text-2xl font-bold">Purchase orders & order tracking</h1>
        <p className="mt-1 text-sm text-slate-400">
          Track lifecycle progression from approved procurement plans to final delivery outcomes.
        </p>
      </div>

      {error && <p role="alert" className="rounded-xl border border-red-700 bg-red-950/40 p-4 text-red-200">{error}</p>}
      {message && <p role="status" className="rounded-xl border border-emerald-700 bg-emerald-950/40 p-4 text-emerald-200">{message}</p>}

      {loading ? (
        <div className="card p-8 text-center text-slate-400">Loading purchase orders…</div>
      ) : orders.length === 0 ? (
        <div className="card p-8 text-center text-slate-400">
          No purchase orders found. Orders are generated from approved procurement plans.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-slate-700 bg-slate-800/80 text-xs text-slate-400 uppercase">
              <tr>
                <th className="py-3 px-3">Order ID</th>
                <th>Material</th>
                <th>Quantity</th>
                <th>Unit price</th>
                <th>Est. total</th>
                <th>Promised date</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {orders.map((o) => {
                const total = o.total_cost ?? (o.quantity * o.quoted_unit_price)
                const currentStatus = o.order_status || o.status
                return (
                  <tr key={o.id} className="hover:bg-slate-800/30">
                    <td className="py-3 px-3 font-mono font-medium text-teal-400">
                      PO-{String(o.id).padStart(5, '0')}
                      {o.demo === 1 && <span className="ml-2 rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] text-amber-300">DEMO</span>}
                    </td>
                    <td className="font-medium text-white">{o.material}</td>
                    <td>{o.quantity.toLocaleString()}</td>
                    <td>₹{o.quoted_unit_price.toLocaleString()}</td>
                    <td className="font-medium text-emerald-400">₹{total.toLocaleString()}</td>
                    <td>{o.promised_delivery_date}</td>
                    <td>
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
                        currentStatus === 'delivered' ? 'bg-emerald-900/60 text-emerald-300' :
                        currentStatus === 'cancelled' || currentStatus === 'rejected' ? 'bg-red-900/60 text-red-300' :
                        currentStatus === 'in-transit' ? 'bg-blue-900/60 text-blue-300' :
                        currentStatus === 'accepted' ? 'bg-teal-900/60 text-teal-300' :
                        'bg-slate-800 text-slate-300'
                      }`}>
                        {currentStatus}
                      </span>
                    </td>
                    <td className="space-x-2">
                      {/* Supplier actions */}
                      {user.role === 'supplier' && currentStatus === 'placed' && (
                        <>
                          <button onClick={() => updateStatus(o.id, 'accepted')} className="btn-secondary !py-1 !px-2 text-xs" disabled={busy}>Accept</button>
                          <button onClick={() => updateStatus(o.id, 'rejected')} className="btn-secondary !border-red-700 !text-red-300 !py-1 !px-2 text-xs" disabled={busy}>Reject</button>
                        </>
                      )}
                      {user.role === 'supplier' && currentStatus === 'accepted' && (
                        <button onClick={() => updateStatus(o.id, 'in-transit')} className="btn-secondary !py-1 !px-2 text-xs" disabled={busy}>Ship (In-transit)</button>
                      )}
                      {user.role === 'supplier' && currentStatus === 'in-transit' && (
                        <button onClick={() => updateStatus(o.id, 'delivered')} className="btn-secondary !py-1 !px-2 text-xs" disabled={busy}>Delivered</button>
                      )}

                      {/* Contractor actions */}
                      {user.role !== 'supplier' && currentStatus !== 'delivered' && currentStatus !== 'cancelled' && (
                        <button onClick={() => { setSelectedOrder(o); setOutcomePrice(String(total)) }} className="btn-secondary !py-1 !px-2 text-xs" disabled={busy}>
                          Record delivery
                        </button>
                      )}
                      {user.role !== 'supplier' && currentStatus === 'delivered' && (
                        <button onClick={() => setReviewOrder(o)} className="btn-secondary !py-1 !px-2 text-xs" disabled={busy}>
                          Leave review
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Record Delivery Outcome Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="card w-full max-w-lg space-y-4">
            <h2 className="text-lg font-bold text-white">Record delivery outcome · PO-{String(selectedOrder.id).padStart(5, '0')}</h2>
            <p className="text-xs text-slate-400">Record actual fulfillment details. These verified outcomes are separated from prediction-time features.</p>
            <form onSubmit={submitOutcome} className="space-y-4">
              <label className="flex items-center gap-2 text-sm text-amber-300">
                <input type="checkbox" checked={outcomeCancelled} onChange={(e) => setOutcomeCancelled(e.target.checked)} className="rounded" />
                Order was cancelled or rejected
              </label>

              {!outcomeCancelled && (
                <>
                  <label className="block text-sm">Actual delivery date
                    <input type="date" required value={outcomeDate} onChange={(e) => setOutcomeDate(e.target.value)} max={new Date().toISOString().slice(0, 10)} className="form-control mt-1" />
                  </label>
                  <label className="block text-sm">Final paid price (total ₹)
                    <input type="number" step="any" min="0" value={outcomePrice} onChange={(e) => setOutcomePrice(e.target.value)} className="form-control mt-1" />
                  </label>
                </>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setSelectedOrder(null)} className="btn-secondary" disabled={busy}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Recording…' : 'Save outcome'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Supplier Review Modal */}
      {reviewOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="card w-full max-w-lg space-y-4">
            <h2 className="text-lg font-bold text-white">Review supplier · PO-{String(reviewOrder.id).padStart(5, '0')}</h2>
            <p className="text-xs text-slate-400">Share your fulfillment experience with this supplier. Only contractors with completed transactions can post reviews.</p>
            <form onSubmit={submitReview} className="space-y-4">
              <label className="block text-sm">Star rating (1 to 5)
                <select value={rating} onChange={(e) => setRating(Number(e.target.value))} className="form-control mt-1">
                  <option value={5}>5 ★ - Outstanding delivery & quality</option>
                  <option value={4}>4 ★ - Good service, minor delay</option>
                  <option value={3}>3 ★ - Acceptable, notable lead time delay</option>
                  <option value={2}>2 ★ - Disappointing fulfillment</option>
                  <option value={1}>1 ★ - Severe delay / partial shortage</option>
                </select>
              </label>
              <label className="block text-sm">Review notes
                <textarea required rows={4} maxLength={1000} value={reviewText} onChange={(e) => setReviewText(e.target.value)} placeholder="Describe communication, material condition, packaging, and offloading punctuality..." className="form-control mt-1" />
              </label>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setReviewOrder(null)} className="btn-secondary" disabled={busy}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit review'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
