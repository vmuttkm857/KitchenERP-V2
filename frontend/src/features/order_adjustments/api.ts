import { apiDownload,apiRequest } from '../../api/client'
import type {MenuAggregate} from '../menus/types'
import type { OrderingAdjustmentBatchUpdate,OrderingAdjustmentCreateRequest,OrderingAdjustmentDetail,OrderingAdjustmentList,OrderingAdjustmentReuseApplyRequest,OrderingAdjustmentReusePreview,OrderingAdjustmentReuseRequest,OrderingAdjustmentStatus,OrderingAdjustmentUnitConversion } from './types'

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

export function convertOrderingAdjustmentUnits(sheetId:string,lockVersion:number,conversion:OrderingAdjustmentUnitConversion){
  return apiRequest<OrderingAdjustmentDetail>(`/order-adjustments/${sheetId}/convert-units`,{method:'POST',body:JSON.stringify({lock_version:lockVersion,conversion})})
}

export function confirmOrderingAdjustment(sheetId:string,lockVersion:number){
  return apiRequest<OrderingAdjustmentDetail>(`/order-adjustments/${sheetId}/confirm`,{method:'POST',body:JSON.stringify({lock_version:lockVersion})})
}

export function deleteOrderingAdjustment(sheetId:string,lockVersion:number){
  return apiRequest<void>(`/order-adjustments/${sheetId}?lock_version=${lockVersion}`,{method:'DELETE'})
}

export function getOrderingAdjustmentMenuLayout(menuId:string){return apiRequest<MenuAggregate>(`/menus/${menuId}/editor`)}
export function downloadOrderingAdjustmentWeekly(sheetId:string,menuId:string){return apiDownload(`/exports/order-adjustments/${sheetId}/weekly-ingredients.xlsx?${new URLSearchParams({menu_id:menuId})}`)}

export function previewOrderingAdjustmentReuse(sheetId:string,payload:OrderingAdjustmentReuseRequest){return apiRequest<OrderingAdjustmentReusePreview>(`/order-adjustments/${sheetId}/reuse-preview`,{method:'POST',body:JSON.stringify(payload)})}
export function applyOrderingAdjustmentReuse(sheetId:string,payload:OrderingAdjustmentReuseApplyRequest){return apiRequest<OrderingAdjustmentDetail>(`/order-adjustments/${sheetId}/reuse`,{method:'POST',body:JSON.stringify(payload)})}
