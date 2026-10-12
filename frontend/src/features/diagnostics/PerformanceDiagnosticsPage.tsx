import { useEffect,useMemo,useState } from 'react'

import { PageHeader,TableFrame } from '../../components/ui/Page'
import { clearDiagnostics,diagnosticsSnapshot,exportDiagnostics,setDetailedDiagnosticsEnabled,subscribeDiagnostics,type DiagnosticEvent } from '../../monitoring/performanceMonitor'

const kindLabels:Record<DiagnosticEvent['kind'],string>={api:'API',page:'頁面',auth_refresh:'認證更新',api_401:'401 重試',error:'錯誤',detail:'詳細事件'}

function duration(value:number|null){return value===null?'—':`${value.toLocaleString('zh-TW',{maximumFractionDigits:1})} ms`}
function statusClass(item:DiagnosticEvent){return item.error?'is-error':item.slow?'is-slow':''}
function downloadJson(){
  const url=URL.createObjectURL(new Blob([exportDiagnostics()],{type:'application/json'}))
  const anchor=document.createElement('a');anchor.href=url;anchor.download=`KitchenERP-performance-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;anchor.click()
  window.setTimeout(()=>URL.revokeObjectURL(url),0)
}

function EventTable({items,empty}:{items:DiagnosticEvent[];empty:string}){
  if(!items.length)return <p className="state-panel empty-state">{empty}</p>
  return <TableFrame><table className="diagnostics-table"><thead><tr><th>時間</th><th>類型</th><th>頁面</th><th>項目</th><th>方法／狀態</th><th>耗時</th><th>Request ID</th></tr></thead><tbody>{items.map(item=><tr className={statusClass(item)} key={item.id}><td>{new Date(item.occurred_at).toLocaleString('zh-TW')}</td><td>{kindLabels[item.kind]}</td><td>{item.page??'—'}</td><td><code>{item.name}</code>{item.detail&&<small>{item.detail}</small>}</td><td>{item.method??'—'}{item.status!==null?` / ${item.status}`:''}</td><td>{duration(item.duration_ms)}</td><td><code>{item.request_id??'—'}</code></td></tr>)}</tbody></table></TableFrame>
}

export function PerformanceDiagnosticsPage(){
  const [snapshot,setSnapshot]=useState(diagnosticsSnapshot),[confirmClear,setConfirmClear]=useState(false)
  useEffect(()=>subscribeDiagnostics(()=>setSnapshot(diagnosticsSnapshot())),[])
  const api=useMemo(()=>snapshot.events.filter(item=>item.kind==='api'||item.kind==='auth_refresh'||item.kind==='api_401').slice(-100).reverse(),[snapshot.events])
  const pages=useMemo(()=>snapshot.events.filter(item=>item.kind==='page').slice(-50).reverse(),[snapshot.events])
  const anomalies=[...snapshot.anomalies].reverse()
  return <section className="diagnostics-page">
    <PageHeader title="效能診斷" description="紀錄只保存在這個瀏覽器，不會自動上傳，也不包含 Token、Cookie、內容或個人資料。" actions={<><button type="button" className="secondary" onClick={downloadJson}>匯出 JSON</button><button type="button" className="secondary-danger" onClick={()=>setConfirmClear(true)}>清除紀錄</button></>}/>
    <div className="diagnostics-controls"><div><strong>詳細診斷模式</strong><small>啟用後額外記錄請求階段與瀏覽器可提供的 Resource Timing；缺少的網路階段會顯示「—」，不視為 0 ms。</small></div><label className="inline-check"><input type="checkbox" checked={snapshot.detailed_enabled} onChange={event=>setDetailedDiagnosticsEnabled(event.target.checked)}/>{snapshot.detailed_enabled?'已啟用':'已關閉'}</label></div>
    <div className="diagnostics-summary"><div><small>記憶體紀錄</small><strong>{snapshot.events.length} / 500</strong></div><div><small>本機異常紀錄</small><strong>{snapshot.anomalies.length} / 20</strong></div><div><small>慢 API</small><strong>{snapshot.events.filter(item=>item.kind==='api'&&item.slow).length}</strong></div><div><small>401</small><strong>{snapshot.events.filter(item=>item.kind==='api_401').length}</strong></div></div>
    <section><h2>慢請求與錯誤紀錄</h2><p>API 超過 2 秒、頁面超過 3 秒、401 或錯誤會保留在瀏覽器本機。</p><EventTable items={anomalies} empty="目前沒有異常紀錄。"/></section>
    <section><h2>最近 API 耗時</h2><EventTable items={api} empty="尚無 API 紀錄。"/></section>
    <section><h2>最近頁面載入耗時</h2><EventTable items={pages} empty="尚無頁面載入紀錄。"/></section>
    {snapshot.detailed_enabled&&<section><h2>Resource Timing 說明</h2><p>瀏覽器可能因連線重用、同源限制或 Timing-Allow-Origin 而無法提供 DNS、TCP、TLS 階段；匯出檔會以 null 表示缺失。可取得時會記錄 DNS、TCP、TLS、requestStart→responseStart、responseStart→responseEnd。</p></section>}
    {confirmClear&&<div className="modal-backdrop"><section className="modal-panel compact" role="dialog" aria-modal="true"><h2>清除效能診斷紀錄？</h2><p>這會清除目前記憶體與這個瀏覽器保存的異常紀錄。</p><footer><button type="button" className="secondary" onClick={()=>setConfirmClear(false)}>取消</button><button type="button" className="danger" onClick={()=>{clearDiagnostics();setConfirmClear(false)}}>清除</button></footer></section></div>}
  </section>
}
