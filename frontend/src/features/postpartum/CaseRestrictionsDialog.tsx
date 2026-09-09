import { FormEvent, useEffect, useMemo, useState } from 'react'
import { ApiError, apiRequest } from '../../api/client'
import { Feedback, LoadingState } from '../../components/ui/Page'
import { CaseRestrictionGroup, PostpartumCase } from './types'
import { filterRestrictionGroups, mergeRestrictionGroups, restrictionMap, toggleRestrictionSelection } from './caseRestrictionState'

interface Paged<T>{items:T[];pagination:{page:number;page_size:number;total:number}}
interface AssignmentResponse{case_id:string;restriction_groups:CaseRestrictionGroup[]}

export function CaseRestrictionBadges({groups}:{groups:CaseRestrictionGroup[]}){
  if(!groups.length)return <span className="muted">—</span>
  return <div className="case-restriction-badges">{groups.map(group=><span key={group.id} className={`case-restriction-badge ${group.is_active?'':'is-inactive'}`} style={{borderColor:group.color,backgroundColor:`${group.color}1A`}}>{group.name}{!group.is_active&&<em>已停用</em>}</span>)}</div>
}

export function CaseRestrictionsDialog({caseItem,assigned,onClose,onSaved}:{caseItem:PostpartumCase;assigned:CaseRestrictionGroup[];onClose:()=>void;onSaved:(groups:CaseRestrictionGroup[])=>void}){
  const [activeGroups,setActiveGroups]=useState<CaseRestrictionGroup[]>([])
  const [selected,setSelected]=useState(()=>restrictionMap(assigned))
  const [search,setSearch]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{
    let current=true
    void apiRequest<Paged<CaseRestrictionGroup>>('/postpartum/restriction-groups?active=true&page=1&page_size=100')
      .then(data=>{if(current){setActiveGroups(data.items);setError('')}})
      .catch(()=>{if(current)setError('禁忌群組載入失敗')})
      .finally(()=>{if(current)setLoading(false)})
    return()=>{current=false}
  },[])
  const options=useMemo(()=>mergeRestrictionGroups(activeGroups,assigned),[activeGroups,assigned])
  const filtered=useMemo(()=>filterRestrictionGroups(options,search),[options,search])
  function toggle(group:CaseRestrictionGroup){
    setSelected(toggleRestrictionSelection(selected,group))
  }
  async function save(event:FormEvent){
    event.preventDefault();setBusy(true);setError('')
    try{
      const response=await apiRequest<AssignmentResponse>(`/postpartum/cases/${caseItem.id}/restriction-groups`,{method:'PUT',body:JSON.stringify({restriction_group_ids:[...selected.keys()]})})
      onSaved(response.restriction_groups)
      onClose()
    }catch(cause){setError(cause instanceof ApiError&&cause.status<500?cause.message:'飲食禁忌儲存失敗，請稍後再試。')}finally{setBusy(false)}
  }
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}><section className="modal-panel case-restriction-dialog" role="dialog" aria-modal="true" aria-labelledby="case-restriction-title">
    <header><div><h2 id="case-restriction-title">管理飲食禁忌</h2><p>{caseItem.case_number}｜{caseItem.name}｜目前房號 {caseItem.current_room}</p></div><button type="button" className="secondary" disabled={busy} onClick={onClose}>關閉</button></header>
    {loading?<LoadingState label="禁忌群組載入中…"/>:<form onSubmit={save}><label>搜尋禁忌群組<input value={search} onChange={event=>setSearch(event.target.value)} placeholder="輸入禁忌名稱"/></label><p className="muted">已選 {selected.size} 個禁忌群組</p>
      <div className="case-restriction-options">{filtered.length?filtered.map(group=>{const checked=selected.has(group.id);return <label key={group.id} className={`case-restriction-option ${group.is_active?'':'is-inactive'}`}><input type="checkbox" checked={checked} disabled={!group.is_active&&!checked} onChange={()=>toggle(group)}/><span className="restriction-color" style={{backgroundColor:group.color}} aria-hidden="true"/><strong>{group.name}</strong>{!group.is_active&&<em>已停用</em>}</label>}):<p>找不到符合條件的禁忌群組</p>}</div>
      {error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button disabled={busy}>{busy?'儲存中…':'儲存'}</button></footer>
    </form>}
  </section></div>
}
