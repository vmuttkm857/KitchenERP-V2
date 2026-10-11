import { useEffect,useState } from 'react'
import { apiRequest } from '../../api/client'
import type { Menu } from './types'
export { menuMonthRange } from './menuCandidateFilterUtils'

interface MenuCategory { id:string; name:string; is_active:boolean }
interface CategoryList { items:MenuCategory[] }

export function MenuCandidateFilters({month,onMonth,categoryId,onCategoryId,search,onSearch}:{month:string;onMonth:(value:string)=>void;categoryId:string;onCategoryId:(value:string)=>void;search:string;onSearch:(value:string)=>void}){
  const [categories,setCategories]=useState<MenuCategory[]>([]),[categoryError,setCategoryError]=useState('')
  useEffect(()=>{let active=true;void apiRequest<CategoryList>('/categories/menu?active=true&page_size=100').then(data=>{if(active){setCategories(data.items);setCategoryError('')}}).catch(()=>{if(active)setCategoryError('菜單類型載入失敗，仍可使用月份與名稱篩選。')});return()=>{active=false}},[])
  const hasFilters=Boolean(month||categoryId||search.trim())
  return <div className="menu-candidate-filter-panel" aria-label="菜單篩選">
    <label>菜單日期<div className="menu-month-filter"><input type="month" value={month} onChange={event=>onMonth(event.target.value)}/><button type="button" className={!month?'':'secondary'} aria-pressed={!month} onClick={()=>onMonth('')}>全部日期</button></div></label>
    <label>菜單類型<select value={categoryId} onChange={event=>onCategoryId(event.target.value)}><option value="">全部類型</option>{categories.map(category=><option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
    <label>菜單名稱<input value={search} onChange={event=>onSearch(event.target.value)} placeholder="輸入菜單名稱"/></label>
    <button type="button" className="secondary menu-filter-clear" disabled={!hasFilters} onClick={()=>{onMonth('');onCategoryId('');onSearch('')}}>清除篩選</button>
    {categoryError&&<small className="error">{categoryError}</small>}
  </div>
}

export function MenuCandidateOption({menu,checked,onToggle}:{menu:Menu;checked:boolean;onToggle:()=>void}){
  return <label className="inline-check menu-candidate-option">
    <input type="checkbox" checked={checked} onChange={onToggle}/>
    <span className="menu-candidate-copy"><strong className="menu-candidate-name">{menu.name}</strong><small className="menu-candidate-meta"><span>{menu.category_name||'未分類'}</span><span>{menu.start_date}～{menu.end_date}</span>{!menu.is_active&&<span className="menu-candidate-inactive">停用</span>}</small></span>
  </label>
}
