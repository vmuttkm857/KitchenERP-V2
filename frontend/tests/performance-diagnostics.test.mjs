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

function runtimeMonitor({detailPreference=false,storageThrows=false,performanceThrows=false,jsonThrows=false}={}){
  let clock=0,timerId=0
  const timers=new Map()
  const storage=new Map(detailPreference?[['kitchenerp.performance.detailed.v1','true']]:[])
  const performance={now:()=>clock,getEntriesByName:()=>{if(performanceThrows)throw new Error('timing unavailable');return []}}
  const runtimeJson={parse:JSON.parse,stringify:(...args)=>{if(jsonThrows)throw new Error('serialization failed');return JSON.stringify(...args)}}
  const sandbox={exports:{},module:{exports:{}},Date,URL,JSON:runtimeJson,performance,
    localStorage:{getItem:key=>{if(storageThrows)throw new Error('storage denied');return storage.get(key)??null},setItem:(key,value)=>{if(storageThrows)throw new Error('quota');storage.set(key,value)},removeItem:key=>{if(storageThrows)throw new Error('storage denied');storage.delete(key)}},
    window:{location:{origin:'https://example.test'},setTimeout:(callback,delay)=>{const id=++timerId;timers.set(id,{callback,delay});return id},clearTimeout:id=>timers.delete(id),addEventListener:()=>{}},
    setTimeout:(callback,delay)=>{const id=++timerId;timers.set(id,{callback,delay});return id},clearTimeout:id=>timers.delete(id),console}
  sandbox.module.exports=sandbox.exports
  const compiled=ts.transpileModule(monitor,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  vm.runInNewContext(compiled,sandbox)
  return {monitor:sandbox.module.exports,setClock:value=>{clock=value},runTimers:delay=>{for(const [id,timer] of [...timers])if(timer.delay===delay){timers.delete(id);timer.callback()}},timers,storage}
}

test('performance monitor keeps bounded memory and persisted anomaly history',()=>{
  assert.match(monitor,/const MEMORY_LIMIT=500/)
  assert.match(monitor,/const ANOMALY_LIMIT=20/)
  assert.match(monitor,/upsert\(events,event,MEMORY_LIMIT\)/)
  assert.match(monitor,/upsert\(anomalies,event,ANOMALY_LIMIT\)/)
  assert.match(monitor,/localStorage\.setItem\(key,value\)/)
})

test('slow thresholds and identifiers are privacy-safe',()=>{
  assert.match(monitor,/const API_SLOW_MS=2000/)
  assert.match(monitor,/const PAGE_SLOW_MS=3000/)
  assert.match(monitor,/input\.split\(\/\[\?#\]\//)
  assert.match(monitor,/return ':id'/)
  assert.doesNotMatch(monitor,/request_body|response_body|access_token|refresh_token/i)
})

test('detailed mode is effective only with administrator access',()=>{
  assert.match(monitor,/function detailed\(\)\{return adminAllowed===true&&detailedPreference\}/)
  assert.match(monitor,/if\(adminAllowed!==true\)return false/)
  assert.match(app,/setDiagnosticAdminAccess\(user\?\.role==='admin'\)/)
  assert.match(app,/if\(isLoading\)return/)
  assert.match(app,/page==='diagnostics'&&user\.role==='admin'/)
})

test('API client records timings, request ids, 401 retries, and completion',()=>{
  assert.match(client,/safeBeginObservation/)
  assert.match(client,/safeMark401\(observation\)/)
  assert.match(client,/safeFinishObservation/)
  assert.match(client,/function safeRequestId/)
  assert.match(client,/if \(refreshPromise\) return refreshPromise/)
  assert.match(client,/response\.status === 401 && accessToken && !path\.startsWith\('\/auth\/'\)/)
  assert.match(client,/X-Request-Id/i)
  assert.match(client,/`\$\{apiBaseUrl\}\$\{path\}`/)
})

test('monitoring entry points and individual subscribers are no-throw',()=>{
  const runtime=runtimeMonitor({storageThrows:true,performanceThrows:true})
  const diagnostics=runtime.monitor
  let notified=0
  assert.doesNotThrow(()=>diagnostics.setDiagnosticAdminAccess(true))
  assert.doesNotThrow(()=>diagnostics.setDetailedDiagnosticsEnabled(true))
  diagnostics.subscribeDiagnostics(()=>{throw new Error('listener failure')})
  diagnostics.subscribeDiagnostics(()=>{notified+=1})
  let observation
  assert.doesNotThrow(()=>{observation=diagnostics.beginApiObservation('/menus/private?token=secret','GET','http://[')})
  assert.doesNotThrow(()=>diagnostics.markApi401(observation))
  assert.doesNotThrow(()=>diagnostics.finishApiObservation(observation,{status:200}))
  assert.doesNotThrow(()=>diagnostics.clearDiagnostics())
  assert.ok(notified>0)
  const serializationFailure=runtimeMonitor({jsonThrows:true})
  assert.doesNotThrow(()=>serializationFailure.monitor.exportDiagnostics())
  assert.equal(serializationFailure.monitor.exportDiagnostics(),'{"schema_version":1,"events":[],"anomalies":[]}')
})

test('pre-auth detailed data is hidden then promoted only for an administrator',()=>{
  const allowed=runtimeMonitor({detailPreference:true})
  allowed.monitor.startPageObservation('spa-startup')
  assert.equal(allowed.monitor.diagnosticsSnapshot().events.some(item=>item.kind==='detail'),false)
  allowed.monitor.setDiagnosticAdminAccess(true)
  assert.equal(allowed.monitor.diagnosticsSnapshot().events.some(item=>item.kind==='detail'),true)

  const denied=runtimeMonitor({detailPreference:true})
  denied.monitor.startPageObservation('spa-startup')
  denied.monitor.setDiagnosticAdminAccess(false)
  assert.equal(denied.monitor.diagnosticsSnapshot().events.some(item=>item.kind==='detail'),false)
})

test('pending watchdog records once and completion updates the same API event',()=>{
  const runtime=runtimeMonitor()
  const observation=runtime.monitor.beginApiObservation('/menus/123e4567-e89b-12d3-a456-426614174000','GET')
  runtime.setClock(3100)
  runtime.runTimers(3000)
  let snapshot=runtime.monitor.diagnosticsSnapshot()
  assert.equal(snapshot.anomalies.length,1)
  assert.equal(snapshot.anomalies[0].detail,'request-pending')
  runtime.monitor.finishApiObservation(observation,{status:200})
  snapshot=runtime.monitor.diagnosticsSnapshot()
  assert.equal(snapshot.anomalies.length,1)
  assert.equal(snapshot.anomalies[0].id,observation.id)
  assert.equal(snapshot.anomalies[0].detail,'completed-after-pending')
  assert.equal(runtime.timers.size,0)
  assert.equal(snapshot.events.find(item=>item.id===observation.id).name,'/menus/:id')
})

test('page watchdog leaves a pending record and replaces it when the page completes',()=>{
  const runtime=runtimeMonitor()
  runtime.monitor.startPageObservation('menus')
  runtime.setClock(3200)
  runtime.runTimers(3000)
  assert.equal(runtime.monitor.diagnosticsSnapshot().anomalies.filter(item=>item.kind==='page').length,1)
  runtime.monitor.markPageMounted('menus')
  runtime.runTimers(50)
  const pages=runtime.monitor.diagnosticsSnapshot().anomalies.filter(item=>item.kind==='page')
  assert.equal(pages.length,1)
  assert.equal(pages[0].detail,'completed-after-pending')
})

test('global browser errors are recorded without persisting exception messages',()=>{
  assert.match(monitor,/window\.addEventListener\('error',\(\)=>recordDiagnosticError\('browser-error','uncaught-error'\)\)/)
  assert.match(monitor,/window\.addEventListener\('unhandledrejection'/)
})

test('diagnostics page exposes export, clear, toggle, timings and nullable resource timing explanation',()=>{
  assert.match(page,/效能診斷/)
  assert.match(page,/匯出 JSON/)
  assert.match(page,/清除紀錄/)
  assert.match(page,/詳細診斷模式/)
  assert.match(page,/最近 API 耗時/)
  assert.match(page,/最近頁面載入耗時/)
  assert.match(page,/null 表示缺失/)
  assert.match(styles,/\.diagnostics-table tr\.is-error/)
})
