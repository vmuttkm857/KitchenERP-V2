export function formatProductionNumber(value:string|number|null|undefined){
  if(value===null||value===undefined||value==='')return '—'
  const number=Number(value)
  return Number.isFinite(number)?number.toLocaleString('zh-TW',{maximumFractionDigits:6}):String(value)
}

export type DurationUnit='seconds'|'minutes'|'hours'

export function durationToInput(seconds:number|null):{value:string;unit:DurationUnit}{
  if(!seconds)return {value:'',unit:'minutes'}
  if(seconds%3600===0)return {value:String(seconds/3600),unit:'hours'}
  if(seconds%60===0)return {value:String(seconds/60),unit:'minutes'}
  return {value:String(seconds),unit:'seconds'}
}

export function durationFromInput(value:string,unit:DurationUnit){
  if(!value)return null
  const amount=Number(value)
  if(!Number.isFinite(amount)||amount<0)return null
  return Math.round(amount*(unit==='hours'?3600:unit==='minutes'?60:1))
}

export function formatDuration(seconds:number|null){
  if(!seconds)return '未設定時間'
  const hours=Math.floor(seconds/3600),minutes=Math.floor((seconds%3600)/60),rest=seconds%60
  return [hours&&`${hours} 小時`,minutes&&`${minutes} 分鐘`,rest&&`${rest} 秒`].filter(Boolean).join(' ')
}

export function aggregateBatches(batches:{serving_count:number;official:boolean}[]){
  const groups=new Map<string,{serving_count:number;official:boolean;count:number}>()
  for(const batch of batches){
    const key=`${batch.serving_count}-${batch.official}`
    const current=groups.get(key)
    groups.set(key,current?{...current,count:current.count+1}:{...batch,count:1})
  }
  return [...groups.values()]
}
