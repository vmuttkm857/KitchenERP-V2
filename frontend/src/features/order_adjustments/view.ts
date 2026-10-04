import type { OrderingAdjustmentCriteria,OrderingAdjustmentLine,OrderingAdjustmentStatus,OrderingAdjustmentSummary } from './types'

export const adjustmentStatusLabels:Record<OrderingAdjustmentStatus,string>={draft:'草稿',confirmed:'已確認',cancelled:'已取消'}

export function adjustmentDateRange(criteria:OrderingAdjustmentCriteria,summary?:Pick<OrderingAdjustmentSummary,'source_menus'>){
  if(criteria.selected_dates?.length){const dates=[...criteria.selected_dates].sort();return dates.length===1?dates[0]:`${dates[0]}～${dates[dates.length-1]}`}
  if(criteria.start_date&&criteria.end_date)return `${criteria.start_date}～${criteria.end_date}`
  const menus=summary?.source_menus??[]
  if(!menus.length)return '全部菜單日期'
  const starts=menus.map(menu=>menu.start_date).sort(),ends=menus.map(menu=>menu.end_date).sort()
  return `${starts[0]}～${ends[ends.length-1]}`
}

export function formatAdjustmentQuantity(value:string){
  const normalized=value.trim()
  if(!/^-?\d+(\.\d+)?$/.test(normalized))return normalized
  return normalized.includes('.')?normalized.replace(/0+$/,'').replace(/\.$/,''):normalized
}

export interface AdjustmentDishGroup {id:string;name:string;code:string;dinerCount:number;lines:OrderingAdjustmentLine[]}
export interface AdjustmentMealGroup {id:string;name:string;dishes:AdjustmentDishGroup[]}
export interface AdjustmentDateGroup {date:string;meals:AdjustmentMealGroup[]}
export interface AdjustmentMenuGroup {id:string;name:string;dates:AdjustmentDateGroup[]}

export function groupAdjustmentLines(lines:OrderingAdjustmentLine[]):AdjustmentMenuGroup[]{
  const menus:AdjustmentMenuGroup[]=[]
  for(const line of lines){
    let menu=menus.find(value=>value.id===line.source_menu_id)
    if(!menu){menu={id:line.source_menu_id,name:line.menu_name_snapshot,dates:[]};menus.push(menu)}
    let day=menu.dates.find(value=>value.date===line.requirement_date)
    if(!day){day={date:line.requirement_date,meals:[]};menu.dates.push(day)}
    let meal=day.meals.find(value=>value.id===line.source_meal_type_id)
    if(!meal){meal={id:line.source_meal_type_id,name:line.meal_type_name_snapshot,dishes:[]};day.meals.push(meal)}
    let dish=meal.dishes.find(value=>value.id===line.source_menu_dish_id)
    if(!dish){dish={id:line.source_menu_dish_id,name:line.dish_name_snapshot,code:line.dish_code_snapshot,dinerCount:line.diner_count_snapshot,lines:[]};meal.dishes.push(dish)}
    dish.lines.push(line)
  }
  return menus
}

const staleReasonLabels:Record<string,string>={
  DINER_COUNT_CHANGED:'供餐人數已變更',RECIPE_QUANTITY_CHANGED:'配方用量已變更',LOSS_RATE_CHANGED:'耗損率已變更',
  SUPPLIER_CHANGED:'供應商已變更',UNIT_CHANGED:'單位設定已變更',MENU_DISH_MOVED:'菜色日期或餐別已移動',
  DISH_CHANGED:'菜色已替換',INGREDIENT_CHANGED:'配方食材已變更',PURCHASING_DATA_CHANGED:'採購設定或價格已變更',
  SOURCE_QUANTITY_CHANGED:'系統計算量已變更',SOURCE_REMOVED:'原始配方項目已不存在',SOURCE_CHANGED:'來源資料已變更',
  SOURCE_FINGERPRINT_CHANGED:'菜單、配方或採購來源資料已變更',NEW_SOURCE_LINE:'目前來源新增了食材項目',
}
export function staleReasonLabel(code:string){return staleReasonLabels[code]??'來源資料已變更'}
