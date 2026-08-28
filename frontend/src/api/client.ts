const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '')
let accessToken: string | null = null
let refreshPromise: Promise<string | null> | null = null
let authExpiredHandler: (() => void) | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function setAuthExpiredHandler(handler: (() => void) | null) {
  authExpiredHandler = handler
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise
  refreshPromise = fetch(`${apiBaseUrl}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
    .then(async (response) => {
      if (!response.ok) return null
      const payload = await response.json() as { access_token: string }
      setAccessToken(payload.access_token)
      return payload.access_token
    })
    .catch(() => null)
    .finally(() => { refreshPromise = null })
  return refreshPromise
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  if (init?.body) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  let response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })

  if (response.status === 401 && accessToken && !path.startsWith('/auth/')) {
    const refreshedToken = await refreshAccessToken()
    if (refreshedToken) {
      headers.set('Authorization', `Bearer ${refreshedToken}`)
      response = await fetch(`${apiBaseUrl}${path}`, { ...init, credentials: 'include', headers })
    } else {
      setAccessToken(null)
      authExpiredHandler?.()
    }
  }

  if (!response.ok) {
    let detail = '系統暫時無法完成要求，請稍後再試。'
    try {
      const payload = await response.json() as { detail?: string }
      if (typeof payload.detail === 'string' && response.status < 500) detail = payload.detail
    } catch {
      // Never expose reverse-proxy HTML or a server traceback to the UI.
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiDownload(path: string, init?: RequestInit): Promise<void> {
  const headers = new Headers(init?.headers)
  if (init?.body) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  let response = await fetch(`${apiBaseUrl}${path}`, { ...init, credentials: 'include', headers })
  if (response.status === 401 && accessToken) {
    const refreshedToken = await refreshAccessToken()
    if (refreshedToken) {
      headers.set('Authorization', `Bearer ${refreshedToken}`)
      response = await fetch(`${apiBaseUrl}${path}`, { ...init, credentials: 'include', headers })
    } else {
      setAccessToken(null)
      authExpiredHandler?.()
    }
  }
  if (!response.ok) throw new Error(`Download failed with status ${response.status}`)
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const fallback = disposition.match(/filename="([^"]+)"/i)?.[1]
  const filename = encoded ? decodeURIComponent(encoded) : fallback ?? 'export'
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click()
  URL.revokeObjectURL(url)
}
