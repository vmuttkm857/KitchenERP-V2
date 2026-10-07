import type {MenuImportGridLine,MenuImportLayoutRow} from './menuImportTypes'

export interface MenuImportGridRow {
  key:string
  mealName:string
  mealSortOrder:number
  columnName:string
  columnSortOrder:number
  cells:(MenuImportGridLine|null)[]
}

function dateRange(start:string,end:string){
  const dates:string[]=[]
  const current=new Date(`${start}T00:00:00Z`)
  const last=new Date(`${end}T00:00:00Z`)
  while(current<=last){dates.push(current.toISOString().slice(0,10));current.setUTCDate(current.getUTCDate()+1)}
  return dates
}

export function menuImportDates(start:string,end:string){return dateRange(start,end)}

export function menuImportGridRows(lines:MenuImportGridLine[],dates:string[],layout:MenuImportLayoutRow[]=[]):MenuImportGridRow[]{
  const byRow=new Map<string,{mealName:string;mealSortOrder:number;columnName:string;columnSortOrder:number;byDate:Map<string,MenuImportGridLine>}>()
  for(const row of layout){
    const key=`${row.meal_sort_order}\u0000${row.meal_name}\u0000${row.column_sort_order}\u0000${row.column_name}`
    byRow.set(key,{mealName:row.meal_name,mealSortOrder:row.meal_sort_order,columnName:row.column_name,columnSortOrder:row.column_sort_order,byDate:new Map()})
  }
  for(const line of lines){
    const key=`${line.meal_sort_order}\u0000${line.meal_name}\u0000${line.column_sort_order}\u0000${line.column_name}`
    const current=byRow.get(key)??{mealName:line.meal_name,mealSortOrder:line.meal_sort_order,columnName:line.column_name,columnSortOrder:line.column_sort_order,byDate:new Map()}
    current.byDate.set(line.date,line);byRow.set(key,current)
  }
  return [...byRow.entries()].sort(([,a],[,b])=>a.mealSortOrder-b.mealSortOrder||a.columnSortOrder-b.columnSortOrder||a.mealName.localeCompare(b.mealName,'zh-TW')||a.columnName.localeCompare(b.columnName,'zh-TW')).map(([key,row])=>({
    key,mealName:row.mealName,mealSortOrder:row.mealSortOrder,columnName:row.columnName,columnSortOrder:row.columnSortOrder,cells:dates.map(date=>row.byDate.get(date)??null),
  }))
}

export function menuImportStatus(line:MenuImportGridLine){return 'resolution_status'in line?line.resolution_status:line.status}
