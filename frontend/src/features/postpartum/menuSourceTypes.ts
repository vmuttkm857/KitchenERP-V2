import type { Meal } from './types'

export interface MenuSourceMenu {id:string;name:string;start_date:string;end_date:string;is_active:boolean}
export interface MenuSourceMealType {id:string;name:string;sort_order:number;is_active:boolean}
export interface MenuSourceMapping {postpartum_meal:Meal;menu_meal_type:MenuSourceMealType}
export interface MenuSourceMealStatus {postpartum_meal:Meal;mapped:boolean;menu_meal_type:MenuSourceMealType|null}
export interface MenuSourceWarning {code:string;message:string;postpartum_meal:Meal|null}
export interface MenuSource {
  id:string
  configured:boolean
  usable:boolean
  menu:MenuSourceMenu
  mappings:MenuSourceMapping[]
  meal_statuses:MenuSourceMealStatus[]
  warnings:MenuSourceWarning[]
}
export interface MenuSourceList {items:MenuSource[]}

export function emptyMenuMappings(meals:readonly {value:string}[]){
  return Object.fromEntries(meals.map(item=>[item.value,''])) as Record<string,string>
}

export function menuMappingsValid(mappings:Record<string,string>){
  const values=Object.values(mappings).filter(Boolean)
  return values.length>0&&new Set(values).size===values.length
}

export function mealTypeUsedByOtherMeal(mappings:Record<string,string>,meal:string,mealTypeId:string){
  return Object.entries(mappings).some(([key,value])=>key!==meal&&value===mealTypeId)
}

export type CoverageStatus='configured'|'unconfigured'|'overlap'|'inactive'
export interface CoveragePeriod {index:number;start_date:string;end_date:string;status:CoverageStatus;sources:MenuSource[]}

function parseYmd(value:string){
  const [year,month,day]=value.split('-').map(Number)
  return new Date(year,month-1,day)
}
function ymd(value:Date){
  const year=value.getFullYear(),month=String(value.getMonth()+1).padStart(2,'0'),day=String(value.getDate()).padStart(2,'0')
  return `${year}-${month}-${day}`
}
function addDays(value:Date,days:number){const next=new Date(value);next.setDate(next.getDate()+days);return next}

export function monthRange(month:string){
  const [year,monthNumber]=month.split('-').map(Number)
  const start=new Date(year,monthNumber-1,1),end=new Date(year,monthNumber,0)
  return {start_date:ymd(start),end_date:ymd(end)}
}

export function nextMonthValue(month:string){
  const [year,monthNumber]=month.split('-').map(Number)
  const value=new Date(year,monthNumber,1)
  return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}`
}

export function buildMonthWeekSegments(sources:MenuSource[],month:string):CoveragePeriod[]{
  const range=monthRange(month),monthEnd=parseYmd(range.end_date)
  let cursor=parseYmd(range.start_date),index=1
  const periods:CoveragePeriod[]=[]
  while(cursor<=monthEnd){
    const daysToSunday=(7-cursor.getDay())%7
    const end=addDays(cursor,daysToSunday)>monthEnd?monthEnd:addDays(cursor,daysToSunday)
    const startDate=ymd(cursor),endDate=ymd(end)
    const matching=sources.filter(source=>source.menu.start_date<=endDate&&source.menu.end_date>=startDate)
    let status:CoverageStatus='unconfigured'
    if(matching.length>1)status='overlap'
    else if(matching.length===1&&!matching[0].menu.is_active)status='inactive'
    else if(matching.length===1)status='configured'
    periods.push({index,start_date:startDate,end_date:endDate,status,sources:matching})
    cursor=addDays(end,1);index+=1
  }
  return periods
}
