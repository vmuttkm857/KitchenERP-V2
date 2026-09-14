import { arrangeMenuDishes } from './menuPlacement.js'
import type { MealTypeColumn, MenuDish, MenuSlot } from './types'

export interface MenuDishInsertTarget {
  targetDate:string
  targetMealTypeId:string
  insertIndex:number
  beforeMenuDishId:string|null
  afterMenuDishId:string|null
}

export function canInsertMenuDish(sourceId:string|null,target:MenuDishInsertTarget|null,moving=false){
  return !moving&&sourceId!==null&&target!==null&&target.insertIndex>=0
}

export function menuDishMovePayload(sourceMenuDishId:string,target:MenuDishInsertTarget){
  return {
    source_menu_dish_id:sourceMenuDishId,
    target_date:target.targetDate,
    target_meal_type_id:target.targetMealTypeId,
    insert_index:target.insertIndex,
    before_menu_dish_id:target.beforeMenuDishId,
    after_menu_dish_id:target.afterMenuDishId,
  }
}

const slotKey=(date:string,mealId:string)=>`${date}:${mealId}`
const slotsRecord=(slots:MenuSlot[])=>Object.fromEntries(slots.map(slot=>[slotKey(slot.menu_date,slot.menu_meal_type_id),slot]))
const orderedColumns=(columns:MealTypeColumn[],mealId:string)=>columns
  .filter(column=>column.menu_meal_type_id===mealId)
  .sort((a,b)=>a.sort_order-b.sort_order||a.id.localeCompare(b.id))

function persistRows(rows:Array<MenuDish|null>,columns:MealTypeColumn[]){
  let order=0
  return rows.flatMap((dish,index)=>{
    if(!dish)return []
    order+=1
    return [{...dish,menu_meal_type_column_id:columns[index]?.id??null,sort_order:order}]
  })
}

export function optimisticallyInsertMenuDish(
  slots:Record<string,MenuSlot>,columns:MealTypeColumn[],sourceId:string,target:MenuDishInsertTarget,
):Record<string,MenuSlot>|null{
  const sourceEntry=Object.entries(slots).find(([,slot])=>slot.dishes.some(dish=>dish.id===sourceId))
  if(!sourceEntry)return null
  const [sourceKey,sourceSlot]=sourceEntry
  const sourceDish=sourceSlot.dishes.find(dish=>dish.id===sourceId)
  if(!sourceDish)return null
  const targetKey=slotKey(target.targetDate,target.targetMealTypeId)
  const targetSlot=slots[targetKey]??{menu_date:target.targetDate,menu_meal_type_id:target.targetMealTypeId,notes:null,dishes:[]}
  if(sourceKey!==targetKey&&targetSlot.dishes.some(dish=>dish.dish_id===sourceDish.dish_id))return null
  const sourceColumns=orderedColumns(columns,sourceSlot.menu_meal_type_id)
  const targetColumns=orderedColumns(columns,target.targetMealTypeId)
  const sourceRows=arrangeMenuDishes(sourceSlot.dishes,sourceColumns)
  const targetRows=sourceKey===targetKey?sourceRows:arrangeMenuDishes(targetSlot.dishes,targetColumns)
  if(target.insertIndex>targetRows.length)return null
  const values=[...targetRows]
  const sourceIndex=sourceRows.findIndex(dish=>dish?.id===sourceId)
  if(sourceIndex<0)return null
  let insertIndex=target.insertIndex
  if(sourceKey===targetKey){
    if(insertIndex===sourceIndex||insertIndex===sourceIndex+1)return slots
    values.splice(sourceIndex,1);if(sourceIndex<insertIndex)insertIndex-=1
    while(values.length<Math.max(targetColumns.length,1))values.push(null)
  }
  if(insertIndex<values.length&&values[insertIndex]===null)values[insertIndex]=sourceDish
  else if(insertIndex>0&&values[insertIndex-1]===null)values[insertIndex-1]=sourceDish
  else values.splice(insertIndex,0,sourceDish)
  const required=Math.max(targetColumns.length,values.filter(Boolean).length,1)
  while(values.length>required&&values.at(-1)===null)values.pop()
  while(values.length<required)values.push(null)
  const next={...slots,[targetKey]:{...targetSlot,dishes:persistRows(values,targetColumns)}}
  if(sourceKey!==targetKey){
    const remaining=[...sourceRows];remaining.splice(sourceIndex,1)
    next[sourceKey]={...sourceSlot,dishes:remaining.filter((dish):dish is MenuDish=>dish!==null)
      .map((dish,index)=>({...dish,sort_order:index+1}))}
  }
  return next
}

function visualSlotValue(slot:MenuSlot){
  return {
    date:slot.menu_date,meal:slot.menu_meal_type_id,notes:slot.notes,
    dishes:[...slot.dishes].sort((a,b)=>a.sort_order-b.sort_order||(a.id??a.dish_id).localeCompare(b.id??b.dish_id))
      .map(dish=>({id:dish.id??null,column:dish.menu_meal_type_column_id,order:dish.sort_order,
        dishId:dish.dish_id,name:dish.dish_name??null,count:dish.diner_count,notes:dish.notes})),
  }
}

export function menuSlotsVisuallyEquivalent(current:Record<string,MenuSlot>,authoritative:MenuSlot[]){
  const server=slotsRecord(authoritative)
  const currentKeys=Object.keys(current).sort(),serverKeys=Object.keys(server).sort()
  if(currentKeys.length!==serverKeys.length||currentKeys.some((key,index)=>key!==serverKeys[index]))return false
  return currentKeys.every(key=>JSON.stringify(visualSlotValue(current[key]))===JSON.stringify(visualSlotValue(server[key])))
}

export function mergeAuthoritativeSlotMetadata(current:Record<string,MenuSlot>,authoritative:MenuSlot[]){
  let next=current
  for(const serverSlot of authoritative){
    const key=slotKey(serverSlot.menu_date,serverSlot.menu_meal_type_id),currentSlot=current[key]
    if(currentSlot&&currentSlot.menu_day_id!==serverSlot.menu_day_id){
      if(next===current)next={...current}
      next[key]={...currentSlot,menu_day_id:serverSlot.menu_day_id}
    }
  }
  return next
}
