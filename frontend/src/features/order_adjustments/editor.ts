import type {OrderingAdjustmentLine,OrderingAdjustmentLineUpdate} from './types'

export function normalizeDecimalString(value:string){
  const trimmed=value.trim()
  const match=/^(\d+)(?:\.(\d+))?$/.exec(trimmed)
  if(!match)return null
  const integer=match[1].replace(/^0+(?=\d)/,'')||'0'
  const fraction=(match[2]??'').replace(/0+$/,'')
  return fraction?`${integer}.${fraction}`:integer
}

export function decimalStringsEqual(left:string,right:string){
  const normalizedLeft=normalizeDecimalString(left),normalizedRight=normalizeDecimalString(right)
  return normalizedLeft!==null&&normalizedRight!==null&&normalizedLeft===normalizedRight
}

export function editableDecimalString(value:string){return normalizeDecimalString(value)??value.trim()}

export function validateAdjustmentQuantity(value:string){
  const trimmed=value.trim()
  if(!trimmed)return '請輸入實際叫貨量'
  if(trimmed.startsWith('-'))return '不可小於 0'
  if(!/^\d+(?:\.\d+)?$/.test(trimmed))return '請輸入有效的小數'
  const [integer,fraction='']=trimmed.split('.')
  if(integer.replace(/^0+(?=\d)/,'').length>12)return '整數部分最多 12 位'
  if(fraction.length>6)return '最多 6 位小數'
  return null
}

export function initialAdjustmentValues(lines:OrderingAdjustmentLine[]){
  return Object.fromEntries(lines.map(line=>[line.id,editableDecimalString(line.adjusted_quantity??line.system_quantity)]))
}

export function dirtyAdjustmentLineIds(lines:OrderingAdjustmentLine[],values:Record<string,string>){
  return lines.filter(line=>!decimalStringsEqual(values[line.id]??'',line.adjusted_quantity??line.system_quantity)).map(line=>line.id)
}

export function buildAdjustmentUpdates(lines:OrderingAdjustmentLine[],values:Record<string,string>):OrderingAdjustmentLineUpdate[]{
  const dirty=new Set(dirtyAdjustmentLineIds(lines,values))
  return lines.filter(line=>dirty.has(line.id)).map(line=>({
    id:line.id,
    adjusted_quantity:decimalStringsEqual(values[line.id]??'',line.system_quantity)?null:(values[line.id]??'').trim(),
  }))
}
