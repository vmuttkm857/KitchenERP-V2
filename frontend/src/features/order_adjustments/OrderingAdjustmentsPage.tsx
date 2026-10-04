import { FormEvent,useCallback,useEffect,useRef,useState } from 'react'
import { ApiError } from '../../api/client'
import { EmptyState,Feedback,LoadingState,PageHeader,TableFrame } from '../../components/ui/Page'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { dateRangeError,preserveSelected,RequestSequence } from '../../utils/listQuery'
import type { Menu } from '../menus/types'
import { useMenuCandidates } from '../menus/useMenuCandidates'
import { createOrderingAdjustment,getOrderingAdjustment,listOrderingAdjustments } from './api'
import type { ExistingAdjustmentDetail,OrderingAdjustmentDetail,OrderingAdjustmentStatus,OrderingAdjustmentSummary } from './types'
import { adjustmentDateRange,adjustmentStatusLabels,formatAdjustmentQuantity,groupAdjustmentLines,staleReasonLabel } from './view'

const pageSize=25

function existingAdjustment(error:unknown):ExistingAdjustmentDetail|null{
  if(!(error instanceof ApiError)||error.status!==409||!error.detail||typeof error.detail!=='object')return null
  const detail=error.detail as Partial<ExistingAdjustmentDetail>
  return (detail.code==='ADJUSTMENT_DRAFT_EXISTS'||detail.code==='ADJUSTMENT_ALREADY_CONFIRMED')&&typeof detail.existing_sheet_id==='string'?detail as ExistingAdjustmentDetail:null
}

export function OrderingAdjustmentsPage(){
  const [detail,setDetail]=useState<OrderingAdjustmentDetail|null>(null),[detailLoading,setDetailLoading]=useState(false)
  const [items,setItems]=useState<OrderingAdjustmentSummary[]>([]),[total,setTotal]=useState(0),[page,setPage]=useState(1)
  const [status,setStatus]=useState<OrderingAdjustmentStatus|''>(''),[startDate,setStartDate]=useState(''),[endDate,setEndDate]=useState('')
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[createOpen,setCreateOpen]=useState(false)
  const sequence=useRef(new RequestSequence());const rangeError=dateRangeError(startDate,endDate)
  const load=useCallback(async()=>{
    if(rangeError){sequence.current.next();setLoading(false);return}
    const request=sequence.current.next();setLoading(true)
    try{const data=await listOrderingAdjustments({page,pageSize,status:status||undefined,startDate:startDate||undefined,endDate:endDate||undefined});if(sequence.current.isCurrent(request)){setItems(data.items);setTotal(data.pagination.total);setError('')}}
    catch{if(sequence.current.isCurrent(request))setError('叫貨調整單載入失敗，請稍後重試。')}
    finally{if(sequence.current.isCurrent(request))setLoading(false)}
  },[endDate,page,rangeError,startDate,status])
  useEffect(()=>{void load()},[load])
  async function open(sheetId:string){setDetailLoading(true);setError('');try{setDetail(await getOrderingAdjustment(sheetId))}catch(cause){setError(cause instanceof ApiError&&cause.status===404?'找不到這張叫貨調整單。':'叫貨調整單內容載入失敗。')}finally{setDetailLoading(false)}}
  function back(){setDetail(null);void load()}
  if(detailLoading)return <section><LoadingState label="叫貨調整單載入中…"/></section>
  if(detail)return <OrderingAdjustmentDetailView detail={detail} onBack={back}/>
  return <section className="ordering-adjustments-page">
    <PageHeader title="叫貨調整" description="依菜單與日期建立調整草稿，保留每道菜、每項食材的系統計算量。" actions={<button onClick={()=>setCreateOpen(true)}>＋ 建立叫貨調整單</button>}/>
    <div className="toolbar ordering-adjustment-filters"><label>狀態<select value={status} onChange={event=>{setStatus(event.target.value as OrderingAdjustmentStatus|'');setPage(1)}}><option value="">全部</option><option value="draft">草稿</option><option value="confirmed">已確認</option><option value="cancelled">已取消</option></select></label><label>開始日期<input type="date" value={startDate} onChange={event=>{setStartDate(event.target.value);setPage(1)}}/></label><label>結束日期<input type="date" value={endDate} onChange={event=>{setEndDate(event.target.value);setPage(1)}}/></label></div>
    {rangeError&&<Feedback type="error">{rangeError}</Feedback>}{error&&<Feedback type="error">{error}</Feedback>}
    {loading?<LoadingState label="叫貨調整單載入中…"/>:!items.length?<EmptyState title="目前沒有叫貨調整單" description="可從上方建立新的叫貨調整草稿。"/>:<AdjustmentList items={items} onOpen={id=>void open(id)}/>}
    {!rangeError&&<PaginationControls page={page} pageSize={pageSize} total={total} onPage={setPage}/>} 
    {createOpen&&<CreateAdjustmentDialog onClose={()=>setCreateOpen(false)} onCreated={value=>{setCreateOpen(false);setDetail(value)}} onOpenExisting={id=>{setCreateOpen(false);void open(id)}}/>}
  </section>
}

function AdjustmentList({items,onOpen}:{items:OrderingAdjustmentSummary[];onOpen:(id:string)=>void}){
  return <TableFrame><table className="ordering-adjustment-list"><thead><tr><th>狀態</th><th>菜單</th><th>日期範圍</th><th>Revision</th><th>建立時間</th><th>最後更新</th><th>建立者</th><th></th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td><AdjustmentStatus status={item.status}/></td><td>{item.source_menus.map(menu=>menu.menu_name).join('、')||'—'}</td><td>{adjustmentDateRange(item.criteria,item)}</td><td>{item.revision}</td><td>{new Date(item.created_at).toLocaleString('zh-TW')}</td><td>{new Date(item.updated_at).toLocaleString('zh-TW')}</td><td>{item.created_by_name||'—'}</td><td><button onClick={()=>onOpen(item.id)}>{item.status==='draft'?'繼續查看':'查看'}</button></td></tr>)}</tbody></table></TableFrame>
}

function AdjustmentStatus({status}:{status:OrderingAdjustmentStatus}){return <span className={`ordering-adjustment-status is-${status}`}>{adjustmentStatusLabels[status]}</span>}

function CreateAdjustmentDialog({onClose,onCreated,onOpenExisting}:{onClose:()=>void;onCreated:(value:OrderingAdjustmentDetail)=>void;onOpenExisting:(id:string)=>void}){
  const candidates=useMenuCandidates({active:'true',pageSize:20});const [selected,setSelected]=useState<Map<string,Menu>>(new Map())
  const [startDate,setStartDate]=useState(''),[endDate,setEndDate]=useState(''),[notes,setNotes]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const [existing,setExisting]=useState<ExistingAdjustmentDetail|null>(null);const rangeError=!startDate||!endDate?'請同時選擇開始日期與結束日期。':dateRangeError(startDate,endDate)
  const choices=preserveSelected(candidates.items,selected)
  function toggle(menu:Menu){setSelected(current=>{const next=new Map(current);if(next.has(menu.id))next.delete(menu.id);else next.set(menu.id,menu);return next})}
  async function submit(event:FormEvent){event.preventDefault();if(!selected.size){setError('請至少選擇一份菜單。');return}if(rangeError){setError(rangeError);return}setBusy(true);setError('');setExisting(null)
    try{onCreated(await createOrderingAdjustment({criteria:{menu_ids:[...selected.keys()],start_date:startDate,end_date:endDate},notes:notes.trim()||null}))}
    catch(cause){const conflict=existingAdjustment(cause);if(conflict){setExisting(conflict);setError(conflict.code==='ADJUSTMENT_DRAFT_EXISTS'?'這個範圍已有叫貨調整草稿。':'這個範圍已有已確認的叫貨調整單。')}else setError('建立叫貨調整單失敗，請確認菜單與日期範圍。')}
    finally{setBusy(false)}
  }
  return <div className="modal-backdrop"><section className="modal-panel wide ordering-adjustment-create" role="dialog" aria-modal="true"><header><div><h2>建立叫貨調整單</h2><p>可同時選擇多份菜單；系統會保留各菜單、菜色與食材來源，不會先合併。</p></div></header><form onSubmit={submit}>
    <fieldset className="workflow-step"><legend>① 選擇菜單</legend><strong>已選 {selected.size} 份菜單</strong><label>搜尋菜單<input value={candidates.search} onChange={event=>candidates.setSearch(event.target.value)} placeholder="輸入菜單名稱"/></label>{candidates.error&&<small className="error">{candidates.error}</small>}<div className="menu-choices">{choices.map(menu=><label className="inline-check" key={menu.id}><input type="checkbox" checked={selected.has(menu.id)} onChange={()=>toggle(menu)}/><span>{menu.name}（{menu.start_date}～{menu.end_date}）</span></label>)}</div>{candidates.loading&&<small>菜單候選載入中…</small>}<PaginationControls page={candidates.page} pageSize={candidates.pageSize} total={candidates.total} onPage={candidates.setPage}/></fieldset>
    <fieldset className="workflow-step"><legend>② 調整日期範圍</legend><div className="date-range-fields"><label>開始日期<input type="date" value={startDate} onChange={event=>{setStartDate(event.target.value);setExisting(null)}}/></label><label>結束日期<input type="date" value={endDate} onChange={event=>{setEndDate(event.target.value);setExisting(null)}}/></label></div><label>備註（選填）<textarea value={notes} maxLength={2000} onChange={event=>setNotes(event.target.value)}/></label></fieldset>
    {error&&<Feedback type="error">{error}{existing&&<button type="button" className="secondary ordering-existing-action" onClick={()=>onOpenExisting(existing.existing_sheet_id)}>{existing.code==='ADJUSTMENT_DRAFT_EXISTS'?'繼續編輯原草稿':'查看已確認調整單'}</button>}</Feedback>}
    <footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button disabled={busy||!selected.size||Boolean(rangeError)}>{busy?'建立中…':'建立叫貨調整單'}</button></footer>
  </form></section></div>
}

function OrderingAdjustmentDetailView({detail,onBack}:{detail:OrderingAdjustmentDetail;onBack:()=>void}){
  const groups=groupAdjustmentLines(detail.lines);const readOnly=detail.status!=='draft'||detail.stale
  const staleReasons=[...new Set([...detail.warnings.map(warning=>warning.code),...detail.lines.flatMap(line=>line.stale_reasons)].map(staleReasonLabel))]
  return <section className={`ordering-adjustment-detail is-${detail.status}${detail.stale?' is-stale':''}`}>
    <PageHeader title="叫貨調整單" description="依原週配料表順序查看每道菜的食材系統量。" actions={<button className="secondary" onClick={onBack}>← 返回叫貨調整單</button>}/>
    <div className="ordering-adjustment-header"><div><small>狀態</small><AdjustmentStatus status={detail.status}/></div><div><small>Revision</small><strong>{detail.revision}</strong></div><div><small>日期範圍</small><strong>{adjustmentDateRange(detail.criteria,detail)}</strong></div><div><small>菜單</small><strong>{detail.source_menus.map(menu=>menu.menu_name).join('、')}</strong></div><div><small>建立時間</small><strong>{new Date(detail.created_at).toLocaleString('zh-TW')}</strong></div><div><small>最後更新</small><strong>{new Date(detail.updated_at).toLocaleString('zh-TW')}</strong></div></div>
    {detail.stale&&<Feedback type="error"><strong>來源資料已變更，此調整單需要重新建立。</strong>{staleReasons.length>0&&<ul>{staleReasons.map(reason=><li key={reason}>{reason}</li>)}</ul>}</Feedback>}
    {!detail.stale&&readOnly&&<Feedback type="info">此調整單為{adjustmentStatusLabels[detail.status]}狀態，目前僅供查看。</Feedback>}
    {!groups.length?<EmptyState title="這張調整單沒有食材明細"/>:<div className="ordering-adjustment-hierarchy">{groups.map(menu=><section className="ordering-adjustment-menu" key={menu.id}><h2>{menu.name}</h2>{menu.dates.map(day=><section className="ordering-adjustment-day" key={day.date}><h3>{formatDate(day.date)}</h3>{day.meals.map(meal=><section className="ordering-adjustment-meal" key={meal.id}><h4>{meal.name}</h4>{meal.dishes.map(dish=><article className="ordering-adjustment-dish" key={dish.id}><header><strong>{dish.name}</strong><span>{dish.dinerCount} 人</span></header><table><thead><tr><th>食材</th><th>系統量</th></tr></thead><tbody>{dish.lines.map(line=><tr key={line.id}><td>{line.ingredient_code_snapshot}　{line.ingredient_name_snapshot}</td><td><strong>{formatAdjustmentQuantity(line.system_quantity)}</strong> {line.system_unit}</td></tr>)}</tbody></table></article>)}</section>)}</section>)}</section>)}</div>}
  </section>
}

function formatDate(value:string){const date=new Date(`${value}T00:00:00+08:00`);const weekday=['日','一','二','三','四','五','六'][date.getDay()];return `${value.slice(5).replace('-','/')}（${weekday}）`}
