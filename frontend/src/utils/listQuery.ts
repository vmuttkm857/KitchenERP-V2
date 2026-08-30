export interface PaginationMeta { page:number; page_size:number; total:number }
export interface PagedResponse<T> { items:T[]; pagination:PaginationMeta }
export interface ListQuery {
  page:number; pageSize:number; search?:string; active?:string; purchaseStatus?:string; categoryId?:string; supplierId?:string; startDate?:string; endDate?:string
}

export function buildListQuery(value:ListQuery){
  const query=new URLSearchParams({page:String(value.page),page_size:String(value.pageSize)})
  if(value.search?.trim())query.set('search',value.search.trim())
  if(value.active)query.set('active',value.active)
  if(value.purchaseStatus)query.set('purchase_status',value.purchaseStatus)
  if(value.categoryId)query.set('category_id',value.categoryId)
  if(value.supplierId)query.set('supplier_id',value.supplierId)
  if(value.startDate)query.set('start_date',value.startDate)
  if(value.endDate)query.set('end_date',value.endDate)
  return query.toString()
}

export function totalPages(total:number,pageSize:number){return Math.max(1,Math.ceil(total/pageSize))}
export function nextFilterPage(){return 1}
export function menuCandidateDateParams(startDate:string,endDate:string){return {startDate:startDate||undefined,endDate:endDate||undefined}}
export function dateRangeError(startDate:string,endDate:string){return startDate&&endDate&&startDate>endDate?'開始日期不可晚於結束日期。':''}
export function clearDateRange(){return {startDate:'',endDate:''}}

export class RequestSequence {
  private value=0
  next(){return ++this.value}
  isCurrent(value:number){return value===this.value}
}

export function preserveSelected<T extends {id:string}>(results:T[],selected:Map<string,T>){
  const merged=new Map(selected)
  for(const item of results)merged.set(item.id,item)
  return [...merged.values()]
}
