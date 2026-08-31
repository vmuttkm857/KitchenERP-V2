import { FormEvent, useCallback, useEffect, useState } from 'react'

import { ApiError, apiRequest } from '../../api/client'
import { EmptyState, Feedback, LoadingState, PageHeader, StatusBadge, TableFrame } from '../../components/ui/Page'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { useDebouncedValue } from '../../utils/useDebouncedValue'
import type { User } from '../../types/api'

type UserList={items:User[];pagination:{page:number;page_size:number;total:number}}
type DialogMode='create'|'edit'|'reset'|'status'

function errorText(error:unknown){
  if(!(error instanceof ApiError)||error.status>=500)return '使用者操作失敗，請稍後再試。'
  const messages:Record<string,string>={
    'Username already exists':'帳號已存在。','User not found':'找不到此使用者。',
    'The last active administrator cannot be disabled or demoted':'不可停用或降級唯一仍啟用的管理員。',
    'Password verification failed':'目前密碼驗證失敗。','Insufficient permissions':'權限不足。',
  }
  return messages[error.message]??error.message
}

function UserDialog({mode,user,busy,error,onClose,onExecute}:{mode:DialogMode;user:User|null;busy:boolean;error:string;onClose:()=>void;onExecute:(action:()=>Promise<void>)=>Promise<void>}){
  const [username,setUsername]=useState(''),[displayName,setDisplayName]=useState(user?.display_name??''),[role,setRole]=useState<'admin'|'user'>(user?.role??'user')
  const [password,setPassword]=useState(''),[confirmPassword,setConfirmPassword]=useState(''),[adminPassword,setAdminPassword]=useState('')
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[busy,onClose])
  const title=mode==='create'?'新增使用者':mode==='edit'?'編輯使用者':mode==='reset'?'重設使用者密碼':user?.is_active?'停用使用者':'恢復使用者'
  async function submit(event:FormEvent){event.preventDefault();await onExecute(async()=>{
    if(mode==='create')await apiRequest('/users',{method:'POST',body:JSON.stringify({username,display_name:displayName,password,confirm_password:confirmPassword,role})})
    if(mode==='edit'&&user)await apiRequest(`/users/${user.id}`,{method:'PATCH',body:JSON.stringify({display_name:displayName,role})})
    if(mode==='reset'&&user)await apiRequest(`/users/${user.id}/reset-password`,{method:'POST',body:JSON.stringify({current_admin_password:adminPassword,new_password:password,confirm_password:confirmPassword})})
    if(mode==='status'&&user)await apiRequest(`/users/${user.id}/${user.is_active?'deactivate':'reactivate'}`,{method:'POST'})
  })}
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}><section className="modal-panel user-dialog" role="dialog" aria-modal="true" aria-labelledby="user-dialog-title"><header><div><h2 id="user-dialog-title">{title}</h2>{user&&<p>{user.username}｜{user.display_name}</p>}</div></header><form onSubmit={event=>void submit(event).catch(()=>undefined)}>
    {mode==='create'&&<label>帳號<input autoFocus required minLength={3} maxLength={100} value={username} onChange={event=>setUsername(event.target.value)} autoComplete="off"/></label>}
    {(mode==='create'||mode==='edit')&&<><label>顯示名稱<input autoFocus={mode==='edit'} required maxLength={150} value={displayName} onChange={event=>setDisplayName(event.target.value)}/></label><label>角色<select value={role} onChange={event=>setRole(event.target.value as 'admin'|'user')}><option value="user">一般使用者</option><option value="admin">管理員</option></select></label></>}
    {(mode==='create'||mode==='reset')&&<><label>新密碼<input type="password" required minLength={12} maxLength={1024} value={password} onChange={event=>setPassword(event.target.value)} autoComplete="new-password"/></label><label>確認新密碼<input type="password" required minLength={12} maxLength={1024} value={confirmPassword} onChange={event=>setConfirmPassword(event.target.value)} autoComplete="new-password"/></label></>}
    {mode==='reset'&&<label>目前管理員密碼<input type="password" required value={adminPassword} onChange={event=>setAdminPassword(event.target.value)} autoComplete="current-password"/></label>}
    {mode==='status'&&<Feedback type={user?.is_active?'info':'success'}>{user?.is_active?'停用後該帳號將無法繼續操作，所有登入工作階段會撤銷。':'恢復後該帳號可以重新登入。'}</Feedback>}
    {error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button className={mode==='status'&&user?.is_active?'danger':''} disabled={busy}>{busy?'處理中…':mode==='status'?'確認':'儲存'}</button></footer>
  </form></section></div>
}

export function UsersPage(){
  const [items,setItems]=useState<User[]>([]),[page,setPage]=useState(1),[pageSize,setPageSize]=useState(25),[total,setTotal]=useState(0)
  const [search,setSearch]=useState(''),[active,setActive]=useState(''),[role,setRole]=useState(''),debouncedSearch=useDebouncedValue(search)
  const [loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  const [dialog,setDialog]=useState<{mode:DialogMode;user:User|null}|null>(null),[dialogError,setDialogError]=useState('')
  const load=useCallback(async()=>{setLoading(true);try{const query=new URLSearchParams({page:String(page),page_size:String(pageSize)});if(debouncedSearch)query.set('search',debouncedSearch);if(active)query.set('active',active);if(role)query.set('role',role);const result=await apiRequest<UserList>(`/users?${query}`);setItems(result.items);setTotal(result.pagination.total);setError('')}catch(cause){setError(errorText(cause))}finally{setLoading(false)}},[active,debouncedSearch,page,pageSize,role])
  useEffect(()=>{void load()},[load])
  async function execute(action:()=>Promise<void>){setBusy(true);setDialogError('');try{await action();await load();setDialog(null);setMessage('使用者資料已更新')}catch(cause){setDialogError(errorText(cause))}finally{setBusy(false)}}
  return <section><PageHeader title="使用者管理" description="建立每位操作人員的獨立帳號，管理角色與登入狀態。" actions={<button onClick={()=>{setDialogError('');setDialog({mode:'create',user:null})}}>新增使用者</button>}/>
    <div className="toolbar"><label>搜尋<input value={search} onChange={event=>{setSearch(event.target.value);setPage(1)}} placeholder="帳號或顯示名稱"/></label><label>狀態<select value={active} onChange={event=>{setActive(event.target.value);setPage(1)}}><option value="">全部</option><option value="true">啟用</option><option value="false">停用</option></select></label><label>角色<select value={role} onChange={event=>{setRole(event.target.value);setPage(1)}}><option value="">全部</option><option value="admin">管理員</option><option value="user">一般使用者</option></select></label></div>
    {error&&<Feedback type="error">{error}</Feedback>}{message&&<Feedback type="success">{message}</Feedback>}
    {loading?<LoadingState/>:!items.length?<EmptyState title="找不到符合條件的使用者"/>:<TableFrame><table><thead><tr><th>帳號</th><th>顯示名稱</th><th>角色</th><th>狀態</th><th>建立時間</th><th>最後更新</th><th>操作</th></tr></thead><tbody>{items.map(user=><tr key={user.id}><td>{user.username}</td><td>{user.display_name}</td><td>{user.role==='admin'?'管理員':'一般使用者'}</td><td><StatusBadge active={user.is_active}/></td><td>{new Date(user.created_at).toLocaleString()}</td><td>{new Date(user.updated_at).toLocaleString()}</td><td className="actions"><button className="secondary" onClick={()=>setDialog({mode:'edit',user})}>修改</button><button className="secondary" onClick={()=>setDialog({mode:'reset',user})}>重設密碼</button><button className={user.is_active?'secondary-danger':'secondary'} onClick={()=>setDialog({mode:'status',user})}>{user.is_active?'停用':'恢復'}</button></td></tr>)}</tbody></table></TableFrame>}
    <PaginationControls page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={size=>{setPageSize(size);setPage(1)}}/>
    {dialog&&<UserDialog mode={dialog.mode} user={dialog.user} busy={busy} error={dialogError} onClose={()=>setDialog(null)} onExecute={execute}/>}</section>
}

export function ChangePasswordDialog({busy,error,onClose,onSubmit}:{busy:boolean;error:string;onClose:()=>void;onSubmit:(current:string,next:string,confirm:string)=>Promise<void>}){
  const [current,setCurrent]=useState(''),[next,setNext]=useState(''),[confirm,setConfirm]=useState('')
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)onClose()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[busy,onClose])
  return <div className="modal-backdrop"><section className="modal-panel user-dialog" role="dialog" aria-modal="true"><h2>修改我的密碼</h2><p>修改成功後，所有登入工作階段都會撤銷，請重新登入。</p><form onSubmit={event=>{event.preventDefault();void onSubmit(current,next,confirm)}}><label>目前密碼<input autoFocus type="password" required value={current} onChange={event=>setCurrent(event.target.value)} autoComplete="current-password"/></label><label>新密碼<input type="password" minLength={12} required value={next} onChange={event=>setNext(event.target.value)} autoComplete="new-password"/></label><label>確認新密碼<input type="password" minLength={12} required value={confirm} onChange={event=>setConfirm(event.target.value)} autoComplete="new-password"/></label>{error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button disabled={busy}>{busy?'修改中…':'修改密碼'}</button></footer></form></section></div>
}
