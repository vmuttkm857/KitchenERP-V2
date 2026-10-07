export type MenuImportMatchStatus='MATCHED'|'UNMATCHED'|'AMBIGUOUS'|'INACTIVE_MATCH'
export type MenuImportResolutionStatus=MenuImportMatchStatus|'MANUALLY_RESOLVED'|'EXCLUDED'
import type {Menu} from './types'

export type MenuImportBatchStatus='REVIEW_REQUIRED'|'READY'|'FINALIZED'

export interface MenuImportDishMatch { id:string; code:string; name:string; is_active:boolean }
export interface MenuImportSummary {
  date_count:number;meal_count:number;column_count:number;dish_count:number;matched_count:number
  review_required_count:number;duplicate_conflict_count:number;excluded_count:number
}
export interface MenuImportLayoutRow { meal_name:string; meal_sort_order:number; column_name:string; column_sort_order:number }
export interface MenuImportOverlap { id:string; name:string; start_date:string; end_date:string; is_active:boolean }

export interface MenuImportPreviewLine {
  line_key:string; date:string; meal_name:string; meal_sort_order:number
  column_name:string; column_sort_order:number; original_import_name:string; normalized_name:string
  dish:MenuImportDishMatch|null; status:MenuImportMatchStatus; review_required:boolean
  source_row:number; source_column:number; diner_count:number
}

export interface MenuImportPreview {
  source_hash:string; parser_version:string; sheet_name:string; start_date:string; end_date:string
  summary:MenuImportSummary; layout:MenuImportLayoutRow[]; lines:MenuImportPreviewLine[]; fatal_errors:string[]; warnings:string[]
  overlapping_menus:MenuImportOverlap[]
}

export interface MenuImportBatchSummary {
  id:string; status:MenuImportBatchStatus; original_filename:string; source_hash:string; parser_version:string
  sheet_name:string; start_date:string; end_date:string; summary:MenuImportSummary
  created_by:string; created_by_name:string|null; created_at:string; updated_at:string
}

export interface MenuImportDraftLine extends Omit<MenuImportPreviewLine,'status'> {
  id:string;resolution_status:MenuImportResolutionStatus;resolved_at:string|null;resolved_by:string|null
  duplicate_conflict:boolean;excluded_at:string|null;excluded_by:string|null
}

export interface MenuImportBatchDetail extends MenuImportBatchSummary {
  layout:MenuImportLayoutRow[];lines:MenuImportDraftLine[];can_finalize:boolean;finalize_warnings:string[]
  finalized_at:string|null;finalized_by:string|null;finalized_menu_id:string|null
  finalized_menu:{id:string;name:string;start_date:string;end_date:string;is_active:boolean}|null
}
export interface MenuImportBatchList { items:MenuImportBatchSummary[]; pagination:{page:number;page_size:number;total:number} }

export interface MenuImportFinalizeResponse {
  batch_id:string;status:'FINALIZED';finalized_menu_id:string;finalized_at:string
  already_finalized:boolean;menu:Menu
}

export type MenuImportGridLine=MenuImportPreviewLine|MenuImportDraftLine
