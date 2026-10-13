import { beginApiAttempt,beginApiObservation,finishApiAttempt,finishApiObservation,markApi401,type ApiAttemptObservation,type ApiObservation } from '../monitoring/performanceMonitor'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '')
let accessToken: string | null = null
let refreshPromise: Promise<string | null> | null = null
let authExpiredHandler: (() => void) | null = null

function safeBeginObservation(path:string,method:string,resourcePath:string,parentObservationId?:string){try{return beginApiObservation(path,method,resourcePath,parentObservationId)}catch{return null}}
function safeBeginAttempt(observation:ApiObservation|null,resourcePath:string,retry=false){if(!observation)return null;try{return beginApiAttempt(observation,resourcePath,retry)}catch{return null}}
function safeFinishAttempt(observation:ApiObservation|null,attempt:ApiAttemptObservation|null,values:{status?:number;error?:boolean;requestId?:string|null}){if(!observation||!attempt)return;try{finishApiAttempt(observation,attempt,values)}catch{/* Monitoring never changes API outcomes. */}}
function safeFinishObservation(observation:ApiObservation|null,values:{status?:number;error?:boolean;requestId?:string|null}){if(!observation)return;try{finishApiObservation(observation,values)}catch{/* Monitoring never changes API outcomes. */}}
function safeMark401(observation:ApiObservation|null){if(!observation)return;try{markApi401(observation)}catch{/* Monitoring never changes retry behavior. */}}
function safeRequestId(response:Response|undefined){try{return response?.headers.get('X-Request-Id')??null}catch{return null}}

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function setAuthExpiredHandler(handler: (() => void) | null) {
  authExpiredHandler = handler
}

async function refreshAccessToken(parentObservationId?:string): Promise<string | null> {
  if (refreshPromise) return refreshPromise
  const resourcePath=`${apiBaseUrl}/auth/refresh`
  const observation=safeBeginObservation('/auth/refresh','POST',resourcePath,parentObservationId)
  const attempt=safeBeginAttempt(observation,resourcePath)
  refreshPromise = fetch(`${apiBaseUrl}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
    .then(async (response) => {
      safeFinishAttempt(observation,attempt,{status:response.status,requestId:safeRequestId(response)})
      if (!response.ok){safeFinishObservation(observation,{status:response.status,error:true,requestId:safeRequestId(response)});return null}
      const payload = await response.json() as { access_token: string }
      setAccessToken(payload.access_token)
      safeFinishObservation(observation,{status:response.status,requestId:safeRequestId(response)})
      return payload.access_token
    })
    .catch(() => {safeFinishAttempt(observation,attempt,{error:true});safeFinishObservation(observation,{error:true});return null})
    .finally(() => { refreshPromise = null })
  return refreshPromise
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const resourcePath=`${apiBaseUrl}${path}`
  const observation=safeBeginObservation(path,init?.method??'GET',resourcePath)
  let attempt=safeBeginAttempt(observation,resourcePath)
  let response:Response|undefined
  let finished=false
  const finish=(error=false)=>{if(finished)return;finished=true;safeFinishObservation(observation,{status:response?.status,error,requestId:safeRequestId(response)})}
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  try{
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      credentials: 'include',
      headers,
    })
    safeFinishAttempt(observation,attempt,{status:response.status,requestId:safeRequestId(response)})

    if (response.status === 401 && accessToken && !path.startsWith('/auth/')) {
      safeMark401(observation)
      const refreshedToken = await refreshAccessToken(observation?.id)
      if (refreshedToken) {
        headers.set('Authorization', `Bearer ${refreshedToken}`)
        attempt=safeBeginAttempt(observation,resourcePath,true)
        response = await fetch(`${apiBaseUrl}${path}`, { ...init, credentials: 'include', headers })
        safeFinishAttempt(observation,attempt,{status:response.status,requestId:safeRequestId(response)})
      } else {
        setAccessToken(null)
        authExpiredHandler?.()
      }
    }

    if (!response.ok) {
      let message = '系統暫時無法完成要求，請稍後再試。'
      let detail: unknown = null
      try {
        const payload = await response.json() as { detail?: unknown }
        detail = payload.detail ?? null
        if (typeof detail === 'string' && response.status < 500) message = detail
      } catch {
        // Never expose reverse-proxy HTML or a server traceback to the UI.
      }
      throw new ApiError(response.status, message, detail)
    }

    if (response.status === 204){finish();return undefined as T}
    const result=await response.json() as T
    finish();return result
  }catch(error){safeFinishAttempt(observation,attempt,{error:true});finish(true);throw error}
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly detail: unknown = null) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiDownload(path: string, init?: RequestInit): Promise<void> {
  const resourcePath=`${apiBaseUrl}${path}`
  const observation=safeBeginObservation(path,init?.method??'GET',resourcePath);let response:Response|undefined;let finished=false
  let attempt=safeBeginAttempt(observation,resourcePath)
  const finish=(error=false)=>{if(finished)return;finished=true;safeFinishObservation(observation,{status:response?.status,error,requestId:safeRequestId(response)})}
  const headers = new Headers(init?.headers)
  if (init?.body) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  try{
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, credentials: 'include', headers })
    safeFinishAttempt(observation,attempt,{status:response.status,requestId:safeRequestId(response)})
    if (response.status === 401 && accessToken) {
      safeMark401(observation)
      const refreshedToken = await refreshAccessToken(observation?.id)
      if (refreshedToken) {
        headers.set('Authorization', `Bearer ${refreshedToken}`)
        attempt=safeBeginAttempt(observation,resourcePath,true)
        response = await fetch(`${apiBaseUrl}${path}`, { ...init, credentials: 'include', headers })
        safeFinishAttempt(observation,attempt,{status:response.status,requestId:safeRequestId(response)})
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
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.style.display = 'none'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    // Let the browser consume the object URL before releasing it. Immediate
    // revocation can cancel the download or turn it into a page navigation.
    window.setTimeout(() => URL.revokeObjectURL(url), 0);finish()
  }catch(error){safeFinishAttempt(observation,attempt,{error:true});finish(true);throw error}
}

export async function apiBlobUrl(path:string):Promise<string>{
  const resourcePath=`${apiBaseUrl}${path}`
  const observation=safeBeginObservation(path,'GET',resourcePath);let response:Response|undefined;let finished=false
  let attempt=safeBeginAttempt(observation,resourcePath)
  const finish=(error=false)=>{if(finished)return;finished=true;safeFinishObservation(observation,{status:response?.status,error,requestId:safeRequestId(response)})}
  const headers=new Headers({Accept:'image/*'})
  if(accessToken)headers.set('Authorization',`Bearer ${accessToken}`)
  try{
    response=await fetch(`${apiBaseUrl}${path}`,{credentials:'include',headers})
    safeFinishAttempt(observation,attempt,{status:response.status,requestId:safeRequestId(response)})
    if(response.status===401&&accessToken){safeMark401(observation);const refreshed=await refreshAccessToken(observation?.id);if(refreshed){headers.set('Authorization',`Bearer ${refreshed}`);attempt=safeBeginAttempt(observation,resourcePath,true);response=await fetch(`${apiBaseUrl}${path}`,{credentials:'include',headers});safeFinishAttempt(observation,attempt,{status:response.status,requestId:safeRequestId(response)})}else{setAccessToken(null);authExpiredHandler?.()}}
    if(!response.ok)throw new Error('Image download failed')
    const url=URL.createObjectURL(await response.blob());finish();return url
  }catch(error){safeFinishAttempt(observation,attempt,{error:true});finish(true);throw error}
}
