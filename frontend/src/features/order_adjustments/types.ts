import type { PaginationMeta } from '../../utils/listQuery'

export type OrderingAdjustmentStatus='draft'|'confirmed'|'cancelled'

export interface OrderingAdjustmentCriteria {
  menu_ids:string[]
  ordering_adjustment_sheet_ids?:string[]|null
  selected_dates?:string[]|null
  start_date?:string|null
  end_date?:string|null
}

export interface OrderingAdjustmentSourceMenu {
  menu_id:string
  menu_name:string
  start_date:string
  end_date:string
  is_active:boolean
}

export interface OrderingAdjustmentSummary {
  id:string
  baseline_snapshot_id:string
  status:OrderingAdjustmentStatus
  revision:number
  lock_version:number
  criteria:OrderingAdjustmentCriteria
  source_menus:OrderingAdjustmentSourceMenu[]
  notes:string|null
  created_at:string
  updated_at:string
  created_by:string
  created_by_name:string
  stale:boolean|null
}

export interface OrderingAdjustmentWarning {code:string;source_line_key?:string}

export interface OrderingAdjustmentLine {
  id:string
  snapshot_item_id:string
  source_line_key:string
  source_menu_id:string
  menu_name_snapshot:string
  source_menu_day_id:string
  requirement_date:string
  source_meal_type_id:string
  meal_type_name_snapshot:string
  meal_type_sort_order_snapshot:number
  source_menu_meal_type_column_id:string|null
  menu_meal_type_column_sort_order_snapshot:number|null
  source_menu_dish_id:string
  menu_dish_sort_order_snapshot:number
  source_dish_id:string
  dish_code_snapshot:string
  dish_name_snapshot:string
  diner_count_snapshot:number
  source_dish_ingredient_id:string
  dish_ingredient_sort_order_snapshot:number
  source_ingredient_id:string
  ingredient_code_snapshot:string
  ingredient_name_snapshot:string
  source_supplier_id:string|null
  supplier_name_snapshot:string|null
  quantity_per_person_snapshot:string
  loss_rate_snapshot:string
  recipe_unit_snapshot:string
  system_quantity:string
  system_unit:string
  adjusted_quantity:string|null
  effective_quantity:string
  modified:boolean
  review_required:boolean
  stale:boolean
  stale_reasons:string[]
}

export interface OrderingAdjustmentDetail extends Omit<OrderingAdjustmentSummary,'created_by_name'> {
  source_fingerprint:string
  last_reuse_source_sheet_id:string|null
  reuse_applied_at:string|null
  reuse_applied_by:string|null
  confirmed_at:string|null
  confirmed_by:string|null
  warnings:OrderingAdjustmentWarning[]
  stale:boolean
  lines:OrderingAdjustmentLine[]
}

export interface OrderingAdjustmentList {items:OrderingAdjustmentSummary[];pagination:PaginationMeta}
export interface OrderingAdjustmentCreateRequest {criteria:OrderingAdjustmentCriteria;notes?:string|null}
export interface OrderingAdjustmentLineUpdate {id:string;adjusted_quantity:string|null}
export interface OrderingAdjustmentBatchUpdate {lock_version:number;lines:OrderingAdjustmentLineUpdate[]}
export interface ExistingAdjustmentDetail {code:'ADJUSTMENT_DRAFT_EXISTS'|'ADJUSTMENT_ALREADY_CONFIRMED';existing_sheet_id:string}

export interface OrderingAdjustmentMenuPair {previous_menu_id:string;current_menu_id:string}
export type OrderingAdjustmentReuseStatus='safe_to_reuse'|'reference_only'|'no_match'|'ambiguous'
export interface OrderingAdjustmentReuseLine {
  status:OrderingAdjustmentReuseStatus;reason_codes:string[];current_line_id:string;previous_line_id:string|null;current_menu_id:string
  requirement_date:string;meal_name:string;dish_name:string;ingredient_name:string
  current_system_quantity:string;current_system_unit:string;current_adjusted_quantity:string|null
  previous_system_quantity:string|null;previous_system_unit:string|null;previous_adjusted_quantity:string|null;reused_quantity:string|null
}
export interface OrderingAdjustmentReusePreview {
  current_sheet_id:string;previous_sheet_id:string;current_lock_version:number;previous_lock_version:number
  summary:Record<OrderingAdjustmentReuseStatus,number>&{no_reusable_adjustment:number};lines:OrderingAdjustmentReuseLine[]
}
export interface OrderingAdjustmentReuseRequest {previous_sheet_id:string;current_lock_version:number;previous_lock_version:number;menu_pairs:OrderingAdjustmentMenuPair[]}
export interface OrderingAdjustmentReuseApplyRequest extends OrderingAdjustmentReuseRequest {selected_current_line_ids:string[]}
