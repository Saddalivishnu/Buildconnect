import { FormEvent, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../App'

interface UserProfile {
  id: number
  name: string
  full_name: string | null
  email: string
  phone_number: string | null
  role: string
  account_status: string
  created_at: string | null
  last_login_at: string | null
}

interface SupplierProfile {
  id: number
  name: string
  business_name: string | null
  business_description: string | null
  category: string
  contact_person: string | null
  phone: string | null
  email: string | null
  address: string | null
  city: string
  state: string | null
  postal_code: string | null
  latitude: number | null
  longitude: number | null
  verified: number
  verification_status: string
  rating: number
  review_count: number
}

export function ProfilePage() {
  const { user, csrfToken, refreshUser } = useAuth()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [supplierProfile, setSupplierProfile] = useState<SupplierProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  // Password change state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [passwordMessage, setPasswordMessage] = useState('')
  const [passwordBusy, setPasswordBusy] = useState(false)

  async function loadProfile() {
    try {
      const data = await api<{ user: UserProfile; supplier_profile: SupplierProfile | null }>('/api/auth/profile')
      setProfile(data.user)
      setSupplierProfile(data.supplier_profile)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load profile.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadProfile()
  }, [])

  async function updateProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    const form = new FormData(event.currentTarget)
    const body: Record<string, unknown> = {
      full_name: form.get('full_name'),
      phone_number: form.get('phone_number'),
    }
    if (user.role === 'supplier') {
      body.supplier_profile = {
        business_name: form.get('business_name'),
        business_description: form.get('business_description'),
        category: form.get('category'),
        contact_person: form.get('contact_person'),
        phone: form.get('phone'),
        email: form.get('email'),
        address: form.get('address'),
        city: form.get('city'),
        state: form.get('state'),
        postal_code: form.get('postal_code'),
        latitude: form.get('latitude') ? Number(form.get('latitude')) : null,
        longitude: form.get('longitude') ? Number(form.get('longitude')) : null,
      }
    }
    try {
      await api('/api/auth/profile', { method: 'PUT', body: JSON.stringify(body) }, csrfToken)
      setMessage('Profile updated successfully.')
      await refreshUser()
      await loadProfile()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to update profile.')
    } finally {
      setBusy(false)
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPasswordBusy(true)
    setPasswordError('')
    setPasswordMessage('')

    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match.')
      setPasswordBusy(false)
      return
    }
    if (newPassword.length < 12) {
      setPasswordError('New password must be at least 12 characters.')
      setPasswordBusy(false)
      return
    }

    try {
      await api('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      }, csrfToken)
      setPasswordMessage('Password changed successfully.')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (cause) {
      setPasswordError(cause instanceof ApiError ? cause.message : 'Unable to change password.')
    } finally {
      setPasswordBusy(false)
    }
  }

  if (loading) {
    return <div className="p-8 text-slate-300">Loading user profile…</div>
  }

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <h1 className="text-2xl font-bold">User profile & settings</h1>
        <p className="mt-1 text-sm text-slate-400">Manage your business information, contact details, and security credentials.</p>
      </div>

      {error && <p role="alert" className="rounded-xl border border-red-700 bg-red-950/40 p-4 text-red-200">{error}</p>}
      {message && <p role="status" className="rounded-xl border border-emerald-700 bg-emerald-950/40 p-4 text-emerald-200">{message}</p>}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Account Summary */}
        <section className="card space-y-4">
          <div className="flex items-center gap-4">
            <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-teal-600/20 text-2xl font-bold text-teal-400">
              {user.name.charAt(0).toUpperCase()}
            </span>
            <div>
              <h2 className="text-lg font-semibold text-white">{profile?.full_name || profile?.name}</h2>
              <p className="text-xs text-slate-400">{profile?.email}</p>
              <span className="mt-1 inline-block rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-medium text-teal-300 capitalize">
                {profile?.role}
              </span>
            </div>
          </div>
          <div className="border-t border-slate-700 pt-3 text-xs text-slate-400 space-y-1">
            <p><strong>Status:</strong> <span className="capitalize">{profile?.account_status}</span></p>
            <p><strong>Account ID:</strong> #{profile?.id}</p>
            {profile?.created_at && <p><strong>Member since:</strong> {profile.created_at.slice(0, 10)}</p>}
            {profile?.last_login_at && <p><strong>Last activity:</strong> {profile.last_login_at.slice(0, 19).replace('T', ' ')}</p>}
          </div>
        </section>

        {/* Profile Edit Form */}
        <section className="card lg:col-span-2 space-y-4">
          <h2 className="text-lg font-semibold text-white">General information</h2>
          <form onSubmit={updateProfile} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm">Full name
                <input required name="full_name" defaultValue={profile?.full_name || profile?.name} maxLength={120} className="form-control mt-1" />
              </label>
              <label className="text-sm">Phone number
                <input name="phone_number" defaultValue={profile?.phone_number || ''} maxLength={30} placeholder="+91 98765 43210" className="form-control mt-1" />
              </label>
            </div>

            {user.role === 'supplier' && (
              <div className="space-y-4 border-t border-slate-700/80 pt-4">
                <h3 className="text-sm font-semibold text-teal-300">Supplier enterprise details</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="text-sm">Business / brand name
                    <input name="business_name" defaultValue={supplierProfile?.business_name || supplierProfile?.name || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">Material category
                    <input required name="category" defaultValue={supplierProfile?.category || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">Contact person
                    <input name="contact_person" defaultValue={supplierProfile?.contact_person || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">Public email
                    <input name="email" type="email" defaultValue={supplierProfile?.email || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">Street address
                    <input name="address" defaultValue={supplierProfile?.address || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">City
                    <input required name="city" defaultValue={supplierProfile?.city || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">State
                    <input name="state" defaultValue={supplierProfile?.state || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">Postal code
                    <input name="postal_code" defaultValue={supplierProfile?.postal_code || ''} className="form-control mt-1" />
                  </label>
                  <label className="text-sm">Latitude (optional map marker)
                    <input name="latitude" type="number" step="any" defaultValue={supplierProfile?.latitude ?? ''} className="form-control mt-1" placeholder="e.g. 17.3850" />
                  </label>
                  <label className="text-sm">Longitude (optional map marker)
                    <input name="longitude" type="number" step="any" defaultValue={supplierProfile?.longitude ?? ''} className="form-control mt-1" placeholder="e.g. 78.4867" />
                  </label>
                </div>
                <label className="text-sm block">Business description
                  <textarea name="business_description" defaultValue={supplierProfile?.business_description || ''} rows={3} className="form-control mt-1" placeholder="Describe materials offered, delivery radius, warehouse locations..." />
                </label>
              </div>
            )}

            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Saving changes…' : 'Save profile changes'}
            </button>
          </form>
        </section>

        {/* Password Security Form */}
        <section className="card lg:col-span-3 space-y-4">
          <h2 className="text-lg font-semibold text-white">Security & password</h2>
          <p className="text-xs text-slate-400">Choose a strong passphrase with at least 12 characters. Never share your password.</p>
          {passwordError && <p role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-sm text-red-200">{passwordError}</p>}
          {passwordMessage && <p role="status" className="rounded border border-emerald-700 bg-emerald-950/40 p-3 text-sm text-emerald-200">{passwordMessage}</p>}
          <form onSubmit={changePassword} className="grid gap-4 sm:grid-cols-3">
            <label className="text-sm">Current password
              <input required type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} className="form-control mt-1" />
            </label>
            <label className="text-sm">New password (min 12 chars)
              <input required type="password" minLength={12} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="form-control mt-1" />
            </label>
            <label className="text-sm">Confirm new password
              <input required type="password" minLength={12} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="form-control mt-1" />
            </label>
            <div className="sm:col-span-3">
              <button type="submit" className="btn-secondary" disabled={passwordBusy}>
                {passwordBusy ? 'Updating password…' : 'Update password'}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
