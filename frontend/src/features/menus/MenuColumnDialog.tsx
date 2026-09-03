import { FormEvent, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import { Feedback } from '../../components/ui/Page'
import { MealType, MealTypeColumn } from './types'

interface Props {
  menuId:string
  meal:MealType
  columns:MealTypeColumn[]
  onChanged:()=>Promise<void>
  onClose:()=>void
}

export function MenuColumnDialog({menuId,meal,columns,onChanged,onClose}:Props){
  const [name,setName]=useState('')
  const [drafts,setDrafts]=useState<Record<string,string>>({})
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const ordered=[...columns].sort((a,b)=>a.sort_order-b.sort_order||a.id.localeCompare(b.id))
  useEffect(()=>setDrafts(Object.fromEntries(columns.map(column=>[column.id,column.name]))),[columns])
  async function perform(action:()=>Promise<unknown>){setBusy(true);setError('');try{await action();await onChanged()}catch{setError('菜單欄位更新失敗，請確認名稱沒有重複。')}finally{setBusy(false)}}
  function add(event:FormEvent){event.preventDefault();const value=name.trim();if(!value)return;void perform(async()=>{await apiRequest(`/menus/${menuId}/meal-types/${meal.id}/columns`,{method:'POST',body:JSON.stringify({name:value,sort_order:ordered.length+1})});setName('')})}
  function save(column:MealTypeColumn){const value=(drafts[column.id]??column.name).trim();if(value)void perform(()=>apiRequest(`/menus/${menuId}/meal-types/${meal.id}/columns/${column.id}`,{method:'PATCH',body:JSON.stringify({name:value})}))}
  function move(index:number,direction:-1|1){const target=index+direction;if(target<0||target>=ordered.length)return;const next=[...ordered];[next[index],next[target]]=[next[target],next[index]];void perform(()=>apiRequest(`/menus/${menuId}/meal-types/${meal.id}/columns/reorder`,{method:'PUT',body:JSON.stringify({ordered_ids:next.map(column=>column.id)})}))}
  function remove(column:MealTypeColumn){void perform(()=>apiRequest(`/menus/${menuId}/meal-types/${meal.id}/columns/${column.id}`,{method:'DELETE'}))}
  return <div className="modal-backdrop" onMouseDown={()=>{if(!busy)onClose()}}><section className="modal-panel menu-column-dialog" role="dialog" aria-modal="true" aria-labelledby="menu-column-title" onMouseDown={event=>event.stopPropagation()}>
    <header><div><p className="eyebrow">編輯菜單欄位</p><h2 id="menu-column-title">{meal.name}</h2></div><button className="secondary" disabled={busy} onClick={onClose}>關閉</button></header>
    <form className="inline-form" onSubmit={add}><label>新欄位名稱<input autoFocus value={name} onChange={event=>setName(event.target.value)} maxLength={100} placeholder="自由輸入欄位名稱" required/></label><button disabled={busy}>新增</button></form>
    <div className="menu-column-list">{ordered.map((column,index)=><div key={column.id}><label>名稱<input disabled={busy} value={drafts[column.id]??column.name} onChange={event=>setDrafts({...drafts,[column.id]:event.target.value})}/></label><button className="secondary" disabled={busy||index===0} onClick={()=>move(index,-1)}>上移</button><button className="secondary" disabled={busy||index===ordered.length-1} onClick={()=>move(index,1)}>下移</button><button disabled={busy} onClick={()=>save(column)}>儲存</button><button className="secondary-danger" disabled={busy} onClick={()=>remove(column)}>刪除</button></div>)}</div>
    {!ordered.length&&<p className="drawer-empty">尚未設定菜單欄位，請輸入第一個欄位名稱。</p>}{error&&<Feedback type="error">{error}</Feedback>}
  </section></div>
}
