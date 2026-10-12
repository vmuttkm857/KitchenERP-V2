export type DiagnosticEventKind='api'|'page'|'auth_refresh'|'api_401'|'error'|'detail'

export interface ResourceTimingSummary{
  dns_ms:number|null
  tcp_ms:number|null
  tls_ms:number|null
  request_to_first_byte_ms:number|null
  response_download_ms:number|null
  total_ms:number|null
}

export interface DiagnosticEvent{
  id:string
  kind:DiagnosticEventKind
  occurred_at:string
  name:string
  duration_ms:number|null
  status:number|null
  method?:string
  page?:string
  request_id?:string
  slow?:boolean
  error?:boolean
  resource_timing?:ResourceTimingSummary
  detail?:string
}

export interface ApiObservation{
  id:string
  name:string
  method:string
  page?:string
  started:number
  url:string
  pendingTimer:number|null
  pendingRecorded:boolean
  completed:boolean
}

interface PageObservation{
  id:string
  name:string
  started:number
  mounted:boolean
  pending:number
  settleTimer:number|null
  watchdogTimer:number|null
  pendingRecorded:boolean
}

const MEMORY_LIMIT=500
const ANOMALY_LIMIT=20
const PRE_AUTH_LIMIT=50
const MAX_WATCHDOG_TIMERS=100
const API_SLOW_MS=2000
const PAGE_SLOW_MS=3000
const PENDING_WARNING_MS=3000
const anomalyStorageKey='kitchenerp.performance.anomalies.v1'
const detailStorageKey='kitchenerp.performance.detailed.v1'
const idPattern=/^[A-Za-z0-9._:-]{1,128}$/
const listeners=new Set<()=>void>()
const watchdogTimers=new Set<number>()
let events:DiagnosticEvent[]=[]
let anomalies:DiagnosticEvent[]=readAnomalies()
let preAuthDetails:DiagnosticEvent[]=[]
let adminAllowed:boolean|null=null
let detailedPreference=readDetailPreference()
let activePage:PageObservation|null=null
let currentPageName:string|undefined
let sequence=0
let globalErrorHandlersInstalled=false

function safeRun(action:()=>void){try{action()}catch{/* Monitoring must never interrupt application work. */}}
function safeValue<T>(fallback:T,action:()=>T){try{return action()}catch{return fallback}}
function now(){return safeValue(0,()=>typeof performance!=='undefined'?performance.now():Date.now())}
function eventId(){return safeValue('diagnostic-event',()=>{sequence=(sequence+1)%1_000_000;return `${Date.now().toString(36)}-${sequence.toString(36)}`})}
function notify(){for(const listener of [...listeners])safeRun(listener)}
function safeLocalGet(key:string){return safeValue<string|null>(null,()=>localStorage.getItem(key))}
function safeLocalSet(key:string,value:string){safeRun(()=>localStorage.setItem(key,value))}
function safeLocalRemove(key:string){safeRun(()=>localStorage.removeItem(key))}
function readDetailPreference(){return safeLocalGet(detailStorageKey)==='true'}
function readAnomalies():DiagnosticEvent[]{
  return safeValue<DiagnosticEvent[]>([],()=>{
    const value=JSON.parse(safeLocalGet(anomalyStorageKey)??'[]')
    if(!Array.isArray(value))return []
    return value.filter(item=>item&&typeof item==='object'&&typeof item.id==='string').slice(-ANOMALY_LIMIT) as DiagnosticEvent[]
  })
}
function round(value:number){return Math.round(value*10)/10}
function phase(start:number,end:number){return start>0&&end>start?round(end-start):null}
function currentPage(){return currentPageName}
function detailed(){return adminAllowed===true&&detailedPreference}
function preAuthDetailed(){return adminAllowed===null&&detailedPreference}
function persistAnomalies(){safeRun(()=>safeLocalSet(anomalyStorageKey,JSON.stringify(anomalies.slice(-ANOMALY_LIMIT))))}
function upsert(list:DiagnosticEvent[],event:DiagnosticEvent,limit:number){
  const existing=list.findIndex(item=>item.id===event.id)
  if(existing>=0)list[existing]=event
  else list.push(event)
  if(list.length>limit)list.splice(0,list.length-limit)
}
function append(event:DiagnosticEvent,anomaly=false){
  safeRun(()=>{
    upsert(events,event,MEMORY_LIMIT)
    if(anomaly){upsert(anomalies,event,ANOMALY_LIMIT);persistAnomalies()}
    notify()
  })
}
function appendDetailed(event:DiagnosticEvent){
  if(detailed())append(event)
  else if(preAuthDetailed())safeRun(()=>upsert(preAuthDetails,event,PRE_AUTH_LIMIT))
}
function makeEvent(kind:DiagnosticEventKind,name:string,values:Partial<DiagnosticEvent>={}):DiagnosticEvent{
  return {id:eventId(),kind,occurred_at:safeValue('',()=>new Date().toISOString()),name,duration_ms:null,status:null,...values}
}
function scheduleWatchdog(action:()=>void){
  if(watchdogTimers.size>=MAX_WATCHDOG_TIMERS)return null
  return safeValue<number|null>(null,()=>{
    const timer=window.setTimeout(()=>{watchdogTimers.delete(timer);safeRun(action)},PENDING_WARNING_MS)
    watchdogTimers.add(timer)
    return timer
  })
}
function clearWatchdog(timer:number|null){
  if(timer===null)return
  watchdogTimers.delete(timer)
  safeRun(()=>window.clearTimeout(timer))
}

export function sanitizeApiPath(input:string){
  return safeValue('/',()=>{
    let path=input.split(/[?#]/,1)[0]||'/'
    try{path=decodeURI(path)}catch{/* Keep the undecoded path. */}
    return path.split('/').map(segment=>{
      if(!segment)return segment
      if(/^\d+$/.test(segment))return ':id'
      if(/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(segment))return ':id'
      if(/^[A-Za-z0-9_-]{20,}$/.test(segment))return ':id'
      return segment
    }).join('/')
  })
}

function resourceTiming(url:string,started:number):ResourceTimingSummary|undefined{
  if((!detailed()&&!preAuthDetailed())||typeof performance==='undefined'||typeof performance.getEntriesByName!=='function')return undefined
  return safeValue<ResourceTimingSummary|undefined>(undefined,()=>{
    const entries=performance.getEntriesByName(url,'resource') as PerformanceResourceTiming[]
    const entry=[...entries].reverse().find(item=>item.startTime>=started-5)
    if(!entry)return undefined
    return {
      dns_ms:phase(entry.domainLookupStart,entry.domainLookupEnd),
      tcp_ms:phase(entry.connectStart,entry.connectEnd),
      tls_ms:phase(entry.secureConnectionStart,entry.connectEnd),
      request_to_first_byte_ms:phase(entry.requestStart,entry.responseStart),
      response_download_ms:phase(entry.responseStart,entry.responseEnd),
      total_ms:entry.duration>0?round(entry.duration):null,
    }
  })
}

function finishPage(page:PageObservation){
  if(activePage!==page)return
  if(page.settleTimer!==null)safeRun(()=>window.clearTimeout(page.settleTimer!))
  clearWatchdog(page.watchdogTimer)
  const duration=round(now()-page.started),slow=duration>PAGE_SLOW_MS
  append(makeEvent('page',page.name,{id:page.id,duration_ms:duration,page:page.name,slow,detail:page.pendingRecorded?'completed-after-pending':undefined}),slow)
  activePage=null
}
function schedulePageCompletion(){
  const page=activePage
  if(!page||!page.mounted||page.pending>0||page.settleTimer!==null)return
  page.settleTimer=safeValue<number|null>(null,()=>window.setTimeout(()=>safeRun(()=>{
    if(activePage===page&&page.pending===0)finishPage(page)
  }),50))
}
function completeActivePage(){
  const page=activePage
  if(!page)return
  if(page.mounted)finishPage(page)
  else{if(page.settleTimer!==null)safeRun(()=>window.clearTimeout(page.settleTimer!));clearWatchdog(page.watchdogTimer);activePage=null}
}

export function startPageObservation(name:string){safeRun(()=>{
  completeActivePage()
  currentPageName=name
  const page:PageObservation={id:eventId(),name,started:now(),mounted:false,pending:0,settleTimer:null,watchdogTimer:null,pendingRecorded:false}
  activePage=page
  page.watchdogTimer=scheduleWatchdog(()=>{
    if(activePage!==page)return
    page.pendingRecorded=true
    append(makeEvent('page',page.name,{id:page.id,duration_ms:round(now()-page.started),page:page.name,slow:true,detail:'page-loading-pending'}),true)
  })
  appendDetailed(makeEvent('detail','page_navigation',{page:name,detail:'navigation-start'}))
})}
export function markPageMounted(name:string){safeRun(()=>{
  if(!activePage||activePage.name!==name)startPageObservation(name)
  if(activePage){activePage.mounted=true;appendDetailed(makeEvent('detail','page_mounted',{page:name,detail:'react-mounted'}))}
  schedulePageCompletion()
})}

function fallbackObservation(path:string,method:string):ApiObservation{
  return {id:'diagnostic-api',name:sanitizeApiPath(path),method:safeValue('GET',()=>method.toUpperCase()),page:currentPage(),started:now(),url:'',pendingTimer:null,pendingRecorded:false,completed:false}
}
export function beginApiObservation(path:string,method='GET',resourcePath=path):ApiObservation{
  return safeValue(fallbackObservation(path,method),()=>{
    const observation:ApiObservation={id:eventId(),name:sanitizeApiPath(path),method:method.toUpperCase(),page:currentPage(),started:now(),url:new URL(resourcePath,window.location.origin).href,pendingTimer:null,pendingRecorded:false,completed:false}
    if(activePage){activePage.pending+=1;if(activePage.settleTimer!==null){safeRun(()=>window.clearTimeout(activePage!.settleTimer!));activePage.settleTimer=null}}
    observation.pendingTimer=scheduleWatchdog(()=>{
      if(observation.completed)return
      observation.pendingRecorded=true
      append(makeEvent('api',observation.name,{id:observation.id,duration_ms:round(now()-observation.started),method:observation.method,page:observation.page,slow:true,detail:'request-pending'}),true)
    })
    appendDetailed(makeEvent('detail',observation.name,{method:observation.method,page:observation.page,detail:'request-sent'}))
    return observation
  })
}

export function markApi401(observation:ApiObservation){safeRun(()=>{
  append(makeEvent('api_401',observation.name,{method:observation.method,page:observation.page,status:401,detail:'refresh-and-retry'}),true)
})}

export function finishApiObservation(observation:ApiObservation,values:{status?:number;error?:boolean;requestId?:string|null}={}){safeRun(()=>{
  observation.completed=true
  clearWatchdog(observation.pendingTimer)
  try{
    const duration=round(now()-observation.started),slow=duration>API_SLOW_MS,error=values.error===true||(values.status!==undefined&&values.status>=400)
    const requestId=values.requestId&&idPattern.test(values.requestId)?values.requestId:undefined
    const timing=resourceTiming(observation.url,observation.started)
    append(makeEvent(observation.name==='/auth/refresh'?'auth_refresh':'api',observation.name,{
      id:observation.id,duration_ms:duration,status:values.status??null,method:observation.method,page:observation.page,
      request_id:requestId,slow,error,resource_timing:detailed()?timing:undefined,detail:observation.pendingRecorded?'completed-after-pending':undefined,
    }),slow||error)
    if(preAuthDetailed()&&timing)appendDetailed(makeEvent('detail',observation.name,{duration_ms:duration,status:values.status??null,method:observation.method,page:observation.page,request_id:requestId,resource_timing:timing,detail:'pre-auth-resource-timing'}))
  }finally{
    if(activePage&&observation.page===activePage.name){activePage.pending=Math.max(0,activePage.pending-1);schedulePageCompletion()}
  }
})}

export function recordDiagnosticError(name:string,detail:string,page=currentPage()){safeRun(()=>{
  append(makeEvent('error',name,{page,error:true,detail:detail.slice(0,160)}),true)
})}

export function installGlobalDiagnostics(){safeRun(()=>{
  if(globalErrorHandlersInstalled)return
  globalErrorHandlersInstalled=true
  window.addEventListener('error',()=>recordDiagnosticError('browser-error','uncaught-error'))
  window.addEventListener('unhandledrejection',()=>recordDiagnosticError('browser-error','unhandled-rejection'))
})}

export function setDiagnosticAdminAccess(allowed:boolean){safeRun(()=>{
  adminAllowed=allowed
  if(allowed&&detailedPreference)for(const event of preAuthDetails)append(event)
  preAuthDetails=[]
  notify()
})}
export function isDetailedDiagnosticsEnabled(){return safeValue(false,detailed)}
export function setDetailedDiagnosticsEnabled(enabled:boolean){
  return safeValue(false,()=>{
    if(adminAllowed!==true)return false
    detailedPreference=enabled;safeLocalSet(detailStorageKey,String(enabled));notify();return true
  })
}
export function subscribeDiagnostics(listener:()=>void){return safeValue<()=>void>(()=>{},()=>{listeners.add(listener);return()=>safeRun(()=>{listeners.delete(listener)})})}
export function diagnosticsSnapshot(){return safeValue({events:[] as DiagnosticEvent[],anomalies:[] as DiagnosticEvent[],detailed_enabled:false},()=>({events:[...events],anomalies:[...anomalies],detailed_enabled:detailed()}))}
export function clearDiagnostics(){safeRun(()=>{events=[];anomalies=[];safeLocalRemove(anomalyStorageKey);notify()})}
export function exportDiagnostics(){
  return safeValue('{"schema_version":1,"events":[],"anomalies":[]}',()=>JSON.stringify({schema_version:1,exported_at:new Date().toISOString(),memory_limit:MEMORY_LIMIT,anomaly_limit:ANOMALY_LIMIT,...diagnosticsSnapshot()},null,2))
}
