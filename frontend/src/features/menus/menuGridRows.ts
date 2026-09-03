import type { MealType, MealTypeColumn, MenuDish, MenuSlot } from './types'

export interface MealGridRow { label:string; dishes:(MenuDish|null)[] }

export function mealGridRows(
  dates:string[],meal:MealType,columns:MealTypeColumn[],slotFor:(date:string,meal:MealType)=>MenuSlot,
):MealGridRow[]{
  const labels=columns.filter(column=>column.menu_meal_type_id===meal.id)
    .sort((a,b)=>a.sort_order-b.sort_order||a.id.localeCompare(b.id))
  const slots=dates.map(date=>slotFor(date,meal))
  const rowCount=Math.max(labels.length,...slots.map(slot=>slot.dishes.length),1)
  return Array.from({length:rowCount},(_,index)=>({
    label:labels[index]?.name??'',
    dishes:slots.map(slot=>slot.dishes[index]??null),
  }))
}
