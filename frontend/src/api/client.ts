const TOKEN_KEY = 'sboard.admin_token'

export class ApiError extends Error {
  status: number
  details: unknown

  constructor(status: number, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

export function getAdminToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setAdminToken(token: string): void {
  const normalized = token.trim()
  if (normalized) {
    window.localStorage.setItem(TOKEN_KEY, normalized)
  } else {
    window.localStorage.removeItem(TOKEN_KEY)
  }
  window.dispatchEvent(new CustomEvent('sboard-token-change'))
}

function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return fallback
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAdminToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    let body: unknown
    try {
      body = await response.json()
    } catch {
      body = null
    }
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent('sboard-auth-invalid'))
    }
    throw new ApiError(response.status, errorMessage(body, `请求失败（${response.status}）`), body)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function withQuery(path: string, values: Record<string, unknown>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  }
  const suffix = query.toString()
  return suffix ? `${path}?${suffix}` : path
}

