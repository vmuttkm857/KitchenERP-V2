export type SupplierMoveDirection='up'|'down'

export function isSupplierReorderEnabled(search:string,activeFilter:string){
  return !search.trim()&&!activeFilter
}

export function moveSupplierId(ids:string[],supplierId:string,direction:SupplierMoveDirection){
  const index=ids.indexOf(supplierId)
  const target=direction==='up'?index-1:index+1
  if(index<0||target<0||target>=ids.length)return ids
  const reordered=[...ids]
  ;[reordered[index],reordered[target]]=[reordered[target],reordered[index]]
  return reordered
}

export async function performSupplierReorder(
  ids:string[],supplierId:string,direction:SupplierMoveDirection,
  submit:(supplierIds:string[])=>Promise<void>,reload:()=>Promise<void>,
){
  const reordered=moveSupplierId(ids,supplierId,direction)
  if(reordered===ids)return ids
  await submit(reordered)
  await reload()
  return reordered
}
