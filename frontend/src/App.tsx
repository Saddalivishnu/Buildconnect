import { createContext, FormEvent, useContext, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ApiUser, api } from './api'

interface AuthContextValue {
  user: ApiUser
  csrfToken: string
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within the authenticated application.')
  return value
}

function AuthenticationPanel({ onAuthenticated }: { onAuthenticated: (user: ApiUser, token: string) => void }) {
  const [mode, setMode] = useState<'login' | 'register' | 'forgot' | 'reset'>('login')
  const [role, setRole] = useState<'contractor' | 'supplier'>('contractor')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [resetToken, setResetToken] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    const form = new FormData(event.currentTarget)

    if (mode === 'forgot') {
      try {
        const response = await api<{ message: string; dev_reset_token?: string }>(
          '/api/auth/forgot-password',
          { method: 'POST', body: JSON.stringify({ email: form.get('email') }) },
        )
        setMessage(response.message || 'If that email exists, password reset instructions have been issued.')
        if (response.dev_reset_token) {
          setResetToken(response.dev_reset_token)
          setMode('reset')
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Password reset request failed.')
      } finally {
        setBusy(false)
      }
      return
    }

    if (mode === 'reset') {
      try {
        const response = await api<{ message: string }>(
          '/api/auth/reset-password',
          {
            method: 'POST',
            body: JSON.stringify({
              token: form.get('token') || resetToken,
              new_password: form.get('new_password'),
            }),
          },
        )
        setMessage(response.message || 'Password successfully updated. You may now sign in.')
        setMode('login')
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Password reset failed.')
      } finally {
        setBusy(false)
      }
      return
    }

    const body: Record<string, unknown> = {
      email: form.get('email'),
      password: form.get('password'),
    }
    if (mode === 'register') {
      body.name = form.get('name')
      body.role = role
      if (role === 'supplier') {
        body.supplier_profile = { category: form.get('category'), city: form.get('city') }
      }
    }
    try {
      const response = await api<{ user: ApiUser; csrf_token: string }>(
        mode === 'login' ? '/api/auth/login' : '/api/auth/register',
        { method: 'POST', body: JSON.stringify(body) },
      )
      onAuthenticated(response.user, response.csrf_token)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Authentication failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-screen">
      <div className="auth-layout">
        <aside className="auth-aside">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden="true">B</span>
            <span><span className="brand-name">BuildConnect AI</span><span className="brand-caption">Procurement intelligence</span></span>
          </div>
          <div className="auth-aside-content">
            <p className="auth-eyebrow">Built for better buying</p>
            <h2>From material signals to confident decisions.</h2>
            <p className="auth-aside-copy">Bring your real project requirements and supplier quotations into one clear procurement workspace.</p>
            <ul className="auth-feature-list">
              <li><span className="auth-feature-dot" />Real WPI history & Conformal intervals</li>
              <li><span className="auth-feature-dot" />Supplier ratings & Provenance verification</li>
              <li><span className="auth-feature-dot" />Purchase order lifecycle & Delivery tracking</li>
              <li><span className="auth-feature-dot" />Scenario simulation & Pareto strategy comparison</li>
            </ul>
          </div>
          <p className="auth-aside-footer">Research-oriented decision support · Strict data provenance</p>
        </aside>
        <section className="auth-form-wrap">
          <form className="auth-form" onSubmit={submit}>
            <p className="auth-eyebrow">
              {mode === 'login' ? 'Welcome back' : mode === 'register' ? 'Get started' : mode === 'forgot' ? 'Account Recovery' : 'Set New Password'}
            </p>
            <h1>
              {mode === 'login'
                ? 'Sign in to your workspace'
                : mode === 'register'
                ? 'Create your account'
                : mode === 'forgot'
                ? 'Reset your password'
                : 'Enter new password'}
            </h1>
            <p className="auth-form-intro">
              {mode === 'forgot'
                ? 'Enter your registered email address to receive password reset instructions.'
                : mode === 'reset'
                ? 'Enter the security token and your new strong password.'
                : 'Use your own account and entered business data. Passwords must be at least 12 characters.'}
            </p>
            <div className="auth-form-fields">
              {mode === 'register' && (
                <>
                  <label>Name<input required name="name" maxLength={120} autoComplete="name" className="form-control" placeholder="Your name or business" /></label>
                  <label>Account type
                    <select value={role} onChange={(event) => setRole(event.target.value as 'contractor' | 'supplier')} className="form-control">
                      <option value="contractor">Contractor / project manager</option>
                      <option value="supplier">Supplier / material shop</option>
                    </select>
                  </label>
                  {role === 'supplier' && (
                    <div className="grid grid-cols-2 gap-3">
                      <label>Material category<input required name="category" maxLength={120} className="form-control" placeholder="e.g. Cement" /></label>
                      <label>City<input required name="city" maxLength={120} className="form-control" placeholder="Your city" /></label>
                    </div>
                  )}
                </>
              )}

              {mode === 'forgot' && (
                <label>Registered email<input required name="email" type="email" autoComplete="email" className="form-control" placeholder="you@company.com" /></label>
              )}

              {mode === 'reset' && (
                <>
                  <label>Reset token<input required name="token" defaultValue={resetToken} className="form-control font-mono text-sm" placeholder="Paste reset token" /></label>
                  <label>New password<input required name="new_password" type="password" minLength={12} className="form-control" placeholder="At least 12 characters" /></label>
                </>
              )}

              {(mode === 'login' || mode === 'register') && (
                <>
                  <label>Email address<input required name="email" type="email" autoComplete="email" className="form-control" placeholder="you@company.com" /></label>
                  <label>Password<input required name="password" type="password" minLength={12} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} className="form-control" placeholder={mode === 'login' ? 'Enter your password' : 'At least 12 characters'} />
                    {mode === 'register' && <span className="mt-1.5 block text-xs font-normal text-slate-400">Choose at least 12 characters.</span>}
                  </label>
                </>
              )}
            </div>

            {error && <p role="alert" className="mt-4 rounded-xl border border-red-700 bg-red-950/50 p-3 text-sm text-red-200">{error}</p>}
            {message && <p role="status" className="mt-4 rounded-xl border border-emerald-700 bg-emerald-950/50 p-3 text-sm text-emerald-200">{message}</p>}

            <button className="btn-primary mt-5 w-full" disabled={busy}>
              {busy
                ? 'Please wait…'
                : mode === 'login'
                ? 'Sign in securely'
                : mode === 'register'
                ? 'Create account'
                : mode === 'forgot'
                ? 'Send reset link'
                : 'Update password'}
            </button>

            <div className="mt-4 flex flex-col gap-2 text-center text-xs">
              {mode === 'login' && (
                <>
                  <button type="button" className="text-amber-400 hover:underline" onClick={() => { setMode('forgot'); setError(''); setMessage('') }}>
                    Forgot your password?
                  </button>
                  <button type="button" className="auth-switch" onClick={() => { setMode('register'); setError(''); setMessage('') }}>
                    New to BuildConnect? Create an account
                  </button>
                </>
              )}
              {mode === 'register' && (
                <button type="button" className="auth-switch" onClick={() => { setMode('login'); setError(''); setMessage('') }}>
                  Already have an account? Sign in
                </button>
              )}
              {(mode === 'forgot' || mode === 'reset') && (
                <button type="button" className="auth-switch" onClick={() => { setMode('login'); setError(''); setMessage('') }}>
                  Back to Sign in
                </button>
              )}
            </div>
          </form>
        </section>
      </div>
    </main>
  )
}

export function App() {
  const [user, setUser] = useState<ApiUser | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [authLoading, setAuthLoading] = useState(true)
  const navigate = useNavigate()
  const location = useLocation()

  async function refreshUser() {
    try {
      const response = await api<{ user: ApiUser; csrf_token: string }>('/api/auth/me')
      setUser(response.user)
      setCsrfToken(response.csrf_token)
    } catch {
      setUser(null)
      setCsrfToken('')
    }
  }

  useEffect(() => {
    refreshUser().finally(() => setAuthLoading(false))
  }, [])

  if (authLoading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-300" role="status">Checking your session…</div>
  }
  if (!user) {
    return <AuthenticationPanel onAuthenticated={(nextUser, token) => { setUser(nextUser); setCsrfToken(token) }} />
  }

  async function logout() {
    try {
      await api('/api/auth/logout', { method: 'POST' }, csrfToken)
      setUser(null)
      setCsrfToken('')
      navigate('/')
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  return (
    <AuthContext.Provider value={{ user, csrfToken, refreshUser }}>
      <div className="app-background">
        <header className="app-header">
          <div className="app-header-inner">
            <Link to="/" className="brand-lockup" aria-label="BuildConnect AI dashboard">
              <span className="brand-mark" aria-hidden="true">B</span>
              <span><span className="brand-name">BuildConnect AI</span><span className="brand-caption">Procurement intelligence</span></span>
            </Link>
            <nav aria-label="Main navigation" className="app-nav">
              <NavLink end className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/">Overview</NavLink>
              {user.role !== 'supplier' && <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/projects">Projects</NavLink>}
              <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/suppliers">Suppliers</NavLink>
              <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/orders">Orders</NavLink>
              <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/forecast">Price intelligence</NavLink>
              {user.role !== 'supplier' && <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/procurement">Procurement</NavLink>}
              <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/scenarios">Scenarios</NavLink>
              <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/research">Research</NavLink>
              <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/import">Data Import</NavLink>
              <NavLink className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to="/reports">Reports</NavLink>
            </nav>
            <div className="flex items-center gap-3">
              <Link to="/profile" className="account-chip hover:border-amber-500/50 transition-colors" title="Manage Profile & Security">
                <span className="account-avatar" aria-hidden="true">{user.name.trim().charAt(0).toUpperCase()}</span>
                <span className="account-details">{user.name}<span className="account-role">{user.role}</span></span>
              </Link>
              <button onClick={logout} className="btn-secondary !min-h-0 !rounded-full !px-3 !py-2 text-xs">Sign out</button>
            </div>
          </div>
        </header>
        <main className="app-content">
          <div key={location.pathname} className="route-enter">
            <Outlet />
          </div>
        </main>
      </div>
    </AuthContext.Provider>
  )
}
