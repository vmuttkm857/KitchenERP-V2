import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../../api/client'
import type {
  ConflictAcknowledgement, ConflictCase, ConflictCaseDishResult, ConflictHandlingResponse,
  ConflictItemInput, ConflictItemStatus, ConflictMenuDish, ConflictWarning, ReplacementCandidate,
  ReplacementCandidateList, ReplacementGroup,
} from './conflictTypes'
import { candidateNeedsRecipeAcknowledgement, candidateWarningPresentation } from './conflictTypes'
import { mealLabel, type Meal } from './types'

interface Category {id:string;name:string}
interface Paged<T>{items:T[];pagination:{total:number}}

export interface SelectedConflict {
  key:string
  meal:Meal
  item:ConflictItemInput
  caseItem:ConflictCase
  dish:ConflictMenuDish
  result:ConflictCaseDishResult
  handling:ConflictItemStatus|null
}

export function conflictItemKey(meal:Meal,caseId:string,menuDishId:string){
  return `${meal}:${caseId}:${menuDishId}`
}

function WarningLines({items}:{items:ConflictWarning[]}){
  if(items.length===0)return null
  return <ul className="postpartum-handling-warnings">{items.map((item,index)=><li key={`${item.code}-${index}`}>⚠ {item.message}</li>)}</ul>
}

function SelectedItems({items}:{items:SelectedConflict[]}){
  return <div className="postpartum-replacement-selected">{items.map(item=><article key={item.key}>
    <b>{item.caseItem.current_room}｜{item.caseItem.name}</b>
    <span>{mealLabel(item.meal)}・{item.dish.dish.name}</span>
    <small>禁忌原因：{[...new Set(item.result.reasons.map(reason=>reason.restriction_group.name))].join('、')}</small>
  </article>)}</div>
}

function candidateLabel(item:ReplacementCandidate){
  if(item.status==='conflict')return '明確命中禁忌，不可選擇'
  if(item.status==='insufficient_recipe_data')return '未發現已知禁忌，但資料不足，請人工確認'
  return '未發現已知禁忌'
}

export function ReplacementDialog({targetDate,meal,available,initial,selected,onClose,onSaved,onFailure}:{
  targetDate:string;meal:Meal;available:SelectedConflict[];initial:ReplacementGroup|null;selected:SelectedConflict[]
  onClose:()=>void;onSaved:()=>Promise<void>;onFailure:(message:string)=>Promise<void>
}){
  const initialKeys=useMemo(()=>new Set(initial?[
    ...initial.items.map(item=>conflictItemKey(meal,item.case_id,item.original_menu_dish_id)),
    ...selected.map(item=>item.key),
  ]:selected.map(item=>item.key)),[initial,meal,selected])
  const [chosen,setChosen]=useState(()=>new Set(initialKeys)),[categories,setCategories]=useState<Category[]>([])
  const [categoryId,setCategoryId]=useState(''),[searchInput,setSearchInput]=useState(''),[search,setSearch]=useState('')
  const [page,setPage]=useState(1),[total,setTotal]=useState(0),[candidates,setCandidates]=useState<ReplacementCandidate[]>([])
  const [candidate,setCandidate]=useState<ReplacementCandidate|null>(initial?{
    dish:initial.replacement_dish,status:initial.candidate_status,coverage:initial.review_needed?'partial':'complete',
    review_needed:initial.review_needed,case_results:[],warnings:initial.warnings,
  }:null)
  const [note,setNote]=useState(initial?.note??''),[reassign,setReassign]=useState(false)
  const [removeStale,setRemoveStale]=useState(false)
  const [insufficientAcknowledged,setInsufficientAcknowledged]=useState(false)
  const [showAllItems,setShowAllItems]=useState(false),[showConflictCandidates,setShowConflictCandidates]=useState(false)
  const [expandedCandidateDetails,setExpandedCandidateDetails]=useState<Set<string>>(()=>new Set())
  const [loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState('')
  const requestSequence=useRef(0)
  const chosenItems=available.filter(item=>chosen.has(item.key))
  const unavailableInitialItems=initial?.items.filter(item=>!available.some(candidate=>candidate.key===conflictItemKey(meal,item.case_id,item.original_menu_dish_id)))??[]
  const needsReassign=Boolean(initial&&chosenItems.some(item=>item.handling&&(
    item.handling.replacement_group_id!==initial.id
  )))
  const needsRecipeAcknowledgement=Boolean(candidate&&candidateNeedsRecipeAcknowledgement(candidate.status))
  const pages=Math.max(1,Math.ceil(total/20))
  const currentGroupKeys=new Set(initial?.items.map(item=>conflictItemKey(meal,item.case_id,item.original_menu_dish_id))??[])
  const orderedAvailable=[...available].sort((left,right)=>Number(currentGroupKeys.has(right.key))-Number(currentGroupKeys.has(left.key)))
  const currentGroupItems=orderedAvailable.filter(item=>currentGroupKeys.has(item.key))
  const otherItems=orderedAvailable.filter(item=>!currentGroupKeys.has(item.key))
  const visibleItems=showAllItems?orderedAvailable:[...currentGroupItems,...otherItems.slice(0,Math.max(0,5-currentGroupItems.length))]
  const hiddenItemCount=orderedAvailable.length-visibleItems.length
  const selectableCandidates=candidates.filter(item=>item.status!=='conflict')
  const conflictCandidates=candidates.filter(item=>item.status==='conflict')

  useEffect(()=>{void apiRequest<Paged<Category>>('/categories/dish?active=true&page_size=100').then(data=>setCategories(data.items)).catch(()=>setError('菜色分類載入失敗'))},[])
  useEffect(()=>{
    if(chosenItems.length===0){setCandidates([]);setTotal(0);return}
    const request=++requestSequence.current;setLoading(true);setError('')
    void apiRequest<ReplacementCandidateList>('/postpartum/replacement-candidates/search',{method:'POST',body:JSON.stringify({
      target_date:targetDate,postpartum_meal:meal,items:chosenItems.map(item=>item.item),page,page_size:20,
      search:search||null,category_id:categoryId||null,
    })}).then(data=>{if(request===requestSequence.current){setCandidates(data.items);setTotal(data.pagination.total)}}).catch(cause=>{if(request===requestSequence.current)setError(cause instanceof ApiError?cause.message:'替代菜搜尋失敗')}).finally(()=>{if(request===requestSequence.current)setLoading(false)})
    return()=>{requestSequence.current+=1}
  },[categoryId,meal,page,search,targetDate,chosenItems.map(item=>item.key).join('|')])

  function toggle(item:SelectedConflict){setChosen(current=>{const next=new Set(current);if(next.has(item.key))next.delete(item.key);else next.add(item.key);return next});setPage(1);setCandidate(null);setInsufficientAcknowledged(false)}
  function chooseCandidate(item:ReplacementCandidate){setCandidate(item);setInsufficientAcknowledged(false)}
  function toggleCandidateDetails(dishId:string){setExpandedCandidateDetails(current=>{const next=new Set(current);if(next.has(dishId))next.delete(dishId);else next.add(dishId);return next})}
  function candidateRow(item:ReplacementCandidate){const hits=[...new Set(item.case_results.flatMap(result=>result.reasons.map(reason=>reason.restriction_group.name)))],review=candidateWarningPresentation(item,[...new Map(chosenItems.map(value=>[value.caseItem.id,value.caseItem])).values()]),expanded=expandedCandidateDetails.has(item.dish.id);return <div key={item.dish.id} className={`postpartum-candidate-row is-${item.status}`}><input id={`replacement-candidate-${item.dish.id}`} type="radio" name="replacement-dish" aria-label={`選擇 ${item.dish.name}`} disabled={item.status==='conflict'} checked={candidate?.dish.id===item.dish.id} onChange={()=>chooseCandidate(item)}/><div className="postpartum-candidate-content"><label htmlFor={`replacement-candidate-${item.dish.id}`}><b>{item.status==='conflict'?'✕ ':item.status==='no_known_conflict'?'✓ ':'⚠ '}{item.dish.code}　{item.dish.name}</b></label><small>{candidateLabel(item)}</small>{hits.length>0&&<small>命中：{hits.join('、')}</small>}{item.status!=='no_known_conflict'&&review.count>0&&<div className="postpartum-candidate-review-summary"><span>{review.count} 項需要人工確認</span><button type="button" className="text-button" aria-expanded={expanded} onClick={()=>toggleCandidateDetails(item.dish.id)}>{expanded?'收合詳情':'查看詳情'}</button></div>}{expanded&&<div className="postpartum-candidate-review-details"><b>以下禁忌目前缺少足夠資料，系統無法確認：</b>{review.caseGroups.map(value=><p key={value.case_id}>{review.caseGroups.length>1&&<strong>{value.current_room} {value.name}：</strong>}{value.groups.join('、')}</p>)}{review.fallbackMessages.length>0&&<ul>{review.fallbackMessages.map(message=><li key={message}>{message}</li>)}</ul>}</div>}</div></div>}
  async function save(){
    if(chosenItems.length===0||!candidate||candidate.status==='conflict'||(needsRecipeAcknowledgement&&!insufficientAcknowledged)||(needsReassign&&!reassign)||(unavailableInitialItems.length>0&&!removeStale))return
    setSaving(true);setError('')
    const body=JSON.stringify({replacement_dish_id:candidate.dish.id,items:chosenItems.map(item=>item.item),note:note.trim()||null,...(initial?{reassign_items:reassign}:{target_date:targetDate,postpartum_meal:meal})})
    try{
      await apiRequest(initial?`/postpartum/replacement-groups/${initial.id}`:'/postpartum/replacement-groups',{method:initial?'PUT':'POST',body})
      await onSaved();onClose()
    }catch(cause){const message=cause instanceof ApiError?cause.message:'共同替代儲存失敗';setError(message);if(cause instanceof ApiError&&(cause.status===409||cause.status===422))await onFailure(message)}finally{setSaving(false)}
  }
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!saving)onClose()}}><section className="modal-panel postpartum-replacement-dialog" role="dialog" aria-modal="true" aria-labelledby="replacement-title">
    <header><div><h2 id="replacement-title">{initial?'修改共同替代':'設定共同替代'}</h2><p>{targetDate}｜{mealLabel(meal)}</p></div><button type="button" className="secondary" disabled={saving} onClick={onClose}>關閉</button></header>
    <div className="postpartum-replacement-step-title"><h3>① 選擇要一起處理的衝突</h3><b>已選 {chosenItems.length} 項</b></div><div className="postpartum-replacement-item-picker">{visibleItems.map(item=>{const occupied=Boolean(item.handling&&item.handling.status!=='pending'),belongsHere=Boolean(initial&&item.handling?.replacement_group_id===initial.id),groups=[...new Set(item.result.reasons.map(reason=>reason.restriction_group.name))];return <label key={item.key} className="postpartum-replacement-item-row"><input type="checkbox" checked={chosen.has(item.key)} disabled={!initial&&occupied} onChange={()=>toggle(item)}/><b className="postpartum-replacement-item-case" title={`${item.caseItem.current_room}｜${item.caseItem.name}`}>{item.caseItem.current_room}｜{item.caseItem.name}</b><span className="postpartum-replacement-item-dish" title={item.dish.dish.name}>{item.dish.dish.name}</span><span className="postpartum-replacement-item-groups">{groups.map(group=><small key={group}>[{group}]</small>)}{occupied&&!belongsHere?<em>{item.handling?.status==='manually_acknowledged'?'已人工確認':'其他共同替代群組'}</em>:''}</span></label>})}</div>
    {(hiddenItemCount>0||showAllItems&&orderedAvailable.length>5)&&<button type="button" className="secondary postpartum-show-more" onClick={()=>setShowAllItems(value=>!value)}>{showAllItems?'收合':`顯示其他 ${hiddenItemCount} 項`}</button>}
    {unavailableInitialItems.length>0&&<div className="feedback feedback-warning"><b>有 {unavailableInitialItems.length} 個原衝突項目已不存在或不再符合目前資料。</b><label><input type="checkbox" checked={removeStale} onChange={event=>setRemoveStale(event.target.checked)}/>我確認從此群組移除這些失效項目</label></div>}
    {needsReassign&&<label className="postpartum-reassign-confirm"><input type="checkbox" checked={reassign} onChange={event=>setReassign(event.target.checked)}/>我確認將所選衝突項目移至此共同替代群組</label>}
    <div className="postpartum-replacement-step-title"><h3>② 選擇共同替代菜</h3></div><form className="postpartum-candidate-filters" onSubmit={event=>{event.preventDefault();setPage(1);setSearch(searchInput.trim())}}><label>菜色分類<select value={categoryId} onChange={event=>{setCategoryId(event.target.value);setPage(1)}}><option value="">全部分類</option>{categories.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>搜尋 Dish<input value={searchInput} onChange={event=>setSearchInput(event.target.value)} placeholder="輸入菜名或代碼"/></label><button type="submit">搜尋</button></form>
    <p className="muted">共 {total} 筆／第 {page} 頁／共 {pages} 頁</p>
    {loading?<p>候選菜搜尋中…</p>:candidates.length===0?<p className="state-panel empty-state">沒有符合條件的候選菜。</p>:<>{selectableCandidates.length===0?<div className="state-panel empty-state postpartum-candidate-page-empty"><b>本頁沒有可直接使用的替代菜</b><p>本頁 {conflictCandidates.length} 道菜皆命中禁忌，可查看不可使用菜色，或使用搜尋／分類尋找其他替代菜。</p></div>:<div className="postpartum-candidate-list">{selectableCandidates.map(candidateRow)}</div>}{conflictCandidates.length>0&&<div className="postpartum-conflict-candidate-group"><button type="button" className="secondary" aria-expanded={showConflictCandidates} onClick={()=>setShowConflictCandidates(value=>!value)}>{showConflictCandidates?'收合不可使用菜色':`顯示本頁 ${conflictCandidates.length} 道不可使用菜色`}</button>{showConflictCandidates&&<div className="postpartum-candidate-list">{conflictCandidates.map(candidateRow)}</div>}</div>}</>}
    <div className="pagination"><button type="button" className="secondary" disabled={page<=1} onClick={()=>setPage(value=>value-1)}>上一頁</button><button type="button" className="secondary" disabled={page>=pages} onClick={()=>setPage(value=>value+1)}>下一頁</button></div>
    {needsRecipeAcknowledgement&&<div className="feedback feedback-warning"><p>此菜餚配方資料不足，系統無法完整確認禁忌，需人工確認。</p><label className="postpartum-insufficient-confirm"><input type="checkbox" checked={insufficientAcknowledged} onChange={event=>setInsufficientAcknowledged(event.target.checked)}/>我已確認此菜餚配方資料不足，仍要使用此替代菜</label></div>}
    <div className="postpartum-replacement-step-title"><h3>③ 確認</h3></div><label>處理備註<textarea maxLength={5000} value={note} onChange={event=>setNote(event.target.value)}/></label>
    {error&&<p className="feedback feedback-error">{error}</p>}
    <footer className="postpartum-replacement-footer"><button type="button" className="secondary" disabled={saving} onClick={onClose}>取消</button><button type="button" disabled={saving||chosenItems.length===0||!candidate||candidate.status==='conflict'||(needsRecipeAcknowledgement&&!insufficientAcknowledged)||(needsReassign&&!reassign)||(unavailableInitialItems.length>0&&!removeStale)} onClick={()=>void save()}>{saving?'儲存中…':'確認共同替代'}</button></footer>
  </section></div>
}

export function AcknowledgementDialog({targetDate,items,onClose,onDone}:{targetDate:string;items:SelectedConflict[];onClose:()=>void;onDone:(message:string,error?:boolean)=>Promise<void>}){
  const [note,setNote]=useState(''),[saving,setSaving]=useState(false)
  async function save(){
    setSaving(true);let success=0;const failures:string[]=[]
    // The backend intentionally exposes one-item acknowledgements, so report partial failure honestly.
    for(const item of items){try{await apiRequest('/postpartum/conflict-acknowledgements',{method:'POST',body:JSON.stringify({target_date:targetDate,postpartum_meal:item.meal,item:item.item,note:note.trim()||null})});success+=1}catch{failures.push(`${item.caseItem.current_room} ${item.dish.dish.name}`)}}
    const message=failures.length===0?`已人工確認 ${success} 個衝突項目`:`成功 ${success} 項；失敗 ${failures.length} 項：${failures.join('、')}`
    await onDone(message,failures.length>0);setSaving(false);onClose()
  }
  return <div className="modal-backdrop"><section className="modal-panel postpartum-ack-dialog" role="dialog" aria-modal="true"><header><h2>人工確認不需替代</h2><button type="button" className="secondary" disabled={saving} onClick={onClose}>關閉</button></header><SelectedItems items={items}/><label>確認備註<textarea value={note} maxLength={5000} onChange={event=>setNote(event.target.value)}/></label><footer><button type="button" className="secondary" onClick={onClose}>取消</button><button type="button" disabled={saving} onClick={()=>void save()}>{saving?'處理中…':'確認不需替代'}</button></footer></section></div>
}

export function HandlingOverview({responses,cases,onEdit,onCancelGroup,onCancelAcknowledgement}:{responses:ConflictHandlingResponse[];cases:Map<string,ConflictCase>;onEdit:(group:ReplacementGroup)=>void;onCancelGroup:(group:ReplacementGroup)=>void;onCancelAcknowledgement:(item:ConflictAcknowledgement)=>void}){
  const groups=responses.flatMap(item=>item.replacement_groups),acks=responses.flatMap(item=>item.manual_acknowledgements)
  if(groups.length===0&&acks.length===0)return null
  return <section className="postpartum-handling-overview"><h3>已處理衝突</h3>{groups.map(group=><article key={group.id} className={group.status==='requires_reconfirmation'?'is-warning':'is-replaced'}><header><div><b>{group.status==='requires_reconfirmation'?'需要重新確認':'已替代'}：{group.replacement_dish.name} × {group.items.length}</b><small>{mealLabel(group.postpartum_meal)}{group.note?`｜${group.note}`:''}</small></div><div className="actions"><button type="button" onClick={()=>onEdit(group)}>修改</button><button type="button" className="secondary" onClick={()=>onCancelGroup(group)}>取消替代</button></div></header><WarningLines items={group.warnings}/><ul>{group.items.map(item=>{const caseItem=cases.get(item.case_id);return <li key={item.id}>{caseItem?`${caseItem.current_room}床 ${caseItem.name}｜`:''}{item.original_dish.name} → {group.replacement_dish.name}{item.status==='requires_reconfirmation'&&<strong>　需要重新確認</strong>}<WarningLines items={item.warnings}/></li>})}</ul></article>)}{acks.map(item=>{const caseItem=cases.get(item.case_id);return <article key={item.id} className={item.status==='requires_reconfirmation'?'is-warning':'is-acknowledged'}><div><b>{item.status==='requires_reconfirmation'?'需要重新確認':'人工確認｜不需替代'}</b><span>{caseItem?`${caseItem.current_room}床 ${caseItem.name}｜`:''}{mealLabel(item.postpartum_meal)}・{item.original_dish.name}{item.note?`｜${item.note}`:''}</span><WarningLines items={item.warnings}/></div><button type="button" className="secondary" onClick={()=>onCancelAcknowledgement(item)}>取消確認</button></article>})}</section>
}
