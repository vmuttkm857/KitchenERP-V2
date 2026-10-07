import {ChangeEvent,useEffect,useState} from 'react'
import {ApiError,apiRequest} from '../../api/client'
import type {MenuImportBatchList,MenuImportPreview} from './menuImportTypes'
import {MenuImportWeekGrid} from './MenuImportWeekGrid'

const MAX_UPLOAD_BYTES=10*1024*1024
function fileSize(size:number){return size<1024*1024?`${Math.max(1,Math.round(size/1024))} KB`:`${(size/1024/1024).toFixed(1)} MB`}
function errorText(cause:unknown,fallback:string){
  if(cause instanceof ApiError&&cause.status<500){
    const detail=cause.detail as {message?:unknown;errors?:unknown}|null
    const code=(cause.detail as {code?:unknown}|null)?.code
    if(code==='SOURCE_HASH_MISMATCH')return 'Excel 檔案內容已變更，請重新解析後再建立草稿。'
    if(detail&&typeof detail.message==='string')return detail.message
    if(detail&&Array.isArray(detail.errors))return detail.errors.filter(item=>typeof item==='string').join('、')||fallback
    if(cause.message!=='系統暫時無法完成要求，請稍後再試。')return cause.message
  }
  return fallback
}

export function MenuImportDialog({onClose,onOpenDraft}:{onClose:()=>void;onOpenDraft:(batchId:string)=>void}){
  const [file,setFile]=useState<File|null>(null),[sheetName,setSheetName]=useState('')
  const [preview,setPreview]=useState<MenuImportPreview|null>(null),[busy,setBusy]=useState(false)
  const [error,setError]=useState(''),[duplicateId,setDuplicateId]=useState<string|null>(null)
  const [drafts,setDrafts]=useState<MenuImportBatchList|null>(null),[draftError,setDraftError]=useState('')
  useEffect(()=>{let active=true;void apiRequest<MenuImportBatchList>('/menu-imports?page=1&page_size=25').then(value=>{if(active)setDrafts(value)}).catch(()=>{if(active)setDraftError('未完成匯入載入失敗，仍可重新選擇 Excel。')});return()=>{active=false}},[])
  function choose(event:ChangeEvent<HTMLInputElement>){const next=event.target.files?.[0]??null;setPreview(null);setDuplicateId(null);setError('');if(next&&!next.name.toLowerCase().endsWith('.xlsx')){setFile(null);setError('請選擇 .xlsx 格式的 Excel 檔案。');event.target.value='';return}if(next&&next.size>MAX_UPLOAD_BYTES){setFile(null);setError('Excel 檔案不可超過 10 MB。');event.target.value='';return}setFile(next)}
  function formData(includeHash=false){const body=new FormData();if(file)body.append('file',file);if(sheetName.trim())body.append('sheet_name',sheetName.trim());if(includeHash&&preview)body.append('expected_source_hash',preview.source_hash);return body}
  async function parse(){if(!file)return;setBusy(true);setError('');setDuplicateId(null);try{setPreview(await apiRequest<MenuImportPreview>('/menu-imports/preview',{method:'POST',body:formData()}))}catch(cause){setError(errorText(cause,'Excel 解析失敗，請確認檔案格式與內容。'))}finally{setBusy(false)}}
  async function createDraft(){if(!file||!preview||preview.fatal_errors.length)return;setBusy(true);setError('');setDuplicateId(null);try{const created=await apiRequest<{id:string}>('/menu-imports',{method:'POST',body:formData(true)});onOpenDraft(created.id)}catch(cause){if(cause instanceof ApiError&&cause.status===409){const detail=cause.detail as {code?:unknown;existing_batch_id?:unknown}|null;if(detail?.code==='MENU_IMPORT_DRAFT_EXISTS'&&typeof detail.existing_batch_id==='string'){setDuplicateId(detail.existing_batch_id);setError('這份 Excel 已建立未完成匯入草稿，請繼續原草稿。');return}}setError(errorText(cause,'匯入草稿建立失敗，請稍後再試。'))}finally{setBusy(false)}}
  return <div className="modal-backdrop" onMouseDown={onClose}><section className="modal-panel menu-import-dialog" role="dialog" aria-modal="true" aria-labelledby="menu-import-title" onMouseDown={event=>event.stopPropagation()}><header><div><h2 id="menu-import-title">匯入 Excel 菜單</h2><p>先解析預覽；確認內容後才建立可持續審核的匯入草稿。</p></div><button className="secondary" onClick={onClose} disabled={busy}>關閉</button></header>
    <div className="menu-import-upload"><label>Excel 檔案（僅支援 .xlsx）<input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={choose} disabled={busy}/></label><label>工作表名稱（選填）<input value={sheetName} onChange={event=>{setSheetName(event.target.value);setPreview(null)}} placeholder="留空使用預設工作表" disabled={busy}/></label>{file&&<p><strong>{file.name}</strong>・{fileSize(file.size)}</p>}<button type="button" onClick={()=>void parse()} disabled={!file||busy}>{busy?'解析中…':'解析預覽'}</button></div>
    {error&&<div className="error menu-import-message" role="alert">{error}{duplicateId&&<button type="button" onClick={()=>onOpenDraft(duplicateId)}>繼續原草稿</button>}</div>}
    {preview&&<section className="menu-import-preview"><div className="menu-import-summary"><strong>{preview.start_date} ～ {preview.end_date}</strong><span>{preview.summary.date_count} 天</span><span>餐別 {preview.summary.meal_count}</span><span>菜單欄位 {preview.summary.column_count}</span><span>{preview.summary.dish_count} 道菜</span><span>已配對 {preview.summary.matched_count}</span><span className={preview.summary.review_required_count?'needs-review-text':''}>需確認 {preview.summary.review_required_count}</span></div>
      {preview.fatal_errors.length>0&&<div className="error"><strong>無法建立草稿</strong><ul>{preview.fatal_errors.map(item=><li key={item}>{item}</li>)}</ul></div>}
      {preview.overlapping_menus.length>0&&<div className="warning"><strong>日期與既有菜單重疊</strong><ul>{preview.overlapping_menus.map(item=><li key={item.id}>{item.name}｜{item.start_date} ～ {item.end_date}{item.is_active?'':'（已停用）'}</li>)}</ul><p>建立匯入草稿不會修改或覆蓋既有菜單。</p></div>}
      {preview.warnings.length>0&&<div className="warning"><ul>{preview.warnings.map((item,index)=><li key={`${index}-${item}`}>{item}</li>)}</ul></div>}
      <MenuImportWeekGrid startDate={preview.start_date} endDate={preview.end_date} layout={preview.layout} lines={preview.lines}/>
      <footer><button type="button" className="secondary" onClick={()=>setPreview(null)} disabled={busy}>返回選檔</button><button type="button" className="secondary" onClick={onClose} disabled={busy}>取消</button><button type="button" onClick={()=>void createDraft()} disabled={busy||preview.fatal_errors.length>0}>{busy?'建立中…':'建立匯入草稿'}</button></footer>
    </section>}
    <section className="menu-import-draft-list"><h3>未完成的 Excel 匯入</h3>{draftError&&<p className="error">{draftError}</p>}{!drafts&&!draftError&&<p>草稿載入中…</p>}{drafts&&<>{drafts.items.length===0?<p className="empty-state">目前沒有匯入草稿。</p>:<div>{drafts.items.map(item=><button type="button" className="menu-import-draft-row" key={item.id} onClick={()=>onOpenDraft(item.id)}><span><strong>{item.original_filename}</strong><small>{item.start_date} ～ {item.end_date}・{item.sheet_name}・建立於 {new Date(item.created_at).toLocaleString('zh-TW')}</small></span><span className={item.status==='READY'?'status-ready':'status-review'}>{item.status==='READY'?'確認完成':`需確認 ${item.summary.review_required_count}`}</span></button>)}</div>}<small>共 {drafts.pagination.total} 份草稿</small></>}</section>
  </section></div>
}
