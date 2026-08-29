export interface DailyRequirementRow {
  requirement_date:string
  menu_id:string
  menu_name:string
  supplier_id:string|null
  supplier_code:string|null
  supplier_name:string|null
  ingredient_id:string
  ingredient_code:string
  ingredient_name:string
  quantity:string
  unit:string
}

export interface MenuDailyGroup {menu_id:string;menu_name:string;rows:DailyRequirementRow[]}
export interface SecondaryDailyGroup {key:string;label:string;menus:MenuDailyGroup[]}
export interface PrimaryDailyGroup {key:string;label:string;groups:SecondaryDailyGroup[]}
export interface SupplierOption {key:string;label:string}

function safeCell(value:string){return value.replace(/[\t\r\n]+/g,' ')}
function plainClipboardDecimal(value:string){const normalized=value.trim();if(!/^-?\d+(\.\d+)?$/.test(normalized))return normalized;const result=normalized.includes('.')?normalized.replace(/0+$/,'').replace(/\.$/,''):normalized;return result==='-0'?'0':result}
export function buildTsv(headers:string[],rows:string[][]){return [headers,...rows].map(row=>row.map(safeCell).join('\t')).join('\n')}
export function sortDailyRows(rows:DailyRequirementRow[],mode:'daily'|'supplier'){
  return [...rows].sort((a,b)=>{
    const supplier=(a.supplier_name??'未指定供應商').localeCompare(b.supplier_name??'未指定供應商','zh-TW')||(a.supplier_id??'unassigned').localeCompare(b.supplier_id??'unassigned')
    const date=a.requirement_date.localeCompare(b.requirement_date)
    const menu=a.menu_name.localeCompare(b.menu_name,'zh-TW')||a.menu_id.localeCompare(b.menu_id)
    const ingredient=a.ingredient_code.localeCompare(b.ingredient_code)||a.ingredient_name.localeCompare(b.ingredient_name,'zh-TW')||a.unit.localeCompare(b.unit)
    return mode==='daily'?date||menu||supplier||ingredient:supplier||date||menu||ingredient
  })
}
export function dailyRowsTsv(rows:DailyRequirementRow[],mode:'daily'|'supplier'){
  const headers=mode==='daily'?['使用日期','菜單','供應商','食材編號','食材','需求量','單位']:['供應商','使用日期','菜單','食材編號','食材','需求量','單位']
  const values=sortDailyRows(rows,mode).map(row=>mode==='daily'?[row.requirement_date,row.menu_name,row.supplier_name??'未指定供應商',row.ingredient_code,row.ingredient_name,plainClipboardDecimal(row.quantity),row.unit]:[row.supplier_name??'未指定供應商',row.requirement_date,row.menu_name,row.ingredient_code,row.ingredient_name,plainClipboardDecimal(row.quantity),row.unit])
  return buildTsv(headers,values)
}
export function supplierOptions(rows:DailyRequirementRow[]):SupplierOption[]{const options=new Map<string,string>();for(const row of rows)options.set(supplierKey(row),supplierLabel(row));return [...options.entries()].map(([key,label])=>({key,label})).sort((a,b)=>a.label.localeCompare(b.label,'zh-TW')||a.key.localeCompare(b.key))}
export function filterSupplierRows(rows:DailyRequirementRow[],key:string){return sortDailyRows(rows.filter(row=>supplierKey(row)===key),'daily')}
export function supplierRowsTsv(rows:DailyRequirementRow[],key:string){return buildTsv(['使用日期','菜單','食材編號','食材','需求量','單位'],filterSupplierRows(rows,key).map(row=>[row.requirement_date,row.menu_name,row.ingredient_code,row.ingredient_name,plainClipboardDecimal(row.quantity),row.unit]))}

function supplierKey(row:DailyRequirementRow){return row.supplier_id??'unassigned'}
function supplierLabel(row:DailyRequirementRow){return row.supplier_name??'未指定供應商'}
function rowsByMenu(rows:DailyRequirementRow[]){
  const menus=new Map<string,MenuDailyGroup>()
  for(const row of rows){const group=menus.get(row.menu_id)??{menu_id:row.menu_id,menu_name:row.menu_name,rows:[]};group.rows.push(row);menus.set(row.menu_id,group)}
  return [...menus.values()].sort((a,b)=>a.menu_name.localeCompare(b.menu_name,'zh-TW')||a.menu_id.localeCompare(b.menu_id)).map(group=>({...group,rows:group.rows.sort((a,b)=>a.ingredient_code.localeCompare(b.ingredient_code)||a.unit.localeCompare(b.unit))}))
}

export function groupDailyByDate(rows:DailyRequirementRow[]):PrimaryDailyGroup[]{
  const dates=new Map<string,DailyRequirementRow[]>()
  for(const row of rows)dates.set(row.requirement_date,[...(dates.get(row.requirement_date)??[]),row])
  return [...dates.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([date,dateRows])=>{
    const suppliers=new Map<string,DailyRequirementRow[]>()
    for(const row of dateRows)suppliers.set(supplierKey(row),[...(suppliers.get(supplierKey(row))??[]),row])
    return {key:date,label:date,groups:[...suppliers.entries()].map(([key,supplierRows])=>({key,label:supplierLabel(supplierRows[0]),menus:rowsByMenu(supplierRows)})).sort((a,b)=>a.label.localeCompare(b.label,'zh-TW')||a.key.localeCompare(b.key))}
  })
}

export function groupDailyBySupplier(rows:DailyRequirementRow[]):PrimaryDailyGroup[]{
  const suppliers=new Map<string,DailyRequirementRow[]>()
  for(const row of rows)suppliers.set(supplierKey(row),[...(suppliers.get(supplierKey(row))??[]),row])
  return [...suppliers.entries()].map(([key,supplierRows])=>{
    const dates=new Map<string,DailyRequirementRow[]>()
    for(const row of supplierRows)dates.set(row.requirement_date,[...(dates.get(row.requirement_date)??[]),row])
    return {key,label:supplierLabel(supplierRows[0]),groups:[...dates.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([date,dateRows])=>({key:date,label:date,menus:rowsByMenu(dateRows)}))}
  }).sort((a,b)=>a.label.localeCompare(b.label,'zh-TW')||a.key.localeCompare(b.key))
}
