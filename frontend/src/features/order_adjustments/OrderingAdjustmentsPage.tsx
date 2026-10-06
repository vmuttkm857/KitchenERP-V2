import { FormEvent,useCallback,useEffect,useRef,useState } from 'react'
import { ApiError } from '../../api/client'
import { useEditorDirty } from '../../app/NavigationBlocker'
import { EmptyState,Feedback,LoadingState,PageHeader,TableFrame } from '../../components/ui/Page'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { dateRangeError,preserveSelected,RequestSequence } from '../../utils/listQuery'
import type { Menu } from '../menus/types'
import { useMenuCandidates } from '../menus/useMenuCandidates'
import type {MenuAggregate} from '../menus/types'
import { applyOrderingAdjustmentReuse,confirmOrderingAdjustment,createOrderingAdjustment,deleteOrderingAdjustment,getOrderingAdjustment,getOrderingAdjustmentMenuLayout,listOrderingAdjustments,previewOrderingAdjustmentReuse,updateOrderingAdjustmentLines } from './api'
import { buildAdjustmentUpdates,decimalStringsEqual,dirtyAdjustmentLineIds,editableDecimalString,initialAdjustmentValues,validateAdjustmentQuantity } from './editor'
import { buildAdjustmentMenuMatrix } from './matrix'
import type {AdjustmentMenuMatrix} from './matrix'
import type { ExistingAdjustmentDetail,OrderingAdjustmentDetail,OrderingAdjustmentMenuPair,OrderingAdjustmentReusePreview,OrderingAdjustmentStatus,OrderingAdjustmentSummary } from './types'
import { adjustmentDateRange,adjustmentStatusLabels,formatAdjustmentQuantity,staleReasonLabel } from './view'

const pageSize=25

function existingAdjustment(error:unknown):ExistingAdjustmentDetail|null{
  if(!(error instanceof ApiError)||error.status!==409||!error.detail||typeof error.detail!=='object')return null
  const detail=error.detail as Partial<ExistingAdjustmentDetail>
  return (detail.code==='ADJUSTMENT_DRAFT_EXISTS'||detail.code==='ADJUSTMENT_ALREADY_CONFIRMED')&&typeof detail.existing_sheet_id==='string'?detail as ExistingAdjustmentDetail:null
}

export function OrderingAdjustmentsPage({initialSheetId,onReview}:{initialSheetId?:string|null;onReview?:(detail:OrderingAdjustmentDetail)=>void}){
  const [detail,setDetail]=useState<OrderingAdjustmentDetail|null>(null),[detailLoading,setDetailLoading]=useState(false)
  const [items,setItems]=useState<OrderingAdjustmentSummary[]>([]),[total,setTotal]=useState(0),[page,setPage]=useState(1)
  const [status,setStatus]=useState<OrderingAdjustmentStatus|''>(''),[startDate,setStartDate]=useState(''),[endDate,setEndDate]=useState('')
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[createOpen,setCreateOpen]=useState(false),[deleteTarget,setDeleteTarget]=useState<OrderingAdjustmentSummary|null>(null),[deleting,setDeleting]=useState(false)
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
  useEffect(()=>{if(initialSheetId)void open(initialSheetId)},[initialSheetId])
  function back(){setDetail(null);void load()}
  async function removeDraft(){if(!deleteTarget||deleting)return;setDeleting(true);setError('');try{await deleteOrderingAdjustment(deleteTarget.id,deleteTarget.lock_version);setDeleteTarget(null);await load()}catch(cause){setDeleteTarget(null);setError(orderingActionError(cause,'刪除叫貨調整單失敗，請重新載入後再試。'))}finally{setDeleting(false)}}
  if(detailLoading)return <section><LoadingState label="叫貨調整單載入中…"/></section>
  if(detail)return <OrderingAdjustmentDetailView detail={detail} onDetailChange={setDetail} onBack={back} onReview={onReview}/>
  return <section className="ordering-adjustments-page">
    <PageHeader title="叫貨調整" description="依菜單與日期建立調整草稿，保留每道菜、每項食材的系統計算量。" actions={<button onClick={()=>setCreateOpen(true)}>＋ 建立叫貨調整單</button>}/>
    <div className="toolbar ordering-adjustment-filters"><label>狀態<select value={status} onChange={event=>{setStatus(event.target.value as OrderingAdjustmentStatus|'');setPage(1)}}><option value="">全部</option><option value="draft">草稿</option><option value="confirmed">已確認</option><option value="cancelled">已取消</option></select></label><label>開始日期<input type="date" value={startDate} onChange={event=>{setStartDate(event.target.value);setPage(1)}}/></label><label>結束日期<input type="date" value={endDate} onChange={event=>{setEndDate(event.target.value);setPage(1)}}/></label></div>
    {rangeError&&<Feedback type="error">{rangeError}</Feedback>}{error&&<Feedback type="error">{error}</Feedback>}
    {loading?<LoadingState label="叫貨調整單載入中…"/>:!items.length?<EmptyState title="目前沒有叫貨調整單" description="可從上方建立新的叫貨調整草稿。"/>:<AdjustmentList items={items} onOpen={id=>void open(id)} onDelete={setDeleteTarget}/>}
    {!rangeError&&<PaginationControls page={page} pageSize={pageSize} total={total} onPage={setPage}/>} 
    {createOpen&&<CreateAdjustmentDialog onClose={()=>setCreateOpen(false)} onCreated={value=>{setCreateOpen(false);setDetail(value)}} onOpenExisting={id=>{setCreateOpen(false);void open(id)}}/>}
    {deleteTarget&&<DeleteAdjustmentDialog item={deleteTarget} busy={deleting} onCancel={()=>setDeleteTarget(null)} onConfirm={()=>void removeDraft()}/>}
  </section>
}

function AdjustmentList({items,onOpen,onDelete}:{items:OrderingAdjustmentSummary[];onOpen:(id:string)=>void;onDelete:(item:OrderingAdjustmentSummary)=>void}){
  return <TableFrame><table className="ordering-adjustment-list"><thead><tr><th>狀態</th><th>菜單</th><th>日期範圍</th><th>Revision</th><th>建立時間</th><th>最後更新</th><th>建立者</th><th></th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td><AdjustmentStatus status={item.status} stale={item.stale===true}/></td><td>{item.source_menus.map(menu=>menu.menu_name).join('、')||'—'}</td><td>{adjustmentDateRange(item.criteria,item)}</td><td>{item.revision}</td><td>{new Date(item.created_at).toLocaleString('zh-TW')}</td><td>{new Date(item.updated_at).toLocaleString('zh-TW')}</td><td>{item.created_by_name||'—'}</td><td><div className="ordering-adjustment-list-actions"><button onClick={()=>onOpen(item.id)}>{item.status==='draft'&&!item.stale?'開啟':'查看'}</button>{item.status==='draft'&&<button className="secondary-danger" onClick={()=>onDelete(item)}>刪除</button>}</div></td></tr>)}</tbody></table></TableFrame>
}

function AdjustmentStatus({status,stale=false}:{status:OrderingAdjustmentStatus;stale?:boolean}){return <span className={`ordering-adjustment-status is-${stale?'stale':status}`}>{stale?'已失效':adjustmentStatusLabels[status]}</span>}

function DeleteAdjustmentDialog({item,busy,onCancel,onConfirm}:{item:OrderingAdjustmentSummary;busy:boolean;onCancel:()=>void;onConfirm:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel danger-dialog" role="alertdialog" aria-modal="true"><header><div><h2>刪除叫貨調整單？</h2><p>刪除後，這張叫貨調整單與尚未確認的調整數量將無法復原。</p></div></header><dl className="ordering-delete-summary"><div><dt>菜單</dt><dd>{item.source_menus.map(menu=>menu.menu_name).join('、')||'—'}</dd></div><div><dt>日期範圍</dt><dd>{adjustmentDateRange(item.criteria,item)}</dd></div><div><dt>狀態</dt><dd>{item.stale?'已失效':'草稿'}</dd></div></dl><footer><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button className="danger" disabled={busy} onClick={onConfirm}>{busy?'刪除中…':'確認刪除'}</button></footer></section></div>
}

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

type AdjustmentConfirmation='back'|'reload'|null
type SaveBlock='conflict'|'stale'|null

function AdjustmentConfirmDialog({kind,onCancel,onConfirm}:{kind:Exclude<AdjustmentConfirmation,null>;onCancel:()=>void;onConfirm:()=>void}){
  const reload=kind==='reload'
  return <div className="modal-backdrop"><section className="modal-panel danger-dialog" role="alertdialog" aria-modal="true"><header><div><h2>{reload?'重新載入最新資料？':'離開叫貨調整單？'}</h2><p>{reload?'重新載入會捨棄尚未儲存的修改，確定要繼續嗎？':'尚有未儲存的叫貨量修改，確定要離開嗎？'}</p></div></header><footer><button autoFocus className="secondary" onClick={onCancel}>留在此頁</button><button className="secondary-danger" onClick={onConfirm}>{reload?'捨棄修改並重新載入':'放棄修改並離開'}</button></footer></section></div>
}

function CompleteAdjustmentDialog({busy,onCancel,onConfirm}:{busy:boolean;onCancel:()=>void;onConfirm:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel" role="alertdialog" aria-modal="true"><header><div><h2>完成叫貨調整？</h2><p>確認後，這張叫貨調整單將標記為「已確認」，並鎖定目前的叫貨調整數量。</p><p>已確認的調整單可以作為之後沿用叫貨量的歷史來源。</p><p><strong>已確認不代表已建立正式採購單。</strong></p></div></header><footer><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button disabled={busy} onClick={onConfirm}>{busy?'確認中…':'確認完成'}</button></footer></section></div>
}

function ReuseAgainDialog({onCancel,onConfirm}:{onCancel:()=>void;onConfirm:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel" role="alertdialog" aria-modal="true"><header><div><h2>重新比對上一張叫貨量？</h2><p>此叫貨調整單已沿用過上一張叫貨量。重新比對會依目前菜單重新分析可沿用項目，但不會覆蓋已人工調整或已確認的叫貨量。</p></div></header><footer><button autoFocus className="secondary" onClick={onCancel}>取消</button><button className="secondary" onClick={onConfirm}>繼續重新比對</button></footer></section></div>
}

function OrderingAdjustmentDetailView({detail,onDetailChange,onBack,onReview}:{detail:OrderingAdjustmentDetail;onDetailChange:(value:OrderingAdjustmentDetail)=>void;onBack:()=>void;onReview?:(detail:OrderingAdjustmentDetail)=>void}){
  const [values,setValues]=useState<Record<string,string>>(()=>initialAdjustmentValues(detail.lines))
  const [saving,setSaving]=useState(false),[reloading,setReloading]=useState(false),[confirming,setConfirming]=useState(false),[completeOpen,setCompleteOpen]=useState(false),[message,setMessage]=useState(''),[saveError,setSaveError]=useState('')
  const [saveBlock,setSaveBlock]=useState<SaveBlock>(null),[confirmation,setConfirmation]=useState<AdjustmentConfirmation>(null),[reuseOpen,setReuseOpen]=useState(false),[reuseAgainOpen,setReuseAgainOpen]=useState(false)
  const [activeMenuId,setActiveMenuId]=useState(detail.source_menus[0]?.menu_id??''),[layouts,setLayouts]=useState<Record<string,MenuAggregate>>({}),[layoutLoading,setLayoutLoading]=useState(Boolean(detail.source_menus.length)),[layoutError,setLayoutError]=useState('')
  const readOnly=detail.status!=='draft'||detail.stale,saveLocked=saveBlock!==null
  const reviewLineIds=new Set(detail.lines.filter(line=>line.review_required).map(line=>line.id))
  const dirtyIds=dirtyAdjustmentLineIds(detail.lines,values),dirtySet=new Set(dirtyIds)
  const menuDirtyCounts=Object.fromEntries(detail.source_menus.map(menu=>[menu.menu_id,detail.lines.filter(line=>line.source_menu_id===menu.menu_id&&dirtySet.has(line.id)).length]))
  const validationErrors=Object.fromEntries(detail.lines.map(line=>[line.id,validateAdjustmentQuantity(values[line.id]??'')]))
  const hasInvalid=dirtyIds.some(id=>Boolean(validationErrors[id]))
  const clearEditorDirty=useEditorDirty(dirtyIds.length>0)
  const staleReasons=[...new Set([...detail.warnings.map(warning=>warning.code),...detail.lines.flatMap(line=>line.stale_reasons)].map(staleReasonLabel))]
  const matrices=detail.source_menus.map(menu=>buildAdjustmentMenuMatrix(detail.lines,menu,layouts[menu.menu_id],detail.criteria)),activeMatrix=matrices.find(matrix=>matrix.menuId===activeMenuId)??matrices[0]
  useEffect(()=>{setValues(initialAdjustmentValues(detail.lines));setSaveBlock(null)},[detail])
  useEffect(()=>{
    let current=true;setLayoutLoading(Boolean(detail.source_menus.length));setLayoutError('')
    void Promise.all(detail.source_menus.map(async menu=>[menu.menu_id,await getOrderingAdjustmentMenuLayout(menu.menu_id)] as const)).then(results=>{if(current)setLayouts(Object.fromEntries(results))}).catch(()=>{if(current)setLayoutError('部分菜單欄位名稱無法載入，已依調整單保存的原始順序顯示。')}).finally(()=>{if(current)setLayoutLoading(false)})
    return()=>{current=false}
  },[detail.id])
  function change(lineId:string,value:string){setValues(current=>({...current,[lineId]:value}));setMessage('');setSaveError('')}
  async function save(){
    if(readOnly||saveLocked||saving||!dirtyIds.length||hasInvalid)return
    setSaving(true);setMessage('');setSaveError('')
    try{const updated=await updateOrderingAdjustmentLines(detail.id,{lock_version:detail.lock_version,lines:buildAdjustmentUpdates(detail.lines,values)});clearEditorDirty();onDetailChange(updated);setMessage('草稿已儲存')}
    catch(cause){
      const code=apiErrorCode(cause)
      if(code==='LOCK_VERSION_CONFLICT'){setSaveBlock('conflict');setSaveError('這張叫貨調整單已在其他地方被修改，請重新載入最新資料。')}
      else if(code==='ADJUSTMENT_STALE'){setSaveBlock('stale');setSaveError('來源資料已變更，無法繼續儲存。請重新載入最新資料。')}
      else setSaveError('儲存失敗，修改尚未遺失，請稍後再試。')
    }finally{setSaving(false)}
  }
  async function reload(){setReloading(true);setMessage('');setSaveError('');try{const updated=await getOrderingAdjustment(detail.id);clearEditorDirty();onDetailChange(updated)}catch{setSaveError('重新載入失敗，尚未儲存的修改仍保留在畫面上。')}finally{setReloading(false)}}
  function requestReload(){if(dirtyIds.length)setConfirmation('reload');else void reload()}
  function requestBack(){if(dirtyIds.length)setConfirmation('back');else onBack()}
  function requestComplete(){if(dirtyIds.length){setSaveError('目前有尚未儲存的修改，請先儲存後再完成叫貨調整。');return}setCompleteOpen(true)}
  function requestReuse(){if(dirtyIds.length){setSaveError('請先儲存或還原目前修改，再沿用上一張叫貨量。');return}if(detail.reuse_applied_at)setReuseAgainOpen(true);else setReuseOpen(true)}
  async function complete(){if(confirming||dirtyIds.length)return;setConfirming(true);setSaveError('');try{const updated=await confirmOrderingAdjustment(detail.id,detail.lock_version);clearEditorDirty();setCompleteOpen(false);onDetailChange(updated);setMessage('叫貨調整已完成確認')}catch(cause){setSaveError(orderingActionError(cause,'完成叫貨調整失敗，請稍後再試。'));setCompleteOpen(false)}finally{setConfirming(false)}}
  return <section className={`ordering-adjustment-detail is-${detail.status}${detail.stale?' is-stale':''}`}>
    <PageHeader title="叫貨調整單" description="可直接編輯的週配料表" actions={<>{detail.status==='draft'&&!detail.stale&&<>{detail.reuse_applied_at?<><span className="ordering-reuse-status">✓ 已沿用上一張叫貨量</span><button className="secondary" onClick={requestReuse}>重新比對</button></>:<button className="secondary" onClick={requestReuse}>沿用上一張叫貨量</button>}<button onClick={requestComplete}>完成叫貨調整</button></>}<button onClick={()=>onReview?.(detail)}>前往食材需求</button><button className="secondary" onClick={requestBack}>← 返回列表</button></>}/>
    <div className="ordering-adjustment-summary"><div><strong>{activeMatrix?.menuName??detail.source_menus.map(menu=>menu.menu_name).join('、')}</strong><span>{activeMatrix?.dates.length?`${formatShortDate(activeMatrix.dates[0])} ～ ${formatShortDate(activeMatrix.dates.at(-1)!)}`:adjustmentDateRange(detail.criteria,detail)}</span><span><AdjustmentStatus status={detail.status}/> · Rev.{detail.revision}</span></div><small>建立：{new Date(detail.created_at).toLocaleString('zh-TW')}　最後更新：{new Date(detail.updated_at).toLocaleString('zh-TW')}</small></div>
    {detail.stale&&<Feedback type="error"><strong>來源資料已變更，此調整單需要重新建立。</strong>{staleReasons.length>0&&<ul>{staleReasons.map(reason=><li key={reason}>{reason}</li>)}</ul>}</Feedback>}
    {saveError&&<Feedback type="error">{saveError}{saveBlock&&<button type="button" className="secondary ordering-reload-action" disabled={reloading} onClick={requestReload}>{reloading?'重新載入中…':'重新載入'}</button>}</Feedback>}
    {message&&<Feedback type="success">{message}</Feedback>}
    {reviewLineIds.size>0&&<div className="ordering-review-banner" role="status"><strong>{reviewLineIds.size} 項叫貨量需要確認</strong><span>請檢查紅色標示的菜色與食材，完成調整並儲存。</span></div>}
    {!detail.stale&&detail.status==='confirmed'&&<Feedback type="info">此叫貨調整已完成確認，數量已鎖定。</Feedback>}
    {!detail.stale&&detail.status==='cancelled'&&<Feedback type="info">此調整單已取消，目前僅供查看。</Feedback>}
    {detail.source_menus.length>1&&<div className="ordering-adjustment-tabs" role="tablist" aria-label="菜單"><>{matrices.map(matrix=><button role="tab" aria-selected={matrix.menuId===activeMenuId} className={matrix.menuId===activeMenuId?'active':''} key={matrix.menuId} onClick={()=>setActiveMenuId(matrix.menuId)}>{matrix.menuName}{menuDirtyCounts[matrix.menuId]?` · ${menuDirtyCounts[matrix.menuId]}`:''}</button>)}</></div>}
    {layoutError&&<Feedback type="info">{layoutError}</Feedback>}
    {layoutLoading?<LoadingState label="菜單欄位載入中…"/>:!activeMatrix||!activeMatrix.meals.length?<EmptyState title="這張調整單沒有食材明細"/>:<AdjustmentWeeklyMatrix matrix={activeMatrix} values={values} dirtySet={dirtySet} reviewLineIds={reviewLineIds} validationErrors={validationErrors} readOnly={readOnly} saving={saving} saveLocked={saveLocked} onChange={change}/>}
    {!readOnly&&<div className="ordering-adjustment-savebar"><strong>{dirtyIds.length?`尚有 ${dirtyIds.length} 筆修改未儲存`:'目前沒有未儲存的修改'}</strong><button disabled={saving||saveLocked||!dirtyIds.length||hasInvalid} onClick={()=>void save()}>{saving?'儲存中…':'儲存草稿'}</button></div>}
    {confirmation&&<AdjustmentConfirmDialog kind={confirmation} onCancel={()=>setConfirmation(null)} onConfirm={()=>{const action=confirmation;setConfirmation(null);if(action==='back'){clearEditorDirty();onBack()}else void reload()}}/>}
    {completeOpen&&<CompleteAdjustmentDialog busy={confirming} onCancel={()=>setCompleteOpen(false)} onConfirm={()=>void complete()}/>}
    {reuseAgainOpen&&<ReuseAgainDialog onCancel={()=>setReuseAgainOpen(false)} onConfirm={()=>{setReuseAgainOpen(false);setReuseOpen(true)}}/>}
    {reuseOpen&&<ReuseAdjustmentDialog current={detail} onClose={()=>setReuseOpen(false)} onApplied={updated=>{clearEditorDirty();setReuseOpen(false);onDetailChange(updated);setMessage('已沿用上一張叫貨量')}}/>}
  </section>
}

function ReuseAdjustmentDialog({current,onClose,onApplied}:{current:OrderingAdjustmentDetail;onClose:()=>void;onApplied:(value:OrderingAdjustmentDetail)=>void}){
  const [sources,setSources]=useState<OrderingAdjustmentSummary[]>([]),[previousId,setPreviousId]=useState(''),[pairs,setPairs]=useState<Record<string,string>>({})
  const [preview,setPreview]=useState<OrderingAdjustmentReusePreview|null>(null),[selected,setSelected]=useState<Set<string>>(new Set())
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{let active=true;void listOrderingAdjustments({page:1,pageSize:100}).then(result=>{if(active)setSources(result.items.filter(item=>item.id!==current.id&&item.status!=='cancelled'))}).catch(()=>{if(active)setError('上一張叫貨調整單載入失敗。')}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[current.id])
  const previous=sources.find(item=>item.id===previousId)
  function choosePrevious(id:string){setPreviousId(id);setPreview(null);setSelected(new Set());const source=sources.find(item=>item.id===id);const next:Record<string,string>={};if(source?.source_menus.length===1&&current.source_menus.length===1)next[current.source_menus[0].menu_id]=source.source_menus[0].menu_id;setPairs(next)}
  const menuPairs:OrderingAdjustmentMenuPair[]=current.source_menus.map(menu=>({current_menu_id:menu.menu_id,previous_menu_id:pairs[menu.menu_id]??''})).filter(pair=>pair.previous_menu_id)
  const request=previous?{previous_sheet_id:previous.id,current_lock_version:current.lock_version,previous_lock_version:previous.lock_version,menu_pairs:menuPairs}:null
  async function runPreview(){if(!request||menuPairs.length!==current.source_menus.length){setError('請完成每一份目前菜單與上一份菜單的配對。');return}setBusy(true);setError('');try{const value=await previewOrderingAdjustmentReuse(current.id,request);setPreview(value);setSelected(new Set(value.lines.filter(line=>line.status==='safe_to_reuse').map(line=>line.current_line_id)))}catch{setError('比對失敗；請確認上一張調整單仍可使用，且目前草稿沒有過期。')}finally{setBusy(false)}}
  async function apply(){if(!request||!preview||!selected.size)return;setBusy(true);setError('');try{const updated=await applyOrderingAdjustmentReuse(current.id,{...request,selected_current_line_ids:[...selected]});onApplied(updated)}catch{setError('套用失敗，資料可能已被更新；請重新比對。')}finally{setBusy(false)}}
  return <div className="modal-backdrop"><section className="modal-panel wide ordering-reuse-dialog" role="dialog" aria-modal="true"><header><div><h2>沿用上一張叫貨量</h2><p>系統會逐項比對；沒有變更的菜色可直接沿用，已更換或理論量有變化的項目會保留給你重新確認。</p></div></header>
    {loading?<LoadingState label="調整單載入中…"/>:<><label>上一張叫貨調整單<select value={previousId} onChange={event=>choosePrevious(event.target.value)}><option value="">請選擇</option>{sources.map(item=><option value={item.id} key={item.id}>{item.source_menus.map(menu=>menu.menu_name).join('、')}｜{adjustmentDateRange(item.criteria,item)}｜{adjustmentStatusLabels[item.status]}</option>)}</select></label>
    {previous&&<div className="ordering-reuse-pairs">{current.source_menus.map(menu=><label key={menu.menu_id}>目前：{menu.menu_name}<select value={pairs[menu.menu_id]??''} onChange={event=>{setPairs(value=>({...value,[menu.menu_id]:event.target.value}));setPreview(null)}}><option value="">選擇上一份菜單</option>{previous.source_menus.map(source=><option value={source.menu_id} disabled={Object.entries(pairs).some(([currentId,previousMenuId])=>currentId!==menu.menu_id&&previousMenuId===source.menu_id)} key={source.menu_id}>{source.menu_name}（{source.start_date}～{source.end_date}）</option>)}</select></label>)}</div>}
    {!preview&&<button disabled={busy||!previous} onClick={()=>void runPreview()}>{busy?'比對中…':'開始比對'}</button>}</>}
    {error&&<Feedback type="error">{error}</Feedback>}
    {preview&&<><div className="ordering-reuse-summary"><span><b>{preview.summary.safe_to_reuse}</b> 可直接沿用</span><span><b>{preview.summary.reference_only}</b> 比對後需人工判斷</span><span><b>{preview.summary.no_match}</b> 新菜／已更換</span><span><b>{preview.summary.ambiguous}</b> 無法唯一比對</span></div><small className="ordering-reuse-comparison-note">此處為新的比對結果；目前草稿尚待確認的數量仍以上方紅色提示為準。</small><div className="ordering-reuse-lines">{preview.lines.filter(line=>line.status!=='no_match'||line.reason_codes[0]!=='NO_REUSABLE_ADJUSTMENT').map(line=><label className={`ordering-reuse-line is-${line.status}`} key={line.current_line_id}><input type="checkbox" disabled={line.status!=='safe_to_reuse'} checked={selected.has(line.current_line_id)} onChange={()=>setSelected(value=>{const next=new Set(value);if(next.has(line.current_line_id))next.delete(line.current_line_id);else next.add(line.current_line_id);return next})}/><span><strong>{line.requirement_date} {line.meal_name}｜{line.dish_name}／{line.ingredient_name}</strong><small>{reuseLineText(line)}</small></span></label>)}</div></>}
    <footer><button className="secondary" disabled={busy} onClick={onClose}>取消</button>{preview&&<button disabled={busy||!selected.size} onClick={()=>void apply()}>{busy?'套用中…':`套用 ${selected.size} 項`}</button>}</footer>
  </section></div>
}

function reuseLineText(line:OrderingAdjustmentReusePreview['lines'][number]){
  if(line.status==='safe_to_reuse')return `上次 ${formatAdjustmentQuantity(line.previous_system_quantity!)} → ${formatAdjustmentQuantity(line.previous_adjusted_quantity!)} ${line.previous_system_unit}；本次理論量相同`
  if(line.reason_codes.includes('SYSTEM_QUANTITY_CHANGED'))return `上次 ${formatAdjustmentQuantity(line.previous_system_quantity!)} → ${formatAdjustmentQuantity(line.previous_adjusted_quantity!)} ${line.previous_system_unit}；本次 ${formatAdjustmentQuantity(line.current_system_quantity)} ${line.current_system_unit}，請人工確認`
  if(line.reason_codes.includes('CURRENT_ALREADY_ADJUSTED'))return '本次已有人工調整，不會覆蓋'
  if(line.status==='ambiguous')return '找到多筆可能來源，無法自動沿用'
  return '新菜、已更換菜色或配方食材已改變，需本次重新處理'
}

function AdjustmentWeeklyMatrix({matrix,values,dirtySet,reviewLineIds,validationErrors,readOnly,saving,saveLocked,onChange}:{matrix:AdjustmentMenuMatrix;values:Record<string,string>;dirtySet:Set<string>;reviewLineIds:Set<string>;validationErrors:Record<string,string|null>;readOnly:boolean;saving:boolean;saveLocked:boolean;onChange:(lineId:string,value:string)=>void}){
  return <div className="ordering-adjustment-matrix"><table><thead><tr><th className="matrix-meal-heading">餐別</th><th className="matrix-column-heading">菜單欄位</th>{matrix.dates.map(date=><th key={date}>{formatDate(date)}</th>)}</tr></thead><tbody>{matrix.meals.flatMap(meal=>meal.rows.map((row,rowIndex)=><tr key={`${meal.id}:${rowIndex}`}>{rowIndex===0&&<th className="matrix-meal-cell" rowSpan={meal.rows.length}>{meal.name}</th>}<th className="matrix-column-cell">{row.label}</th>{matrix.dates.map(date=><td key={date}><div className="ordering-adjustment-cell">{(row.cells[date]??[]).map(dish=>{const dishNeedsReview=dish.lines.some(line=>reviewLineIds.has(line.id));return <article className={`ordering-adjustment-cell-dish${dishNeedsReview?' needs-review':''}`} key={dish.id}><header><strong>{dish.name}</strong><span>{dish.dinerCount} 人</span>{dishNeedsReview&&<b className="ordering-review-badge">需確認</b>}</header>{dish.lines.map(line=>{
    const persistedAdjusted=line.adjusted_quantity!==null&&!decimalStringsEqual(line.adjusted_quantity,line.system_quantity),dirty=dirtySet.has(line.id),error=dirty?validationErrors[line.id]:null
    const actual=values[line.id]??editableDecimalString(line.effective_quantity),showRestore=!decimalStringsEqual(actual,line.system_quantity)||dirty
    const needsReview=reviewLineIds.has(line.id)
    return <div className={`ordering-adjustment-cell-line${dirty?' is-dirty':''}${needsReview?' needs-review':''}`} key={line.id}><strong>{line.ingredient_name_snapshot}</strong><div className="ordering-adjustment-cell-quantity"><span>{formatAdjustmentQuantity(line.system_quantity)}</span><span aria-hidden="true">→</span>{readOnly?<b>{formatAdjustmentQuantity(line.effective_quantity)}</b>:<input type="text" inputMode="decimal" aria-label={`${dish.name} - ${line.ingredient_name_snapshot} 實際叫貨量`} disabled={saving||saveLocked} value={actual} onChange={event=>onChange(line.id,event.target.value)} onKeyDown={event=>{if(event.key==='Enter')event.preventDefault()}}/>}<span>{line.system_unit}</span></div><div className="ordering-adjustment-cell-state">{needsReview&&<small className="ordering-review-badge">需確認</small>}{persistedAdjusted&&<small className="persisted">人工調整</small>}{dirty&&<small className="dirty">已修改</small>}{!readOnly&&showRestore&&<button type="button" className="text-button" disabled={saving||saveLocked} onClick={()=>onChange(line.id,editableDecimalString(line.system_quantity))}>恢復</button>}</div>{error&&<small className="error">{error}</small>}</div>
  })}</article>})}</div></td>)}</tr>))}</tbody></table></div>
}

function apiErrorCode(error:unknown){
  if(!(error instanceof ApiError)||!error.detail||typeof error.detail!=='object')return null
  const code=(error.detail as {code?:unknown}).code
  return typeof code==='string'?code:null
}

function orderingActionError(error:unknown,fallback:string){
  const code=apiErrorCode(error)
  if(code==='LOCK_VERSION_CONFLICT')return '資料已被更新，請重新載入後再試。'
  if(code==='ADJUSTMENT_STALE')return '來源菜單或配方已變更，這張調整單無法完成確認。'
  if(code==='CONFIRMED_DELETE_FORBIDDEN')return '已確認的叫貨調整單不能刪除。'
  if(code==='CANCELLED_DELETE_FORBIDDEN')return '已取消的叫貨調整單不能刪除。'
  if(code==='SNAPSHOT_LOCKED')return '這張調整單已被正式流程使用，不能刪除。'
  if(error instanceof ApiError&&error.status===404)return '找不到這張叫貨調整單。'
  return fallback
}

function formatShortDate(value:string){const [,month,day]=value.split('-');return `${String(Number(month)).padStart(2,'0')}/${String(Number(day)).padStart(2,'0')}`}
function formatDate(value:string){const date=new Date(`${value}T00:00:00+08:00`);const weekday=['日','一','二','三','四','五','六'][date.getDay()];return `${formatShortDate(value)}（${weekday}）`}
