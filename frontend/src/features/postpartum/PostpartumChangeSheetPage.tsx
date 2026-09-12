import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../../api/client'
import { addYmdDays, todayTaipeiYmd } from './conflictTypes'
import type {
  ChangeSheetAcknowledgement, ChangeSheetDailyResponse, ChangeSheetMealResponse,
  ChangeSheetReconfirmationItem, ChangeSheetRestrictionGroup, ChangeSheetWarning,
} from './changeSheetTypes'
import './PostpartumChangeSheetPage.css'

function WarningDetails({items}:{items:ChangeSheetWarning[]}){
  const messages=[...new Set(items.map(item=>item.message).filter(Boolean))]
  if(messages.length===0)return null
  return <details className="postpartum-change-warning-details"><summary>查看詳情</summary><ul>{messages.map(message=><li key={message}>{message}</li>)}</ul></details>
}

function RestrictionBadges({groups}:{groups:ChangeSheetRestrictionGroup[]}){
  if(groups.length===0)return null
  return <div className="postpartum-change-restrictions">{groups.map(group=><span key={group.id} style={{borderColor:group.color}}>{group.name}</span>)}</div>
}

function ReconfirmationItem({item}:{item:ChangeSheetReconfirmationItem}){
  return <article className="postpartum-change-reconfirmation-item" data-handling-id={item.handling_id}>
    <div><strong>{item.current_room}｜{item.case_name}</strong><small>{item.case_number}</small></div>
    <p>{item.original_dish.code}　{item.original_dish.name}</p>
    <p>{item.handling_type==='replacement'?`原處理：替代為 ${item.replacement_dish?.code??''} ${item.replacement_dish?.name??'—'}`:'原處理：人工確認不需替代'}</p>
    {item.warnings.length>0&&<WarningDetails items={item.warnings}/>}
  </article>
}

function AcknowledgementRow({item}:{item:ChangeSheetAcknowledgement}){
  const stale=item.status==='requires_reconfirmation'
  return <div className={`postpartum-change-ack-row ${stale?'is-warning':''}`} data-handling-id={item.handling_id}>
    <strong>{item.current_room}</strong><span><b>{item.case_name}</b><small>{item.case_number}</small></span>
    <span>{item.original_dish.code}　{item.original_dish.name}</span>
    <b>{stale?'⚠ 待重新確認':'不需替代'}</b>
    <span>{item.note||'—'}</span>
    {!stale&&item.warnings.length>0&&<WarningDetails items={item.warnings}/>}
  </div>
}

function MealSection({meal}:{meal:ChangeSheetMealResponse}){
  if(!meal.has_changes)return <section className="postpartum-change-meal-empty" aria-label={`${meal.meal_label}無異動`}><strong>{meal.meal_label}</strong><span>無異動</span></section>
  return <section className="postpartum-change-meal">
    <header><h3>【{meal.meal_label}】</h3><span>替代 {meal.summary.replacement_item_count} 項｜人工確認 {meal.summary.manual_acknowledgement_count} 項</span></header>
    {meal.replacement_groups.length>0&&<section className="postpartum-change-meal-block"><h4>廚房製作</h4><div className="postpartum-change-production-list">{meal.replacement_groups.map(group=><article key={group.group_id} className={group.status==='requires_reconfirmation'?'is-warning':''}>
      {group.status==='requires_reconfirmation'?<><b className="postpartum-change-warning-label">⚠ 待重新確認</b><p className="postpartum-change-reconfirm-copy">此替代內容尚需營養師重新確認</p></>:<b className="postpartum-change-ok-label">已設定替代</b>}
      <div className="postpartum-change-production-main"><h5>{group.replacement_dish.code}　{group.replacement_dish.name}</h5><strong>{group.quantity} 份</strong></div>
      <p>床號：{group.case_rooms.length?group.case_rooms.join('、'):'—'}</p>
      {group.note&&<p className="postpartum-change-note">備註：{group.note}</p>}
      {group.warnings.length>0&&<WarningDetails items={group.warnings}/>}
    </article>)}</div></section>}
    {meal.replacement_groups.some(group=>group.items.length>0)&&<section className="postpartum-change-meal-block"><h4>個案異動</h4><div className="postpartum-change-detail-table" role="table" aria-label={`${meal.meal_label}個案異動`}>
      <div className="postpartum-change-detail-head" role="row"><b>床號</b><b>個案</b><b>原菜</b><b aria-label="改為">→</b><b>替代菜</b><b>禁忌</b></div>
      {meal.replacement_groups.flatMap(group=>group.items.map(item=><div className={`postpartum-change-detail-row ${item.status==='requires_reconfirmation'?'is-warning':''}`} role="row" key={item.handling_id}>
        <strong>{item.current_room}</strong><span><b>{item.case_name}</b><small>{item.case_number}</small></span><span>{item.original_dish.code}　{item.original_dish.name}</span><span aria-hidden="true">→</span><span>{item.replacement_dish.code}　{item.replacement_dish.name}</span><RestrictionBadges groups={item.restriction_groups}/>
        {item.status==='requires_reconfirmation'&&<strong className="postpartum-change-row-warning">⚠ 待重新確認</strong>}{item.warnings.length>0&&<WarningDetails items={item.warnings}/>}
      </div>))}
    </div></section>}
    {meal.manual_acknowledgements.length>0&&<section className="postpartum-change-meal-block"><h4>人工確認｜不需替代</h4><div className="postpartum-change-ack-table"><div className="postpartum-change-ack-head"><b>床號</b><b>個案</b><b>原菜</b><b>結果</b><b>備註</b></div>{meal.manual_acknowledgements.map(item=><AcknowledgementRow key={item.handling_id} item={item}/>)}</div></section>}
    {meal.requires_reconfirmation.length>0&&<section className="postpartum-change-meal-block is-reconfirmation"><h4>⚠ 待重新確認 {meal.requires_reconfirmation.length} 項</h4><div className="postpartum-change-reconfirmation-list">{meal.requires_reconfirmation.map(item=><ReconfirmationItem key={`${item.handling_type}-${item.handling_id}`} item={item}/>)}</div></section>}
    {meal.warnings.length>0&&<WarningDetails items={meal.warnings}/>}
  </section>
}

export function PostpartumChangeSheetPage({onOpenConflicts}:{onOpenConflicts?:()=>void}){
  const [targetDate,setTargetDate]=useState(todayTaipeiYmd)
  const [data,setData]=useState<ChangeSheetDailyResponse|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('')
  const requestSequence=useRef(0)
  const load=useCallback(async()=>{
    const request=++requestSequence.current;setLoading(true);setError('')
    try{
      const query=new URLSearchParams({target_date:targetDate})
      const result=await apiRequest<ChangeSheetDailyResponse>(`/postpartum/change-sheet/daily?${query}`)
      if(request===requestSequence.current)setData(result)
    }catch(cause){
      if(request===requestSequence.current){setData(null);setError(cause instanceof ApiError&&cause.status<500?cause.message:'每日異動單載入失敗，請稍後再試。')}
    }finally{if(request===requestSequence.current)setLoading(false)}
  },[targetDate])
  useEffect(()=>{void load();return()=>{requestSequence.current+=1}},[load])
  const isEmpty=Boolean(data&&data.summary.replacement_item_count===0&&data.summary.manual_acknowledgement_count===0&&data.summary.requires_reconfirmation_count===0)

  return <section className="postpartum-change-sheet-page">
    <div className="section-heading"><div><h2>月子餐每日異動單</h2><small>依日期查看當日六餐異動，供廚房製作與核對。</small></div>{onOpenConflicts&&<button type="button" className="secondary" onClick={onOpenConflicts}>前往禁忌總覽處理</button>}</div>
    <div className="postpartum-change-controls"><div className="postpartum-change-date-nav"><button type="button" onClick={()=>setTargetDate(addYmdDays(targetDate,-1))}>前一天</button><button type="button" onClick={()=>setTargetDate(todayTaipeiYmd())}>今天</button><button type="button" onClick={()=>setTargetDate(addYmdDays(targetDate,1))}>下一天</button><label>日期<input type="date" required value={targetDate} onChange={event=>setTargetDate(event.target.value)}/></label></div></div>
    {error&&<div className="feedback feedback-error"><p>{error}</p><button type="button" onClick={()=>void load()}>重新載入</button></div>}
    {loading?<div className="state-panel"><span className="spinner"/>每日異動單載入中…</div>:data&&<>
      <div className="postpartum-change-context"><strong>{data.target_date}</strong><div><span>替代製作：{data.summary.replacement_item_count} 項</span><span>人工確認：{data.summary.manual_acknowledgement_count} 項</span><span>待重新確認：{data.summary.requires_reconfirmation_count} 項</span></div></div>
      {data.summary.requires_reconfirmation_count>0&&<div className="feedback feedback-warning postpartum-change-reconfirmation-alert">⚠ 今日共有 {data.summary.requires_reconfirmation_count} 項異動需要重新確認</div>}
      {data.warnings.length>0&&<WarningDetails items={data.warnings}/>} 
      {isEmpty&&<p className="postpartum-change-day-empty">今日六餐目前沒有月子餐異動。</p>}
      <div className="postpartum-change-day-meals">{data.meals.map(meal=><MealSection key={meal.postpartum_meal} meal={meal}/>)}</div>
    </>}
  </section>
}
