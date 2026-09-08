const dayMilliseconds=86_400_000

function dateOnlyMilliseconds(value:string){
  const [year,month,day]=value.split('-').map(Number)
  return Date.UTC(year,month-1,day)
}

function formatDateOnly(milliseconds:number){return new Date(milliseconds).toISOString().slice(0,10)}

export function postpartumWeekRanges(deliveryDate:string){
  const start=dateOnlyMilliseconds(deliveryDate)
  return Array.from({length:4},(_,index)=>({
    week:index+1,
    from:formatDateOnly(start+index*7*dayMilliseconds),
    to:formatDateOnly(start+(index*7+6)*dayMilliseconds),
  }))
}

export function postpartumWeek(deliveryDate:string,today=new Date()){
  const current=Date.UTC(today.getFullYear(),today.getMonth(),today.getDate())
  const days=Math.floor((current-dateOnlyMilliseconds(deliveryDate))/dayMilliseconds)
  if(days<0)return '尚未生產'
  if(days>=28)return '第 4 週後'
  return `第 ${Math.floor(days/7)+1} 週`
}
