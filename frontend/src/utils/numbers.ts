const quantityFormatter=new Intl.NumberFormat('zh-TW',{maximumFractionDigits:6})
const moneyFormatter=new Intl.NumberFormat('zh-TW',{maximumFractionDigits:2})

export function formatQuantity(value:string|null|undefined){if(value===null||value===undefined)return '—';const number=Number(value);return Number.isFinite(number)?quantityFormatter.format(number):value}
export function formatMoney(value:string|null|undefined){if(value===null||value===undefined)return '—';const number=Number(value);return Number.isFinite(number)?moneyFormatter.format(number):value}
export function plainDecimal(value:string){
  const normalized=value.trim()
  if(!/^-?\d+(\.\d+)?$/.test(normalized))return normalized
  const result=normalized.includes('.')?normalized.replace(/0+$/,'').replace(/\.$/,''):normalized
  return result==='-0'?'0':result
}
export function addDecimals(values:string[]){
  const parsed=values.map(value=>{const [whole,fraction='']=value.split('.');return {whole,fraction}})
  const scale=Math.max(0,...parsed.map(value=>value.fraction.length))
  const total=parsed.reduce((sum,value)=>sum+BigInt(`${value.whole}${value.fraction.padEnd(scale,'0')}`),0n)
  const negative=total<0n;const digits=(negative?-total:total).toString().padStart(scale+1,'0')
  const result=scale?`${digits.slice(0,-scale)}.${digits.slice(-scale)}`:digits
  return plainDecimal(`${negative?'-':''}${result}`)
}
