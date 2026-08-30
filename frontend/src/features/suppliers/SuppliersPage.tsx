import { FormEvent,useCallback,useEffect,useRef,useState } from 'react'
import { ApiError,apiRequest } from '../../api/client'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { EmptyState,Feedback,LoadingState,PageHeader,StatusBadge,TableFrame } from '../../components/ui/Page'
import { buildListQuery,PagedResponse,RequestSequence } from '../../utils/listQuery'
import { useDebouncedValue } from '../../utils/useDebouncedValue'
import { normalizeSupplierValues,SupplierValues } from './supplierForm'
import { isSupplierReorderEnabled,performSupplierReorder,SupplierMoveDirection } from './supplierOrdering'

interface Supplier{
  id:string;code:string;name:string;contact_person:string|null;phone:string|null;address:string|null;notes:string|null;sort_order:number;is_active:boolean
}

function supplierError(error:unknown,fallback:string){
  if(error instanceof ApiError&&error.status===409)return error.message.includes('code')?'供應商代碼已存在，請使用其他代碼。':'供應商仍被其他資料引用，無法永久刪除。'
  if(error instanceof ApiError&&error.status===401)return '目前密碼不正確，請重新輸入。'
  if(error instanceof ApiError&&error.status===422)return '供應商排序資料已變更，請重新載入後再試。'
  return fallback
}

function supplierValues(supplier:Supplier):SupplierValues{return {code:supplier.code,name:supplier.name,contact_person:supplier.contact_person,phone:supplier.phone,address:supplier.address,notes:supplier.notes,is_active:supplier.is_active}}

function SupplierFields({values,onChange,autoFocus=false}:{values:SupplierValues;onChange:(values:SupplierValues)=>void;autoFocus?:boolean}){
  const set=<K extends keyof SupplierValues,>(key:K,value:SupplierValues[K])=>onChange({...values,[key]:value})
  return <div className="supplier-edit-fields">
    <label>代碼<input autoFocus={autoFocus} required maxLength={50} value={values.code} onChange={event=>set('code',event.target.value)}/></label>
    <label>名稱<input required maxLength={150} value={values.name} onChange={event=>set('name',event.target.value)}/></label>
    <label>聯絡人<input maxLength={100} value={values.contact_person??''} onChange={event=>set('contact_person',event.target.value)}/></label>
    <label>電話<input maxLength={50} value={values.phone??''} onChange={event=>set('phone',event.target.value)}/></label>
    <label className="supplier-wide-field">地址<input maxLength={500} value={values.address??''} onChange={event=>set('address',event.target.value)}/></label>
    <label className="supplier-wide-field">備註<textarea maxLength={1000} rows={3} value={values.notes??''} onChange={event=>set('notes',event.target.value)}/></label>
    <label className="checkbox-label"><input type="checkbox" checked={values.is_active} onChange={event=>set('is_active',event.target.checked)}/>啟用</label>
  </div>
}

function SupplierEditDialog({supplier,busy,error,onClose,onSave}:{supplier:Supplier;busy:boolean;error:string;onClose:()=>void;onSave:(values:SupplierValues)=>Promise<void>}){
  const [values,setValues]=useState<SupplierValues>(supplierValues(supplier))
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[busy,onClose])
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}><section className="modal-panel supplier-dialog" role="dialog" aria-modal="true" aria-labelledby="supplier-edit-title"><header><div><h2 id="supplier-edit-title">編輯供應商</h2><p>更新供應商聯絡資訊與狀態。</p></div></header><form onSubmit={event=>{event.preventDefault();void onSave(normalizeSupplierValues(values))}}><SupplierFields values={values} onChange={setValues} autoFocus/>{error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button disabled={busy||!values.code.trim()||!values.name.trim()}>{busy?'儲存中…':'儲存'}</button></footer></form></section></div>
}

function SupplierDeleteDialog({supplier,busy,error,onClose,onDelete}:{supplier:Supplier;busy:boolean;error:string;onClose:()=>void;onDelete:(password:string)=>Promise<void>}){
  const [password,setPassword]=useState('')
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[busy,onClose])
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}><section className="modal-panel supplier-dialog" role="dialog" aria-modal="true" aria-labelledby="supplier-delete-title"><header><div><h2 id="supplier-delete-title">永久刪除「{supplier.name}」</h2><p>此操作無法復原。若供應商仍被資料引用，系統會拒絕刪除。</p></div></header><form onSubmit={event=>{event.preventDefault();void onDelete(password)}}><label>目前密碼<input autoFocus required type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)}/></label>{error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button className="danger" disabled={busy||!password}>{busy?'刪除中…':'永久刪除'}</button></footer></form></section></div>
}

const emptyValues:SupplierValues={code:'',name:'',contact_person:null,phone:null,address:null,notes:null,is_active:true}

export function SuppliersPage(){
  const [items,setItems]=useState<Supplier[]>([]),[createValues,setCreateValues]=useState<SupplierValues>(emptyValues)
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[reorderBusy,setReorderBusy]=useState('')
  const [editing,setEditing]=useState<Supplier|null>(null),[deleting,setDeleting]=useState<Supplier|null>(null),[dialogError,setDialogError]=useState('')
  const [search,setSearch]=useState(''),[activeFilter,setActiveFilter]=useState(''),[page,setPage]=useState(1),[pageSize,setPageSize]=useState(25),[total,setTotal]=useState(0),[orderIds,setOrderIds]=useState<string[]>([])
  const debouncedSearch=useDebouncedValue(search),sequence=useRef(new RequestSequence())
  const reorderEnabled=isSupplierReorderEnabled(search,activeFilter)
  const load=useCallback(async()=>{const request=sequence.current.next();setLoading(true);try{const query=buildListQuery({page,pageSize,search:debouncedSearch,active:activeFilter});const [list,ordering]=await Promise.all([apiRequest<PagedResponse<Supplier>>(`/suppliers?${query}`),reorderEnabled?apiRequest<string[]>('/suppliers/order'):Promise.resolve([])]);if(sequence.current.isCurrent(request)){setItems(list.items);setTotal(list.pagination.total);setOrderIds(ordering);setError('')}}catch{if(sequence.current.isCurrent(request))setError('供應商載入失敗，請稍後重試。')}finally{if(sequence.current.isCurrent(request))setLoading(false)}},[activeFilter,debouncedSearch,page,pageSize,reorderEnabled])
  useEffect(()=>{void load()},[load])

  async function create(event:FormEvent){event.preventDefault();setBusy(true);setError('');try{await apiRequest('/suppliers',{method:'POST',body:JSON.stringify(normalizeSupplierValues(createValues))});setCreateValues(emptyValues);setMessage('供應商已新增');await load()}catch(cause){setError(supplierError(cause,'供應商新增失敗，請檢查輸入內容。'))}finally{setBusy(false)}}
  async function saveEdit(values:SupplierValues){if(!editing)return;setBusy(true);setDialogError('');try{await apiRequest(`/suppliers/${editing.id}`,{method:'PATCH',body:JSON.stringify(values)});setEditing(null);setMessage('供應商已修改');await load()}catch(cause){setDialogError(supplierError(cause,'供應商修改失敗，請稍後重試。'))}finally{setBusy(false)}}
  async function toggle(supplier:Supplier){setError('');try{await apiRequest(`/suppliers/${supplier.id}/${supplier.is_active?'deactivate':'reactivate'}`,{method:'POST'});setMessage(supplier.is_active?'供應商已停用，歷史資料仍保留':'供應商已恢復');await load()}catch(cause){setError(supplierError(cause,'供應商狀態更新失敗。'))}}
  async function reorder(supplier:Supplier,direction:SupplierMoveDirection){setReorderBusy(supplier.id);setError('');setMessage('');try{await performSupplierReorder(orderIds,supplier.id,direction,async ids=>{await apiRequest('/suppliers/reorder',{method:'POST',body:JSON.stringify({supplier_ids:ids})})},load);setMessage('供應商順序已更新')}catch(cause){setError(supplierError(cause,'供應商排序失敗，原順序未變更。'))}finally{setReorderBusy('')}}
  async function hardDelete(password:string){if(!deleting)return;setBusy(true);setDialogError('');try{await apiRequest(`/suppliers/${deleting.id}/hard-delete`,{method:'POST',body:JSON.stringify({password})});setDeleting(null);setMessage('未被引用的供應商已永久刪除');await load()}catch(cause){setDialogError(supplierError(cause,'供應商無法永久刪除，請稍後重試。'))}finally{setBusy(false)}}
  const resetPage=()=>setPage(1)
  return <section><PageHeader title="供應商管理" description="維護供應商聯絡資訊；停用後不再供新資料選用。"/>
    <form className="panel-form supplier-create-form" onSubmit={create}><SupplierFields values={createValues} onChange={setCreateValues}/><button disabled={busy||!createValues.code.trim()||!createValues.name.trim()}>{busy?'新增中…':'新增供應商'}</button></form>
    <div className="toolbar"><label>搜尋<input value={search} onChange={event=>{setSearch(event.target.value);resetPage()}} placeholder="代碼或名稱"/></label><label>狀態<select value={activeFilter} onChange={event=>{setActiveFilter(event.target.value);resetPage()}}><option value="">全部</option><option value="true">啟用</option><option value="false">停用</option></select></label></div>
    {!reorderEnabled&&<Feedback type="info">清除搜尋／篩選後可調整供應商順序。</Feedback>}{error&&<Feedback type="error">{error}</Feedback>}{message&&<Feedback type="success">{message}</Feedback>}
    {loading?<LoadingState/>:!items.length?<EmptyState title="找不到符合條件的供應商" description="請調整搜尋或篩選條件。"/>:<TableFrame><table><thead><tr><th>排序</th><th>代碼</th><th>名稱</th><th>聯絡人</th><th>電話</th><th>地址</th><th>狀態</th><th>操作</th></tr></thead><tbody>{items.map(supplier=>{const globalIndex=orderIds.indexOf(supplier.id);return <tr key={supplier.id}><td className="supplier-order-cell"><span>{supplier.sort_order}</span><button type="button" className="secondary compact-button" aria-label={`上移 ${supplier.name}`} disabled={!reorderEnabled||globalIndex<=0||Boolean(reorderBusy)} onClick={()=>void reorder(supplier,'up')}>↑</button><button type="button" className="secondary compact-button" aria-label={`下移 ${supplier.name}`} disabled={!reorderEnabled||globalIndex<0||globalIndex>=orderIds.length-1||Boolean(reorderBusy)} onClick={()=>void reorder(supplier,'down')}>↓</button></td><td>{supplier.code}</td><td>{supplier.name}</td><td>{supplier.contact_person??'—'}</td><td>{supplier.phone??'—'}</td><td className="supplier-address-cell" title={supplier.address??''}>{supplier.address??'—'}</td><td><StatusBadge active={supplier.is_active}/></td><td className="actions"><button type="button" className="secondary" onClick={()=>{setDialogError('');setEditing(supplier)}}>修改</button><button type="button" className="secondary" onClick={()=>void toggle(supplier)}>{supplier.is_active?'停用':'恢復'}</button><button type="button" className="secondary-danger" onClick={()=>{setDialogError('');setDeleting(supplier)}}>永久刪除</button></td></tr>})}</tbody></table></TableFrame>}
    <PaginationControls page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={size=>{setPageSize(size);setPage(1)}}/>
    {editing&&<SupplierEditDialog supplier={editing} busy={busy} error={dialogError} onClose={()=>setEditing(null)} onSave={saveEdit}/>} {deleting&&<SupplierDeleteDialog supplier={deleting} busy={busy} error={dialogError} onClose={()=>setDeleting(null)} onDelete={hardDelete}/>}</section>
}
