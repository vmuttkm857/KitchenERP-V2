import type { Meal } from './types'

export type ChangeSheetHandlingStatus='replaced'|'manually_acknowledged'|'requires_reconfirmation'|'pending'

export interface ChangeSheetWarning {
  code:string
  message:string
  case_id?:string|null
  menu_dish_id?:string|null
  restriction_group_id?:string|null
  ingredient_id?:string|null
  target_id?:string|null
}

export interface ChangeSheetDish {id:string;code:string;name:string;is_active:boolean}
export interface ChangeSheetRestrictionGroup {id:string;name:string;color:string}
export interface ChangeSheetSummary {
  replacement_group_count:number
  replacement_item_count:number
  manual_acknowledgement_count:number
  requires_reconfirmation_count:number
}
export interface ChangeSheetCaseSummary {case_id:string;case_number:string;name:string;current_room:string}
export interface ChangeSheetReplacementItem {
  handling_id:string
  case_id:string
  case_number:string
  case_name:string
  current_room:string
  original_menu_dish_id:string
  original_dish:ChangeSheetDish
  replacement_dish:ChangeSheetDish
  restriction_groups:ChangeSheetRestrictionGroup[]
  status:ChangeSheetHandlingStatus
  review_needed:boolean
  warnings:ChangeSheetWarning[]
}
export interface ChangeSheetReplacementGroup {
  group_id:string
  replacement_dish:ChangeSheetDish
  quantity:number
  case_rooms:string[]
  cases:ChangeSheetCaseSummary[]
  items:ChangeSheetReplacementItem[]
  note:string|null
  status:ChangeSheetHandlingStatus
  review_needed:boolean
  warnings:ChangeSheetWarning[]
}
export interface ChangeSheetAcknowledgement {
  handling_id:string
  case_id:string
  case_number:string
  case_name:string
  current_room:string
  original_menu_dish_id:string
  original_dish:ChangeSheetDish
  restriction_groups:ChangeSheetRestrictionGroup[]
  note:string|null
  status:ChangeSheetHandlingStatus
  review_needed:boolean
  warnings:ChangeSheetWarning[]
}
export interface ChangeSheetReconfirmationItem extends ChangeSheetAcknowledgement {
  handling_type:'replacement'|'manual_acknowledgement'
  group_id:string|null
  replacement_dish:ChangeSheetDish|null
}
export interface ChangeSheetResponse {
  target_date:string
  postpartum_meal:Meal
  meal_label:string
  summary:ChangeSheetSummary
  replacement_groups:ChangeSheetReplacementGroup[]
  manual_acknowledgements:ChangeSheetAcknowledgement[]
  requires_reconfirmation:ChangeSheetReconfirmationItem[]
  warnings:ChangeSheetWarning[]
}

export interface ChangeSheetMealResponse extends ChangeSheetResponse {has_changes:boolean}
export interface ChangeSheetDailyResponse {
  target_date:string
  summary:ChangeSheetSummary
  meals:ChangeSheetMealResponse[]
  warnings:ChangeSheetWarning[]
}

export interface ChangeSheetCaseItems {
  case_id:string
  case_number:string
  case_name:string
  current_room:string
  items:ChangeSheetReplacementItem[]
}

export function groupReplacementItemsByCase(groups:ReadonlyArray<ChangeSheetReplacementGroup>):ChangeSheetCaseItems[]{
  const cases=new Map<string,ChangeSheetCaseItems>()
  for(const group of groups){
    for(const item of group.items){
      const value=cases.get(item.case_id)??{
        case_id:item.case_id,case_number:item.case_number,case_name:item.case_name,
        current_room:item.current_room,items:[],
      }
      value.items.push(item);cases.set(item.case_id,value)
    }
  }
  return [...cases.values()]
}
