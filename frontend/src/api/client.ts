const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
let accessToken: string | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  if (init?.body) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function apiDownload(path: string, init?: RequestInit): Promise<void> {
  const headers = new Headers(init?.headers)
  if (init?.body) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(`${apiBaseUrl}${path}`, { ...init, credentials: 'include', headers })
  if (!response.ok) throw new Error(`Download failed with status ${response.status}`)
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const fallback = disposition.match(/filename="([^"]+)"/i)?.[1]
  const filename = encoded ? decodeURIComponent(encoded) : fallback ?? 'export'
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click()
  URL.revokeObjectURL(url)
}
