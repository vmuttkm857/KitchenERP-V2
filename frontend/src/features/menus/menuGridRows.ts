import type { MealType, MealTypeColumn, MenuDish, MenuSlot } from './types'

export interface MealGridRow { label:string; dishes:(MenuDish|null)[] }

function arrangeDishes(dishes:MenuDish[],columnIndexes:Map<string,number>):(MenuDish|null)[]{
  const ordered=[...dishes].sort((a,b)=>a.sort_order-b.sort_order||(a.id??a.dish_id).localeCompare(b.id??b.dish_id))
  const arranged:Array<MenuDish|null>=Array.from({length:columnIndexes.size},()=>null)
  const fallback:MenuDish[]=[]
  for(const dish of ordered){
    const assignedIndex=dish.menu_meal_type_column_id===null
      ? undefined
      : columnIndexes.get(dish.menu_meal_type_column_id)
    if(assignedIndex===undefined||arranged[assignedIndex]!==null) fallback.push(dish)
    else arranged[assignedIndex]=dish
  }
  for(const dish of fallback){
    const emptyIndex=arranged.indexOf(null)
    if(emptyIndex===-1) arranged.push(dish)
    else arranged[emptyIndex]=dish
  }
  return arranged
}

export function mealGridRows(
  dates:string[],meal:MealType,columns:MealTypeColumn[],slotFor:(date:string,meal:MealType)=>MenuSlot,
):MealGridRow[]{
  const labels=columns.filter(column=>column.menu_meal_type_id===meal.id)
    .sort((a,b)=>a.sort_order-b.sort_order||a.id.localeCompare(b.id))
  const slots=dates.map(date=>slotFor(date,meal))
  const columnIndexes=new Map(labels.map((column,index)=>[column.id,index]))
  const arrangedSlots=slots.map(slot=>arrangeDishes(slot.dishes,columnIndexes))
  const rowCount=Math.max(labels.length,...arrangedSlots.map(dishes=>dishes.length),1)
  return Array.from({length:rowCount},(_,index)=>({
    label:labels[index]?.name??'',
    dishes:arrangedSlots.map(dishes=>dishes[index]??null),
  }))
}
