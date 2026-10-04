import type {MealTypeColumn,MenuAggregate} from '../menus/types'
import type {OrderingAdjustmentCriteria,OrderingAdjustmentLine,OrderingAdjustmentSourceMenu} from './types'

export interface AdjustmentMatrixDish {id:string;name:string;dinerCount:number;sortOrder:number;columnId:string|null;lines:OrderingAdjustmentLine[]}
export interface AdjustmentMatrixRow {label:string;columnId:string|null;cells:Record<string,AdjustmentMatrixDish[]>}
export interface AdjustmentMatrixMeal {id:string;name:string;sortOrder:number;rows:AdjustmentMatrixRow[]}
export interface AdjustmentMenuMatrix {menuId:string;menuName:string;dates:string[];meals:AdjustmentMatrixMeal[]}

function dishGroups(lines:OrderingAdjustmentLine[]){
  const dishes:AdjustmentMatrixDish[]=[]
  for(const line of lines){
    let dish=dishes.find(value=>value.id===line.source_menu_dish_id)
    if(!dish){dish={id:line.source_menu_dish_id,name:line.dish_name_snapshot,dinerCount:line.diner_count_snapshot,sortOrder:line.menu_dish_sort_order_snapshot,columnId:line.source_menu_meal_type_column_id,lines:[]};dishes.push(dish)}
    dish.lines.push(line)
  }
  for(const dish of dishes)dish.lines.sort((left,right)=>left.dish_ingredient_sort_order_snapshot-right.dish_ingredient_sort_order_snapshot)
  return dishes.sort((left,right)=>left.sortOrder-right.sortOrder)
}

function snapshotColumns(lines:OrderingAdjustmentLine[],mealId:string):MealTypeColumn[]{
  const result:MealTypeColumn[]=[]
  for(const line of lines){
    if(line.source_meal_type_id!==mealId||!line.source_menu_meal_type_column_id||result.some(column=>column.id===line.source_menu_meal_type_column_id))continue
    const order=line.menu_meal_type_column_sort_order_snapshot??Number.MAX_SAFE_INTEGER
    result.push({id:line.source_menu_meal_type_column_id,menu_meal_type_id:mealId,name:`菜單欄位 ${order===Number.MAX_SAFE_INTEGER?'':order}`.trim(),sort_order:order})
  }
  return result.sort((left,right)=>left.sort_order-right.sort_order)
}

function includedDates(criteria:OrderingAdjustmentCriteria,menu:OrderingAdjustmentSourceMenu,layout?:MenuAggregate){
  if(criteria.selected_dates?.length)return [...criteria.selected_dates].filter(date=>date>=menu.start_date&&date<=menu.end_date).sort()
  const start=criteria.start_date&&criteria.start_date>menu.start_date?criteria.start_date:menu.start_date
  const end=criteria.end_date&&criteria.end_date<menu.end_date?criteria.end_date:menu.end_date
  if(start>end)return []
  const dates:string[]=[];const cursor=new Date(`${start}T00:00:00Z`),last=new Date(`${end}T00:00:00Z`)
  while(cursor<=last){dates.push(cursor.toISOString().slice(0,10));cursor.setUTCDate(cursor.getUTCDate()+1)}
  return dates.length?dates:layout?.dates??[]
}

export function buildAdjustmentMenuMatrix(allLines:OrderingAdjustmentLine[],menu:OrderingAdjustmentSourceMenu,layout:MenuAggregate|undefined,criteria:OrderingAdjustmentCriteria):AdjustmentMenuMatrix{
  const lines=allLines.filter(line=>line.source_menu_id===menu.menu_id)
  const dates=includedDates(criteria,menu,layout)
  const mealSeeds:AdjustmentMatrixMeal[]=[]
  for(const meal of [...(layout?.meal_types??[])].sort((left,right)=>left.sort_order-right.sort_order))mealSeeds.push({id:meal.id,name:meal.name,sortOrder:meal.sort_order,rows:[]})
  for(const line of lines){
    if(!mealSeeds.some(meal=>meal.id===line.source_meal_type_id))mealSeeds.push({id:line.source_meal_type_id,name:line.meal_type_name_snapshot,sortOrder:line.meal_type_sort_order_snapshot,rows:[]})
  }
  mealSeeds.sort((left,right)=>left.sortOrder-right.sortOrder)
  for(const meal of mealSeeds){
    const currentColumns=(layout?.meal_type_columns??[]).filter(column=>column.menu_meal_type_id===meal.id).sort((left,right)=>left.sort_order-right.sort_order)
    const columns=currentColumns.length?currentColumns:snapshotColumns(lines,meal.id)
    meal.rows=columns.map(column=>({label:column.name,columnId:column.id,cells:{}}))
    const columnIndex=new Map(columns.map((column,index)=>[column.id,index]))
    for(const date of dates){
      const dishes=dishGroups(lines.filter(line=>line.source_meal_type_id===meal.id&&line.requirement_date===date))
      const fallback:AdjustmentMatrixDish[]=[]
      for(const dish of dishes){
        const index=dish.columnId?columnIndex.get(dish.columnId):undefined
        if(index===undefined)fallback.push(dish)
        else (meal.rows[index].cells[date]??=[]).push(dish)
      }
      for(const dish of fallback){
        let row=meal.rows.find(value=>(value.cells[date]?.length??0)===0)
        if(!row){row={label:'',columnId:null,cells:{}};meal.rows.push(row)}
        row.cells[date]=[dish]
      }
    }
    if(!meal.rows.length)meal.rows.push({label:'',columnId:null,cells:{}})
  }
  return {menuId:menu.menu_id,menuName:menu.menu_name,dates,meals:mealSeeds}
}
