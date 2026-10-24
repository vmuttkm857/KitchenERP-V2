import { FormEvent,useCallback,useEffect,useLayoutEffect,useRef,useState } from 'react'
import type {Dispatch,ReactNode,SetStateAction} from 'react'
import { ApiError } from '../../api/client'
import { useEditorDirty } from '../../app/NavigationBlocker'
import { EmptyState,Feedback,LoadingState,PageHeader,TableFrame } from '../../components/ui/Page'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { dateRangeError,RequestSequence } from '../../utils/listQuery'
import { MenuCandidateFilters,MenuCandidateOption,menuMonthRange } from '../menus/MenuCandidateFilters'
import {mealSectionTone} from '../menus/mealSectionTone'
import {MenuMealEditorDialog} from '../menus/MenuMealEditorDialog'
import type { Menu } from '../menus/types'
import { useMenuCandidates } from '../menus/useMenuCandidates'
import type {MenuAggregate} from '../menus/types'
import { applyOrderingAdjustmentReuse,applyOrderingAdjustmentSync,confirmOrderingAdjustment,convertOrderingAdjustmentUnits,createOrderingAdjustment,deleteOrderingAdjustment,downloadOrderingAdjustmentWeekly,getOrderingAdjustment,getOrderingAdjustmentMenuLayout,listOrderingAdjustments,previewOrderingAdjustmentReuse,previewOrderingAdjustmentSync,reopenOrderingAdjustment,updateOrderingAdjustmentLines } from './api'
import { buildAdjustmentUpdates,decimalStringsEqual,dirtyAdjustmentLineIds,editableDecimalString,initialAdjustmentUnits,initialAdjustmentValues,validateAdjustmentQuantity } from './editor'
import { buildAdjustmentMenuMatrix } from './matrix'
import {canAutoApplyMealSync,captureAdjustmentScroll,prepareAdjustmentMealEdit,restoreAdjustmentScroll,validAdjustmentMealTarget} from './mealEditing'
import type {AdjustmentMealTarget,AdjustmentScrollPosition} from './mealEditing'
import type {AdjustmentMenuMatrix} from './matrix'
import type { ExistingAdjustmentDetail,OrderingAdjustmentDetail,OrderingAdjustmentMenuPair,OrderingAdjustmentReusePreview,OrderingAdjustmentStatus,OrderingAdjustmentSummary,OrderingAdjustmentSyncChange,OrderingAdjustmentSyncPreview,OrderingAdjustmentSyncSnapshot,OrderingAdjustmentUnitConversion } from './types'
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
  async function review(sheetId:string){setDetailLoading(true);setError('');try{onReview?.(await getOrderingAdjustment(sheetId))}catch{setError('叫貨調整單內容載入失敗，無法前往食材需求。')}finally{setDetailLoading(false)}}
  useEffect(()=>{if(initialSheetId)void open(initialSheetId)},[initialSheetId])
  function back(){setDetail(null);void load()}
  async function removeDraft(){if(!deleteTarget||deleting)return;setDeleting(true);setError('');try{await deleteOrderingAdjustment(deleteTarget.id,deleteTarget.lock_version);setDeleteTarget(null);await load()}catch(cause){setDeleteTarget(null);setError(orderingActionError(cause,'刪除叫貨調整單失敗，請重新載入後再試。'))}finally{setDeleting(false)}}
  if(detailLoading)return <section><LoadingState label="叫貨調整單載入中…"/></section>
  if(detail)return <OrderingAdjustmentDetailView detail={detail} onDetailChange={setDetail} onBack={back} onReview={onReview}/>
  return <section className="ordering-adjustments-page">
    <PageHeader title="叫貨調整" description="依菜單與日期建立調整草稿，保留每道菜、每項食材的系統計算量。" actions={<button onClick={()=>setCreateOpen(true)}>＋ 建立叫貨調整單</button>}/>
    <div className="toolbar ordering-adjustment-filters"><label>狀態<select value={status} onChange={event=>{setStatus(event.target.value as OrderingAdjustmentStatus|'');setPage(1)}}><option value="">全部</option><option value="draft">草稿</option><option value="confirmed">已確認</option><option value="cancelled">已取消</option></select></label><label>開始日期<input type="date" value={startDate} onChange={event=>{setStartDate(event.target.value);setPage(1)}}/></label><label>結束日期<input type="date" value={endDate} onChange={event=>{setEndDate(event.target.value);setPage(1)}}/></label></div>
    {rangeError&&<Feedback type="error">{rangeError}</Feedback>}{error&&<Feedback type="error">{error}</Feedback>}
    <WorkflowGuide active="adjustment"/>
    {loading?<LoadingState label="叫貨調整單載入中…"/>:!items.length?<EmptyState title="目前沒有叫貨調整單" description="可從上方建立新的叫貨調整草稿。"/>:<AdjustmentList items={items} onOpen={id=>void open(id)} onReview={id=>void review(id)} onDelete={setDeleteTarget}/>}
    {!rangeError&&<PaginationControls page={page} pageSize={pageSize} total={total} onPage={setPage}/>} 
    {createOpen&&<CreateAdjustmentDialog onClose={()=>setCreateOpen(false)} onCreated={value=>{setCreateOpen(false);setDetail(value)}} onOpenExisting={id=>{setCreateOpen(false);void open(id)}}/>}
    {deleteTarget&&<DeleteAdjustmentDialog item={deleteTarget} busy={deleting} onCancel={()=>setDeleteTarget(null)} onConfirm={()=>void removeDraft()}/>}
  </section>
}

function AdjustmentList({items,onOpen,onReview,onDelete}:{items:OrderingAdjustmentSummary[];onOpen:(id:string)=>void;onReview:(id:string)=>void;onDelete:(item:OrderingAdjustmentSummary)=>void}){
  return <TableFrame><table className="ordering-adjustment-list"><thead><tr><th>狀態</th><th>菜單</th><th>日期範圍</th><th>Revision</th><th>建立時間</th><th>最後更新</th><th>建立者</th><th>操作</th></tr></thead><tbody>{items.map(item=><tr className={`is-${item.stale?'stale':item.status}`} key={item.id}><td><AdjustmentStatus status={item.status} stale={item.stale===true}/></td><td className="ordering-adjustment-list-menu"><strong>{item.source_menus.map(menu=>menu.menu_name).join('、')||'—'}</strong></td><td className="ordering-adjustment-list-range">{adjustmentDateRange(item.criteria,item)}</td><td>{item.revision}</td><td>{new Date(item.created_at).toLocaleString('zh-TW')}</td><td>{new Date(item.updated_at).toLocaleString('zh-TW')}</td><td>{item.created_by_name||'—'}</td><td><div className="ordering-adjustment-list-actions"><button onClick={()=>onOpen(item.id)}>{item.status==='draft'&&!item.stale?'開啟':'查看'}</button>{item.status==='confirmed'&&<button onClick={()=>onReview(item.id)}>前往食材需求</button>}{item.status==='draft'&&<button className="secondary-danger" onClick={()=>onDelete(item)}>刪除</button>}</div></td></tr>)}</tbody></table></TableFrame>
}

function WorkflowGuide({active}:{active:'adjustment'|'requirements'}){return <div className="procurement-workflow-guide" aria-label="需求採購作業流程"><span>1 選擇菜單</span><strong className={active==='adjustment'?'active':''}>2 叫貨調整</strong><strong className={active==='requirements'?'active':''}>3 食材需求</strong><span>4 固定需求快照</span><span>5 正式採購</span></div>}

function AdjustmentStatus({status,stale=false}:{status:OrderingAdjustmentStatus;stale?:boolean}){return <span className={`ordering-adjustment-status is-${stale?'stale':status}`}>{stale?'已失效':adjustmentStatusLabels[status]}</span>}

function DeleteAdjustmentDialog({item,busy,onCancel,onConfirm}:{item:OrderingAdjustmentSummary;busy:boolean;onCancel:()=>void;onConfirm:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel danger-dialog" role="alertdialog" aria-modal="true"><header><div><h2>刪除叫貨調整單？</h2><p>刪除後，這張叫貨調整單與尚未確認的調整數量將無法復原。</p></div></header><dl className="ordering-delete-summary"><div><dt>菜單</dt><dd>{item.source_menus.map(menu=>menu.menu_name).join('、')||'—'}</dd></div><div><dt>日期範圍</dt><dd>{adjustmentDateRange(item.criteria,item)}</dd></div><div><dt>狀態</dt><dd>{item.stale?'已失效':'草稿'}</dd></div></dl><footer><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button className="danger" disabled={busy} onClick={onConfirm}>{busy?'刪除中…':'確認刪除'}</button></footer></section></div>
}

function CreateAdjustmentDialog({onClose,onCreated,onOpenExisting}:{onClose:()=>void;onCreated:(value:OrderingAdjustmentDetail)=>void;onOpenExisting:(id:string)=>void}){
  const [menuMonth,setMenuMonth]=useState(''),[menuCategoryId,setMenuCategoryId]=useState('');const candidateRange=menuMonthRange(menuMonth)
  const candidates=useMenuCandidates({active:'true',categoryId:menuCategoryId||undefined,...candidateRange,pageSize:20});const [selected,setSelected]=useState<Map<string,Menu>>(new Map())
  const [startDate,setStartDate]=useState(''),[endDate,setEndDate]=useState(''),[datesTouched,setDatesTouched]=useState(false),[notes,setNotes]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const [existing,setExisting]=useState<ExistingAdjustmentDetail|null>(null);const rangeError=!startDate||!endDate?'請同時選擇開始日期與結束日期。':dateRangeError(startDate,endDate)
  const choices=candidates.items
  const selectedMenus=[...selected.values()],suggestedStart=selectedMenus.length?selectedMenus.map(menu=>menu.start_date).sort()[0]:'',suggestedEnd=selectedMenus.length?selectedMenus.map(menu=>menu.end_date).sort().at(-1)??'':'',sameMenuDates=selectedMenus.every(menu=>menu.start_date===selectedMenus[0]?.start_date&&menu.end_date===selectedMenus[0]?.end_date)
  function applySuggestedDates(menus:Menu[]){setStartDate(menus.length?menus.map(item=>item.start_date).sort()[0]:'');setEndDate(menus.length?menus.map(item=>item.end_date).sort().at(-1)??'':'');setExisting(null)}
  function toggle(menu:Menu){const next=new Map(selected);if(next.has(menu.id))next.delete(menu.id);else next.set(menu.id,menu);setSelected(next);if(!datesTouched)applySuggestedDates([...next.values()])}
  async function submit(event:FormEvent){event.preventDefault();if(!selected.size){setError('請至少選擇一份菜單。');return}if(rangeError){setError(rangeError);return}setBusy(true);setError('');setExisting(null)
    try{onCreated(await createOrderingAdjustment({criteria:{menu_ids:[...selected.keys()],start_date:startDate,end_date:endDate},notes:notes.trim()||null}))}
    catch(cause){const conflict=existingAdjustment(cause);if(conflict){setExisting(conflict);setError(conflict.code==='ADJUSTMENT_DRAFT_EXISTS'?'這個範圍已有叫貨調整草稿。':'這個範圍已有已確認的叫貨調整單。')}else setError('建立叫貨調整單失敗，請確認菜單與日期範圍。')}
    finally{setBusy(false)}
  }
  return <div className="modal-backdrop"><section className="modal-panel wide ordering-adjustment-create" role="dialog" aria-modal="true"><header><div><h2>建立叫貨調整單</h2><p>可同時選擇多份菜單；系統會保留各菜單、菜色與食材來源，不會先合併。</p></div></header><form onSubmit={submit}>
    <fieldset className="workflow-step"><legend>① 選擇菜單</legend><strong>已選 {selected.size} 份菜單</strong>{selectedMenus.length>0&&<div className="ordering-selected-menus" aria-label="已選菜單">{selectedMenus.map(menu=><button type="button" className="menu-selection-chip" aria-label={`取消選取 ${menu.name}`} key={menu.id} onClick={()=>toggle(menu)}>{menu.name}　×</button>)}</div>}<MenuCandidateFilters month={menuMonth} onMonth={setMenuMonth} categoryId={menuCategoryId} onCategoryId={setMenuCategoryId} search={candidates.search} onSearch={candidates.setSearch}/>{candidates.error&&<small className="error">{candidates.error}</small>}<div className="menu-choices">{choices.map(menu=><MenuCandidateOption key={menu.id} menu={menu} checked={selected.has(menu.id)} onToggle={()=>toggle(menu)}/>)}</div>{!candidates.loading&&!choices.length&&<small>目前篩選條件沒有符合的菜單；已選菜單仍會保留。</small>}{candidates.loading&&<small>菜單候選載入中…</small>}<PaginationControls page={candidates.page} pageSize={candidates.pageSize} total={candidates.total} onPage={candidates.setPage}/></fieldset>
    <fieldset className="workflow-step"><legend>② 調整日期範圍</legend>{selectedMenus.length>1&&!sameMenuDates&&<Feedback type="info">所選菜單日期不完全相同；建議範圍會涵蓋所有菜單，實際計算仍只採各菜單有效日期。</Feedback>}{selectedMenus.length>0&&<div className="ordering-date-suggestion"><span>建議：{suggestedStart}～{suggestedEnd}</span><button type="button" className="secondary" onClick={()=>{applySuggestedDates(selectedMenus);setDatesTouched(false)}}>套用建議範圍</button></div>}<div className="date-range-fields"><label>開始日期<input type="date" value={startDate} onChange={event=>{setStartDate(event.target.value);setDatesTouched(true);setExisting(null)}}/></label><label>結束日期<input type="date" value={endDate} onChange={event=>{setEndDate(event.target.value);setDatesTouched(true);setExisting(null)}}/></label></div><small>可依實際作業需要縮短為部分日期。</small><label>備註（選填）<textarea value={notes} maxLength={2000} onChange={event=>setNotes(event.target.value)}/></label></fieldset>
    {error&&<Feedback type="error">{error}{existing&&<button type="button" className="secondary ordering-existing-action" onClick={()=>onOpenExisting(existing.existing_sheet_id)}>{existing.code==='ADJUSTMENT_DRAFT_EXISTS'?'繼續編輯原草稿':'查看已確認調整單'}</button>}</Feedback>}
    <footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button disabled={busy||!selected.size||Boolean(rangeError)}>{busy?'建立中…':'建立叫貨調整單'}</button></footer>
  </form></section></div>
}

type AdjustmentConfirmation='back'|'reload'|null
type SaveBlock='conflict'|'stale'|null

const unitConversionLabels:Record<OrderingAdjustmentUnitConversion,string>={g_and_jin_to_kg:'g、斤 → kg',g_to_kg:'g → kg',jin_to_g:'斤 → g'}
const unitConversionSources:Record<OrderingAdjustmentUnitConversion,string[]>={g_and_jin_to_kg:['g','斤'],g_to_kg:['g'],jin_to_g:['斤']}

function AdjustmentConfirmDialog({kind,onCancel,onConfirm}:{kind:Exclude<AdjustmentConfirmation,null>;onCancel:()=>void;onConfirm:()=>void}){
  const reload=kind==='reload'
  return <div className="modal-backdrop"><section className="modal-panel danger-dialog" role="alertdialog" aria-modal="true"><header><div><h2>{reload?'重新載入最新資料？':'離開叫貨調整單？'}</h2><p>{reload?'重新載入會捨棄尚未儲存的修改，確定要繼續嗎？':'尚有未儲存的叫貨量修改，確定要離開嗎？'}</p></div></header><footer><button autoFocus className="secondary" onClick={onCancel}>留在此頁</button><button className="secondary-danger" onClick={onConfirm}>{reload?'捨棄修改並重新載入':'放棄修改並離開'}</button></footer></section></div>
}

function CompleteAdjustmentDialog({busy,onCancel,onConfirm}:{busy:boolean;onCancel:()=>void;onConfirm:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel" role="alertdialog" aria-modal="true"><header><div><h2>完成叫貨調整？</h2><p>確認後，這張叫貨調整單將標記為「已確認」，並鎖定目前的叫貨調整數量。</p><p>已確認的調整單可以作為之後沿用叫貨量的歷史來源。</p><p><strong>已確認不代表已建立正式採購單。</strong></p></div></header><footer><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button disabled={busy} onClick={onConfirm}>{busy?'確認中…':'確認完成'}</button></footer></section></div>
}

function ReopenAdjustmentDialog({busy,onCancel,onConfirm}:{busy:boolean;onCancel:()=>void;onConfirm:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel" role="alertdialog" aria-modal="true"><header><div><h2>解除叫貨調整鎖定？</h2><p>解除後可繼續編輯並再次完成確認。原有人工叫貨數量與單位會完整保留。</p></div></header><footer><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button disabled={busy} onClick={onConfirm}>{busy?'解除鎖定中…':'確認解除鎖定'}</button></footer></section></div>
}

function ReuseAgainDialog({onCancel,onConfirm}:{onCancel:()=>void;onConfirm:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel" role="alertdialog" aria-modal="true"><header><div><h2>重新比對上一張叫貨量？</h2><p>此叫貨調整單已沿用過上一張叫貨量。重新比對會依目前菜單重新分析可沿用項目，但不會覆蓋已人工調整或已確認的叫貨量。</p></div></header><footer><button autoFocus className="secondary" onClick={onCancel}>取消</button><button className="secondary" onClick={onConfirm}>繼續重新比對</button></footer></section></div>
}

function OrderingAdjustmentDetailView({detail,onDetailChange,onBack,onReview}:{detail:OrderingAdjustmentDetail;onDetailChange:(value:OrderingAdjustmentDetail)=>void;onBack:()=>void;onReview?:(detail:OrderingAdjustmentDetail)=>void}){
  const [values,setValues]=useState<Record<string,string>>(()=>initialAdjustmentValues(detail.lines))
  const [units,setUnits]=useState<Record<string,string>>(()=>initialAdjustmentUnits(detail.lines))
  const [saving,setSaving]=useState(false),[reloading,setReloading]=useState(false),[confirming,setConfirming]=useState(false),[reopening,setReopening]=useState(false),[converting,setConverting]=useState(false),[unitConversion,setUnitConversion]=useState<OrderingAdjustmentUnitConversion|null>(null),[completeOpen,setCompleteOpen]=useState(false),[reopenOpen,setReopenOpen]=useState(false),[message,setMessage]=useState(''),[saveError,setSaveError]=useState('')
  const [saveBlock,setSaveBlock]=useState<SaveBlock>(null),[confirmation,setConfirmation]=useState<AdjustmentConfirmation>(null),[reuseOpen,setReuseOpen]=useState(false),[reuseAgainOpen,setReuseAgainOpen]=useState(false)
  const [exportOpen,setExportOpen]=useState(false),[exportingMenuId,setExportingMenuId]=useState<string|null>(null)
  const [syncDirtyOpen,setSyncDirtyOpen]=useState(false),[syncPreviewing,setSyncPreviewing]=useState(false),[syncApplying,setSyncApplying]=useState(false),[syncPreview,setSyncPreview]=useState<OrderingAdjustmentSyncPreview|null>(null)
  const syncPreviewingRef=useRef(false),syncApplyingRef=useRef(false)
  const [mealTarget,setMealTarget]=useState<(AdjustmentMealTarget&{lockVersion:number;hadPendingSource:boolean})|null>(null),[openingMeal,setOpeningMeal]=useState(false),[sourcePendingSync,setSourcePendingSync]=useState(false),[refreshingSource,setRefreshingSource]=useState(false),[layoutRevision,setLayoutRevision]=useState(0)
  const [syncAfterMeal,setSyncAfterMeal]=useState(false)
  const automaticSyncRef=useRef(false),syncGeneration=useRef(0),currentDetailRef=useRef(detail)
  const detailRoot=useRef<HTMLElement>(null),scrollToRestore=useRef<AdjustmentScrollPosition|null>(null)
  currentDetailRef.current=detail
  const openingMealRef=useRef(false),savingRef=useRef(false)
  const [activeMenuId,setActiveMenuId]=useState(detail.source_menus[0]?.menu_id??''),[layouts,setLayouts]=useState<Record<string,MenuAggregate>>({}),[layoutLoading,setLayoutLoading]=useState(Boolean(detail.source_menus.length)),[layoutError,setLayoutError]=useState('')
  const readOnly=detail.status!=='draft'||detail.stale||sourcePendingSync||detail.purchase_locked,saveLocked=saveBlock!==null
  const sourceStale=detail.stale||sourcePendingSync
  const mealEntryBusy=openingMeal||refreshingSource||saving||reloading||confirming||reopening||converting||syncPreviewing||syncApplying||Boolean(exportingMenuId)||Boolean(mealTarget)||Boolean(syncPreview||syncDirtyOpen||completeOpen||reopenOpen||reuseOpen||reuseAgainOpen||unitConversion||exportOpen||confirmation)
  const reviewLineIds=new Set(detail.lines.filter(line=>line.review_required).map(line=>line.id))
  const dirtyIds=dirtyAdjustmentLineIds(detail.lines,values,units),dirtySet=new Set(dirtyIds)
  const menuDirtyCounts=Object.fromEntries(detail.source_menus.map(menu=>[menu.menu_id,detail.lines.filter(line=>line.source_menu_id===menu.menu_id&&dirtySet.has(line.id)).length]))
  const validationErrors=Object.fromEntries(detail.lines.map(line=>[line.id,validateAdjustmentQuantity(values[line.id]??'')]))
  const hasInvalid=dirtyIds.some(id=>Boolean(validationErrors[id]))
  const clearEditorDirty=useEditorDirty(dirtyIds.length>0)
  const staleReasons=[...new Set([...detail.warnings.map(warning=>warning.code),...detail.lines.flatMap(line=>line.stale_reasons)].map(staleReasonLabel))]
  const matrices=detail.source_menus.map(menu=>buildAdjustmentMenuMatrix(detail.lines,menu,layouts[menu.menu_id],detail.criteria)),activeMatrix=matrices.find(matrix=>matrix.menuId===activeMenuId)??matrices[0]
  function preserveScroll(){scrollToRestore.current=captureAdjustmentScroll(detailRoot.current)}
  useLayoutEffect(()=>{restoreAdjustmentScroll(detailRoot.current,scrollToRestore.current);scrollToRestore.current=null})
  useEffect(()=>()=>{syncGeneration.current++},[detail.id])
  useEffect(()=>{setValues(initialAdjustmentValues(detail.lines));setUnits(initialAdjustmentUnits(detail.lines));setSaveBlock(null)},[detail])
  useEffect(()=>{
    let current=true;setLayoutLoading(Boolean(detail.source_menus.length));setLayoutError('')
    void Promise.all(detail.source_menus.map(async menu=>[menu.menu_id,await getOrderingAdjustmentMenuLayout(menu.menu_id)] as const)).then(results=>{if(current){preserveScroll();setLayouts(Object.fromEntries(results))}}).catch(()=>{if(current)setLayoutError('部分菜單欄位名稱無法載入，已依調整單保存的原始順序顯示。')}).finally(()=>{if(current)setLayoutLoading(false)})
    return()=>{current=false}
  },[detail.id,detail.lock_version,detail.source_fingerprint,layoutRevision])
  function change(lineId:string,value:string){if(automaticSyncRef.current)return;setValues(current=>({...current,[lineId]:value}));setMessage('');setSaveError('')}
  function restore(line:OrderingAdjustmentDetail['lines'][number]){if(automaticSyncRef.current)return;setValues(current=>({...current,[line.id]:editableDecimalString(line.system_quantity)}));setUnits(current=>({...current,[line.id]:line.system_unit}));setMessage('');setSaveError('')}
  async function save():Promise<OrderingAdjustmentDetail|null>{
    if(automaticSyncRef.current||readOnly||saveLocked||savingRef.current||!dirtyIds.length||hasInvalid)return null
    savingRef.current=true
    setSaving(true);setMessage('');setSaveError('')
    try{const updated=await updateOrderingAdjustmentLines(detail.id,{lock_version:detail.lock_version,lines:buildAdjustmentUpdates(detail.lines,values,units)});clearEditorDirty();onDetailChange(updated);setMessage('草稿已儲存');return updated}
    catch(cause){
      const code=apiErrorCode(cause)
      if(code==='LOCK_VERSION_CONFLICT'){setSaveBlock('conflict');setSaveError('這張叫貨調整單已在其他地方被修改，請重新載入最新資料。')}
      else if(code==='ADJUSTMENT_STALE'){setSaveBlock('stale');setSaveError('來源資料已變更，無法繼續儲存。請重新載入最新資料。')}
      else setSaveError('儲存失敗，修改尚未遺失，請稍後再試。')
      return null
    }finally{savingRef.current=false;setSaving(false)}
  }
  async function reload(){setReloading(true);setMessage('');setSaveError('');try{const updated=await getOrderingAdjustment(detail.id);clearEditorDirty();onDetailChange(updated);setSourcePendingSync(false);setLayoutRevision(value=>value+1)}catch{setSaveError('重新載入失敗，尚未儲存的修改仍保留在畫面上。')}finally{setReloading(false)}}
  function requestReload(){if(automaticSyncRef.current||syncApplyingRef.current)return;if(dirtyIds.length)setConfirmation('reload');else void reload()}
  function requestBack(){if(automaticSyncRef.current||syncApplyingRef.current||openingMealRef.current||refreshingSource||savingRef.current)return;if(dirtyIds.length)setConfirmation('back');else onBack()}
  async function editMeal(target:AdjustmentMealTarget){
    if(automaticSyncRef.current||openingMealRef.current||mealEntryBusy||layoutLoading||layoutError)return
    openingMealRef.current=true;setOpeningMeal(true);setSaveError('');setMessage(dirtyIds.length?'正在儲存叫貨草稿，成功後開啟餐次編輯…':'正在檢查工作表狀態…')
    try{
      const current=await prepareAdjustmentMealEdit({detail,target,layout:layouts[target.menuId],dirty:dirtyIds.length>0,invalid:hasInvalid,saveBlocked:saveLocked,sourceUnverified:sourcePendingSync,save,refresh:()=>getOrderingAdjustment(detail.id)})
      if(!current)return
      onDetailChange(current);setSourcePendingSync(false);setSyncPreview(null)
      setMealTarget({...target,lockVersion:current.lock_version,hadPendingSource:current.stale||sourcePendingSync});setMessage(dirtyIds.length?'叫貨草稿已儲存，可編輯原始菜單餐次。':'')
    }catch(cause){setMessage('');setSaveError(cause instanceof ApiError?orderingActionError(cause,'檢查工作表失敗，未開啟餐次編輯；目前輸入仍保留。'):cause instanceof Error?cause.message:'無法開啟餐次編輯。')}
    finally{openingMealRef.current=false;setOpeningMeal(false)}
  }
  async function mealSaved(aggregate:MenuAggregate,changed:boolean){
    if(automaticSyncRef.current||!mealTarget)return
    const target=mealTarget,generation=syncGeneration.current,sheetId=detail.id
    const current=()=>generation===syncGeneration.current&&currentDetailRef.current.id===sheetId
    preserveScroll();setMealTarget(null);setLayouts(value=>({...value,[aggregate.menu.id]:aggregate}))
    if(!changed)return
    automaticSyncRef.current=true
    setSyncPreview(null);setSyncAfterMeal(true);setSourcePendingSync(true);setRefreshingSource(true);setSaveError('')
    setMessage('菜單已儲存，正在同步叫貨資料……')
    try{
      const updated=await getOrderingAdjustment(sheetId)
      if(!current())return
      if(updated.status!=='draft'||updated.purchase_locked!==false)throw new Error('工作表狀態已改變或已被採購鎖定，請重新載入。')
      preserveScroll();onDetailChange(updated)
      const preview=await previewOrderingAdjustmentSync(sheetId,updated.lock_version)
      if(!current())return
      if(preview.sheet_id!==sheetId||preview.status!=='draft'||preview.lock_version!==updated.lock_version||preview.saved_source_fingerprint!==updated.source_fingerprint)throw new Error('預覽版本不一致，請重新預覽。')
      preserveScroll()
      if(!preview.changed&&!updated.stale){setSourcePendingSync(false);setSyncAfterMeal(false);setMessage('菜單已儲存；來源檢查未發現需要同步的食材變更。');return}
      if(canAutoApplyMealSync(preview,updated,target,aggregate,target.hadPendingSource)){
        await applySync([],[],preview,true)
      }else{
        setSyncPreview(preview);setMessage('菜單已儲存，叫貨資料尚未同步。請確認整張工作表的差異後再套用。')
      }
    }catch(cause){
      if(current()){preserveScroll();setMessage('菜單已儲存，但叫貨資料尚未同步。');setSaveError(orderingActionError(cause,cause instanceof Error?`${cause.message} 請重新執行同步。`:'同步檢查失敗，請重新執行同步。'))}
    }finally{if(current()){automaticSyncRef.current=false;setRefreshingSource(false)}}
  }
  function requestComplete(){if(automaticSyncRef.current)return;if(dirtyIds.length){setSaveError('目前有尚未儲存的修改，請先儲存後再完成叫貨調整。');return}setCompleteOpen(true)}
  function requestReuse(){if(automaticSyncRef.current)return;if(dirtyIds.length){setSaveError('請先儲存或還原目前修改，再沿用上一張叫貨量。');return}if(detail.reuse_applied_at)setReuseAgainOpen(true);else setReuseOpen(true)}
  function requestUnitConversion(conversion:OrderingAdjustmentUnitConversion){if(automaticSyncRef.current)return;if(dirtyIds.length){setSaveError('請先儲存或還原目前修改，再進行批次單位換算。');return}setUnitConversion(conversion)}
  async function applyUnitConversion(){if(!unitConversion||converting)return;setConverting(true);setSaveError('');try{const updated=await convertOrderingAdjustmentUnits(detail.id,detail.lock_version,unitConversion);clearEditorDirty();setUnitConversion(null);onDetailChange(updated);setMessage('批次單位換算已完成')}catch(cause){setUnitConversion(null);setSaveError(orderingActionError(cause,'批次單位換算失敗，資料未變更。'))}finally{setConverting(false)}}
  async function complete(){if(confirming||dirtyIds.length)return;setConfirming(true);setSaveError('');try{const updated=await confirmOrderingAdjustment(detail.id,detail.lock_version);clearEditorDirty();setCompleteOpen(false);onDetailChange(updated);setMessage('叫貨調整已完成確認')}catch(cause){setSaveError(orderingActionError(cause,'完成叫貨調整失敗，請稍後再試。'));setCompleteOpen(false)}finally{setConfirming(false)}}
  async function reopen(){if(reopening||detail.status!=='confirmed')return;setReopening(true);setSaveError('');setMessage('');try{const updated=await reopenOrderingAdjustment(detail.id,detail.lock_version);clearEditorDirty();setReopenOpen(false);onDetailChange(updated);setMessage('已解除鎖定，可繼續修改叫貨量')}catch(cause){setSaveError(orderingActionError(cause,'解除鎖定失敗，資料未變更。'));setReopenOpen(false)}finally{setReopening(false)}}
  async function loadSyncPreview(current:OrderingAdjustmentDetail){
    if(automaticSyncRef.current||syncPreviewingRef.current||current.status!=='draft')return
    setSyncAfterMeal(false)
    syncPreviewingRef.current=true
    setSyncPreviewing(true);setSaveError('');setMessage('')
    try{setSyncPreview(await previewOrderingAdjustmentSync(current.id,current.lock_version))}
    catch(cause){setSaveError(orderingActionError(cause,'同步差異載入失敗，工作表資料未變更。'))}
    finally{syncPreviewingRef.current=false;setSyncPreviewing(false)}
  }
  function requestSync(){
    if(automaticSyncRef.current||syncApplyingRef.current||detail.status!=='draft'||syncPreviewingRef.current)return
    if(dirtyIds.length){setSyncDirtyOpen(true);return}
    void loadSyncPreview(detail)
  }
  async function discardAndPreviewSync(){
    if(reloading||syncPreviewing)return
    setReloading(true);setSaveError('')
    try{const updated=await getOrderingAdjustment(detail.id);clearEditorDirty();onDetailChange(updated);setSyncDirtyOpen(false);await loadSyncPreview(updated)}
    catch{setSaveError('重新載入失敗，尚未儲存的修改仍保留在畫面上。')}
    finally{setReloading(false)}
  }
  async function saveAndPreviewSync(){
    if(sourceStale||saving||syncPreviewing||hasInvalid||!dirtyIds.length)return
    setSaving(true);setSaveError('')
    try{const updated=await updateOrderingAdjustmentLines(detail.id,{lock_version:detail.lock_version,lines:buildAdjustmentUpdates(detail.lines,values,units)});clearEditorDirty();onDetailChange(updated);setSyncDirtyOpen(false);await loadSyncPreview(updated)}
    catch(cause){setSaveError(orderingActionError(cause,'儲存失敗，修改仍保留在畫面上。'))}
    finally{setSaving(false)}
  }
  async function applySync(acceptedRemoved:string[],resetLineIds:string[],preview=syncPreview,automatic=false){
    if(!preview||syncApplyingRef.current||(!automatic&&automaticSyncRef.current))return
    const generation=syncGeneration.current,sheetId=detail.id
    const current=()=>generation===syncGeneration.current&&currentDetailRef.current.id===sheetId
    if(currentDetailRef.current.status!=='draft'||currentDetailRef.current.purchase_locked||currentDetailRef.current.lock_version!==preview.lock_version){
      setSyncPreview(null);setMessage('叫貨資料尚未同步。');setSaveError('工作表版本或狀態已變更，請重新載入並預覽。');return
    }
    syncApplyingRef.current=true
    preserveScroll();setSyncApplying(true);setSaveError('');if(!automatic)setMessage('')
    try{
      const updated=await applyOrderingAdjustmentSync(sheetId,{lock_version:preview.lock_version,expected_source_fingerprint:preview.preview_source_fingerprint,accepted_removed_source_line_keys:acceptedRemoved,reset_adjustment_line_ids:resetLineIds})
      if(!current())return
      const added=preview.summary.added_ingredients??0,removed=preview.summary.removed_ingredients??0
      preserveScroll();clearEditorDirty();setSyncPreview(null);onDetailChange(updated);setSourcePendingSync(updated.stale);setSyncAfterMeal(updated.stale);setLayoutRevision(value=>value+1);setMessage(updated.stale?'同步已套用，但來源隨後又有變更，請重新檢查同步。':automatic?'菜單與叫貨資料已更新':`同步完成：新增 ${added} 項、移除 ${removed} 項食材明細`)
    }catch(cause){
      if(!current())return
      const code=apiErrorCode(cause)
      preserveScroll();setSyncAfterMeal(true);setMessage(automatic||syncAfterMeal?'菜單已儲存，但叫貨資料尚未同步。請重新執行同步。':'叫貨資料尚未同步。請重新執行同步。')
      setSaveError(orderingActionError(cause,'同步套用失敗，原有人工叫貨量仍完整保留。'))
      if(code==='SYNC_SOURCE_CHANGED'||code==='LOCK_VERSION_CONFLICT')setSyncPreview(null)
    }finally{if(current()){syncApplyingRef.current=false;setSyncApplying(false)}}
  }
  function requestExport(){
    if(automaticSyncRef.current)return
    if(dirtyIds.length){setSaveError('目前有尚未儲存的修改，請先儲存後再下載 Excel。');return}
    if(detail.source_menus.length===1)void downloadExport(detail.source_menus[0].menu_id)
    else setExportOpen(true)
  }
  async function downloadExport(menuId:string){
    if(exportingMenuId)return
    setExportingMenuId(menuId);setSaveError('');setMessage('')
    try{await downloadOrderingAdjustmentWeekly(detail.id,menuId);setExportOpen(false);setMessage('調整後廚房配料表已下載')}
    catch(cause){setSaveError(orderingActionError(cause,'Excel 下載失敗，請確認調整單來源資料後再試。'))}
    finally{setExportingMenuId(null)}
  }
  const conversionCount=(conversion:OrderingAdjustmentUnitConversion)=>detail.lines.filter(line=>unitConversionSources[conversion].includes(line.effective_unit)).length
  return <section ref={detailRoot} className={`ordering-adjustment-detail is-${detail.status}${detail.stale?' is-stale':''}`}>
    <PageHeader title="叫貨調整單" description="依工作順序完成調整、確認，再帶入食材需求。" actions={<button className="secondary" onClick={requestBack}>← 返回列表</button>}/>
    <WorkflowGuide active="adjustment"/>
    <div className="ordering-adjustment-summary"><div><strong>{activeMatrix?.menuName??detail.source_menus.map(menu=>menu.menu_name).join('、')}</strong><span>{activeMatrix?.dates.length?`${formatShortDate(activeMatrix.dates[0])} ～ ${formatShortDate(activeMatrix.dates.at(-1)!)}`:adjustmentDateRange(detail.criteria,detail)}</span><span><AdjustmentStatus status={detail.status}/> · Rev.{detail.revision}</span></div><small>建立：{new Date(detail.created_at).toLocaleString('zh-TW')}　最後更新：{new Date(detail.updated_at).toLocaleString('zh-TW')}</small></div>
    <fieldset className="ordering-adjustment-actionbar ordering-meal-operation-guard" disabled={openingMeal||refreshingSource||Boolean(mealTarget)} aria-label="叫貨調整操作">
      {detail.status==='draft'&&<div className={`ordering-action-group ordering-sync-action${sourceStale?' is-required':''}`}><small>{sourceStale?'來源已變更':'菜單與食譜'}</small><div><button className={sourceStale?'':'secondary'} disabled={syncPreviewing||syncApplying||detail.purchase_locked} onClick={requestSync}>{syncPreviewing?'檢查差異中…':'同步最新菜單與食譜'}</button></div></div>}
      {detail.status==='draft'&&!sourceStale&&<div className="ordering-action-group"><small>歷史叫貨量</small><div>{detail.reuse_applied_at&&<span className="ordering-reuse-status">✓ 已沿用上一張叫貨量</span>}<button className="secondary" onClick={requestReuse}>{detail.reuse_applied_at?'重新比對':'沿用上一張叫貨量'}</button></div></div>}
      {detail.status==='draft'&&!sourceStale&&<div className="ordering-action-group"><small>批次單位換算</small><div>{(Object.keys(unitConversionLabels) as OrderingAdjustmentUnitConversion[]).map(conversion=><button className="secondary" disabled={converting||conversionCount(conversion)===0} key={conversion} onClick={()=>requestUnitConversion(conversion)}>{unitConversionLabels[conversion]}</button>)}</div></div>}
      <div className="ordering-action-group"><small>匯出與下一步</small><div><button className="secondary" disabled={detail.status==='cancelled'||sourceStale||Boolean(exportingMenuId)} onClick={requestExport}>{exportingMenuId?'下載中…':'下載 Excel'}</button>{detail.status==='draft'&&!sourceStale&&<button onClick={requestComplete}>完成叫貨調整</button>}{detail.status==='confirmed'&&<button className="secondary" disabled={reopening} onClick={()=>setReopenOpen(true)}>{reopening?'解除鎖定中…':'解除鎖定'}</button>}<button className={detail.status==='confirmed'?'':'secondary'} disabled={detail.status==='cancelled'||sourceStale} onClick={()=>onReview?.(detail)}>前往食材需求</button></div></div>
    </fieldset>
    {sourceStale&&<Feedback type="info"><strong>原始菜單已變更，食材尚未同步。</strong><p>下方保留同步前的食材資料，數量暫停編輯。儲存本餐後會檢查同步；需要確認或尚未完成時，可使用「同步最新菜單與食譜」。</p>{staleReasons.length>0&&<ul>{staleReasons.map(reason=><li key={reason}>{reason}</li>)}</ul>}{sourcePendingSync&&!refreshingSource&&<button className="secondary" onClick={requestReload}>重新載入來源狀態</button>}</Feedback>}
    {saveError&&<Feedback type="error">{saveError}{saveBlock&&<button type="button" className="secondary ordering-reload-action" disabled={reloading} onClick={requestReload}>{reloading?'重新載入中…':'重新載入'}</button>}</Feedback>}
    {message&&<Feedback type={refreshingSource||syncAfterMeal?'info':'success'}>{message}</Feedback>}
    {reviewLineIds.size>0&&<div className="ordering-review-banner" role="status"><strong>{reviewLineIds.size} 項叫貨量需要確認</strong><span>請檢查紅色標示的菜色與食材，完成調整並儲存。</span></div>}
    {!sourceStale&&detail.status==='confirmed'&&<Feedback type="info">此叫貨調整已完成確認，數量已鎖定。如需同步最新菜單與食譜，請先解除鎖定。</Feedback>}
    {!sourceStale&&detail.status==='cancelled'&&<Feedback type="info">此調整單已取消，目前僅供查看。</Feedback>}
    {detail.source_menus.length>1&&<div className="ordering-adjustment-tabs" role="tablist" aria-label="菜單"><>{matrices.map(matrix=><button role="tab" aria-selected={matrix.menuId===activeMenuId} className={matrix.menuId===activeMenuId?'active':''} key={matrix.menuId} onClick={()=>setActiveMenuId(matrix.menuId)}>{matrix.menuName}{menuDirtyCounts[matrix.menuId]?` · ${menuDirtyCounts[matrix.menuId]}`:''}</button>)}</></div>}
    {layoutError&&<Feedback type="info">{layoutError}</Feedback>}
    {layoutLoading&&Object.keys(layouts).length===0?<LoadingState label="菜單欄位載入中…"/>:!activeMatrix||!activeMatrix.meals.length?<EmptyState title="這張調整單沒有食材明細"/>:<AdjustmentWeeklyMatrix matrix={activeMatrix} values={values} units={units} dirtySet={dirtySet} reviewLineIds={reviewLineIds} validationErrors={validationErrors} readOnly={readOnly} saving={saving||openingMeal||refreshingSource} saveLocked={saveLocked} onChange={change} onRestore={restore} onEditMeal={detail.status==='draft'&&!detail.purchase_locked?target=>void editMeal(target):undefined} canEditMeal={target=>!mealEntryBusy&&!layoutLoading&&!layoutError&&validAdjustmentMealTarget(detail,target,layouts[target.menuId])}/>}
    {!readOnly&&<div className="ordering-adjustment-savebar"><strong>{dirtyIds.length?`尚有 ${dirtyIds.length} 筆修改未儲存`:'目前沒有未儲存的修改'}</strong><button disabled={saving||openingMeal||refreshingSource||saveLocked||!dirtyIds.length||hasInvalid} onClick={()=>void save()}>{saving?'儲存中…':'儲存草稿'}</button></div>}
    {mealTarget&&<MenuMealEditorDialog menuId={mealTarget.menuId} date={mealTarget.date} mealTypeId={mealTarget.mealTypeId} orderingAdjustmentContext={{sheet_id:detail.id,lock_version:mealTarget.lockVersion}} onSaved={(aggregate,result)=>void mealSaved(aggregate,result.changed)} onClose={()=>setMealTarget(null)}/>}
    {confirmation&&<AdjustmentConfirmDialog kind={confirmation} onCancel={()=>setConfirmation(null)} onConfirm={()=>{const action=confirmation;setConfirmation(null);if(action==='back'){clearEditorDirty();onBack()}else void reload()}}/>}
    {completeOpen&&<CompleteAdjustmentDialog busy={confirming} onCancel={()=>setCompleteOpen(false)} onConfirm={()=>void complete()}/>}
    {reopenOpen&&<ReopenAdjustmentDialog busy={reopening} onCancel={()=>setReopenOpen(false)} onConfirm={()=>void reopen()}/>}
    {syncDirtyOpen&&<SyncDirtyDialog stale={sourceStale} invalid={hasInvalid} busy={saving||reloading||syncPreviewing} onCancel={()=>setSyncDirtyOpen(false)} onDiscard={()=>void discardAndPreviewSync()} onSave={()=>void saveAndPreviewSync()}/>}
    {syncPreview&&<SyncAdjustmentDialog preview={syncPreview} busy={syncApplying} onCancel={()=>{preserveScroll();setSyncPreview(null)}} onApply={(removed,resets)=>void applySync(removed,resets)}/>}
    {reuseAgainOpen&&<ReuseAgainDialog onCancel={()=>setReuseAgainOpen(false)} onConfirm={()=>{setReuseAgainOpen(false);setReuseOpen(true)}}/>}
    {reuseOpen&&<ReuseAdjustmentDialog current={detail} onClose={()=>setReuseOpen(false)} onApplied={updated=>{clearEditorDirty();setReuseOpen(false);onDetailChange(updated);setMessage('已沿用上一張叫貨量')}}/>}
    {unitConversion&&<UnitConversionDialog conversion={unitConversion} gCount={detail.lines.filter(line=>line.effective_unit==='g').length} jinCount={detail.lines.filter(line=>line.effective_unit==='斤').length} busy={converting} onCancel={()=>setUnitConversion(null)} onConfirm={()=>void applyUnitConversion()}/>}
    {exportOpen&&<AdjustmentExportDialog menus={detail.source_menus} busy={Boolean(exportingMenuId)} onCancel={()=>setExportOpen(false)} onDownload={menuId=>void downloadExport(menuId)}/>}
  </section>
}

function SyncDirtyDialog({stale,invalid,busy,onCancel,onDiscard,onSave}:{stale:boolean;invalid:boolean;busy:boolean;onCancel:()=>void;onDiscard:()=>void;onSave:()=>void}){
  return <div className="modal-backdrop"><section className="modal-panel" role="alertdialog" aria-modal="true" aria-labelledby="sync-dirty-title"><header><div><h2 id="sync-dirty-title">先處理尚未儲存的修改</h2><p>{stale?'來源已變更，舊來源上的未儲存輸入不能安全儲存。請捨棄畫面修改並重新載入，再檢查同步差異。':'可先儲存目前修改再檢查同步差異，或捨棄尚未儲存的輸入並重新載入。'}</p></div></header>{invalid&&!stale&&<Feedback type="error">目前有格式不正確的數量，請返回修正，或捨棄修改後繼續。</Feedback>}<footer><button className="secondary" disabled={busy} onClick={onCancel}>返回工作表</button><button className="secondary-danger" disabled={busy} onClick={onDiscard}>{busy?'處理中…':'捨棄修改並預覽'}</button>{!stale&&<button disabled={busy||invalid} onClick={onSave}>{busy?'處理中…':'儲存後預覽'}</button>}</footer></section></div>
}

function SyncAdjustmentDialog({preview,busy,onCancel,onApply}:{preview:OrderingAdjustmentSyncPreview;busy:boolean;onCancel:()=>void;onApply:(removed:string[],resets:string[])=>void}){
  const requiredRemoved=preview.removed_ingredients.map(change=>change.source_line_key??change.previous?.source_line_key).filter((value):value is string=>Boolean(value))
  const requiredResets=preview.unit_conflicts.map(change=>change.previous?.line_id).filter((value):value is string=>Boolean(value))
  const [acceptedRemoved,setAcceptedRemoved]=useState<Set<string>>(new Set())
  const [resetLines,setResetLines]=useState<Set<string>>(new Set())
  const removalsReady=requiredRemoved.every(key=>acceptedRemoved.has(key)),unitsReady=requiredResets.every(id=>resetLines.has(id))
  const applyReady=preview.changed&&removalsReady&&unitsReady&&!busy
  return <div className="modal-backdrop"><section className="modal-panel wide ordering-sync-dialog" role="dialog" aria-modal="true" aria-labelledby="sync-preview-title"><header><div><h2 id="sync-preview-title">同步最新菜單與食譜</h2><p>這是整張叫貨調整單的完整差異，可能包含其他餐別尚未同步的變更。未變動明細的人工叫貨量會保留；舊菜的人工量不會轉移到新菜。</p></div></header>
    <div className="ordering-sync-summary" aria-label="同步差異摘要"><span><b>{preview.summary.added_dishes??0}</b> 新增菜色</span><span><b>{preview.summary.removed_dishes??0}</b> 移除菜色</span><span><b>{preview.summary.added_ingredients??0}</b> 新增食材</span><span><b>{preview.summary.removed_ingredients??0}</b> 移除食材</span><span><b>{preview.summary.changed_lines??0}</b> 來源內容變更</span><span><b>{preview.summary.unit_conflicts??0}</b> 單位需處理</span></div>
    {!preview.changed&&<Feedback type="success">目前工作表已與最新菜單及食譜一致，沒有需要套用的變更。</Feedback>}
    <div className="ordering-sync-sections">
      {preview.possible_dish_replacements.length>0&&<SyncSection title="可能的菜色替換" tone="notice"><p>這是來源配置變更提示，不代表舊菜色的人工數量會轉移至新菜色。</p>{preview.possible_dish_replacements.map((change,index)=><div className="ordering-sync-change" key={`replacement-${index}`}><strong>{syncDishName(change.previous)} → {syncDishName(change.current)}</strong><small>{syncPosition(change.previous)} → {syncPosition(change.current)}</small></div>)}</SyncSection>}
      {preview.added_dishes.length>0&&<SyncSection title="新增菜色"><div className="ordering-sync-grid">{preview.added_dishes.map(dish=><div className="ordering-sync-change" key={`added-dish-${String(dish.source_menu_dish_id)}-${String(dish.source_dish_id)}`}><strong>{syncDishName(dish)}</strong><small>{syncPosition(dish)} · {dish.diner_count??0} 人</small></div>)}</div></SyncSection>}
      {preview.removed_dishes.length>0&&<SyncSection title="移除菜色" tone="warning"><div className="ordering-sync-grid">{preview.removed_dishes.map(dish=><div className="ordering-sync-change" key={`removed-dish-${String(dish.source_menu_dish_id)}-${String(dish.source_dish_id)}`}><strong>{syncDishName(dish)}</strong><small>{syncPosition(dish)}</small></div>)}</div></SyncSection>}
      {preview.added_ingredients.length>0&&<SyncSection title="新增食材"><div className="ordering-sync-grid">{preview.added_ingredients.map((change,index)=><div className="ordering-sync-change" key={change.source_line_key??`added-${index}`}><strong>{syncLineTitle(change.current)}</strong><small>最新參考量：{syncQuantity(change.current,'system')}；人工量尚未設定</small></div>)}</div></SyncSection>}
      {preview.removed_ingredients.length>0&&<SyncSection title="移除食材（逐筆確認）" tone="warning"><p>確認後，這些來源明細不再進入食材需求；原人工量不會轉移至其他菜色。</p>{preview.removed_ingredients.map((change,index)=>{const key=change.source_line_key??change.previous?.source_line_key??'';return <label className="ordering-sync-confirm" key={key||`removed-${index}`}><input type="checkbox" checked={Boolean(key)&&acceptedRemoved.has(key)} disabled={busy||!key} onChange={()=>toggleSet(setAcceptedRemoved,key)}/><span><strong>{syncLineTitle(change.previous)}</strong><small>原人工叫貨：{syncQuantity(change.previous,'effective')}。同步後該來源明細將移除。</small></span></label>})}</SyncSection>}
      {preview.line_changes.length>0&&<SyncSection title="保留明細的來源變更"><div className="ordering-sync-grid">{preview.line_changes.map((change,index)=><div className="ordering-sync-change" key={change.source_line_key??`changed-${index}`}><strong>{syncLineTitle(change.current??change.previous)}</strong><small>{change.change_types.map(syncChangeLabel).join('、')}；{change.preserves_adjustment?'原人工叫貨量會保留':'需重新確認人工叫貨量'}</small></div>)}</div></SyncSection>}
      {preview.unit_conflicts.length>0&&<SyncSection title="單位衝突（逐筆處理）" tone="warning"><p>以下人工單位無法安全換算成新來源單位。勾選後會重設該筆人工量，改用新的系統參考量。</p>{preview.unit_conflicts.map((change,index)=>{const id=change.previous?.line_id??'';return <label className="ordering-sync-confirm" key={id||`unit-${index}`}><input type="checkbox" checked={Boolean(id)&&resetLines.has(id)} disabled={busy||!id} onChange={()=>toggleSet(setResetLines,id)}/><span><strong>{syncLineTitle(change.current??change.previous)}</strong><small>原人工叫貨：{syncQuantity(change.previous,'effective')}；新來源單位：{change.current?.system_unit??'—'}</small><b>重設此筆人工數量</b></span></label>})}</SyncSection>}
    </div>
    <footer><span className="ordering-sync-readiness" role="status">{!removalsReady?`尚有 ${requiredRemoved.filter(key=>!acceptedRemoved.has(key)).length} 筆移除未確認`:!unitsReady?`尚有 ${requiredResets.filter(id=>!resetLines.has(id)).length} 筆單位衝突未處理`:preview.changed?'已完成必要確認':'沒有需要套用的變更'}</span><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button disabled={!applyReady} onClick={()=>onApply([...acceptedRemoved],[...resetLines])}>{busy?'同步中…':'確認套用同步'}</button></footer>
  </section></div>
}

function SyncSection({title,tone='',children}:{title:string;tone?:'notice'|'warning'|'';children:ReactNode}){return <section className={`ordering-sync-section${tone?` is-${tone}`:''}`}><h3>{title}</h3>{children}</section>}
function toggleSet(setter:Dispatch<SetStateAction<Set<string>>>,value:string){if(!value)return;setter(current=>{const next=new Set(current);if(next.has(value))next.delete(value);else next.add(value);return next})}
function syncDishName(snapshot:OrderingAdjustmentSyncSnapshot|null){return snapshot?.dish_name?.trim()||'未命名菜色'}
function syncPosition(snapshot:OrderingAdjustmentSyncSnapshot|null){return [snapshot?.requirement_date,snapshot?.meal_name].filter(Boolean).join(' ')||'位置未提供'}
function syncLineTitle(snapshot:OrderingAdjustmentSyncSnapshot|null){return `${syncDishName(snapshot)}／${snapshot?.ingredient_name?.trim()||'未命名食材'}`}
function syncQuantity(snapshot:OrderingAdjustmentSyncSnapshot|null,kind:'system'|'effective'){const quantity=kind==='effective'?(snapshot?.effective_quantity??snapshot?.adjusted_quantity??snapshot?.system_quantity):snapshot?.system_quantity;const unit=kind==='effective'?(snapshot?.effective_unit??snapshot?.adjusted_unit??snapshot?.system_unit):snapshot?.system_unit;return quantity&&unit?`${formatAdjustmentQuantity(String(quantity))} ${unit}`:'—'}
function syncChangeLabel(value:string){return ({dish_name_changed:'菜名更新',ingredient_name_changed:'食材名稱更新',menu_position_changed:'日期／餐別／位置更新',diner_count_changed:'用餐人數更新',reference_quantity_changed:'食譜參考量更新',unit_changed:'參考單位更新',source_metadata_changed:'供應商或來源資料更新',unit_conflict:'人工單位無法安全換算'} as Record<string,string>)[value]??value}

function AdjustmentExportDialog({menus,busy,onCancel,onDownload}:{menus:OrderingAdjustmentDetail['source_menus'];busy:boolean;onCancel:()=>void;onDownload:(menuId:string)=>void}){
  const [menuId,setMenuId]=useState(menus[0]?.menu_id??'')
  return <div className="modal-backdrop"><section className="modal-panel" role="dialog" aria-modal="true"><header><div><h2>下載調整後廚房配料表</h2><p>這張調整單包含多份菜單，請選擇要匯出的菜單。</p></div></header><label>菜單<select value={menuId} onChange={event=>setMenuId(event.target.value)}>{menus.map(menu=><option value={menu.menu_id} key={menu.menu_id}>{menu.menu_name}（{menu.start_date}～{menu.end_date}）</option>)}</select></label><footer><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button disabled={busy||!menuId} onClick={()=>onDownload(menuId)}>{busy?'下載中…':'下載 Excel'}</button></footer></section></div>
}

function UnitConversionDialog({conversion,gCount,jinCount,busy,onCancel,onConfirm}:{conversion:OrderingAdjustmentUnitConversion;gCount:number;jinCount:number;busy:boolean;onCancel:()=>void;onConfirm:()=>void}){
  const parts=conversion==='g_and_jin_to_kg'?[`${gCount} 筆 g`,`${jinCount} 筆斤`]:conversion==='g_to_kg'?[`${gCount} 筆 g`]:[`${jinCount} 筆斤`]
  return <div className="modal-backdrop"><section className="modal-panel" role="alertdialog" aria-modal="true"><header><div><h2>批次換算叫貨單位？</h2><p>將目前這張叫貨調整單中的 {parts.join(' 與 ')} 換算為 {conversion==='jin_to_g'?'g':'kg'}。數量會同步精確換算，其他單位不受影響。</p></div></header><footer><button className="secondary" disabled={busy} onClick={onCancel}>取消</button><button disabled={busy} onClick={onConfirm}>{busy?'換算中…':'確認換算'}</button></footer></section></div>
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
  if(line.status==='safe_to_reuse')return `上次 ${formatAdjustmentQuantity(line.previous_system_quantity!)} ${line.previous_system_unit} → ${formatAdjustmentQuantity(line.previous_adjusted_quantity!)} ${line.previous_adjusted_unit??line.previous_system_unit}；本次理論量相同`
  if(line.reason_codes.includes('SYSTEM_QUANTITY_CHANGED'))return `上次 ${formatAdjustmentQuantity(line.previous_system_quantity!)} ${line.previous_system_unit} → ${formatAdjustmentQuantity(line.previous_adjusted_quantity!)} ${line.previous_adjusted_unit??line.previous_system_unit}；本次 ${formatAdjustmentQuantity(line.current_system_quantity)} ${line.current_system_unit}，請人工確認`
  if(line.reason_codes.includes('CURRENT_ALREADY_ADJUSTED'))return '本次已有人工調整，不會覆蓋'
  if(line.status==='ambiguous')return '找到多筆可能來源，無法自動沿用'
  return '新菜、已更換菜色或配方食材已改變，需本次重新處理'
}

function AdjustmentWeeklyMatrix({matrix,values,units,dirtySet,reviewLineIds,validationErrors,readOnly,saving,saveLocked,onChange,onRestore,onEditMeal,canEditMeal}:{matrix:AdjustmentMenuMatrix;values:Record<string,string>;units:Record<string,string>;dirtySet:Set<string>;reviewLineIds:Set<string>;validationErrors:Record<string,string|null>;readOnly:boolean;saving:boolean;saveLocked:boolean;onChange:(lineId:string,value:string)=>void;onRestore:(line:OrderingAdjustmentDetail['lines'][number])=>void;onEditMeal?:(target:AdjustmentMealTarget)=>void;canEditMeal:(target:AdjustmentMealTarget)=>boolean}){
  return <div className="ordering-adjustment-matrix"><table><thead><tr><th className="matrix-meal-heading">餐別</th><th className="matrix-column-heading">菜單欄位</th>{matrix.dates.map(date=><th key={date}>{formatDate(date)}</th>)}</tr></thead><tbody>{matrix.meals.flatMap((meal,mealIndex)=>meal.rows.map((row,rowIndex)=><tr className={`ordering-meal-row ${mealSectionTone(mealIndex)}${rowIndex===0?' ordering-meal-row-start':''}${rowIndex===meal.rows.length-1?' ordering-meal-row-end':''}`} data-meal-id={meal.id} data-meal-index={mealIndex} key={`${meal.id}:${rowIndex}`}>{rowIndex===0&&<th className="matrix-meal-cell" rowSpan={meal.rows.length}>{meal.name}</th>}<th className="matrix-column-cell">{row.label}</th>{matrix.dates.map(date=><td key={date}>{rowIndex===0&&onEditMeal&&<div className="ordering-meal-edit-entry"><button type="button" className="secondary compact" disabled={!canEditMeal({menuId:matrix.menuId,date,mealTypeId:meal.id})} title="編輯本餐" aria-label={`編輯本餐：${matrix.menuName} ${date} ${meal.name}`} onClick={()=>onEditMeal({menuId:matrix.menuId,date,mealTypeId:meal.id})}><span aria-hidden="true">✎</span><span className="sr-only">編輯本餐</span></button></div>}<div className="ordering-adjustment-cell">{(row.cells[date]??[]).map(dish=>{const dishNeedsReview=dish.lines.some(line=>reviewLineIds.has(line.id));return <article className={`ordering-adjustment-cell-dish${dishNeedsReview?' needs-review':''}`} key={dish.id}><header><strong>{dish.name}</strong><span>{dish.dinerCount} 人</span>{dishNeedsReview&&<b className="ordering-review-badge">需確認</b>}</header>{dish.lines.map(line=>{
    const persistedAdjusted=line.adjusted_quantity!==null,dirty=dirtySet.has(line.id),error=dirty?validationErrors[line.id]:null
    const actual=values[line.id]??editableDecimalString(line.effective_quantity),actualUnit=units[line.id]??line.effective_unit,showRestore=!decimalStringsEqual(actual,line.system_quantity)||actualUnit!==line.system_unit||dirty
    const needsReview=reviewLineIds.has(line.id)
    return <div className={`ordering-adjustment-cell-line${dirty?' is-dirty':''}${needsReview?' needs-review':''}`} key={line.id}><strong>{line.ingredient_name_snapshot}</strong><div className="ordering-adjustment-cell-quantity"><span>{formatAdjustmentQuantity(line.system_quantity)} {line.system_unit}</span><span aria-hidden="true">→</span>{readOnly?<b>{formatAdjustmentQuantity(line.effective_quantity)}</b>:<input type="text" inputMode="decimal" aria-label={`${dish.name} - ${line.ingredient_name_snapshot} 實際叫貨量`} disabled={saving||saveLocked} value={actual} onChange={event=>onChange(line.id,event.target.value)} onKeyDown={event=>{if(event.key==='Enter')event.preventDefault()}}/>}<span>{actualUnit}</span></div><div className="ordering-adjustment-cell-state">{needsReview&&<small className="ordering-review-badge">需確認</small>}{persistedAdjusted&&<small className="persisted">人工調整</small>}{dirty&&<small className="dirty">已修改</small>}{!readOnly&&showRestore&&<button type="button" className="text-button" disabled={saving||saveLocked} onClick={()=>onRestore(line)}>恢復</button>}</div>{error&&<small className="error">{error}</small>}</div>
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
  if(code==='ADJUSTMENT_SYNC_REQUIRED')return '原始菜單或食譜已變更，目前需要先完成菜單同步功能才能解除鎖定。'
  if(code==='SYNC_SOURCE_CHANGED')return '來源已再次變更，請重新預覽後再套用。'
  if(code==='SYNC_REMOVALS_NOT_ACCEPTED')return '尚未確認全部移除項目，請重新檢查差異。'
  if(code==='SYNC_UNIT_CONFLICT')return '仍有單位衝突未處理，請明確選擇需要重設的項目。'
  if(code==='ADJUSTMENT_DRAFT_EXISTS')return '已有相同來源的草稿，請先處理該草稿。'
  if(code==='INVALID_ADJUSTMENT_STATUS')return '目前調整單狀態不允許同步。'
  if(code==='CONFIRMED_DELETE_FORBIDDEN')return '已確認的叫貨調整單不能刪除。'
  if(code==='CANCELLED_DELETE_FORBIDDEN')return '已取消的叫貨調整單不能刪除。'
  if(code==='SNAPSHOT_LOCKED')return '這張調整單已被正式採購使用，不能解除鎖定或刪除。'
  if(error instanceof ApiError&&error.status===404)return '找不到這張叫貨調整單。'
  return fallback
}

function formatShortDate(value:string){const [,month,day]=value.split('-');return `${String(Number(month)).padStart(2,'0')}/${String(Number(day)).padStart(2,'0')}`}
function formatDate(value:string){const date=new Date(`${value}T00:00:00+08:00`);const weekday=['日','一','二','三','四','五','六'][date.getDay()];return `${formatShortDate(value)}（${weekday}）`}
