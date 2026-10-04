import { apiRequest } from '../../api/client'
import type { OrderingAdjustmentBatchUpdate,OrderingAdjustmentCreateRequest,OrderingAdjustmentDetail,OrderingAdjustmentList,OrderingAdjustmentStatus } from './types'

export interface OrderingAdjustmentListParams {page:number;pageSize:number;status?:OrderingAdjustmentStatus;startDate?:string;endDate?:string;menuId?:string}

export function listOrderingAdjustments(params:OrderingAdjustmentListParams){
  const query=new URLSearchParams({page:String(params.page),page_size:String(params.pageSize)})
  if(params.status)query.set('status',params.status)
  if(params.startDate)query.set('start_date',params.startDate)
  if(params.endDate)query.set('end_date',params.endDate)
  if(params.menuId)query.set('menu_id',params.menuId)
  return apiRequest<OrderingAdjustmentList>(`/order-adjustments?${query}`)
}

export function createOrderingAdjustment(payload:OrderingAdjustmentCreateRequest){
  return apiRequest<OrderingAdjustmentDetail>('/order-adjustments',{method:'POST',body:JSON.stringify(payload)})
}

export function getOrderingAdjustment(sheetId:string){
  return apiRequest<OrderingAdjustmentDetail>(`/order-adjustments/${sheetId}`)
}

export function updateOrderingAdjustmentLines(sheetId:string,payload:OrderingAdjustmentBatchUpdate){
  return apiRequest<OrderingAdjustmentDetail>(`/order-adjustments/${sheetId}/lines`,{method:'PATCH',body:JSON.stringify(payload)})
}
