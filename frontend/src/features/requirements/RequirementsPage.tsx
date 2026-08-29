import { FormEvent, useEffect, useState } from 'react'
import { apiDownload, apiRequest } from '../../api/client'
import { AnomalyGroups } from '../../components/anomalies/AnomalyGroups'
import { groupAnomalies,type Anomaly } from '../../components/anomalies/anomalies'
import { Menu } from '../menus/types'

interface Paged<T> { items: T[]; pagination: { total: number } }
interface Row { row_key:string; ingredient_code:string; ingredient_name:string; supplier_name:string|null; requirement_quantity:string; requirement_unit:string; suggested_purchase_quantity:string|null; suggested_purchase_unit:string|null; configured_purchase_unit:string|null; package_size:string; minimum_order_quantity:string; current_price:string|null; estimated_cost:string|null; needs_review:boolean }
interface SupplierGroup { supplier_id:string|null; supplier_name:string; row_keys:string[]; known_estimated_cost:string; estimated_cost:string|null; needs_review:boolean }
interface Result { rows:Row[]; supplier_groups:SupplierGroup[]; known_estimated_cost:string; total_estimated_cost:string|null; anomalies:Anomaly[]; anomaly_summary:{total:number;errors:number;warnings:number} }
type RangeMode='all'|'custom'
const costFormatter=new Intl.NumberFormat('zh-TW',{maximumFractionDigits:2})
function formatCost(value:string){const number=Number(value);return Number.isFinite(number)?costFormatter.format(number):value}

export function RequirementsPage() {
  const [menus,setMenus]=useState<Menu[]>([]); const [menuIds,setMenuIds]=useState<string[]>([])
  const [rangeMode,setRangeMode]=useState<RangeMode>('all')
  const [startDate,setStartDate]=useState(''); const [endDate,setEndDate]=useState('')
  const [result,setResult]=useState<Result|null>(null); const [grouped,setGrouped]=useState(false)
  const [loading,setLoading]=useState(false); const [error,setError]=useState('')
  const [snapshotMessage,setSnapshotMessage]=useState(''); const [savingSnapshot,setSavingSnapshot]=useState(false)
  useEffect(()=>{void apiRequest<Paged<Menu>>('/menus?page=1&page_size=100').then(data=>setMenus(data.items)).catch(()=>setError('菜單載入失敗'))},[])
  const selectedMenus=menus.filter(menu=>menuIds.includes(menu.id))
  const rangeMin=selectedMenus.length?selectedMenus.reduce((value,menu)=>menu.start_date<value?menu.start_date:value,selectedMenus[0].start_date):''
  const rangeMax=selectedMenus.length?selectedMenus.reduce((value,menu)=>menu.end_date>value?menu.end_date:value,selectedMenus[0].end_date):''
  const rangeError=rangeMode==='custom'&&(!startDate||!endDate)?'請同時選擇開始日期與結束日期。':rangeMode==='custom'&&startDate>endDate?'開始日期不可晚於結束日期。':rangeMode==='custom'&&rangeMin&&(startDate<rangeMin||endDate>rangeMax)?'日期必須落在已選菜單的可用範圍內。':''
  const criteriaDates=rangeMode==='custom'?{start_date:startDate,end_date:endDate}:{start_date:null,end_date:null}
  function toggle(id:string){setMenuIds(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id])}
  function changeRangeMode(mode:RangeMode){setRangeMode(mode);if(mode==='all'){setStartDate('');setEndDate('')}else{setStartDate(rangeMin);setEndDate(rangeMax)}}
  async function calculate(event:FormEvent){event.preventDefault();if(!menuIds.length){setError('請至少選擇一份菜單');return}if(rangeError)return;setLoading(true);setError('');try{setResult(await apiRequest<Result>('/requirements/calculate',{method:'POST',body:JSON.stringify({menu_ids:menuIds,...criteriaDates})}))}catch{setError('需求量計算失敗，請檢查日期範圍與菜單資料')}finally{setLoading(false)}}
  async function saveSnapshot(){if(rangeError)return;setSavingSnapshot(true);setSnapshotMessage('');try{await apiRequest('/requirement-snapshots',{method:'POST',body:JSON.stringify({criteria:{menu_ids:menuIds,...criteriaDates}})});setSnapshotMessage('固定需求快照已建立')}catch(error){setSnapshotMessage(error instanceof Error&&error.message.includes('409')?'相同條件的固定快照已存在':'固定快照建立失敗')}finally{setSavingSnapshot(false)}}
  async function download(){if(rangeError)return;setLoading(true);setError('');try{await apiDownload('/exports/requirements/xlsx',{method:'POST',body:JSON.stringify({menu_ids:menuIds,...criteriaDates})})}catch{setError('需求量 Excel 下載失敗')}finally{setLoading(false)}}
  const byKey=new Map(result?.rows.map(row=>[row.row_key,row]))
  const anomalyGroups=groupAnomalies(result?.anomalies??[])
  const issueKinds=anomalyGroups.filter(group=>group.severity==='error').length
  const affectedOccurrences=anomalyGroups.filter(group=>group.severity==='error').reduce((total,group)=>total+group.count,0)
  const reminderKinds=anomalyGroups.filter(group=>group.severity==='warning').length
  return <section><div className="section-heading"><div><h2>需求量預覽</h2><small>此頁只讀取並計算現有菜單，不會建立需求單或修改資料。</small></div></div>
    <form className="calculation-workflow" onSubmit={calculate}><fieldset className="workflow-step"><legend>① 選擇菜單</legend><strong>已選 {menuIds.length} 份菜單</strong><div className="menu-choices">{menus.map(menu=><label className="inline-check" key={menu.id}><input type="checkbox" checked={menuIds.includes(menu.id)} onChange={()=>toggle(menu.id)}/><span>{menu.name}（{menu.start_date}～{menu.end_date}）{!menu.is_active?'〔停用〕':''}</span></label>)}</div></fieldset><fieldset className="workflow-step"><legend>② 計算範圍</legend><div className="range-options"><label className="inline-check"><input type="radio" checked={rangeMode==='all'} onChange={()=>changeRangeMode('all')}/>全部已選菜單日期</label><label className="inline-check"><input type="radio" checked={rangeMode==='custom'} disabled={!menuIds.length} onChange={()=>changeRangeMode('custom')}/>自訂日期範圍</label></div>{rangeMode==='custom'&&<div className="date-range-fields"><label>開始日期<input type="date" min={rangeMin} max={rangeMax} value={startDate} onChange={e=>setStartDate(e.target.value)}/></label><label>結束日期<input type="date" min={rangeMin} max={rangeMax} value={endDate} onChange={e=>setEndDate(e.target.value)}/></label></div>}{rangeError&&<p className="error inline-validation">{rangeError}</p>}</fieldset><div className="workflow-submit"><strong>③ 計算</strong><button disabled={loading||Boolean(rangeError)}>{loading?'計算中…':'計算需求量'}</button></div></form>
    {error&&<p className="error">{error}</p>}{result&&<><div className="requirement-summary summary-cards"><div><small>預估成本</small><strong>{formatCost(result.total_estimated_cost??result.known_estimated_cost)}</strong><span>{result.total_estimated_cost===null?'部分食材缺少價格，總成本尚未完整':'成本資料完整'}</span></div><div><small>資料問題</small><strong>{issueKinds} 個</strong><span>影響 {affectedOccurrences} 筆菜單內容</span></div><div><small>提醒</small><strong>{reminderKinds} 項</strong><span>請依下方分組確認</span></div><button type="button" className="secondary" onClick={()=>setGrouped(value=>!value)}>{grouped?'顯示總表':'依供應商分組'}</button></div>
      <div className="snapshot-action"><button type="button" className="secondary" disabled={loading} onClick={()=>void download()}>下載 Excel</button><button type="button" disabled={savingSnapshot} onClick={()=>void saveSnapshot()}>{savingSnapshot?'儲存中…':'儲存為固定需求快照'}</button><small>快照建立後不受菜單、配方、食材或價格後續修改影響。</small>{snapshotMessage&&<strong>{snapshotMessage}</strong>}</div>
      <AnomalyGroups groups={anomalyGroups}/>
      {grouped?result.supplier_groups.map(group=><div key={group.supplier_id??'none'}><h3>{group.supplier_name} — {group.estimated_cost??`已知 ${group.known_estimated_cost}`}</h3><RequirementTable rows={group.row_keys.map(key=>byKey.get(key)).filter((row):row is Row=>Boolean(row))}/></div>):<RequirementTable rows={result.rows}/>}</>}
  </section>
}

function RequirementTable({rows}:{rows:Row[]}){return <div className="requirements-table"><table><thead><tr><th>食材</th><th>供應商</th><th>需求量</th><th>建議採購量</th><th>採購設定（參考）</th><th>現價</th><th>預估成本</th><th>狀態</th></tr></thead><tbody>{rows.map(row=><tr key={row.row_key}><td>{row.ingredient_code}　{row.ingredient_name}</td><td>{row.supplier_name??'未指定'}</td><td>{row.requirement_quantity} {row.requirement_unit}</td><td>{row.suggested_purchase_quantity===null?'待確認':`${row.suggested_purchase_quantity} ${row.suggested_purchase_unit}`}</td><td>{row.configured_purchase_unit??'—'}／包裝 {row.package_size}／最低 {row.minimum_order_quantity}</td><td>{row.current_price??'缺少'}</td><td>{row.estimated_cost??'無法估算'}</td><td>{row.needs_review?'需確認':'正常'}</td></tr>)}</tbody></table>{rows.length===0&&<p>此條件沒有可計算的需求資料。</p>}</div>}
