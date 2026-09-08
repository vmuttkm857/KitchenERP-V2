export type Meal='breakfast'|'lunch'|'dinner'
export type DeliveryType='vaginal'|'cesarean'
export type CaseStatus='pending'|'active'|'paused'|'ended'
export type PreparationMode='no_herbal'|'herbal'|'rice_wine_sesame'|'no_rice_wine_sesame'
export interface PostpartumCase {id:string;case_number:string;name:string;current_room:string;delivery_type:DeliveryType;delivery_date:string;service_start_date:string;service_start_meal:Meal;service_end_date:string|null;service_end_meal:Meal|null;status:CaseStatus;preparation_mode:PreparationMode;service_note:string|null;is_active:boolean;created_at:string;updated_at:string;created_by:string;updated_by:string}
export interface RoomHistory {id:string;case_id:string;room:string;effective_date:string;effective_meal:Meal;created_at:string;updated_at:string;created_by:string;updated_by:string}
export interface ServicePause {id:string;case_id:string;start_date:string;start_meal:Meal;end_date:string;end_meal:Meal;note:string|null;created_at:string;updated_at:string;created_by:string;updated_by:string}
export interface CaseDetail {case:PostpartumCase;room_history:RoomHistory[];pauses:ServicePause[]}
