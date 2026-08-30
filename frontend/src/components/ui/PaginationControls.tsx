import { totalPages } from '../../utils/listQuery'

export function PaginationControls({page,pageSize,total,onPage,onPageSize,pageSizes=[25,50,100]}:{page:number;pageSize:number;total:number;onPage:(page:number)=>void;onPageSize?:(size:number)=>void;pageSizes?:number[]}){
  const pages=totalPages(total,pageSize)
  return <div className="toolbar pagination-controls"><span>共 {total} 筆／第 {page} 頁，共 {pages} 頁</span>{onPageSize&&<label>每頁<select value={pageSize} onChange={event=>onPageSize(Number(event.target.value))}>{pageSizes.map(size=><option key={size} value={size}>{size}</option>)}</select></label>}<button type="button" className="secondary" disabled={page<=1} onClick={()=>onPage(page-1)}>上一頁</button><button type="button" className="secondary" disabled={page>=pages} onClick={()=>onPage(page+1)}>下一頁</button></div>
}
