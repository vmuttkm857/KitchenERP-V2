export const POSTPARTUM_MEALS=[
  {value:'breakfast',label:'早餐'},
  {value:'morning_snack',label:'早點'},
  {value:'lunch',label:'午餐'},
  {value:'afternoon_snack',label:'午點'},
  {value:'dinner',label:'晚餐'},
  {value:'evening_snack',label:'晚點'},
] as const
export type Meal=(typeof POSTPARTUM_MEALS)[number]['value']
export function mealLabel(meal:Meal|null){return POSTPARTUM_MEALS.find(item=>item.value===meal)?.label??''}
export type DeliveryType='vaginal'|'cesarean'
export type CaseStatus='pending'|'active'|'paused'|'ended'
export type PreparationMode='no_herbal'|'herbal'|'rice_wine_sesame'|'no_rice_wine_sesame'
export interface CaseRestrictionGroup {id:string;name:string;color:string;is_active:boolean}
export interface PostpartumCase {id:string;case_number:string;name:string;current_room:string;delivery_type:DeliveryType;delivery_date:string;service_start_date:string;service_start_meal:Meal;service_end_date:string|null;service_end_meal:Meal|null;status:CaseStatus;preparation_mode:PreparationMode;service_note:string|null;is_active:boolean;created_at:string;updated_at:string;created_by:string;updated_by:string}
export interface PostpartumCaseListItem extends PostpartumCase {restriction_groups:CaseRestrictionGroup[]}
export interface RoomHistory {id:string;case_id:string;room:string;effective_date:string;effective_meal:Meal;created_at:string;updated_at:string;created_by:string;updated_by:string}
export interface ServicePause {id:string;case_id:string;start_date:string;start_meal:Meal;end_date:string;end_meal:Meal;note:string|null;created_at:string;updated_at:string;created_by:string;updated_by:string}
export interface CaseDetail {case:PostpartumCase;room_history:RoomHistory[];pauses:ServicePause[];restriction_groups:CaseRestrictionGroup[]}
