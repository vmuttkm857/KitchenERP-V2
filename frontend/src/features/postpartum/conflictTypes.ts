import type { CaseStatus, Meal } from './types'

export type ConflictCoverage='complete'|'partial'|'unavailable'
export type ConflictOutcome='conflict'|'no_conflict'|'unknown'

export interface ConflictWarning {
  code:string
  message:string
  case_id?:string|null
  menu_dish_id?:string|null
  restriction_group_id?:string|null
  ingredient_id?:string|null
  target_id?:string|null
}

export interface ConflictTarget {id:string;code:string;name:string;is_active:boolean}
export interface ConflictRestrictionGroup {id:string;name:string;color:string;notes:string|null;is_active:boolean}
export interface ConflictSource {
  source_id:string;menu_id:string;menu_name:string;start_date:string;end_date:string;is_active:boolean
}
export interface ConflictSourceResolution {
  status:'available'|'not_configured'|'ambiguous'|'inactive'
  source:ConflictSource|null
  candidates:ConflictSource[]
}
export interface ConflictMealType {id:string;name:string;sort_order:number;is_active:boolean}
export interface ConflictMappingResolution {
  status:'mapped'|'not_mapped'|'inactive'|'inconsistent'|'not_checked'
  menu_meal_type:ConflictMealType|null
}
export interface ConflictMenuDish {
  menu_dish_id:string
  sort_order:number
  dish:ConflictTarget
  ingredient_coverage:'complete'|'partial'
  warnings:ConflictWarning[]
}
export interface ConflictCase {
  id:string;case_number:string;name:string;current_room:string;status:CaseStatus
  restriction_groups:ConflictRestrictionGroup[]
  warnings:ConflictWarning[]
}
export interface ConflictReason {
  type:'direct_dish'|'ingredient'
  restriction_group:ConflictRestrictionGroup
  matched_target:ConflictTarget
}
export interface ConflictCaseDishResult {
  case_id:string
  menu_dish_id:string
  outcome:ConflictOutcome
  coverage:'complete'|'partial'
  reasons:ConflictReason[]
  warnings:ConflictWarning[]
}
export interface PostpartumConflictResponse {
  target_date:string
  postpartum_meal:Meal
  evaluation_status:ConflictCoverage
  evaluation_performed:boolean
  source_resolution:ConflictSourceResolution
  mapping_resolution:ConflictMappingResolution
  menu_day:{id:string;menu_date:string}|null
  menu_dishes:ConflictMenuDish[]
  eligible_cases:ConflictCase[]
  case_dish_results:ConflictCaseDishResult[]
  warnings:ConflictWarning[]
}

export type ConflictSummaryStatus='conflict'|'partial'|'complete'|'unmapped'|'unavailable'
export interface ConflictMealSummary {
  target_date:string
  postpartum_meal:Meal
  status:ConflictSummaryStatus
  evaluation_status:ConflictCoverage
  evaluation_performed:boolean
  source_status:ConflictSourceResolution['status']
  mapping_status:ConflictMappingResolution['status']
  menu_name:string|null
  menu_meal_type_name:string|null
  eligible_case_count:number
  menu_dish_count:number
  conflict_case_count:number
  conflict_count:number
  manual_review_case_count:number
  warnings:ConflictWarning[]
}
export interface PostpartumConflictDailyResponse {
  target_date:string
  meals:PostpartumConflictResponse[]
  summaries:ConflictMealSummary[]
  conflict_case_count:number
  conflict_count:number
  manual_review_case_count:number
}
export interface PostpartumConflictWeeklyResponse {
  week_start:string
  week_end:string
  days:{target_date:string;meals:ConflictMealSummary[]}[]
}

export function todayTaipeiYmd(now=new Date()){
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now)
  const values=Object.fromEntries(parts.map(part=>[part.type,part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

export function unavailableMessage(result:PostpartumConflictResponse){
  if(result.source_resolution.status==='not_configured')return '該日期尚未設定月子餐 ERP 菜單來源。'
  if(result.source_resolution.status==='ambiguous')return '該日期有多個月子餐菜單來源，為避免誤判，未執行禁忌檢查。'
  if(result.mapping_resolution.status==='not_mapped')return '本餐未設定 ERP 菜單對應，因此未執行禁忌檢查。'
  return result.warnings[0]?.message??'目前資料無法執行禁忌檢查。'
}

export function conflictOutcomeLabel(result:ConflictCaseDishResult){
  if(result.outcome==='conflict')return '發現禁忌衝突'
  if(result.outcome==='no_conflict'&&result.coverage==='complete')return '未發現衝突'
  return '資料不足，無法完整判定'
}

export function addYmdDays(value:string,days:number){
  const parsed=new Date(`${value}T00:00:00Z`)
  parsed.setUTCDate(parsed.getUTCDate()+days)
  return parsed.toISOString().slice(0,10)
}

export function summaryLabel(summary:ConflictMealSummary){
  if(summary.status==='conflict')return `🔴 ${summary.conflict_case_count}人・${summary.conflict_count}項`
  if(summary.status==='partial')return summary.manual_review_case_count>0?`⚠ ${summary.manual_review_case_count}人`:'⚠ 需人工確認'
  if(summary.status==='complete')return '✓'
  if(summary.status==='unmapped')return '—'
  return '⚠ 無法檢查'
}

export function formatWeekDate(value:string){
  const parsed=new Date(`${value}T00:00:00Z`)
  const weekdays=['日','一','二','三','四','五','六']
  return `${value.slice(5).replace('-','/')}（${weekdays[parsed.getUTCDay()]}）`
}
