export type DiagnosticEventKind='api'|'page'|'auth_refresh'|'api_401'|'error'|'detail'
export type TimingMatchStatus='matched'|'ambiguous'|'unavailable'

export interface ResourceTimingSummary{
  observation_to_fetch_start_ms:number|null
  fetch_to_request_start_ms:number|null
  redirect_ms:number|null
  service_worker_ms:number|null
  dns_ms:number|null
  tcp_ms:number|null
  tls_ms:number|null
  request_to_first_byte_ms:number|null
  response_download_ms:number|null
  resource_total_ms:number|null
  response_end_to_client_finish_ms:number|null
  next_hop_protocol:string|null
  transfer_size:number|null
  encoded_body_size:number|null
  decoded_body_size:number|null
  /** v1 compatibility for locally persisted records. */
  total_ms?:number|null
}

export interface PhysicalAttemptRecord{
  index:number
  method:string
  route:string
  status:number|null
  request_id?:string
  duration_ms:number|null
  retry:boolean
  error:boolean
  timing_match:TimingMatchStatus
  timing_missing_reason:string|null
  resource_timing?:ResourceTimingSummary
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
  observation_id?:string
  parent_observation_id?:string
  attempts?:PhysicalAttemptRecord[]
}

export interface ApiAttemptObservation{
  index:number
  method:string
  route:string
  started:number
  finished:number|null
  retry:boolean
  status:number|null
  requestId?:string
  error:boolean
  completed:boolean
  concurrentSameUrl:boolean
}

export interface ApiObservation{
  id:string
  name:string
  method:string
  page?:string
  started:number
  pendingTimer:number|null
  pendingRecorded:boolean
  completed:boolean
  had401:boolean
  parentObservationId?:string
  attempts:ApiAttemptObservation[]
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
const MAX_TIMING_ENRICHMENT_TIMERS=50
const MAX_ACTIVE_ATTEMPTS=100
const MAX_ATTEMPTS=4
const API_SLOW_MS=2000
const PAGE_SLOW_MS=3000
const PENDING_WARNING_MS=3000
const TIMING_ENRICHMENT_DELAY_MS=100
const anomalyStorageKey='kitchenerp.performance.anomalies.v1'
const detailStorageKey='kitchenerp.performance.detailed.v1'
const idPattern=/^[A-Za-z0-9._:-]{1,128}$/
const listeners=new Set<()=>void>()
const watchdogTimers=new Set<number>()
const timingEnrichmentTimers=new Set<number>()
const activeAttemptsByUrl=new Map<string,Set<ApiAttemptObservation>>()
const activeAttemptOrder:ApiAttemptObservation[]=[]
const attemptResourceUrls=new WeakMap<ApiAttemptObservation,string>()
const capacityReleasedAttempts=new WeakSet<ApiAttemptObservation>()
const safeRootSegments=new Set([
  'audit-logs','auth','categories','dishes','exports','health','ingredients','kitchen-operations','menu-imports',
  'menus','nutrition','order-adjustments','postpartum','purchases','ready','recipes','requirement-snapshots',
  'requirements','suppliers','users',
])
const safeRouteSegments=new Set([
  'a4-xlsx','associations','bulk','calculate','cancel','catering-overview','catering-overview.docx',
  'catering-overview.xlsx','change-password','change-sheet','columns','confirm','convert-units','copy-day','copy-week',
  'daily','daily.docx','deactivate','dish-move','editor','exclude','finalize','foods','hard-delete','imports','items',
  'lines','login','logout','manual-foods','me','meal-types','menu-conflicts','menu-sources','nutrition',
  'nutrition-unit-conversions','nutrients','order','pauses','pdf','price-history','reactivate','recipe-cards','refresh',
  'reorder','replacement-candidates','replacement-groups','reset-password','restriction-groups','restore','reuse',
  'reuse-preview','revalidate','room-changes','search','selection-options','simple','weekly','weekly-ingredients.xlsx',
  'xlsx','conflict-acknowledgements','conflict-handlings','cases','preview',
])
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
    return value.map(normalizeStoredEvent).filter((item):item is DiagnosticEvent=>item!==null).slice(-ANOMALY_LIMIT)
  })
}
function round(value:number){return Math.round(value*10)/10}
function elapsed(start:number,end:number){return Number.isFinite(start)&&Number.isFinite(end)&&start>=0&&end>=start?round(end-start):null}
function phase(start:number,end:number){return start>0&&end>=start?round(end-start):null}
function size(value:number){return Number.isFinite(value)&&value>=0?value:null}
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
function scheduleTimingEnrichment(action:()=>void){
  if(timingEnrichmentTimers.size>=MAX_TIMING_ENRICHMENT_TIMERS)return false
  return safeValue(false,()=>{
    const timer=window.setTimeout(()=>{timingEnrichmentTimers.delete(timer);safeRun(action)},TIMING_ENRICHMENT_DELAY_MS)
    timingEnrichmentTimers.add(timer)
    return true
  })
}

export function sanitizeApiPath(input:string){
  return safeValue('/api/:redacted',()=>{
    const path=(input.split(/[?#]/,1)[0]||'/').replace(/^https?:\/\/[^/]+/i,'')
    let decoded=path
    try{decoded=decodeURI(path)}catch{/* Keep undecoded input and apply conservative redaction. */}
    const segments=decoded.split('/').filter(Boolean)
    if(!segments.length)return '/'
    const result:string[]=[]
    let index=0
    if(segments[0]==='api'&&segments[1]==='v1'){result.push('api','v1');index=2}
    const root=segments[index]
    if(!root||!safeRootSegments.has(root))return '/api/:redacted'
    result.push(root)
    for(const segment of segments.slice(index+1))result.push(safeRouteSegments.has(segment)?segment:':id')
    return `/${result.join('/')}`
  })
}

function finiteOrNull(value:unknown){return typeof value==='number'&&Number.isFinite(value)&&value>=0?value:null}
function normalizeTiming(value:unknown):ResourceTimingSummary|undefined{
  if(!value||typeof value!=='object')return undefined
  const raw=value as Record<string,unknown>
  const protocol=typeof raw.next_hop_protocol==='string'&&raw.next_hop_protocol.length<=32?raw.next_hop_protocol:null
  return {
    observation_to_fetch_start_ms:finiteOrNull(raw.observation_to_fetch_start_ms),
    fetch_to_request_start_ms:finiteOrNull(raw.fetch_to_request_start_ms),redirect_ms:finiteOrNull(raw.redirect_ms),
    service_worker_ms:finiteOrNull(raw.service_worker_ms),dns_ms:finiteOrNull(raw.dns_ms),tcp_ms:finiteOrNull(raw.tcp_ms),
    tls_ms:finiteOrNull(raw.tls_ms),request_to_first_byte_ms:finiteOrNull(raw.request_to_first_byte_ms),
    response_download_ms:finiteOrNull(raw.response_download_ms),resource_total_ms:finiteOrNull(raw.resource_total_ms),
    response_end_to_client_finish_ms:finiteOrNull(raw.response_end_to_client_finish_ms),next_hop_protocol:protocol,
    transfer_size:finiteOrNull(raw.transfer_size),encoded_body_size:finiteOrNull(raw.encoded_body_size),decoded_body_size:finiteOrNull(raw.decoded_body_size),
    total_ms:finiteOrNull(raw.total_ms),
  }
}
function normalizeAttempt(value:unknown):PhysicalAttemptRecord|null{
  if(!value||typeof value!=='object')return null
  const raw=value as Record<string,unknown>
  const matching:TimingMatchStatus=raw.timing_match==='matched'?'matched':raw.timing_match==='ambiguous'?'ambiguous':'unavailable'
  const requestId=typeof raw.request_id==='string'&&idPattern.test(raw.request_id)?raw.request_id:undefined
  const missingReasons=new Set(['concurrent-same-url','resource-url-unavailable','monitoring-capacity-released','performance-api-unavailable','multiple-candidate-entries','entry-not-found-or-buffer-full','not-captured-for-fast-request','request-still-pending','timing-pending-logical-completion'])
  return {
    index:typeof raw.index==='number'&&Number.isInteger(raw.index)&&raw.index>0?raw.index:1,
    method:typeof raw.method==='string'&&/^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$/.test(raw.method)?raw.method:'GET',
    route:sanitizeApiPath(typeof raw.route==='string'?raw.route:'/api/:redacted'),status:typeof raw.status==='number'?raw.status:null,
    request_id:requestId,duration_ms:finiteOrNull(raw.duration_ms),retry:raw.retry===true,error:raw.error===true,
    timing_match:matching,timing_missing_reason:typeof raw.timing_missing_reason==='string'&&missingReasons.has(raw.timing_missing_reason)?raw.timing_missing_reason:null,
    resource_timing:normalizeTiming(raw.resource_timing),
  }
}
function normalizeStoredEvent(value:unknown):DiagnosticEvent|null{
  if(!value||typeof value!=='object')return null
  const raw=value as Record<string,unknown>
  if(typeof raw.id!=='string'||!idPattern.test(raw.id))return null
  const kinds:DiagnosticEventKind[]=['api','page','auth_refresh','api_401','error','detail']
  const kind=kinds.includes(raw.kind as DiagnosticEventKind)?raw.kind as DiagnosticEventKind:'error'
  const isApi=kind==='api'||kind==='auth_refresh'||kind==='api_401'
  const safeName=isApi?sanitizeApiPath(typeof raw.name==='string'?raw.name:'/api/:redacted'):
    typeof raw.name==='string'&&/^[a-z0-9_-]{1,64}$/i.test(raw.name)?raw.name:'diagnostic-event'
  const details=new Set(['request-pending','completed-after-pending','page-loading-pending','navigation-start','react-mounted','request-sent','pre-auth-resource-timing','refresh-and-retry','logical-request-start','uncaught-error','unhandled-rejection'])
  const method=typeof raw.method==='string'&&/^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$/.test(raw.method)?raw.method:undefined
  const requestId=typeof raw.request_id==='string'&&idPattern.test(raw.request_id)?raw.request_id:undefined
  const attempts=Array.isArray(raw.attempts)?raw.attempts.map(normalizeAttempt).filter((item):item is PhysicalAttemptRecord=>item!==null).slice(0,MAX_ATTEMPTS):undefined
  return {
    id:raw.id,kind,occurred_at:typeof raw.occurred_at==='string'&&raw.occurred_at.length<=40?raw.occurred_at:'',name:safeName,
    duration_ms:finiteOrNull(raw.duration_ms),status:typeof raw.status==='number'?raw.status:null,method,
    page:typeof raw.page==='string'&&/^[a-z0-9_-]{1,64}$/i.test(raw.page)?raw.page:undefined,request_id:requestId,
    slow:raw.slow===true,error:raw.error===true,resource_timing:normalizeTiming(raw.resource_timing),
    detail:typeof raw.detail==='string'&&details.has(raw.detail)?raw.detail:undefined,
    observation_id:typeof raw.observation_id==='string'&&idPattern.test(raw.observation_id)?raw.observation_id:undefined,
    parent_observation_id:typeof raw.parent_observation_id==='string'&&idPattern.test(raw.parent_observation_id)?raw.parent_observation_id:undefined,
    attempts,
  }
}

function resourceEntries(url:string){
  return safeValue<PerformanceResourceTiming[]|null>(null,()=>{
    if(typeof performance==='undefined'||typeof performance.getEntriesByName!=='function')return null
    return performance.getEntriesByName(url,'resource') as PerformanceResourceTiming[]
  })
}
function timingSummary(entry:PerformanceResourceTiming,attempt:ApiAttemptObservation,clientFinished:number,isFinal:boolean):ResourceTimingSummary{
  return {
    observation_to_fetch_start_ms:elapsed(attempt.started,entry.fetchStart),
    fetch_to_request_start_ms:entry.fetchStart>0&&entry.requestStart>0?elapsed(entry.fetchStart,entry.requestStart):null,
    redirect_ms:phase(entry.redirectStart,entry.redirectEnd),
    service_worker_ms:entry.workerStart>0&&entry.fetchStart>0?elapsed(entry.workerStart,entry.fetchStart):null,
    dns_ms:phase(entry.domainLookupStart,entry.domainLookupEnd),
    tcp_ms:phase(entry.connectStart,entry.connectEnd),
    tls_ms:phase(entry.secureConnectionStart,entry.connectEnd),
    request_to_first_byte_ms:phase(entry.requestStart,entry.responseStart),
    response_download_ms:phase(entry.responseStart,entry.responseEnd),
    resource_total_ms:entry.duration>=0?round(entry.duration):null,
    response_end_to_client_finish_ms:isFinal&&entry.responseEnd>0?elapsed(entry.responseEnd,clientFinished):null,
    next_hop_protocol:typeof entry.nextHopProtocol==='string'&&entry.nextHopProtocol.length<=32?entry.nextHopProtocol||null:null,
    transfer_size:size(entry.transferSize),
    encoded_body_size:size(entry.encodedBodySize),
    decoded_body_size:size(entry.decodedBodySize),
  }
}
function matchAttemptTiming(attempt:ApiAttemptObservation,nextStarted:number|undefined,clientFinished:number,isFinal:boolean):Pick<PhysicalAttemptRecord,'timing_match'|'timing_missing_reason'|'resource_timing'>{
  if(capacityReleasedAttempts.has(attempt))return {timing_match:'unavailable',timing_missing_reason:'monitoring-capacity-released'}
  if(attempt.concurrentSameUrl)return {timing_match:'ambiguous',timing_missing_reason:'concurrent-same-url'}
  const resourceUrl=attemptResourceUrls.get(attempt)
  if(!resourceUrl)return {timing_match:'unavailable',timing_missing_reason:'resource-url-unavailable'}
  const entries=resourceEntries(resourceUrl)
  if(entries===null)return {timing_match:'unavailable',timing_missing_reason:'performance-api-unavailable'}
  const upper=nextStarted??clientFinished+5
  const candidates=entries.filter(entry=>entry.startTime>=attempt.started-2&&entry.startTime<upper)
  if(candidates.length>1)return {timing_match:'ambiguous',timing_missing_reason:'multiple-candidate-entries'}
  if(candidates.length===0)return {timing_match:'unavailable',timing_missing_reason:'entry-not-found-or-buffer-full'}
  return {timing_match:'matched',timing_missing_reason:null,resource_timing:timingSummary(candidates[0],attempt,clientFinished,isFinal)}
}
function attemptRecords(observation:ApiObservation,clientFinished:number,captureTiming:boolean):PhysicalAttemptRecord[]{
  const attempts=observation.attempts.slice(0,MAX_ATTEMPTS)
  return attempts.map((attempt,index)=>{
    const timing=captureTiming
      ?matchAttemptTiming(attempt,attempts[index+1]?.started,clientFinished,index===attempts.length-1)
      :{timing_match:'unavailable' as const,timing_missing_reason:'not-captured-for-fast-request'}
    return {
      index:attempt.index,method:attempt.method,route:attempt.route,status:attempt.status,request_id:attempt.requestId,
      duration_ms:attempt.finished===null?null:elapsed(attempt.started,attempt.finished),retry:attempt.retry,error:attempt.error,...timing,
    }
  })
}
function pendingAttemptRecords(observation:ApiObservation):PhysicalAttemptRecord[]{
  return observation.attempts.slice(0,MAX_ATTEMPTS).map(attempt=>({
    index:attempt.index,method:attempt.method,route:attempt.route,status:attempt.status,request_id:attempt.requestId,
    duration_ms:attempt.finished===null?round(now()-attempt.started):elapsed(attempt.started,attempt.finished),retry:attempt.retry,
    error:attempt.error,timing_match:'unavailable',timing_missing_reason:attempt.finished===null?'request-still-pending':'timing-pending-logical-completion',
  }))
}
function releaseAttemptUrl(attempt:ApiAttemptObservation,discardResourceUrl=false){
  const resourceUrl=attemptResourceUrls.get(attempt)
  if(resourceUrl){
    const active=activeAttemptsByUrl.get(resourceUrl)
    active?.delete(attempt)
    if(active?.size===0)activeAttemptsByUrl.delete(resourceUrl)
  }
  const orderIndex=activeAttemptOrder.indexOf(attempt)
  if(orderIndex>=0)activeAttemptOrder.splice(orderIndex,1)
  if(discardResourceUrl)attemptResourceUrls.delete(attempt)
}
function releaseOldestActiveAttempt(){
  const oldest=activeAttemptOrder[0]
  if(!oldest)return
  capacityReleasedAttempts.add(oldest)
  releaseAttemptUrl(oldest,true)
}
function discardResourceUrls(observation:ApiObservation){for(const attempt of observation.attempts)attemptResourceUrls.delete(attempt)}

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

function fallbackObservation(path:string,method:string,parentObservationId?:string):ApiObservation{
  return {id:'diagnostic-api',name:sanitizeApiPath(path),method:safeValue('GET',()=>method.toUpperCase()),page:currentPage(),started:now(),pendingTimer:null,pendingRecorded:false,completed:false,had401:false,parentObservationId,attempts:[]}
}
export function beginApiObservation(path:string,method='GET',_resourcePath=path,parentObservationId?:string):ApiObservation{
  return safeValue(fallbackObservation(path,method,parentObservationId),()=>{
    const observation:ApiObservation={id:eventId(),name:sanitizeApiPath(path),method:method.toUpperCase(),page:currentPage(),started:now(),pendingTimer:null,pendingRecorded:false,completed:false,had401:false,parentObservationId,attempts:[]}
    if(activePage){activePage.pending+=1;if(activePage.settleTimer!==null){safeRun(()=>window.clearTimeout(activePage!.settleTimer!));activePage.settleTimer=null}}
    observation.pendingTimer=scheduleWatchdog(()=>{
      if(observation.completed)return
      observation.pendingRecorded=true
      append(makeEvent('api',observation.name,{id:observation.id,observation_id:observation.id,duration_ms:round(now()-observation.started),method:observation.method,page:observation.page,slow:true,detail:'request-pending',attempts:pendingAttemptRecords(observation)}),true)
    })
    appendDetailed(makeEvent('detail','api-request',{observation_id:observation.id,method:observation.method,page:observation.page,detail:'logical-request-start'}))
    return observation
  })
}
export function beginApiAttempt(observation:ApiObservation,resourcePath:string,retry=false):ApiAttemptObservation{
  const fallback:ApiAttemptObservation={index:observation.attempts.length+1,method:observation.method,route:observation.name,started:now(),finished:null,retry,status:null,error:false,completed:false,concurrentSameUrl:false}
  return safeValue(fallback,()=>{
    const url=new URL(resourcePath,window.location.origin).href
    const attempt:ApiAttemptObservation={...fallback}
    while(activeAttemptOrder.length>=MAX_ACTIVE_ATTEMPTS)releaseOldestActiveAttempt()
    attemptResourceUrls.set(attempt,url)
    if(observation.attempts.length<MAX_ATTEMPTS)observation.attempts.push(attempt)
    const active=activeAttemptsByUrl.get(url)??new Set<ApiAttemptObservation>()
    if(active.size){attempt.concurrentSameUrl=true;for(const item of active)item.concurrentSameUrl=true}
    active.add(attempt);activeAttemptsByUrl.set(url,active)
    activeAttemptOrder.push(attempt)
    return attempt
  })
}
export function finishApiAttempt(_observation:ApiObservation,attempt:ApiAttemptObservation,values:{status?:number;error?:boolean;requestId?:string|null}={}){safeRun(()=>{
  if(attempt.completed)return
  attempt.completed=true;attempt.finished=now();attempt.status=values.status??null;attempt.error=values.error===true||(values.status!==undefined&&values.status>=400)
  if(values.requestId&&idPattern.test(values.requestId))attempt.requestId=values.requestId
  releaseAttemptUrl(attempt)
})}

export function markApi401(observation:ApiObservation){safeRun(()=>{
  observation.had401=true
  const last=observation.attempts.at(-1)
  append(makeEvent('api_401',observation.name,{observation_id:observation.id,method:observation.method,page:observation.page,status:401,request_id:last?.requestId,detail:'refresh-and-retry',attempts:pendingAttemptRecords(observation)}),true)
})}

export function finishApiObservation(observation:ApiObservation,values:{status?:number;error?:boolean;requestId?:string|null}={}){safeRun(()=>{
  if(observation.completed)return
  observation.completed=true
  clearWatchdog(observation.pendingTimer)
  const clientFinished=now()
  try{
    const duration=round(clientFinished-observation.started),slow=duration>API_SLOW_MS,error=values.error===true||(values.status!==undefined&&values.status>=400)
    const requestId=values.requestId&&idPattern.test(values.requestId)?values.requestId:undefined
    const anomaly=slow||error||observation.pendingRecorded||observation.had401
    const captureTiming=detailed()||preAuthDetailed()||anomaly
    const attempts=captureTiming?attemptRecords(observation,clientFinished,true):undefined
    const event=makeEvent(observation.name==='/auth/refresh'?'auth_refresh':'api',observation.name,{
      id:observation.id,observation_id:observation.id,parent_observation_id:observation.parentObservationId,duration_ms:duration,
      status:values.status??null,method:observation.method,page:observation.page,request_id:requestId,slow,error,
      resource_timing:attempts?.at(-1)?.resource_timing,attempts,detail:observation.pendingRecorded?'completed-after-pending':undefined,
    })
    append(event,anomaly)
    const retryable=attempts?.some(item=>item.timing_match==='unavailable'&&item.timing_missing_reason==='entry-not-found-or-buffer-full')===true
    if(retryable&&scheduleTimingEnrichment(()=>{
      const enriched=attemptRecords(observation,clientFinished,true)
      append({...event,attempts:enriched,resource_timing:enriched.at(-1)?.resource_timing},anomaly)
      discardResourceUrls(observation)
    })){
      // Exact URLs remain only in this bounded, short-lived closure and are never exported.
    }else discardResourceUrls(observation)
  }finally{
    for(const attempt of observation.attempts)releaseAttemptUrl(attempt)
    if(activePage&&observation.page===activePage.name){activePage.pending=Math.max(0,activePage.pending-1);schedulePageCompletion()}
  }
})}

export type DiagnosticErrorCode='uncaught-error'|'unhandled-rejection'
const diagnosticErrorCodes=new Set<DiagnosticErrorCode>(['uncaught-error','unhandled-rejection'])
export function recordDiagnosticError(code:DiagnosticErrorCode){
  return safeValue(false,()=>{
    if(!diagnosticErrorCodes.has(code as DiagnosticErrorCode))return false
    append(makeEvent('error','browser-error',{page:currentPage(),error:true,detail:code}),true)
    return true
  })
}

export function installGlobalDiagnostics(){safeRun(()=>{
  if(globalErrorHandlersInstalled)return
  globalErrorHandlersInstalled=true
  window.addEventListener('error',()=>recordDiagnosticError('uncaught-error'))
  window.addEventListener('unhandledrejection',()=>recordDiagnosticError('unhandled-rejection'))
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
export function clearDiagnostics(){safeRun(()=>{
  for(const timer of timingEnrichmentTimers)safeRun(()=>window.clearTimeout(timer))
  timingEnrichmentTimers.clear();events=[];anomalies=[];safeLocalRemove(anomalyStorageKey);notify()
})}
export function exportDiagnostics(){
  return safeValue('{"schema_version":2,"events":[],"anomalies":[]}',()=>JSON.stringify({schema_version:2,exported_at:new Date().toISOString(),memory_limit:MEMORY_LIMIT,anomaly_limit:ANOMALY_LIMIT,...diagnosticsSnapshot()},null,2))
}
