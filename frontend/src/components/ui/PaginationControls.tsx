import { FormEvent,useEffect,useState } from 'react'
import { totalPages } from '../../utils/listQuery'
import { jumpPage,paginationItems } from './pagination'

export function PaginationControls({page,pageSize,total,onPage,onPageSize,pageSizes=[25,50,100],disabled=false}:{page:number;pageSize:number;total:number;onPage:(page:number)=>void;onPageSize?:(size:number)=>void;pageSizes?:number[];disabled?:boolean}){
  const pages=totalPages(total,pageSize)
  const [target,setTarget]=useState(''),[invalid,setInvalid]=useState(false)
  useEffect(()=>{setTarget('');setInvalid(false)},[page,pages])
  function submit(event:FormEvent){event.preventDefault();const next=jumpPage(target,pages);if(next===null){setInvalid(true);return}setInvalid(false);onPage(next)}
  return <nav className="pagination-controls" aria-label="分頁導覽">
    <span className="pagination-summary">共 {total} 筆／第 {page} 頁，共 {pages} 頁</span>
    {onPageSize&&<label className="pagination-page-size">每頁<select value={pageSize} disabled={disabled} onChange={event=>onPageSize(Number(event.target.value))}>{pageSizes.map(size=><option key={size} value={size}>{size}</option>)}</select></label>}
    <div className="pagination-pages">
      <button type="button" className="secondary" disabled={disabled||page<=1} onClick={()=>onPage(1)}>第一頁</button>
      <button type="button" className="secondary" disabled={disabled||page<=1} onClick={()=>onPage(page-1)}>上一頁</button>
      {paginationItems(page,pages).map((item,index)=>item==='ellipsis'
        ? <span className="pagination-ellipsis" aria-hidden="true" key={`ellipsis-${index}`}>…</span>
        : <button type="button" className={`pagination-page${item===page?' is-active':''}`} aria-current={item===page?'page':undefined} disabled={disabled} key={item} onClick={()=>onPage(item)}>{item}</button>)}
      <button type="button" className="secondary" disabled={disabled||page>=pages} onClick={()=>onPage(page+1)}>下一頁</button>
      <button type="button" className="secondary" disabled={disabled||page>=pages} onClick={()=>onPage(pages)}>最後一頁</button>
    </div>
    <form className="pagination-jump" onSubmit={submit} noValidate><label>跳至<input aria-label="跳至頁碼" inputMode="numeric" value={target} onChange={event=>{setTarget(event.target.value);setInvalid(false)}}/></label><span>頁</span><button type="submit" className="secondary" disabled={disabled}>前往</button>{invalid&&<small className="error" role="alert">請輸入 1～{pages} 的整數頁碼</small>}</form>
  </nav>
}
