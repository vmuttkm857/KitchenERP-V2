export interface RestrictionTarget { id:string; code:string; name:string; is_active:boolean }
export interface RestrictionGroup {
  id:string; name:string; color:string; notes:string|null; is_active:boolean
  ingredient_count:number; dish_count:number
  created_at:string; updated_at:string; created_by:string; updated_by:string
}
export interface RestrictionGroupDetail {
  group:RestrictionGroup
  ingredients:RestrictionTarget[]
  dishes:RestrictionTarget[]
}

export function targetMap(items:RestrictionTarget[]){return new Map(items.map(item=>[item.id,item]))}
export function toggleTarget(selected:Map<string,RestrictionTarget>,item:RestrictionTarget){
  const next=new Map(selected)
  if(next.has(item.id))next.delete(item.id);else next.set(item.id,item)
  return next
}
export function addTargets(selected:Map<string,RestrictionTarget>,items:RestrictionTarget[]){
  const next=new Map(selected)
  for(const item of items)next.set(item.id,item)
  return next
}
export function removeTargets(selected:Map<string,RestrictionTarget>,items:RestrictionTarget[]){
  const next=new Map(selected)
  for(const item of items)next.delete(item.id)
  return next
}
export function bulkSelectionQuery(search:string,categoryId:string){
  const query=new URLSearchParams({active:'true'})
  if(search.trim())query.set('search',search.trim())
  if(categoryId)query.set('category_id',categoryId)
  return query.toString()
}
