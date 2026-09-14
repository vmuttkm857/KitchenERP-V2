import type { MealType, MealTypeColumn, MenuDish, MenuSlot } from './types'
import { arrangeMenuDishes } from './menuPlacement.js'

export interface MealGridRow { label:string; columnId:string|null; dishes:(MenuDish|null)[] }

export function mealGridRows(
  dates:string[],meal:MealType,columns:MealTypeColumn[],slotFor:(date:string,meal:MealType)=>MenuSlot,
):MealGridRow[]{
  const labels=columns.filter(column=>column.menu_meal_type_id===meal.id)
    .sort((a,b)=>a.sort_order-b.sort_order||a.id.localeCompare(b.id))
  const slots=dates.map(date=>slotFor(date,meal))
  const arrangedSlots=slots.map(slot=>arrangeMenuDishes(slot.dishes,labels))
  const rowCount=Math.max(labels.length,...arrangedSlots.map(dishes=>dishes.length),1)
  return Array.from({length:rowCount},(_,index)=>({
    label:labels[index]?.name??'',
    columnId:labels[index]?.id??null,
    dishes:arrangedSlots.map(dishes=>dishes[index]??null),
  }))
}
