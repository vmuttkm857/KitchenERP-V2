export type PaginationItem=number|'ellipsis'

export function paginationItems(currentPage:number,totalPages:number,windowSize=5):PaginationItem[]{
  if(totalPages<=windowSize+2)return Array.from({length:totalPages},(_,index)=>index+1)
  const half=Math.floor(windowSize/2)
  const start=Math.max(1,Math.min(currentPage-half,totalPages-windowSize+1))
  const window=Array.from({length:windowSize},(_,index)=>start+index)
  const pages=[1,...window,totalPages].filter((page,index,values)=>page>=1&&page<=totalPages&&values.indexOf(page)===index)
  const result:PaginationItem[]=[]
  for(const page of pages){
    const previous=result.at(-1)
    if(typeof previous==='number'&&page-previous>1)result.push('ellipsis')
    result.push(page)
  }
  return result
}

export function jumpPage(value:string,totalPages:number):number|null{
  if(!/^\d+$/.test(value.trim()))return null
  const page=Number(value)
  return Number.isSafeInteger(page)&&page>=1&&page<=totalPages?page:null
}
