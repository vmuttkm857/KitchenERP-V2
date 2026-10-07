import {useCallback,useEffect,useRef,useState} from 'react'
import {ApiError,apiRequest} from '../../api/client'
import {DishSearchPicker} from './DishSearchPicker'
import type {DishCategoryOption,DishOption,List,Menu} from './types'
import type {MenuImportBatchDetail,MenuImportDraftLine,MenuImportFinalizeResponse,MenuImportGridLine,MenuImportOverlap} from './menuImportTypes'
import {menuImportStatus} from './menuImportGrid'
import {MenuImportWeekGrid} from './MenuImportWeekGrid'

interface Paged<T>{items:T[];pagination:{page:number;page_size:number;total:number}}
const statusLabels={MATCHED:'已配對',MANUALLY_RESOLVED:'已人工確認',UNMATCHED:'找不到菜色',AMBIGUOUS:'多筆菜色名稱相符',INACTIVE_MATCH:'相符菜色已停用',EXCLUDED:'已排除'} as const
function displayDateTime(value:string){return new Intl.DateTimeFormat('zh-TW',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value))}
function publicError(cause:unknown,fallback:string){return cause instanceof ApiError&&cause.status<500&&cause.message!=='系統暫時無法完成要求，請稍後再試。'?cause.message:fallback}
function defaultMenuName(filename:string){return filename.replace(/\.xlsx$/i,'').trim()||'匯入菜單'}
function finalizePublicError(cause:unknown){
  if(cause instanceof ApiError&&cause.detail&&typeof cause.detail==='object'){
    const detail=cause.detail as {code?:unknown;message?:unknown;warnings?:unknown}
    if(detail.code==='MENU_IMPORT_NOT_READY'&&Array.isArray(detail.warnings))return `草稿目前無法建立正式菜單：${detail.warnings.filter(value=>typeof value==='string').join('、')}`
    if(detail.code==='MENU_IMPORT_INVALID'&&typeof detail.message==='string')return `正式菜單資料需要修正：${detail.message}`
    if(detail.code==='DISH_NOT_ACTIVE_OR_NOT_FOUND')return '部分菜色已失效，請返回審核並重新確認。'
  }
  return publicError(cause,'正式菜單建立失敗；匯入草稿與既有菜單都沒有變更。')
}

interface MenuCategory {id:string;name:string;is_active:boolean}

function FinalizeMenuDialog({batch,onClose,onFinalized}:{batch:MenuImportBatchDetail;onClose:()=>void;onFinalized:(result:MenuImportFinalizeResponse)=>void}){
  const [name,setName]=useState(defaultMenuName(batch.original_filename)),[categoryId,setCategoryId]=useState(''),[notes,setNotes]=useState('')
  const [categories,setCategories]=useState<MenuCategory[]>([]),[overlaps,setOverlaps]=useState<MenuImportOverlap[]>([])
  const [loadingInfo,setLoadingInfo]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState('')
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!saving)onClose()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[onClose,saving])
  useEffect(()=>{let active=true;setLoadingInfo(true);const params=new URLSearchParams({start_date:batch.start_date,end_date:batch.end_date,page:'1',page_size:'100'});void Promise.all([
    apiRequest<List<MenuCategory>>('/categories/menu?active=true&page_size=100'),
    apiRequest<Paged<Menu>>(`/menus?${params}`),
  ]).then(([categoryList,menuList])=>{if(active){setCategories(categoryList.items.filter(item=>item.is_active));setOverlaps(menuList.items)}}).catch(()=>{if(active)setError('菜單分類或日期重疊資訊載入失敗，請關閉後重試。')}).finally(()=>{if(active)setLoadingInfo(false)});return()=>{active=false}},[batch.end_date,batch.start_date])
  async function save(){if(!name.trim()||saving||loadingInfo)return;setSaving(true);setError('');try{const result=await apiRequest<MenuImportFinalizeResponse>(`/menu-imports/${batch.id}/finalize`,{method:'POST',body:JSON.stringify({name:name.trim(),category_id:categoryId||null,notes:notes.trim()||null})});onFinalized(result)}catch(cause){setError(finalizePublicError(cause))}finally{setSaving(false)}}
  return <div className="modal-backdrop nested" onMouseDown={()=>!saving&&onClose()}><section className="modal-panel menu-import-finalize-dialog" role="dialog" aria-modal="true" aria-labelledby="finalize-menu-title" onMouseDown={event=>event.stopPropagation()}><header><div><h2 id="finalize-menu-title">建立正式菜單</h2><p>將已確認的 Excel 匯入草稿建立為一份新的菜單。</p></div><button type="button" className="secondary" onClick={onClose} disabled={saving}>取消</button></header>
    <div className="menu-import-finalize-summary"><span>Excel 檔案</span><strong>{batch.original_filename}</strong><span>固定日期</span><strong>{batch.start_date} ～ {batch.end_date}</strong><span>有效菜色</span><strong>{batch.summary.dish_count-batch.summary.excluded_count} 道</strong><span>已排除</span><strong>{batch.summary.excluded_count} 道</strong><span>餐別／菜單欄位</span><strong>{batch.summary.meal_count} 個／{batch.summary.column_count} 個</strong></div>
    <label>菜單名稱<input autoFocus required maxLength={150} value={name} onChange={event=>setName(event.target.value)}/></label>
    <label>菜單分類（選填）<select value={categoryId} onChange={event=>setCategoryId(event.target.value)}><option value="">未分類</option>{categories.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>備註（選填）<textarea maxLength={1000} rows={3} value={notes} onChange={event=>setNotes(event.target.value)}/></label>
    <div className="menu-import-overlap-info" role="status"><strong>日期重疊僅供參考，不會覆蓋既有菜單</strong>{loadingInfo?<span>正在檢查既有菜單…</span>:overlaps.length?<><span>此日期與 {overlaps.length} 份既有菜單重疊：</span>{overlaps.map(menu=><span key={menu.id}>{menu.name}｜{menu.start_date} ～ {menu.end_date}{menu.is_active?'':'（已停用）'}</span>)}</>:<span>此日期未與既有菜單重疊。</span>}</div>
    <p className="menu-import-finalize-confirm">建立後，這份 Excel 匯入會成為正式菜單，之後可直接在菜單管理中編輯，並使用食材需求、叫貨及廚房作業等既有流程。本操作不會修改或覆蓋其他既有菜單。</p>
    {error&&<p className="error" role="alert">{error}</p>}
    <footer><button type="button" className="secondary" onClick={onClose} disabled={saving}>返回審核</button><button type="button" onClick={()=>void save()} disabled={saving||loadingInfo||!name.trim()}>{saving?'建立中…':'確認建立正式菜單'}</button></footer>
  </section></div>
}

function DishResolutionDialog({batchId,line,onClose,onResolved}:{batchId:string;line:MenuImportDraftLine;onClose:()=>void;onResolved:(detail:MenuImportBatchDetail)=>void}){
  const [search,setSearch]=useState(''),[debounced,setDebounced]=useState(''),[categoryId,setCategoryId]=useState(''),[page,setPage]=useState(1)
  const [categories,setCategories]=useState<DishCategoryOption[]>([]),[results,setResults]=useState<DishOption[]>([]),[total,setTotal]=useState(0)
  const [selected,setSelected]=useState<DishOption|null>(null),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState('')
  const [excludeConfirm,setExcludeConfirm]=useState(false)
  const inputRef=useRef<HTMLInputElement>(null)
  useEffect(()=>{void apiRequest<List<DishCategoryOption>>('/categories/dish?active=true&page_size=100').then(value=>setCategories(value.items)).catch(()=>setError('菜色分類載入失敗，但仍可使用名稱搜尋。'));window.setTimeout(()=>inputRef.current?.focus(),0)},[])
  useEffect(()=>{const timer=window.setTimeout(()=>setDebounced(search.trim()),250);return()=>window.clearTimeout(timer)},[search])
  useEffect(()=>{setPage(1)},[debounced,categoryId])
  useEffect(()=>{if(!debounced&&!categoryId){setResults([]);setTotal(0);setLoading(false);return}let active=true;setLoading(true);const params=new URLSearchParams({active:'true',page:String(page),page_size:'20'});if(debounced)params.set('search',debounced);if(categoryId)params.set('category_id',categoryId);void apiRequest<Paged<DishOption>>(`/dishes?${params}`).then(value=>{if(active){setResults(value.items);setTotal(value.pagination.total)}}).catch(()=>{if(active)setError('菜色搜尋失敗，請稍後再試。')}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[categoryId,debounced,page])
  async function mutate(path:string,init:RequestInit,fallback:string){setSaving(true);setError('');try{await apiRequest(path,init);onResolved(await apiRequest<MenuImportBatchDetail>(`/menu-imports/${batchId}`))}catch(cause){setError(publicError(cause,fallback))}finally{setSaving(false)}}
  async function save(){if(!selected)return;await mutate(`/menu-imports/${batchId}/lines/${line.id}`,{method:'PATCH',body:JSON.stringify({dish_id:selected.id})},'菜色確認失敗，草稿尚未變更。')}
  async function exclude(){await mutate(`/menu-imports/${batchId}/lines/${line.id}/exclude`,{method:'POST'},'排除菜色失敗，草稿尚未變更。')}
  async function restore(){await mutate(`/menu-imports/${batchId}/lines/${line.id}/restore`,{method:'POST'},'恢復菜色失敗，草稿尚未變更。')}
  const excluded=line.resolution_status==='EXCLUDED'
  return <div className="modal-backdrop nested" onMouseDown={()=>!saving&&onClose()}><section className="modal-panel wide menu-import-resolve-dialog" role="dialog" aria-modal="true" aria-labelledby="resolve-import-line-title" onMouseDown={event=>event.stopPropagation()}><header><div><h2 id="resolve-import-line-title">{excluded?'恢復匯入菜色':'編輯匯入菜色'}</h2><p>{line.date}｜{line.meal_name}｜{line.column_name}</p></div><button className="secondary" onClick={onClose} disabled={saving}>取消</button></header>
    <div className={`menu-import-line-context ${excluded?'is-excluded':''}`}><span>Excel 原始菜名</span><strong>{line.original_import_name}</strong><span className={excluded?'menu-import-excluded-badge':'menu-import-state-badge'}>{statusLabels[menuImportStatus(line)]}</span>{!excluded&&<><span>目前菜色</span><strong>{line.dish?`${line.dish.code} ${line.dish.name}`:'尚未指定'}</strong></>}</div>
    {error&&<p className="error" role="alert">{error}</p>}
    {excluded?<div className="menu-import-restore-panel"><p>恢復後會以 Excel 原始菜名重新執行自動配對；若無法唯一配對，會回到「需確認」狀態。</p><button type="button" onClick={()=>void restore()} disabled={saving}>{saving?'恢復中…':'恢復此菜色'}</button></div>:<>
      <DishSearchPicker title="搜尋並選擇現有菜色" actionLabel="選擇" selectedActionLabel="已選擇" search={search} categoryId={categoryId} categories={categories} results={results} addedIds={new Set(selected?[selected.id]:[])} total={total} page={page} disabled={saving} loading={loading} inputRef={inputRef} onSearch={value=>setSearch(value)} onCategory={setCategoryId} onPage={setPage} onAdd={dish=>setSelected(dish)}/>
      {excludeConfirm?<div className="menu-import-exclude-confirm" role="alert"><strong>確定要從這次匯入排除這道菜嗎？</strong><span>{line.date}｜{line.meal_name}｜{line.column_name}｜{line.original_import_name}</span><p>只會從本次 Excel 匯入排除，不會刪除菜色資料庫中的菜色。</p><div className="actions"><button type="button" className="secondary" onClick={()=>setExcludeConfirm(false)} disabled={saving}>返回</button><button type="button" className="danger" onClick={()=>void exclude()} disabled={saving}>{saving?'排除中…':'確定排除'}</button></div></div>:<button type="button" className="danger menu-import-exclude-action" onClick={()=>setExcludeConfirm(true)} disabled={saving}>從匯入排除</button>}
      <footer><span>{selected?<>將對應到：<strong>{selected.code} {selected.name}</strong></>:'可重新指定菜色，或保留目前對應。'}</span><button type="button" disabled={!selected||saving} onClick={()=>void save()}>{saving?'儲存中…':'確認變更'}</button></footer>
    </>}
  </section></div>
}

export function MenuImportReviewPage({batchId,onClose,onOpenMenu}:{batchId:string;onClose:()=>void;onOpenMenu:(menu:Menu)=>void}){
  const [detail,setDetail]=useState<MenuImportBatchDetail|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('')
  const [reviewLine,setReviewLine]=useState<MenuImportDraftLine|null>(null),[deleteOpen,setDeleteOpen]=useState(false),[deleting,setDeleting]=useState(false),[finalizeOpen,setFinalizeOpen]=useState(false)
  const load=useCallback(async()=>{setLoading(true);try{setDetail(await apiRequest<MenuImportBatchDetail>(`/menu-imports/${batchId}`));setError('')}catch(cause){setError(publicError(cause,'匯入草稿載入失敗，請返回菜單管理後重試。'))}finally{setLoading(false)}},[batchId])
  useEffect(()=>{void load()},[load])
  async function remove(){setDeleting(true);setError('');try{await apiRequest(`/menu-imports/${batchId}`,{method:'DELETE'});onClose()}catch(cause){setError(publicError(cause,'草稿刪除失敗，資料仍然保留。'));setDeleteOpen(false)}finally{setDeleting(false)}}
  function openReview(line:MenuImportGridLine){if('id'in line)setReviewLine(line)}
  async function openFinalizedMenu(menuId:string){setError('');try{onOpenMenu(await apiRequest<Menu>(`/menus/${menuId}`))}catch(cause){setError(publicError(cause,'已建立的正式菜單目前無法開啟。'))}}
  if(loading&&!detail)return <section><h2>Excel 菜單匯入審核</h2><p>匯入草稿載入中…</p></section>
  if(!detail)return <section><h2>Excel 菜單匯入審核</h2><p className="error">{error}</p><button className="secondary" onClick={onClose}>返回菜單管理</button></section>
  const finalized=detail.status==='FINALIZED'
  return <section className="menu-import-review-page"><header className="menu-import-review-header"><div><button type="button" className="link-button" onClick={onClose}>← 返回菜單管理</button><h2>Excel 菜單匯入審核</h2><p>{detail.original_filename}｜{detail.sheet_name}</p></div><div className="actions"><span className={finalized?'status-finalized':detail.status==='READY'?'status-ready':'status-review'}>{finalized?'已建立正式菜單':detail.status==='READY'?'確認完成':'需要審核'}</span>{detail.can_finalize&&<button type="button" onClick={()=>setFinalizeOpen(true)}>建立正式菜單</button>}{finalized&&detail.finalized_menu_id&&<button type="button" onClick={()=>void openFinalizedMenu(detail.finalized_menu_id!)}>開啟正式菜單</button>}{!finalized&&<button type="button" className="danger" onClick={()=>setDeleteOpen(true)}>刪除草稿</button>}</div></header>
    <div className="menu-import-metadata"><span>日期：<strong>{detail.start_date} ～ {detail.end_date}</strong></span><span>建立者：<strong>{detail.created_by_name??detail.created_by}</strong></span><span>建立時間：<strong>{displayDateTime(detail.created_at)}</strong></span><span>更新時間：<strong>{displayDateTime(detail.updated_at)}</strong></span></div>
    {finalized&&<div className="menu-import-finalized-banner"><div><strong>✓ 已建立正式菜單「{detail.finalized_menu?.name??'正式菜單'}」</strong><span>{detail.finalized_at?`建立時間：${displayDateTime(detail.finalized_at)}`:''}</span></div>{detail.finalized_menu_id&&<button type="button" onClick={()=>void openFinalizedMenu(detail.finalized_menu_id!)}>前往菜單編輯</button>}</div>}
    <div className={`menu-import-review-banner ${detail.status==='READY'||finalized?'is-ready':''}`}><div><strong>{finalized?'此匯入紀錄已完成，內容僅供查閱':detail.status==='READY'?'✓ 菜單審核完成':'匯入草稿仍需處理'}</strong><span>共 {detail.summary.dish_count} 道 Excel 菜色｜有效菜色 {detail.summary.dish_count-detail.summary.excluded_count}</span></div><div className="menu-import-review-counts"><span>需確認：<strong>{detail.summary.review_required_count}</strong></span><span>重複菜色：<strong>{detail.summary.duplicate_conflict_count}</strong></span><span>已排除：<strong>{detail.summary.excluded_count}</strong></span></div></div>
    {detail.finalize_warnings.length>0&&detail.summary.review_required_count===0&&detail.summary.duplicate_conflict_count===0&&<div className="menu-import-finalize-warnings" role="status"><strong>目前仍不能建立正式菜單</strong>{detail.finalize_warnings.map(message=><span key={message}>{message}</span>)}</div>}
    {error&&<p className="error" role="alert">{error}</p>}
    <MenuImportWeekGrid startDate={detail.start_date} endDate={detail.end_date} layout={detail.layout} lines={detail.lines} onLine={finalized?undefined:openReview}/>
    <p className="menu-import-ready-note">{finalized?'匯入紀錄已鎖定；請至正式菜單繼續編輯。':detail.status==='READY'?'草稿已完成配對，可以建立新的正式菜單。':'所有菜色均可點擊編輯；請處理粉紅色需確認與橘色重複菜色。'}</p>
    {reviewLine&&<DishResolutionDialog batchId={batchId} line={reviewLine} onClose={()=>setReviewLine(null)} onResolved={value=>{setDetail(value);setReviewLine(null)}}/>}
    {finalizeOpen&&<FinalizeMenuDialog batch={detail} onClose={()=>setFinalizeOpen(false)} onFinalized={result=>{setFinalizeOpen(false);onOpenMenu(result.menu)}}/>}
    {deleteOpen&&<div className="modal-backdrop nested" onMouseDown={()=>!deleting&&setDeleteOpen(false)}><section className="modal-panel danger-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-import-title" onMouseDown={event=>event.stopPropagation()}><header><h2 id="delete-import-title">刪除匯入草稿</h2><button className="secondary" onClick={()=>setDeleteOpen(false)} disabled={deleting}>取消</button></header><p>確定刪除「{detail.original_filename}」的匯入草稿？這不會刪除任何正式菜單或菜色。</p><footer><button className="danger" onClick={()=>void remove()} disabled={deleting}>{deleting?'刪除中…':'確認刪除草稿'}</button></footer></section></div>}
  </section>
}
