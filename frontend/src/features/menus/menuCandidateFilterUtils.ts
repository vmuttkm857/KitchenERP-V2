export function menuMonthRange(month:string){
  if(!/^\d{4}-\d{2}$/.test(month))return {startDate:undefined,endDate:undefined}
  const [year,monthNumber]=month.split('-').map(Number)
  if(monthNumber<1||monthNumber>12)return {startDate:undefined,endDate:undefined}
  const lastDay=new Date(Date.UTC(year,monthNumber,0)).getUTCDate()
  return {startDate:`${month}-01`,endDate:`${month}-${String(lastDay).padStart(2,'0')}`}
}
