import { Link } from 'react-router-dom'

export function AccessDeniedPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="card max-w-md p-8 space-y-4">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-red-950/60 text-2xl text-red-400">
          ✕
        </div>
        <h1 className="text-xl font-bold text-white">Access Denied (403)</h1>
        <p className="text-sm text-slate-400">
          Your account role does not have authorization to view or perform operations on this resource.
        </p>
        <div className="pt-2">
          <Link to="/" className="btn-primary inline-block">Return to overview</Link>
        </div>
      </div>
    </div>
  )
}
