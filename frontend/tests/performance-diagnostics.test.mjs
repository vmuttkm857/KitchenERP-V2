import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { createRequire } from 'node:module'
import test from 'node:test'

const require=createRequire(import.meta.url)
const ts=require('typescript')

const monitor=readFileSync(new URL('../src/monitoring/performanceMonitor.ts',import.meta.url),'utf8')
const client=readFileSync(new URL('../src/api/client.ts',import.meta.url),'utf8')
const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const page=readFileSync(new URL('../src/features/diagnostics/PerformanceDiagnosticsPage.tsx',import.meta.url),'utf8')
const styles=readFileSync(new URL('../src/styles/global.css',import.meta.url),'utf8')

function resourceEntry(overrides={}){
  return {startTime:1,fetchStart:2,workerStart:0,redirectStart:0,redirectEnd:0,domainLookupStart:3,domainLookupEnd:5,connectStart:5,secureConnectionStart:6,connectEnd:10,requestStart:12,responseStart:50,responseEnd:60,duration:59,nextHopProtocol:'h2',transferSize:1200,encodedBodySize:900,decodedBodySize:1800,...overrides}
}

function runtimeMonitor({detailPreference=false,storageThrows=false,performanceThrows=false,jsonThrows=false,initialAnomalies=[]}={}){
  let clock=0,timerId=0,performanceCalls=0
  const timers=new Map(),entries=new Map()
  const storage=new Map()
  if(detailPreference)storage.set('kitchenerp.performance.detailed.v1','true')
  if(initialAnomalies.length)storage.set('kitchenerp.performance.anomalies.v1',JSON.stringify(initialAnomalies))
  const performance={now:()=>clock,getEntriesByName:name=>{performanceCalls+=1;if(performanceThrows)throw new Error('timing unavailable');return entries.get(name)??[]}}
  const runtimeJson={parse:JSON.parse,stringify:(...args)=>{if(jsonThrows)throw new Error('serialization failed');return JSON.stringify(...args)}}
  const sandbox={exports:{},module:{exports:{}},Date,URL,JSON:runtimeJson,performance,
    localStorage:{getItem:key=>{if(storageThrows)throw new Error('storage denied');return storage.get(key)??null},setItem:(key,value)=>{if(storageThrows)throw new Error('quota');storage.set(key,value)},removeItem:key=>{if(storageThrows)throw new Error('storage denied');storage.delete(key)}},
    window:{location:{origin:'https://example.test'},setTimeout:(callback,delay)=>{const id=++timerId;timers.set(id,{callback,delay});return id},clearTimeout:id=>timers.delete(id),addEventListener:()=>{}},
    setTimeout:(callback,delay)=>{const id=++timerId;timers.set(id,{callback,delay});return id},clearTimeout:id=>timers.delete(id),console}
  sandbox.module.exports=sandbox.exports
  const compiled=ts.transpileModule(monitor,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  vm.runInNewContext(compiled,sandbox)
  return {
    monitor:sandbox.module.exports,setClock:value=>{clock=value},
    setEntries:(url,value)=>entries.set(url,value),
    runTimers:delay=>{for(const [id,timer] of [...timers])if(timer.delay===delay){timers.delete(id);timer.callback()}},
    performanceCalls:()=>performanceCalls,timers,storage,
  }
}

function runtimeClient(responses,{monitorThrows=false,fetchImpl}={}){
  const calls=[],observations=[],attempts=[],objectUrls=[],revokedUrls=[]
  const monitorStub={
    beginApiObservation:(path,method,_resource,parent)=>{if(monitorThrows)throw new Error('monitor failed');const value={id:`logical-${observations.length+1}`,path,method,parent};observations.push(value);return value},
    beginApiAttempt:(observation,resource,retry)=>{const value={observation,resource,retry:Boolean(retry)};attempts.push(value);return value},
    finishApiAttempt:()=>{},finishApiObservation:()=>{},markApi401:()=>{},
  }
  const urlApi={createObjectURL:()=>{const value=`blob:test-${objectUrls.length+1}`;objectUrls.push(value);return value},revokeObjectURL:value=>revokedUrls.push(value)}
  const sandbox={exports:{},module:{exports:{}},require:specifier=>{if(specifier.includes('performanceMonitor'))return monitorStub;throw new Error(`Unexpected module ${specifier}`)},
    fetch:async(url,init)=>{calls.push({url,init});if(fetchImpl)return fetchImpl(url,init,calls);const next=responses.shift();if(typeof next==='function')return next(url,init);if(next instanceof Error)throw next;return next},
    Headers,FormData,Response,URL:urlApi,Blob,console,
    document:{createElement:()=>({style:{},href:'',download:'',click(){},remove(){}}),body:{appendChild(){}}},
    window:{setTimeout:callback=>{callback();return 1}},
  }
  sandbox.module.exports=sandbox.exports
  const source=client.replace(/import\.meta\.env\.VITE_API_BASE_URL/g,'undefined')
  const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  vm.runInNewContext(compiled,sandbox)
  return {api:sandbox.module.exports,calls,observations,attempts,objectUrls,revokedUrls}
}

test('performance monitor keeps bounded memory, attempts, timers, and anomaly history',()=>{
  assert.match(monitor,/const MEMORY_LIMIT=500/)
  assert.match(monitor,/const ANOMALY_LIMIT=20/)
  assert.match(monitor,/const MAX_ATTEMPTS=4/)
  assert.match(monitor,/const MAX_ACTIVE_ATTEMPTS=100/)
  assert.match(monitor,/const MAX_TIMING_ENRICHMENT_TIMERS=50/)
  assert.match(monitor,/upsert\(events,event,MEMORY_LIMIT\)/)
  assert.match(monitor,/upsert\(anomalies,event,ANOMALY_LIMIT\)/)
})

test('fast API remains lightweight when detailed mode is off',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const observation=diagnostics.beginApiObservation('/ingredients','GET','/api/v1/ingredients')
  const attempt=diagnostics.beginApiAttempt(observation,'/api/v1/ingredients')
  runtime.setClock(10);diagnostics.finishApiAttempt(observation,attempt,{status:200,requestId:'fast-request'})
  runtime.setClock(20);diagnostics.finishApiObservation(observation,{status:200,requestId:'fast-request'})
  const event=diagnostics.diagnosticsSnapshot().events.find(item=>item.id===observation.id)
  assert.equal(event.attempts,undefined)
  assert.equal(runtime.performanceCalls(),0)
  assert.equal(diagnostics.diagnosticsSnapshot().anomalies.length,0)
})

test('slow API automatically stores matched Resource Timing while detailed mode is off',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const observation=diagnostics.beginApiObservation('/ingredients?search=private','GET','/api/v1/ingredients?search=private')
  const attempt=diagnostics.beginApiAttempt(observation,'/api/v1/ingredients?search=private')
  runtime.setEntries('https://example.test/api/v1/ingredients?search=private',[resourceEntry()])
  runtime.setClock(100);diagnostics.finishApiAttempt(observation,attempt,{status:200,requestId:'request-1'})
  runtime.setClock(2501);diagnostics.finishApiObservation(observation,{status:200,requestId:'request-1'})
  const event=diagnostics.diagnosticsSnapshot().anomalies[0]
  assert.equal(event.name,'/ingredients')
  assert.equal(event.attempts[0].timing_match,'matched')
  assert.equal(event.attempts[0].resource_timing.request_to_first_byte_ms,38)
  assert.equal(event.attempts[0].resource_timing.response_download_ms,10)
  assert.equal(event.attempts[0].resource_timing.response_end_to_client_finish_ms,2441)
  assert.equal(JSON.stringify(event).includes('search=private'),false)
})

test('pending watchdog records an in-flight attempt and final completion replaces it',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const observation=diagnostics.beginApiObservation('/menus/secret-slug','GET','/api/v1/menus/secret-slug')
  const attempt=diagnostics.beginApiAttempt(observation,'/api/v1/menus/secret-slug')
  runtime.setClock(3100);runtime.runTimers(3000)
  let event=diagnostics.diagnosticsSnapshot().anomalies[0]
  assert.equal(event.detail,'request-pending')
  assert.equal(event.attempts[0].timing_missing_reason,'request-still-pending')
  runtime.setEntries('https://example.test/api/v1/menus/secret-slug',[resourceEntry()])
  runtime.setClock(3200);diagnostics.finishApiAttempt(observation,attempt,{status:200})
  diagnostics.finishApiObservation(observation,{status:200})
  event=diagnostics.diagnosticsSnapshot().anomalies[0]
  assert.equal(event.id,observation.id)
  assert.equal(event.detail,'completed-after-pending')
  assert.equal(event.attempts[0].timing_match,'matched')
})

test('concurrent requests to the same URL are conservatively marked ambiguous',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const first=diagnostics.beginApiObservation('/ingredients','GET','/api/v1/ingredients')
  const firstAttempt=diagnostics.beginApiAttempt(first,'/api/v1/ingredients')
  runtime.setClock(1)
  const second=diagnostics.beginApiObservation('/ingredients','GET','/api/v1/ingredients')
  const secondAttempt=diagnostics.beginApiAttempt(second,'/api/v1/ingredients')
  runtime.setEntries('https://example.test/api/v1/ingredients',[resourceEntry(),resourceEntry({startTime:2})])
  runtime.setClock(2200);diagnostics.finishApiAttempt(first,firstAttempt,{status:200});diagnostics.finishApiObservation(first,{status:200})
  runtime.setClock(2300);diagnostics.finishApiAttempt(second,secondAttempt,{status:200});diagnostics.finishApiObservation(second,{status:200})
  for(const event of diagnostics.diagnosticsSnapshot().anomalies)assert.equal(event.attempts[0].timing_match,'ambiguous')
})

test('delayed Resource Timing enriches an existing anomaly without delaying API completion',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const observation=diagnostics.beginApiObservation('/requirements/calculate','POST','/api/v1/requirements/calculate')
  const attempt=diagnostics.beginApiAttempt(observation,'/api/v1/requirements/calculate')
  runtime.setClock(100);diagnostics.finishApiAttempt(observation,attempt,{status:200})
  runtime.setClock(2200);diagnostics.finishApiObservation(observation,{status:200})
  assert.equal(diagnostics.diagnosticsSnapshot().anomalies[0].attempts[0].timing_match,'unavailable')
  runtime.setEntries('https://example.test/api/v1/requirements/calculate',[resourceEntry()])
  runtime.runTimers(100)
  const anomalies=diagnostics.diagnosticsSnapshot().anomalies
  assert.equal(anomalies.length,1)
  assert.equal(anomalies[0].attempts[0].timing_match,'matched')
})

test('clearing diagnostics cancels delayed Resource Timing enrichment',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const observation=diagnostics.beginApiObservation('/ingredients','GET','/api/v1/ingredients')
  const attempt=diagnostics.beginApiAttempt(observation,'/api/v1/ingredients')
  runtime.setClock(2200);diagnostics.finishApiAttempt(observation,attempt,{status:200});diagnostics.finishApiObservation(observation,{status:200})
  diagnostics.clearDiagnostics();runtime.setEntries('https://example.test/api/v1/ingredients',[resourceEntry()]);runtime.runTimers(100)
  assert.equal(diagnostics.diagnosticsSnapshot().anomalies.length,0)
})

test('401 logical request retains physical attempts and refresh/retry behavior is unchanged',async()=>{
  const first=new Response('{}',{status:401,headers:{'X-Request-ID':'first-id'}})
  const refresh=new Response(JSON.stringify({access_token:'new-token'}),{status:200,headers:{'Content-Type':'application/json','X-Request-ID':'refresh-id'}})
  const retry=new Response(JSON.stringify({ok:true}),{status:200,headers:{'Content-Type':'application/json','X-Request-ID':'retry-id'}})
  const runtime=runtimeClient([first,refresh,retry])
  runtime.api.setAccessToken('old-token')
  assert.deepEqual(await runtime.api.apiRequest('/ingredients'),{ok:true})
  assert.deepEqual(runtime.calls.map(item=>item.url),['/api/v1/ingredients','/api/v1/auth/refresh','/api/v1/ingredients'])
  assert.equal(runtime.attempts.length,3)
  assert.equal(runtime.attempts.at(-1).retry,true)
  assert.equal(runtime.observations[1].parent,runtime.observations[0].id)
})

test('apiDownload preserves 401 refresh and retry behavior',async()=>{
  const runtime=runtimeClient([
    new Response('{}',{status:401}),
    new Response(JSON.stringify({access_token:'download-token'}),{status:200,headers:{'Content-Type':'application/json'}}),
    new Response(new Blob(['xlsx']),{status:200,headers:{'Content-Disposition':`attachment; filename="report.xlsx"`}}),
  ])
  runtime.api.setAccessToken('old-token')
  await runtime.api.apiDownload('/exports/report.xlsx')
  assert.deepEqual(runtime.calls.map(item=>item.url),['/api/v1/exports/report.xlsx','/api/v1/auth/refresh','/api/v1/exports/report.xlsx'])
  assert.equal(runtime.attempts.at(-1).retry,true)
  assert.equal(runtime.objectUrls.length,1)
  assert.deepEqual(runtime.revokedUrls,runtime.objectUrls)
})

test('apiBlobUrl preserves 401 refresh and retry behavior',async()=>{
  const runtime=runtimeClient([
    new Response('{}',{status:401}),
    new Response(JSON.stringify({access_token:'image-token'}),{status:200,headers:{'Content-Type':'application/json'}}),
    new Response(new Blob(['image']),{status:200}),
  ])
  runtime.api.setAccessToken('old-token')
  assert.equal(await runtime.api.apiBlobUrl('/dishes/image'),'blob:test-1')
  assert.deepEqual(runtime.calls.map(item=>item.url),['/api/v1/dishes/image','/api/v1/auth/refresh','/api/v1/dishes/image'])
  assert.equal(runtime.attempts.at(-1).retry,true)
})

test('AbortSignal preserves the original abort error and does not trigger retry',async()=>{
  const abortReason=new Error('caller cancelled request')
  const runtime=runtimeClient([],{fetchImpl:(_url,init)=>new Promise((_,reject)=>{
    if(init.signal?.aborted){reject(init.signal.reason);return}
    init.signal?.addEventListener('abort',()=>reject(init.signal.reason),{once:true})
  })})
  const controller=new AbortController()
  const pending=runtime.api.apiRequest('/ingredients',{signal:controller.signal})
  controller.abort(abortReason)
  await assert.rejects(pending,error=>error===abortReason)
  assert.equal(runtime.calls.length,1)
})

test('concurrent 401 responses share one refreshPromise',async()=>{
  let releaseRefresh
  const refreshGate=new Promise(resolve=>{releaseRefresh=resolve})
  let refreshCount=0
  const attemptsByPath=new Map()
  const runtime=runtimeClient([],{fetchImpl:(url,init)=>{
    if(url==='/api/v1/auth/refresh'){
      refreshCount+=1
      return refreshGate.then(()=>new Response(JSON.stringify({access_token:'shared-token'}),{status:200,headers:{'Content-Type':'application/json'}}))
    }
    const count=(attemptsByPath.get(url)??0)+1
    attemptsByPath.set(url,count)
    if(count===1)return new Response('{}',{status:401})
    return new Response(JSON.stringify({path:url,authorization:new Headers(init.headers).get('Authorization')}),{status:200,headers:{'Content-Type':'application/json'}})
  }})
  runtime.api.setAccessToken('old-token')
  const first=runtime.api.apiRequest('/ingredients')
  const second=runtime.api.apiRequest('/menus')
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(refreshCount,1)
  releaseRefresh()
  const results=await Promise.all([first,second])
  assert.equal(results[0].authorization,'Bearer shared-token')
  assert.equal(results[1].authorization,'Bearer shared-token')
  assert.equal(refreshCount,1)
  assert.equal(runtime.calls.length,5)
})

test('failed auth refresh preserves original failure flow and does not retry business request',async()=>{
  const runtime=runtimeClient([new Response('{}',{status:401}),new Response('{}',{status:401})])
  runtime.api.setAccessToken('old-token')
  let expired=0;runtime.api.setAuthExpiredHandler(()=>{expired+=1})
  await assert.rejects(()=>runtime.api.apiRequest('/ingredients'),error=>error.status===401)
  assert.equal(runtime.calls.length,2)
  assert.equal(expired,1)
})

test('monitor failure cannot change a successful API result',async()=>{
  const runtime=runtimeClient([new Response(JSON.stringify({ok:true}),{status:200,headers:{'Content-Type':'application/json'}})],{monitorThrows:true})
  assert.deepEqual(await runtime.api.apiRequest('/ingredients'),{ok:true})
  assert.equal(runtime.calls.length,1)
})

test('permanently pending attempts have bounded matching state and late completion remains harmless',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const pending=[]
  for(let index=0;index<101;index+=1){
    const observation=diagnostics.beginApiObservation(`/ingredients/${index}`,'GET',`/api/v1/ingredients/${index}`)
    const attempt=diagnostics.beginApiAttempt(observation,`/api/v1/ingredients/${index}`)
    pending.push({observation,attempt})
  }
  runtime.setClock(2200)
  const oldest=pending[0]
  assert.doesNotThrow(()=>diagnostics.finishApiAttempt(oldest.observation,oldest.attempt,{status:200}))
  assert.doesNotThrow(()=>diagnostics.finishApiObservation(oldest.observation,{status:200}))
  const event=diagnostics.diagnosticsSnapshot().anomalies.find(item=>item.id===oldest.observation.id)
  assert.equal(event.attempts[0].timing_match,'unavailable')
  assert.equal(event.attempts[0].timing_missing_reason,'monitoring-capacity-released')
  for(const item of pending.slice(1))diagnostics.finishApiAttempt(item.observation,item.attempt,{status:200})
})

test('recordDiagnosticError accepts only fixed codes and never persists arbitrary sensitive text',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  const secret='token=secret-cookie account@example.test /api/v1/users/private payload'
  assert.equal(diagnostics.recordDiagnosticError(secret),false)
  assert.doesNotMatch(diagnostics.exportDiagnostics(),/secret-cookie|example\.test|private|payload/i)
  assert.equal(diagnostics.recordDiagnosticError('uncaught-error'),true)
  const error=diagnostics.diagnosticsSnapshot().anomalies.at(-1)
  assert.equal(error.name,'browser-error')
  assert.equal(error.detail,'uncaught-error')
})

test('missing and throwing Performance APIs safely degrade to unavailable',()=>{
  const runtime=runtimeMonitor({performanceThrows:true}),diagnostics=runtime.monitor
  const observation=diagnostics.beginApiObservation('/ingredients','GET','/api/v1/ingredients')
  const attempt=diagnostics.beginApiAttempt(observation,'/api/v1/ingredients')
  runtime.setClock(2200);diagnostics.finishApiAttempt(observation,attempt,{status:500});diagnostics.finishApiObservation(observation,{status:500,error:true})
  const item=diagnostics.diagnosticsSnapshot().anomalies.at(-1).attempts[0]
  assert.equal(item.timing_match,'unavailable')
  assert.equal(item.timing_missing_reason,'performance-api-unavailable')
})

test('monitoring entry points, storage, serialization, and individual subscribers are no-throw',()=>{
  const runtime=runtimeMonitor({storageThrows:true,performanceThrows:true}),diagnostics=runtime.monitor
  let notified=0
  diagnostics.subscribeDiagnostics(()=>{throw new Error('listener failure')})
  diagnostics.subscribeDiagnostics(()=>{notified+=1})
  assert.doesNotThrow(()=>diagnostics.setDiagnosticAdminAccess(true))
  assert.doesNotThrow(()=>diagnostics.setDetailedDiagnosticsEnabled(true))
  const observation=diagnostics.beginApiObservation('/menus/private?token=secret','GET','http://[')
  const attempt=diagnostics.beginApiAttempt(observation,'http://[')
  assert.doesNotThrow(()=>diagnostics.finishApiAttempt(observation,attempt,{status:500}))
  assert.doesNotThrow(()=>diagnostics.finishApiObservation(observation,{status:500,error:true}))
  assert.ok(notified>0)
  const serializationFailure=runtimeMonitor({jsonThrows:true})
  assert.equal(serializationFailure.monitor.exportDiagnostics(),'{"schema_version":2,"events":[],"anomalies":[]}')
})

test('route templates and JSON export remove queries, unknown segments, URLs, and secrets',()=>{
  const runtime=runtimeMonitor(),diagnostics=runtime.monitor
  assert.equal(diagnostics.sanitizeApiPath('/postpartum/cases/jane?token=secret'),'/postpartum/cases/:id')
  assert.equal(diagnostics.sanitizeApiPath('/unknown/jane'),'/api/:redacted')
  const observation=diagnostics.beginApiObservation('/postpartum/cases/jane?password=hidden','GET','/api/v1/postpartum/cases/jane?password=hidden')
  const attempt=diagnostics.beginApiAttempt(observation,'/api/v1/postpartum/cases/jane?password=hidden')
  runtime.setClock(2200);diagnostics.finishApiAttempt(observation,attempt,{status:500});diagnostics.finishApiObservation(observation,{status:500,error:true})
  const exported=diagnostics.exportDiagnostics()
  assert.match(exported,/"schema_version": 2/)
  assert.doesNotMatch(exported,/jane|password|hidden|https:\/\/example\.test/i)
})

test('administrator gating, pre-auth details, and old persisted records remain compatible',()=>{
  const legacy={id:'legacy',kind:'api',occurred_at:'2026-01-01T00:00:00Z',name:'/menus/private-short-slug?token=secret',duration_ms:2100,status:200,slow:true,token:'must-not-survive'}
  const allowed=runtimeMonitor({detailPreference:true,initialAnomalies:[legacy]})
  assert.equal(allowed.monitor.diagnosticsSnapshot().anomalies[0].id,'legacy')
  assert.equal(allowed.monitor.diagnosticsSnapshot().anomalies[0].name,'/menus/:id')
  assert.doesNotMatch(allowed.monitor.exportDiagnostics(),/private-short-slug|must-not-survive|token/i)
  allowed.monitor.startPageObservation('spa-startup')
  assert.equal(allowed.monitor.diagnosticsSnapshot().events.some(item=>item.kind==='detail'),false)
  allowed.monitor.setDiagnosticAdminAccess(true)
  assert.equal(allowed.monitor.diagnosticsSnapshot().events.some(item=>item.kind==='detail'),true)
  const denied=runtimeMonitor({detailPreference:true});denied.monitor.startPageObservation('spa-startup');denied.monitor.setDiagnosticAdminAccess(false)
  assert.equal(denied.monitor.diagnosticsSnapshot().events.some(item=>item.kind==='detail'),false)
  assert.match(app,/page==='diagnostics'&&user\.role==='admin'/)
  assert.match(page,/if\(!attempts\?\.length\)return null/)
})

test('page watchdog still replaces its pending record when loading completes',()=>{
  const runtime=runtimeMonitor();runtime.monitor.startPageObservation('menus')
  runtime.setClock(3200);runtime.runTimers(3000);runtime.monitor.markPageMounted('menus');runtime.runTimers(50)
  const pages=runtime.monitor.diagnosticsSnapshot().anomalies.filter(item=>item.kind==='page')
  assert.equal(pages.length,1);assert.equal(pages[0].detail,'completed-after-pending')
})

test('diagnostics page exposes attempts, network timings, export, clear, and manual detail toggle',()=>{
  assert.match(page,/效能診斷/)
  assert.match(page,/匯出 JSON/)
  assert.match(page,/清除紀錄/)
  assert.match(page,/詳細診斷模式/)
  assert.match(page,/HTTP 嘗試/)
  assert.match(page,/Timing：/)
  assert.match(page,/觀察→Fetch/)
  assert.match(page,/buffer 已滿/)
  assert.match(styles,/\.diagnostics-attempts/)
})
