import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../../api/client'
import {
  addYmdDays, conflictOutcomeLabel, findHandlingContext, formatWeekDate, selectionMatchesMeal, summaryLabel, todayTaipeiYmd, unavailableMessage,
  type ConflictCase, type ConflictCaseDishResult, type ConflictMealSummary, type ConflictReason,
  type ConflictWarning, type PostpartumConflictDailyResponse, type PostpartumConflictResponse,
  type PostpartumConflictWeeklyResponse, type ConflictHandlingResponse, type ConflictItemStatus,
  type ReplacementGroup, type ConflictAcknowledgement,
} from './conflictTypes'
import { mealLabel, POSTPARTUM_MEALS, type Meal } from './types'
import {
  AcknowledgementDialog, conflictItemKey, HandlingOverview, ReplacementDialog,
  type SelectedConflict,
} from './PostpartumConflictHandling'
import './PostpartumConflictPage.css'

type ViewMode='daily'|'weekly'
type MealFilter='all'|Meal

function WarningList({items}:{items:ConflictWarning[]}){
  if(items.length===0)return null
  return <ul className="postpartum-conflict-warnings">{items.map((item,index)=><li key={`${item.code}-${item.target_id??item.restriction_group_id??item.menu_dish_id??'general'}-${index}`}>⚠ {item.message}</li>)}</ul>
}

function SummaryBadge({summary}:{summary:ConflictMealSummary}){
  return <span className={`postpartum-conflict-summary-value is-${summary.status}`}>{summaryLabel(summary)}</span>
}

function StatusMark({status}:{status:ConflictMealSummary['status']}){
  if(status==='conflict')return <span className="postpartum-conflict-status-mark is-conflict" aria-label="有衝突"/>
  if(status==='partial'||status==='unavailable')return <span className="postpartum-conflict-status-mark is-warning" aria-label="需注意">!</span>
  if(status==='complete')return <span className="postpartum-conflict-status-mark is-complete" aria-label="未發現衝突">✓</span>
  return <span className="postpartum-conflict-status-mark is-unmapped" aria-label="未設定">—</span>
}

function SelectorStatus({summary}:{summary:ConflictMealSummary}){
  const text=summary.status==='conflict'?`${summary.conflict_case_count}人・${summary.conflict_count}項`:summary.status==='partial'?(summary.manual_review_case_count>0?`${summary.manual_review_case_count}人需確認`:'需確認'):summary.status==='unavailable'?'無法檢查':summary.status==='complete'?'正常':''
  return <span className={`postpartum-conflict-selector-status is-${summary.status}`}><StatusMark status={summary.status}/>{text&&<b>{text}</b>}</span>
}

function MealSummaryBar({data,selected,onChoose}:{data:PostpartumConflictDailyResponse;selected:MealFilter;onChoose:(meal:MealFilter)=>void}){
  const allStatus:ConflictMealSummary['status']=data.conflict_count>0?'conflict':data.manual_review_case_count>0?'partial':data.summaries.some(item=>item.status==='complete')?'complete':'unmapped'
  const allText=allStatus==='conflict'?`${data.conflict_case_count}人・${data.conflict_count}項`:allStatus==='partial'?`${data.manual_review_case_count}人需確認`:allStatus==='complete'?'正常':''
  return <div className="postpartum-conflict-meal-summary" aria-label="六餐禁忌摘要">
    <button type="button" className={selected==='all'?'is-highlighted':''} onClick={()=>onChoose('all')}><strong>全部</strong><span className={`postpartum-conflict-selector-status is-${allStatus}`}><StatusMark status={allStatus}/>{allText&&<b>{allText}</b>}</span></button>
    {data.summaries.map(summary=><button type="button" key={summary.postpartum_meal} className={selected===summary.postpartum_meal?'is-highlighted':''} onClick={()=>onChoose(summary.postpartum_meal)}>
      <strong>{mealLabel(summary.postpartum_meal)}</strong><SelectorStatus summary={summary}/>
    </button>)}
  </div>
}

function MealNotices({meals,filter}:{meals:PostpartumConflictResponse[];filter:MealFilter}){
  const unavailable=meals.filter(item=>!item.evaluation_performed&&item.mapping_resolution.status!=='not_mapped'&&(filter==='all'||item.postpartum_meal===filter))
  if(unavailable.length===0)return null
  const grouped=new Map<string,{labels:string[];message:string;warnings:ConflictWarning[]}>()
  for(const item of unavailable){
    const message=unavailableMessage(item)
    const key=`${message}:${item.warnings.map(warning=>`${warning.code}:${warning.message}`).join('|')}`
    const value=grouped.get(key)??{labels:[],message,warnings:item.warnings}
    value.labels.push(mealLabel(item.postpartum_meal));grouped.set(key,value)
  }
  return <section className="postpartum-conflict-day-notices">
    {[...grouped.values()].map(item=><div key={`${item.labels.join('-')}-${item.message}`} className="is-warning">
      <strong>{item.labels.join('、')}</strong><span>{item.message}</span><WarningList items={item.warnings}/>
    </div>)}
  </section>
}

interface DailyCaseMeal {meal:PostpartumConflictResponse;caseItem:ConflictCase;results:ConflictCaseDishResult[]}
interface DailyCaseView {caseItem:ConflictCase;meals:DailyCaseMeal[]}

function buildDailyCases(data:PostpartumConflictDailyResponse):DailyCaseView[]{
  const cases=new Map<string,DailyCaseView>()
  for(const meal of data.meals){
    for(const caseItem of meal.eligible_cases){
      const view=cases.get(caseItem.id)??{caseItem,meals:[]}
      view.meals.push({meal,caseItem,results:meal.case_dish_results.filter(item=>item.case_id===caseItem.id)})
      cases.set(caseItem.id,view)
    }
  }
  return [...cases.values()]
}

function uniqueWarnings(entries:DailyCaseMeal[]){
  const values=new Map<string,ConflictWarning>()
  for(const entry of entries){
    for(const warning of [...entry.caseItem.warnings,...entry.meal.warnings]){
      const key=`${warning.code}:${warning.restriction_group_id??''}:${warning.target_id??''}:${warning.message}`
      if(!values.has(key))values.set(key,warning)
    }
  }
  return [...values.values()]
}

function entryState(entry:DailyCaseMeal){
  const conflicts=entry.results.filter(item=>item.outcome==='conflict')
  const manual=entry.results.some(item=>item.coverage==='partial')||entry.caseItem.warnings.length>0||entry.meal.warnings.length>0
  return {conflicts:conflicts.length,manual,status:conflicts.length>0?'conflict':manual?'partial':'complete'} as const
}

function GroupedReasons({reasons}:{reasons:ConflictReason[]}){
  const groups=new Map<string,{group:ConflictReason['restriction_group'];direct:boolean;ingredients:string[];inactiveTarget:boolean}>()
  for(const reason of reasons){
    const value=groups.get(reason.restriction_group.id)??{group:reason.restriction_group,direct:false,ingredients:[],inactiveTarget:false}
    if(reason.type==='direct_dish')value.direct=true
    else if(!value.ingredients.includes(reason.matched_target.name))value.ingredients.push(reason.matched_target.name)
    value.inactiveTarget ||= !reason.matched_target.is_active
    groups.set(reason.restriction_group.id,value)
  }
  return <div className="postpartum-conflict-hit-lines">{[...groups.values()].map(value=><p key={value.group.id}>
    <span className="postpartum-conflict-hit-dot">🔴</span><b>{value.group.name}{!value.group.is_active?'（已停用）':''}</b>
    <span>{[value.direct?'菜色命中':'',value.ingredients.length>0?`食材：${value.ingredients.join('、')}`:''].filter(Boolean).join(' · ')}</span>
    {value.inactiveTarget&&<em>關聯目標已停用</em>}
  </p>)}</div>
}

function handlingText(item:ConflictItemStatus|null){
  if(!item||item.status==='pending')return '未處理衝突'
  if(item.status==='replaced')return '已設定共同替代'
  if(item.status==='manually_acknowledged')return '人工確認｜不需替代'
  return '需要重新確認'
}

function MealDetails({entry,handling,selected,selectedMeal,onToggle,onEditGroup,onReprocessAcknowledgement}:{entry:DailyCaseMeal;handling:ConflictHandlingResponse|undefined;selected:Set<string>;selectedMeal:Meal|null;onToggle:(item:SelectedConflict)=>void;onEditGroup:(group:ReplacementGroup)=>void;onReprocessAcknowledgement:(item:ConflictAcknowledgement)=>void}){
  const dishById=new Map(entry.meal.menu_dishes.map(item=>[item.menu_dish_id,item]))
  const problems=entry.results.filter(item=>item.outcome==='conflict'||item.coverage==='partial')
  return <section className="postpartum-conflict-case-meal">
    <header><h4>{mealLabel(entry.meal.postpartum_meal)}</h4><small>{entry.meal.source_resolution.source?.menu_name??'—'}｜{entry.meal.mapping_resolution.menu_meal_type?.name??'—'}</small></header>
    {problems.length===0?<p className="postpartum-conflict-safe">✓ 未發現衝突</p>:<div className="postpartum-conflict-dish-rows">{problems.map(result=>{
      const dish=dishById.get(result.menu_dish_id)
      const context=findHandlingContext(handling,entry.caseItem.id,result.menu_dish_id),handled=context.status
      const key=conflictItemKey(entry.meal.postpartum_meal,entry.caseItem.id,result.menu_dish_id)
      const selection:SelectedConflict|null=dish?{key,meal:entry.meal.postpartum_meal,item:{case_id:entry.caseItem.id,original_menu_dish_id:result.menu_dish_id,original_dish_id:dish.dish.id},caseItem:entry.caseItem,dish,result,handling:handled}:null
      const pending=result.outcome==='conflict'&&(!handled||handled.status==='pending')
      return <article key={result.menu_dish_id} className={`is-${result.outcome}`}>
        <div className="postpartum-conflict-dish-title">{pending&&dish&&<input type="checkbox" aria-label={`選取 ${entry.caseItem.current_room} ${dish.dish.name}`} checked={selected.has(key)} disabled={selectedMeal!==null&&selectedMeal!==entry.meal.postpartum_meal} onChange={()=>{if(selection)onToggle(selection)}}/>}<strong>{dish?.dish.name??'未知菜色'}</strong>{result.outcome==='conflict'&&<span className={`postpartum-handling-status is-${handled?.status??'pending'}`}>{handlingText(handled)}</span>}{context.replacementGroup&&handled?.status!=='pending'&&<button type="button" className="secondary postpartum-row-action" onClick={()=>onEditGroup(context.replacementGroup!)}>{handled?.status==='requires_reconfirmation'?'重新確認':'修改處理'}</button>}{context.acknowledgement&&handled?.status!=='pending'&&<button type="button" className="secondary postpartum-row-action" onClick={()=>onReprocessAcknowledgement(context.acknowledgement!)}>重新處理</button>}</div>
        {result.reasons.length>0?<GroupedReasons reasons={result.reasons}/>:<p className="postpartum-conflict-manual">⚠ {conflictOutcomeLabel(result)}</p>}
        {dish?.ingredient_coverage==='partial'&&<p className="postpartum-conflict-manual">⚠ 配方資料不足</p>}
        <WarningList items={[...(dish?.warnings??[]),...result.warnings]}/>
      </article>
    })}</div>}
  </section>
}

function DailyCaseCard({view,filter,expanded,onToggle,handlings,selected,selectedMeal,onToggleConflict,onEditGroup,onReprocessAcknowledgement}:{view:DailyCaseView;filter:MealFilter;expanded:boolean;onToggle:()=>void;handlings:Map<Meal,ConflictHandlingResponse>;selected:Set<string>;selectedMeal:Meal|null;onToggleConflict:(item:SelectedConflict)=>void;onEditGroup:(group:ReplacementGroup)=>void;onReprocessAcknowledgement:(item:ConflictAcknowledgement)=>void}){
  const entries=view.meals.filter(entry=>filter==='all'||entry.meal.postpartum_meal===filter)
  const states=entries.map(entry=>({entry,...entryState(entry)}))
  const hasConflict=states.some(item=>item.status==='conflict')
  const hasManual=states.some(item=>item.status==='partial')
  const noteworthy=states.filter(item=>item.status!=='complete')
  const warnings=uniqueWarnings(entries)
  return <article className={`postpartum-conflict-case-card ${hasConflict?'is-conflict':hasManual?'is-partial':'is-complete'}`}>
    <header><span className="postpartum-conflict-case-status">{hasConflict?'🔴':hasManual?'⚠':'✓'}</span><div><h3>{view.caseItem.current_room}｜{view.caseItem.name}｜{view.caseItem.case_number}</h3></div></header>
    <div className="postpartum-conflict-case-groups"><b>禁忌：</b>{view.caseItem.restriction_groups.length===0?<span>未設定</span>:view.caseItem.restriction_groups.map(group=><span key={group.id} style={{borderColor:group.color}}>{group.name}{!group.is_active?'（已停用）':''}</span>)}</div>
    {noteworthy.length===0?<p className="postpartum-conflict-safe">✓ 未發現衝突</p>:<div className="postpartum-conflict-case-summary-lines">{noteworthy.map(item=><p key={item.entry.meal.postpartum_meal}><b>{mealLabel(item.entry.meal.postpartum_meal)}</b><span className={`is-${item.status}`}>{item.status==='conflict'?`🔴 ${item.conflicts}項${item.manual?'・⚠':''}`:'⚠ 需人工確認'}</span></p>)}</div>}
    <button type="button" className="secondary postpartum-conflict-detail-toggle" aria-expanded={expanded} onClick={onToggle}>{expanded?'收合詳情':'查看詳情'}</button>
    {expanded&&<div className="postpartum-conflict-expanded"><WarningList items={warnings}/>{entries.map(entry=><MealDetails key={entry.meal.postpartum_meal} entry={entry} handling={handlings.get(entry.meal.postpartum_meal)} selected={selected} selectedMeal={selectedMeal} onToggle={onToggleConflict} onEditGroup={onEditGroup} onReprocessAcknowledgement={onReprocessAcknowledgement}/>)}</div>}
  </article>
}

function DailyView({data,filter,expanded,onToggle,handlings,selected,selectedMeal,onToggleConflict,onEditGroup,onReprocessAcknowledgement}:{data:PostpartumConflictDailyResponse;filter:MealFilter;expanded:Set<string>;onToggle:(id:string)=>void;handlings:Map<Meal,ConflictHandlingResponse>;selected:Set<string>;selectedMeal:Meal|null;onToggleConflict:(item:SelectedConflict)=>void;onEditGroup:(group:ReplacementGroup)=>void;onReprocessAcknowledgement:(item:ConflictAcknowledgement)=>void}){
  const cases=useMemo(()=>buildDailyCases(data),[data])
  const visible=cases.filter(item=>filter==='all'||item.meals.some(entry=>entry.meal.postpartum_meal===filter))
  return <div className="postpartum-conflict-daily">
    <section><h3>個案禁忌總覽</h3>{visible.length===0?<div className="state-panel empty-state"><p>{filter==='all'?'這一天沒有符合供餐資格的月子餐個案。':'本餐沒有符合供餐資格的月子餐個案。'}</p></div>:<div className="postpartum-conflict-case-list">{visible.map(item=><DailyCaseCard key={item.caseItem.id} view={item} filter={filter} expanded={expanded.has(item.caseItem.id)} onToggle={()=>onToggle(item.caseItem.id)} handlings={handlings} selected={selected} selectedMeal={selectedMeal} onToggleConflict={onToggleConflict} onEditGroup={onEditGroup} onReprocessAcknowledgement={onReprocessAcknowledgement}/>)}</div>}</section>
    <section className="postpartum-conflict-menu-context"><h3>ERP 菜單資訊</h3><div>{data.meals.filter(item=>item.mapping_resolution.status==='mapped'&&(filter==='all'||item.postpartum_meal===filter)).map(item=><span key={item.postpartum_meal}>{mealLabel(item.postpartum_meal)}：{item.source_resolution.source?.menu_name??'—'}／{item.mapping_resolution.menu_meal_type?.name??'—'}</span>)}</div></section>
  </div>
}

function WeeklyView({data,onOpen}:{data:PostpartumConflictWeeklyResponse;onOpen:(date:string,meal:Meal)=>void}){
  const today=todayTaipeiYmd()
  return <div className="postpartum-conflict-weekly"><p className="postpartum-conflict-week-range">{data.week_start} ～ {data.week_end}</p>
    <div className="table-frame"><table><thead><tr><th>日期</th>{POSTPARTUM_MEALS.map(item=><th key={item.value}>{item.label}</th>)}</tr></thead><tbody>{data.days.map(day=><tr key={day.target_date} className={day.target_date===today?'is-today':''}><th scope="row">{formatWeekDate(day.target_date)}{day.target_date===today&&<small>今天</small>}</th>{day.meals.map(summary=><td key={summary.postpartum_meal}><button type="button" className={`postpartum-conflict-week-cell is-${summary.status}`} onClick={()=>onOpen(day.target_date,summary.postpartum_meal)} aria-label={`${day.target_date} ${mealLabel(summary.postpartum_meal)}`}><SummaryBadge summary={summary}/></button></td>)}</tr>)}</tbody></table></div>
  </div>
}

export function PostpartumConflictPage(){
  const [view,setView]=useState<ViewMode>('daily'),[targetDate,setTargetDate]=useState(todayTaipeiYmd)
  const [daily,setDaily]=useState<PostpartumConflictDailyResponse|null>(null),[weekly,setWeekly]=useState<PostpartumConflictWeeklyResponse|null>(null)
  const [mealFilter,setMealFilter]=useState<MealFilter>('all'),[expanded,setExpanded]=useState<Set<string>>(()=>new Set())
  const [handlings,setHandlings]=useState<Map<Meal,ConflictHandlingResponse>>(()=>new Map())
  const [selected,setSelected]=useState<Map<string,SelectedConflict>>(()=>new Map()),[selectedMeal,setSelectedMeal]=useState<Meal|null>(null)
  const [replacementEditor,setReplacementEditor]=useState<{meal:Meal;group:ReplacementGroup|null}|null>(null),[acknowledgementOpen,setAcknowledgementOpen]=useState(false)
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  const requestSequence=useRef(0)

  async function loadCurrent(request:number){
    setLoading(true);setError('')
    try{
      if(view==='daily'){
        const data=await apiRequest<PostpartumConflictDailyResponse>(`/postpartum/menu-conflicts/daily?${new URLSearchParams({target_date:targetDate})}`)
        const responses=await Promise.all(POSTPARTUM_MEALS.map(item=>apiRequest<ConflictHandlingResponse>(`/postpartum/conflict-handlings?${new URLSearchParams({target_date:targetDate,postpartum_meal:item.value})}`)))
        if(request!==requestSequence.current)return
        setDaily(data);setWeekly(null);setHandlings(new Map(responses.map(item=>[item.postpartum_meal,item])))
      }else{
        const data=await apiRequest<PostpartumConflictWeeklyResponse>(`/postpartum/menu-conflicts/weekly?${new URLSearchParams({anchor_date:targetDate})}`)
        if(request!==requestSequence.current)return
        setWeekly(data);setDaily(null);setHandlings(new Map())
      }
    }catch(cause){if(request===requestSequence.current)setError(cause instanceof ApiError&&cause.status<500?cause.message:'禁忌總覽載入失敗，請稍後再試。')}finally{if(request===requestSequence.current)setLoading(false)}
  }
  useEffect(()=>{
    const request=++requestSequence.current;void loadCurrent(request)
    return ()=>{requestSequence.current+=1}
  },[view,targetDate])

  async function refreshAuthoritative(){const request=++requestSequence.current;await loadCurrent(request)}
  function clearSelection(){setSelected(new Map());setSelectedMeal(null)}
  function changeDate(value:string){setExpanded(new Set());setMealFilter('all');clearSelection();setReplacementEditor(null);setAcknowledgementOpen(false);setTargetDate(value)}
  function move(amount:number){changeDate(addYmdDays(targetDate,amount))}
  function openDay(date:string,meal:Meal){setExpanded(new Set());clearSelection();setTargetDate(date);setMealFilter(meal);setView('daily')}
  function toggleCase(id:string){setExpanded(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next})}
  function chooseMeal(meal:MealFilter){clearSelection();setMealFilter(meal)}
  function chooseView(next:ViewMode){clearSelection();setReplacementEditor(null);setAcknowledgementOpen(false);setView(next)}
  function toggleConflict(item:SelectedConflict){setSelected(current=>{const next=new Map(current);if(next.has(item.key)){next.delete(item.key);setSelectedMeal(next.values().next().value?.meal??null);return next}const currentMeal=current.values().next().value?.meal??selectedMeal;if(currentMeal!==null&&item.meal!==currentMeal)return current;next.set(item.key,item);setSelectedMeal(currentMeal??item.meal);return next})}
  function validSelectedItems(){const items=[...selected.values()];if(selectionMatchesMeal(items,selectedMeal))return items;setError('選取內容必須屬於同一天、同一餐，請重新選取。');clearSelection();return null}
  function openReplacement(){const items=validSelectedItems();if(!items)return;setReplacementEditor({meal:items[0].meal,group:null})}
  function openAcknowledgement(){if(!validSelectedItems())return;setAcknowledgementOpen(true)}

  const availableConflicts=useMemo(()=>{
    if(!daily)return []
    const values:SelectedConflict[]=[]
    for(const meal of daily.meals){const cases=new Map(meal.eligible_cases.map(item=>[item.id,item])),dishes=new Map(meal.menu_dishes.map(item=>[item.menu_dish_id,item])),handling=handlings.get(meal.postpartum_meal)
      for(const result of meal.case_dish_results){if(result.outcome!=='conflict')continue;const caseItem=cases.get(result.case_id),dish=dishes.get(result.menu_dish_id);if(!caseItem||!dish)continue;const handled=handling?.conflict_items.find(item=>item.case_id===result.case_id&&item.original_menu_dish_id===result.menu_dish_id)??null;values.push({key:conflictItemKey(meal.postpartum_meal,result.case_id,result.menu_dish_id),meal:meal.postpartum_meal,item:{case_id:result.case_id,original_menu_dish_id:result.menu_dish_id,original_dish_id:dish.dish.id},caseItem,dish,result,handling:handled})}
    }return values
  },[daily,handlings])
  const caseIndex=useMemo(()=>new Map(daily?.meals.flatMap(meal=>meal.eligible_cases).map(item=>[item.id,item])??[]),[daily])

  async function mutationFailure(message:string){setError(message);clearSelection();await refreshAuthoritative()}
  function editReplacementGroup(group:ReplacementGroup){clearSelection();setMealFilter(group.postpartum_meal);setReplacementEditor({meal:group.postpartum_meal,group})}
  async function cancelGroup(group:ReplacementGroup){if(!window.confirm(`確定取消「${group.replacement_dish.name}」共同替代？`))return;try{await apiRequest(`/postpartum/replacement-groups/${group.id}/cancel`,{method:'POST'});setMessage('已取消共同替代');clearSelection();await refreshAuthoritative()}catch(cause){await mutationFailure(cause instanceof ApiError?cause.message:'取消共同替代失敗')}}
  async function cancelAcknowledgement(item:ConflictAcknowledgement){if(!window.confirm('確定取消人工確認，將此衝突恢復為待處理？'))return;try{await apiRequest(`/postpartum/conflict-acknowledgements/${item.id}/cancel`,{method:'POST'});setMessage('已取消人工確認，可重新處理此衝突');clearSelection();await refreshAuthoritative()}catch(cause){await mutationFailure(cause instanceof ApiError?cause.message:'取消人工確認失敗')}}

  const effectiveCaseCount=daily?new Set(daily.meals.flatMap(item=>item.eligible_cases.map(caseItem=>caseItem.id))).size:0

  return <section><div className="section-heading"><div><h2>月子餐禁忌總覽</h2><small>先從週檢視找日期，再從日檢視找個案；展開個案即可查看菜色與禁忌原因。</small></div></div>
    <div className={view==='daily'?'postpartum-conflict-control-panel':''}><div className="postpartum-conflict-toolbar"><div className="segmented-control" aria-label="禁忌總覽檢視"><button type="button" className={view==='daily'?'active':''} onClick={()=>chooseView('daily')}>日檢視</button><button type="button" className={view==='weekly'?'active':''} onClick={()=>chooseView('weekly')}>週檢視</button></div><div className="postpartum-conflict-date-nav"><button type="button" onClick={()=>move(view==='daily'?-1:-7)}>{view==='daily'?'前一天':'上一週'}</button><button type="button" onClick={()=>changeDate(todayTaipeiYmd())}>{view==='daily'?'今天':'本週'}</button><button type="button" onClick={()=>move(view==='daily'?1:7)}>{view==='daily'?'下一天':'下一週'}</button><label>日期<input type="date" required value={targetDate} onChange={event=>changeDate(event.target.value)}/></label></div></div>
      {view==='daily'&&daily&&<><MealSummaryBar data={daily} selected={mealFilter} onChoose={chooseMeal}/><div className="postpartum-conflict-overall"><strong>本日摘要</strong><span>有效個案 {effectiveCaseCount} 人</span><span>衝突 {daily.conflict_count} 項</span><span>需人工確認 {daily.manual_review_case_count} 人</span></div><MealNotices meals={daily.meals} filter={mealFilter}/></>}
    </div>
    {message&&<p className="feedback feedback-success">{message}</p>}{error&&<p className="feedback feedback-error">{error}</p>}
    {selected.size>0&&<div className="postpartum-conflict-selection-bar"><b>已選 {selected.size} 個衝突項目</b><button type="button" onClick={openReplacement}>設定共同替代</button><button type="button" className="secondary" onClick={openAcknowledgement}>人工確認不需替代</button><button type="button" className="secondary" onClick={clearSelection}>清除選取</button></div>}
    {loading?<div className="state-panel"><span className="spinner"/>禁忌總覽載入中…</div>:view==='daily'&&daily?<><DailyView data={daily} filter={mealFilter} expanded={expanded} onToggle={toggleCase} handlings={handlings} selected={new Set(selected.keys())} selectedMeal={selectedMeal} onToggleConflict={toggleConflict} onEditGroup={editReplacementGroup} onReprocessAcknowledgement={item=>void cancelAcknowledgement(item)}/><HandlingOverview responses={[...handlings.values()]} cases={caseIndex} onEdit={editReplacementGroup} onCancelGroup={group=>void cancelGroup(group)} onCancelAcknowledgement={item=>void cancelAcknowledgement(item)}/></>:view==='weekly'&&weekly?<WeeklyView data={weekly} onOpen={openDay}/>:<div className="state-panel empty-state"><p>目前沒有可顯示的禁忌檢查資料。</p></div>}
    {replacementEditor&&<ReplacementDialog targetDate={targetDate} meal={replacementEditor.meal} initial={replacementEditor.group} selected={[...selected.values()]} available={availableConflicts.filter(item=>item.meal===replacementEditor.meal)} onClose={()=>setReplacementEditor(null)} onSaved={async()=>{setMessage(replacementEditor.group?'共同替代已更新':'共同替代已建立');clearSelection();await refreshAuthoritative()}} onFailure={mutationFailure}/>}
    {acknowledgementOpen&&<AcknowledgementDialog targetDate={targetDate} items={[...selected.values()]} onClose={()=>setAcknowledgementOpen(false)} onDone={async(text,failed)=>{failed?setError(text):setMessage(text);clearSelection();await refreshAuthoritative()}}/>}
  </section>
}
