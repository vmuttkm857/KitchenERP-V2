export interface Anomaly {
  code:string
  severity:'warning'|'error'
  message:string
  related_entity_id?:string|null
  related_entity_name?:string|null
  context?:Record<string,unknown>
}

export interface FormattedAnomaly {title:string;description:string}
export interface AnomalyGroup extends FormattedAnomaly {key:string;severity:'warning'|'error';count:number;items:Anomaly[]}

const contextText=(anomaly:Anomaly,key:string)=>typeof anomaly.context?.[key]==='string'?String(anomaly.context[key]):''
const identity=(anomaly:Anomaly)=>anomaly.related_entity_id||anomaly.related_entity_name||'unknown'
const entityLabel:Record<string,string>={menu:'菜單',meal_type:'餐別',dish:'菜色',ingredient:'食材',supplier:'供應商'}

export function formatAnomaly(anomaly:Anomaly):FormattedAnomaly{
  const name=anomaly.related_entity_name||'未命名資料'
  const dish=contextText(anomaly,'dish_name')
  const recipeUnit=contextText(anomaly,'recipe_unit')
  const baseUnit=contextText(anomaly,'base_unit')
  switch(anomaly.code){
    case 'INCOMPATIBLE_UNIT':return {title:'單位無法換算',description:`菜色「${dish||'未命名菜色'}」的食材「${name}」配方使用「${recipeUnit||'未知'}」，基本單位為「${baseUnit||'未知'}」。`}
    case 'MISSING_RECIPE':return {title:'缺少標準配方',description:`菜色「${name}」尚未建立配方。`}
    case 'MISSING_INGREDIENT':return {title:'配方食材不存在',description:`菜色「${dish||name}」的配方包含已不存在的食材關聯。`}
    case 'ZERO_RECIPE_QUANTITY':return {title:'配方數量未設定',description:`「${name}」的每人用量必須大於 0。`}
    case 'MISSING_PRICE':return {title:'未設定目前價格',description:`食材「${name}」尚未設定目前價格。`}
    case 'MISSING_SUPPLIER':return {title:'未設定供應商',description:`食材「${name}」尚未設定主要供應商。`}
    case 'INACTIVE_SOURCE':{
      const type=contextText(anomaly,'entity_type'),label=entityLabel[type]||'資料'
      return {title:'使用已停用資料',description:`${label}「${name}」已停用，歷史內容仍會納入計算。`}
    }
    case 'INACTIVE_MENU':return {title:'使用已停用資料',description:`菜單「${name}」已停用，排程內容仍會納入計算。`}
    case 'INACTIVE_MEAL_TYPE':return {title:'使用已停用資料',description:`餐別「${name}」已停用，排程內容仍會納入計算。`}
    case 'INACTIVE_DISH':return {title:'使用已停用資料',description:`菜色「${name}」已停用，排程內容仍會納入計算。`}
    case 'INACTIVE_INGREDIENT':return {title:'使用已停用資料',description:`食材「${name}」已停用，配方內容仍會納入計算。`}
    case 'NO_SCHEDULED_DISHES':return {title:'沒有排程內容',description:`「${name}」在目前條件下沒有可計算的排程菜色。`}
    default:return {title:'資料異常',description:anomaly.message||'發現尚未識別的資料問題。'}
  }
}

function groupKey(anomaly:Anomaly){
  const dish=contextText(anomaly,'dish_id')||contextText(anomaly,'dish_name')
  switch(anomaly.code){
    case 'INCOMPATIBLE_UNIT':return [anomaly.code,dish,identity(anomaly),contextText(anomaly,'recipe_unit'),contextText(anomaly,'base_unit')].join('|')
    case 'MISSING_SUPPLIER':case 'MISSING_PRICE':return [anomaly.code,identity(anomaly)].join('|')
    case 'MISSING_RECIPE':return [anomaly.code,identity(anomaly)].join('|')
    case 'INACTIVE_SOURCE':return [anomaly.code,contextText(anomaly,'entity_type'),identity(anomaly)].join('|')
    case 'INACTIVE_MENU':case 'INACTIVE_MEAL_TYPE':case 'INACTIVE_DISH':case 'INACTIVE_INGREDIENT':return [anomaly.code,identity(anomaly)].join('|')
    case 'MISSING_INGREDIENT':case 'ZERO_RECIPE_QUANTITY':return [anomaly.code,identity(anomaly),dish].join('|')
    case 'NO_SCHEDULED_DISHES':return [anomaly.code,identity(anomaly)].join('|')
    default:return [anomaly.code,identity(anomaly),anomaly.message].join('|')
  }
}

export function groupAnomalies(anomalies:Anomaly[]):AnomalyGroup[]{
  const groups=new Map<string,AnomalyGroup>()
  for(const anomaly of anomalies){
    const key=`${anomaly.severity}|${groupKey(anomaly)}`,existing=groups.get(key)
    if(existing){existing.count+=1;existing.items.push(anomaly);continue}
    groups.set(key,{key,severity:anomaly.severity,count:1,items:[anomaly],...formatAnomaly(anomaly)})
  }
  return [...groups.values()]
}

export function anomalySummary(groups:AnomalyGroup[]){
  const errors=groups.filter(group=>group.severity==='error'),warnings=groups.filter(group=>group.severity==='warning')
  const affected=errors.reduce((total,group)=>total+group.count,0)
  return `${errors.length} 個問題${affected?`（影響 ${affected} 筆）`:''}／${warnings.length} 個提醒`
}
