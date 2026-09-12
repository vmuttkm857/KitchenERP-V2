import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, apiDownload, apiRequest } from '../../api/client'
import { addYmdDays, todayTaipeiYmd } from './conflictTypes'
import type { CateringOverviewResponse } from './cateringOverviewTypes'

function serviceMoment(date:string|null,mealLabel:string|null){
  if(!date||!mealLabel)return '—'
  const [,month,day]=date.split('-').map(Number)
  return `${month}/${day} ${mealLabel}`
}

export function PostpartumCateringOverviewPage(){
  const [targetDate,setTargetDate]=useState(todayTaipeiYmd)
  const [data,setData]=useState<CateringOverviewResponse|null>(null)
  const [loading,setLoading]=useState(true),[error,setError]=useState('')
  const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState('')
  const requestSequence=useRef(0)
  const load=useCallback(async()=>{
    const request=++requestSequence.current;setLoading(true);setError('')
    try{
      const result=await apiRequest<CateringOverviewResponse>(`/postpartum/catering-overview?${new URLSearchParams({target_date:targetDate})}`)
      if(request===requestSequence.current)setData(result)
    }catch(cause){
      if(request===requestSequence.current){setData(null);setError(cause instanceof ApiError&&cause.status<500?cause.message:'供餐總覽載入失敗，請稍後再試。')}
    }finally{if(request===requestSequence.current)setLoading(false)}
  },[targetDate])
  useEffect(()=>{void load();return()=>{requestSequence.current+=1}},[load])
  async function exportWord(){
    setExporting(true);setExportError('')
    try{await apiDownload(`/postpartum/catering-overview.docx?${new URLSearchParams({target_date:targetDate})}`)}
    catch{setExportError('Word 供餐清單匯出失敗，請稍後再試。')}
    finally{setExporting(false)}
  }
  return <section className="postpartum-catering-page">
    <div className="section-heading"><div><h2>月子餐個案供餐總覽</h2><small>依日期核對當日需供餐個案、禁忌與備註。</small></div><button type="button" disabled={exporting||loading} onClick={()=>void exportWord()}>{exporting?'匯出中…':'匯出 Word'}</button></div>
    <div className="postpartum-catering-toolbar"><button type="button" className="secondary" onClick={()=>setTargetDate(value=>addYmdDays(value,-1))}>前一天</button><button type="button" className="secondary" onClick={()=>setTargetDate(todayTaipeiYmd())}>今天</button><button type="button" className="secondary" onClick={()=>setTargetDate(value=>addYmdDays(value,1))}>下一天</button><label>供餐日期<input type="date" value={targetDate} onChange={event=>setTargetDate(event.target.value)}/></label></div>
    {error&&<p className="error">{error}</p>}{exportError&&<p className="error">{exportError}</p>}
    {loading?<p>供餐總覽載入中…</p>:data&&<>
      <div className="postpartum-catering-summary"><strong>{data.target_date.replace(/^(\d{4})-(\d{2})-(\d{2})$/,'$1 年 $2 月 $3 日')}（{data.weekday_label}）</strong><span>共 {data.total} 位供餐個案</span></div>
      {data.items.length===0?<div className="empty-state">本日無月子餐供餐個案</div>:<div className="table-frame postpartum-catering-table"><table><thead><tr><th>床號</th><th>姓名</th><th>調理方式</th><th>飲食禁忌／備註</th></tr></thead><tbody>{data.items.map(item=><tr key={item.case_id}><td className="postpartum-catering-room">{item.current_room}</td><td className="postpartum-catering-person"><strong>{item.name}</strong><small>起伙：{serviceMoment(item.service_start_date,item.service_start_meal_label)}</small></td><td>{item.preparation_mode_label}</td><td><div className="postpartum-catering-combined">{item.restriction_groups.length>0&&<div className="postpartum-catering-restrictions">{item.restriction_groups.map(group=><span key={group.id} style={{borderColor:group.color}}>{group.name}{!group.is_active&&<small> 已停用</small>}</span>)}</div>}{item.service_note&&<p className="postpartum-catering-note">{item.service_note}</p>}{item.restriction_groups.length===0&&!item.service_note&&<span className="muted">—</span>}</div></td></tr>)}</tbody></table></div>}
    </>}
  </section>
}
