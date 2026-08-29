import { FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, apiRequest } from '../../api/client'
import { EmptyState, Feedback, LoadingState, PageHeader, StatusBadge, TableFrame } from '../../components/ui/Page'

type Kind='ingredient'|'dish'|'menu'
interface Category{id:string;name:string;sort_order:number;is_active:boolean}
interface List{items:Category[]}
const kinds:Kind[]=['ingredient','dish','menu']
const labels:Record<Kind,string>={ingredient:'食材分類',dish:'菜色分類',menu:'菜單分類'}

function friendlyError(error:unknown,fallback:string){
  if(error instanceof ApiError&&error.status===409)return '名稱重複，或這筆分類仍被其他資料引用。'
  if(error instanceof ApiError&&error.status===401)return '目前密碼不正確，請重新輸入。'
  return fallback
}

function CategoryTypeTabs({kind,onChange}:{kind:Kind;onChange:(kind:Kind)=>void}){
  return <div className="category-tabs" role="tablist" aria-label="分類類型">{kinds.map(value=><button key={value} id={`category-tab-${value}`} role="tab" aria-selected={kind===value} aria-controls="category-panel" tabIndex={kind===value?0:-1} className={kind===value?'is-active':''} onClick={()=>onChange(value)} onKeyDown={event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return
    event.preventDefault();const current=kinds.indexOf(value)
    const next=event.key==='Home'?0:event.key==='End'?kinds.length-1:event.key==='ArrowRight'?(current+1)%kinds.length:(current-1+kinds.length)%kinds.length
    onChange(kinds[next]);document.getElementById(`category-tab-${kinds[next]}`)?.focus()
  }}>{labels[value]}</button>)}</div>
}

function CategoryDialog({category,kind,busy,error,onClose,onSave}:{category:Category;kind:Kind;busy:boolean;error:string;onClose:()=>void;onSave:(name:string)=>Promise<void>}){
  const [name,setName]=useState(category.name)
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[busy,onClose])
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}><section className="modal-panel category-dialog" role="dialog" aria-modal="true" aria-labelledby="category-edit-title">
    <header><div><h2 id="category-edit-title">編輯{labels[kind]}</h2><p>更新分類顯示名稱。</p></div></header>
    <form onSubmit={event=>{event.preventDefault();void onSave(name)}}><label>分類名稱<input autoFocus required maxLength={100} value={name} onChange={event=>setName(event.target.value)}/></label>{error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button disabled={busy||!name.trim()}>{busy?'儲存中…':'儲存'}</button></footer></form>
  </section></div>
}

function CategoryDeleteDialog({category,busy,error,onClose,onDelete}:{category:Category;busy:boolean;error:string;onClose:()=>void;onDelete:(password:string)=>Promise<void>}){
  const [password,setPassword]=useState('')
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[busy,onClose])
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}><section className="modal-panel category-dialog" role="dialog" aria-modal="true" aria-labelledby="category-delete-title">
    <header><div><h2 id="category-delete-title">永久刪除「{category.name}」</h2><p>此操作無法復原。若分類仍被資料引用，系統會拒絕刪除。</p></div></header>
    <form onSubmit={event=>{event.preventDefault();void onDelete(password)}}><label>目前密碼<input autoFocus required type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)}/></label>{error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button className="danger" disabled={busy||!password}>{busy?'刪除中…':'永久刪除'}</button></footer></form>
  </section></div>
}

export function CategoriesPage(){
  const [kind,setKind]=useState<Kind>('ingredient'),[items,setItems]=useState<Category[]>([]),[name,setName]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false)
  const [editing,setEditing]=useState<Category|null>(null),[deleting,setDeleting]=useState<Category|null>(null),[dialogError,setDialogError]=useState('')
  const load=useCallback(async()=>{setLoading(true);try{setItems((await apiRequest<List>(`/categories/${kind}?page_size=100`)).items);setError('')}catch{setError('分類載入失敗，請稍後重試')}finally{setLoading(false)}},[kind]);useEffect(()=>{void load()},[load])
  function changeKind(next:Kind){setKind(next);setName('');setMessage('');setError('')}
  async function create(event:FormEvent){event.preventDefault();setBusy(true);setError('');try{const nextOrder=items.length?Math.max(...items.map(item=>item.sort_order))+1:0;await apiRequest(`/categories/${kind}`,{method:'POST',body:JSON.stringify({name:name.trim(),sort_order:nextOrder})});setName('');setMessage(`${labels[kind]}已新增`);await load()}catch(cause){setError(friendlyError(cause,'分類新增失敗，請稍後重試。'))}finally{setBusy(false)}}
  async function saveEdit(nextName:string){if(!editing)return;setBusy(true);setDialogError('');try{await apiRequest(`/categories/${kind}/${editing.id}`,{method:'PATCH',body:JSON.stringify({name:nextName.trim()})});setEditing(null);setMessage('分類名稱已更新');await load()}catch(cause){setDialogError(friendlyError(cause,'分類名稱更新失敗，請稍後重試。'))}finally{setBusy(false)}}
  async function toggle(category:Category){setBusy(true);setError('');try{await apiRequest(`/categories/${kind}/${category.id}/${category.is_active?'deactivate':'reactivate'}`,{method:'POST'});setMessage(category.is_active?'分類已停用':'分類已重新啟用');await load()}catch{setError('分類狀態更新失敗，請稍後重試。')}finally{setBusy(false)}}
  async function move(index:number,direction:-1|1){const target=index+direction;if(target<0||target>=items.length)return;setBusy(true);setError('');const reordered=[...items];[reordered[index],reordered[target]]=[reordered[target],reordered[index]];try{for(let position=0;position<reordered.length;position++)await apiRequest(`/categories/${kind}/${reordered[position].id}`,{method:'PATCH',body:JSON.stringify({sort_order:position})});setMessage('分類順序已更新');await load()}catch{setError('分類順序更新失敗，已重新載入目前順序。');await load()}finally{setBusy(false)}}
  async function hardDelete(password:string){if(!deleting)return;setBusy(true);setDialogError('');try{await apiRequest(`/categories/${kind}/${deleting.id}/hard-delete`,{method:'POST',body:JSON.stringify({password})});setDeleting(null);setMessage('未被引用的分類已永久刪除');await load()}catch(cause){setDialogError(friendlyError(cause,'分類無法永久刪除，請稍後重試。'))}finally{setBusy(false)}}
  return <section><PageHeader title="分類管理" description="管理食材、菜色與菜單分類；停用不會刪除既有歷史。"/>
    <CategoryTypeTabs kind={kind} onChange={changeKind}/><div id="category-panel" role="tabpanel" aria-labelledby={`category-tab-${kind}`}><div className="category-context"><h2>{labels[kind]}</h2><p>新增、調整順序或管理現有{labels[kind]}。</p></div>
      <form className="category-create-form" onSubmit={create}><label>分類名稱<input value={name} maxLength={100} onChange={event=>setName(event.target.value)} required/></label><button disabled={busy||!name.trim()}>{busy?'處理中…':`新增${labels[kind]}`}</button></form>
      {error&&<Feedback type="error">{error}</Feedback>}{message&&<Feedback type="success">{message}</Feedback>}{loading?<LoadingState/>:!items.length?<EmptyState title={`尚未建立${labels[kind]}`} description={`可以使用上方「新增${labels[kind]}」建立第一筆資料。`}/>:<TableFrame><table className="category-table"><thead><tr><th>名稱</th><th>狀態</th><th>排序</th><th>操作</th></tr></thead><tbody>{items.map((category,index)=><tr key={category.id}><td><strong>{category.name}</strong></td><td><StatusBadge active={category.is_active}/></td><td><div className="category-order-actions"><button className="secondary compact" disabled={busy||index===0} aria-label={`將${category.name}上移`} onClick={()=>void move(index,-1)}>↑ 上移</button><button className="secondary compact" disabled={busy||index===items.length-1} aria-label={`將${category.name}下移`} onClick={()=>void move(index,1)}>↓ 下移</button></div></td><td className="actions"><button className="secondary" disabled={busy} onClick={()=>{setDialogError('');setEditing(category)}}>修改</button><button className="secondary" disabled={busy} onClick={()=>void toggle(category)}>{category.is_active?'停用':'重新啟用'}</button><button className="secondary-danger" disabled={busy} onClick={()=>{setDialogError('');setDeleting(category)}}>永久刪除</button></td></tr>)}</tbody></table></TableFrame>}
    </div>{editing&&<CategoryDialog category={editing} kind={kind} busy={busy} error={dialogError} onClose={()=>setEditing(null)} onSave={saveEdit}/>} {deleting&&<CategoryDeleteDialog category={deleting} busy={busy} error={dialogError} onClose={()=>setDeleting(null)} onDelete={hardDelete}/>}</section>
}
