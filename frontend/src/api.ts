export interface ApiUser {
  id: number
  name: string
  email: string
  role: 'contractor' | 'supplier' | 'administrator'
  demo: number
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  csrfToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (csrfToken) headers.set('X-CSRF-Token', csrfToken)

  let response: Response
  try {
    response = await fetch(path, { ...options, headers, credentials: 'include' })
  } catch (error) {
    console.error('API request failed:', error)
    throw new ApiError('The BuildConnect API is unavailable. Check that the backend is running.', 0)
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()
  if (!response.ok) {
    const message = typeof payload === 'object' && payload !== null && 'error' in payload
      ? String(payload.error)
      : `Request failed (${response.status}).`
    throw new ApiError(message, response.status)
  }
  return payload as T
}
