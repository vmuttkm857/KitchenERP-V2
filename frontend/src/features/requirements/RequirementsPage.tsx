import { FormEvent, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import { Menu } from '../menus/types'

interface Paged<T> { items: T[]; pagination: { total: number } }
interface Anomaly { code:string; severity:'warning'|'error'; message:string; related_entity_name:string|null }
interface Row { row_key:string; ingredient_code:string; ingredient_name:string; supplier_name:string|null; requirement_quantity:string; requirement_unit:string; suggested_purchase_quantity:string|null; suggested_purchase_unit:string|null; configured_purchase_unit:string|null; package_size:string; minimum_order_quantity:string; current_price:string|null; estimated_cost:string|null; needs_review:boolean }
interface SupplierGroup { supplier_id:string|null; supplier_name:string; row_keys:string[]; known_estimated_cost:string; estimated_cost:string|null; needs_review:boolean }
interface Result { rows:Row[]; supplier_groups:SupplierGroup[]; known_estimated_cost:string; total_estimated_cost:string|null; anomalies:Anomaly[]; anomaly_summary:{total:number;errors:number;warnings:number} }

export function RequirementsPage() {
  const [menus,setMenus]=useState<Menu[]>([]); const [menuIds,setMenuIds]=useState<string[]>([])
  const [startDate,setStartDate]=useState(''); const [endDate,setEndDate]=useState('')
  const [result,setResult]=useState<Result|null>(null); const [grouped,setGrouped]=useState(false)
  const [loading,setLoading]=useState(false); const [error,setError]=useState('')
  useEffect(()=>{void apiRequest<Paged<Menu>>('/menus?page=1&page_size=100').then(data=>setMenus(data.items)).catch(()=>setError('菜單載入失敗'))},[])
  function toggle(id:string){setMenuIds(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id])}
  async function calculate(event:FormEvent){event.preventDefault();if(!menuIds.length){setError('請至少選擇一份菜單');return}setLoading(true);setError('');try{setResult(await apiRequest<Result>('/requirements/calculate',{method:'POST',body:JSON.stringify({menu_ids:menuIds,start_date:startDate||null,end_date:endDate||null})}))}catch{setError('需求量計算失敗，請檢查日期範圍與菜單資料')}finally{setLoading(false)}}
  const byKey=new Map(result?.rows.map(row=>[row.row_key,row]))
  return <section><div className="section-heading"><div><h2>需求量預覽</h2><small>此頁只讀取並計算現有菜單，不會建立需求單或修改資料。</small></div></div>
    <form className="requirements-form" onSubmit={calculate}><fieldset><legend>選擇菜單</legend><div className="menu-choices">{menus.map(menu=><label className="inline-check" key={menu.id}><input type="checkbox" checked={menuIds.includes(menu.id)} onChange={()=>toggle(menu.id)}/><span>{menu.name}（{menu.start_date}～{menu.end_date}）{!menu.is_active?'〔停用〕':''}</span></label>)}</div></fieldset><label>開始日期（選填）<input type="date" value={startDate} onChange={e=>setStartDate(e.target.value)}/></label><label>結束日期（選填）<input type="date" value={endDate} onChange={e=>setEndDate(e.target.value)}/></label><button disabled={loading}>{loading?'計算中…':'計算需求量'}</button></form>
    {error&&<p className="error">{error}</p>}{result&&<><div className="requirement-summary"><strong>已知成本：{result.known_estimated_cost}</strong><strong>完整預估成本：{result.total_estimated_cost??'無法完整估算'}</strong><span>異常：{result.anomaly_summary.errors} 錯誤／{result.anomaly_summary.warnings} 警告</span><button type="button" className="secondary" onClick={()=>setGrouped(value=>!value)}>{grouped?'顯示總表':'依供應商分組'}</button></div>
      {result.anomalies.length>0&&<div className="anomaly-list"><h3>資料提醒</h3><ul>{result.anomalies.map((item,index)=><li className={item.severity} key={`${item.code}-${index}`}><strong>{item.code}</strong>：{item.message}{item.related_entity_name&&`（${item.related_entity_name}）`}</li>)}</ul></div>}
      {grouped?result.supplier_groups.map(group=><div key={group.supplier_id??'none'}><h3>{group.supplier_name} — {group.estimated_cost??`已知 ${group.known_estimated_cost}`}</h3><RequirementTable rows={group.row_keys.map(key=>byKey.get(key)).filter((row):row is Row=>Boolean(row))}/></div>):<RequirementTable rows={result.rows}/>}</>}
  </section>
}

function RequirementTable({rows}:{rows:Row[]}){return <div className="requirements-table"><table><thead><tr><th>食材</th><th>供應商</th><th>需求量</th><th>建議採購量</th><th>採購設定（參考）</th><th>現價</th><th>預估成本</th><th>狀態</th></tr></thead><tbody>{rows.map(row=><tr key={row.row_key}><td>{row.ingredient_code}　{row.ingredient_name}</td><td>{row.supplier_name??'未指定'}</td><td>{row.requirement_quantity} {row.requirement_unit}</td><td>{row.suggested_purchase_quantity===null?'待確認':`${row.suggested_purchase_quantity} ${row.suggested_purchase_unit}`}</td><td>{row.configured_purchase_unit??'—'}／包裝 {row.package_size}／最低 {row.minimum_order_quantity}</td><td>{row.current_price??'缺少'}</td><td>{row.estimated_cost??'無法估算'}</td><td>{row.needs_review?'需確認':'正常'}</td></tr>)}</tbody></table>{rows.length===0&&<p>此條件沒有可計算的需求資料。</p>}</div>}
