import type { Meal, PreparationMode } from './types'

export interface CateringRestrictionGroup {
  id:string
  name:string
  color:string
  is_active:boolean
}

export interface CateringOverviewItem {
  case_id:string
  case_number:string
  name:string
  current_room:string
  preparation_mode:PreparationMode
  preparation_mode_label:string
  service_start_date:string
  service_start_meal:Meal
  service_start_meal_label:string
  service_end_date:string|null
  service_end_meal:Meal|null
  service_end_meal_label:string|null
  restriction_groups:CateringRestrictionGroup[]
  service_note:string|null
  service_meals:{meal:Meal;label:string}[]
}

export interface CateringOverviewResponse {
  target_date:string
  weekday_label:string
  total:number
  items:CateringOverviewItem[]
}
