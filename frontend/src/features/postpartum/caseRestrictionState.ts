import { CaseRestrictionGroup } from './types'

export function restrictionMap(items:CaseRestrictionGroup[]){return new Map(items.map(item=>[item.id,item]))}

export function mergeRestrictionGroups(active:CaseRestrictionGroup[],assigned:CaseRestrictionGroup[]){
  const values=new Map<string,CaseRestrictionGroup>()
  for(const item of active)values.set(item.id,item)
  for(const item of assigned)values.set(item.id,item)
  return [...values.values()].sort((a,b)=>a.name.localeCompare(b.name,'zh-Hant')||a.id.localeCompare(b.id))
}

export function toggleRestrictionSelection(selected:Map<string,CaseRestrictionGroup>,group:CaseRestrictionGroup){
  const next=new Map(selected)
  if(next.has(group.id))next.delete(group.id)
  else if(group.is_active)next.set(group.id,group)
  return next
}

export function filterRestrictionGroups(items:CaseRestrictionGroup[],search:string){
  const term=search.trim().toLocaleLowerCase()
  return term?items.filter(item=>item.name.toLocaleLowerCase().includes(term)):items
}
