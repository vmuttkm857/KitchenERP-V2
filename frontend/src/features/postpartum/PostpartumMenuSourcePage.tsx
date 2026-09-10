import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiRequest } from '../../api/client'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { useMenuCandidates } from '../menus/useMenuCandidates'
import type { MealType } from '../menus/types'
import { POSTPARTUM_MEALS } from './types'
import {
  buildMonthWeekSegments, emptyMenuMappings, mealTypeUsedByOtherMeal, menuMappingsValid, monthRange, nextMonthValue,
  type MenuSource, type MenuSourceList, type MenuSourceMenu,
} from './menuSourceTypes'

const statusLabels={configured:'已設定',unconfigured:'尚未設定',overlap:'日期重疊',inactive:'來源已停用'} as const
const todayYmd=()=>{
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date())
  const value=Object.fromEntries(parts.map(part=>[part.type,part.value]))
  return `${value.year}-${value.month}-${value.day}`
}
const currentMonth=()=>todayYmd().slice(0,7)

function MonthSelector({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}){
  const now=currentMonth()
  return <div className="postpartum-month-selector" aria-label={label}>
    <button type="button" className={value===now?'active':'secondary'} onClick={()=>onChange(now)}>當月</button>
    <button type="button" className={value===nextMonthValue(now)?'active':'secondary'} onClick={()=>onChange(nextMonthValue(now))}>下個月</button>
    <label>自選月份<input type="month" value={value} onChange={event=>onChange(event.target.value)}/></label>
  </div>
}

export function PostpartumMenuSourcePage(){
  const [coverageSources,setCoverageSources]=useState<MenuSource[]>([])
  const [listSources,setListSources]=useState<MenuSource[]>([])
  const [coverageMonth,setCoverageMonth]=useState(currentMonth)
  const [listMonth,setListMonth]=useState(currentMonth)
  const [dialogMonth,setDialogMonth]=useState(currentMonth)
  const [editingSource,setEditingSource]=useState<MenuSource|null>(null)
  const [editorOpen,setEditorOpen]=useState(false)
  const [selectedMenuId,setSelectedMenuId]=useState('')
  const [selectedMenuSnapshot,setSelectedMenuSnapshot]=useState<MenuSourceMenu|null>(null)
  const [mappings,setMappings]=useState<Record<string,string>>(()=>emptyMenuMappings(POSTPARTUM_MEALS))
  const [mealTypes,setMealTypes]=useState<MealType[]>([])
  const [coverageLoading,setCoverageLoading]=useState(true),[listLoading,setListLoading]=useState(true)
  const [mealLoading,setMealLoading]=useState(false),[saving,setSaving]=useState(false)
  const [coverageError,setCoverageError]=useState(''),[listError,setListError]=useState('')
  const [error,setError]=useState(''),[message,setMessage]=useState('')
  const mealRequest=useRef(0),coverageRequest=useRef(0),listRequest=useRef(0)
  const dialogRange=monthRange(dialogMonth)
  const candidates=useMenuCandidates({
    active:'true',startDate:dialogRange.start_date,endDate:dialogRange.end_date,
    pageSize:20,enabled:editorOpen,
  })

  const loadCoverageSources=useCallback(async()=>{
    const request=++coverageRequest.current,range=monthRange(coverageMonth);setCoverageLoading(true);setCoverageError('')
    try{const data=await apiRequest<MenuSourceList>(`/postpartum/menu-sources?from_date=${range.start_date}&to_date=${range.end_date}`);if(request===coverageRequest.current)setCoverageSources(data.items)}
    catch{if(request===coverageRequest.current){setCoverageSources([]);setCoverageError('週期覆蓋載入失敗')}}
    finally{if(request===coverageRequest.current)setCoverageLoading(false)}
  },[coverageMonth])
  const loadListSources=useCallback(async()=>{
    const request=++listRequest.current,range=monthRange(listMonth);setListLoading(true);setListError('')
    try{const data=await apiRequest<MenuSourceList>(`/postpartum/menu-sources?from_date=${range.start_date}&to_date=${range.end_date}`);if(request===listRequest.current)setListSources(data.items)}
    catch{if(request===listRequest.current){setListSources([]);setListError('已設定菜單來源載入失敗')}}
    finally{if(request===listRequest.current)setListLoading(false)}
  },[listMonth])
  useEffect(()=>{void loadCoverageSources()},[loadCoverageSources])
  useEffect(()=>{void loadListSources()},[loadListSources])

  useEffect(()=>{
    const request=++mealRequest.current
    if(!selectedMenuId){setMealTypes([]);setMealLoading(false);return}
    setMealLoading(true)
    void apiRequest<MealType[]>(`/menus/${selectedMenuId}/meal-types`)
      .then(items=>{if(request===mealRequest.current)setMealTypes(items)})
      .catch(()=>{if(request===mealRequest.current){setMealTypes([]);setError('菜單餐別載入失敗')}})
      .finally(()=>{if(request===mealRequest.current)setMealLoading(false)})
  },[selectedMenuId])

  const menuOptions=useMemo(()=>{
    const values=candidates.items.map(item=>({
      id:item.id,name:item.name,start_date:item.start_date,end_date:item.end_date,is_active:item.is_active,
    }))
    if(selectedMenuSnapshot&&!values.some(item=>item.id===selectedMenuSnapshot.id))values.unshift(selectedMenuSnapshot)
    return values
  },[candidates.items,selectedMenuSnapshot])
  const selectedMenu=menuOptions.find(item=>item.id===selectedMenuId)
  const mealTypesById=new Map(mealTypes.map(item=>[item.id,item]))
  const mappingsValid=menuMappingsValid(mappings)
  const selectedIds=Object.values(mappings).filter(Boolean)
  const allSelectedMealTypesActive=selectedIds.every(id=>mealTypesById.get(id)?.is_active)
  const canSave=Boolean(selectedMenu?.is_active&&mappingsValid&&allSelectedMealTypesActive&&!mealLoading&&!saving)
  const coverage=buildMonthWeekSegments(coverageSources,coverageMonth)

  function clearCandidateSelection(){
    setSelectedMenuId('');setSelectedMenuSnapshot(null);setMappings(emptyMenuMappings(POSTPARTUM_MEALS))
  }
  function openCreate(month=coverageMonth){
    setDialogMonth(month);candidates.setSearch('')
    setEditingSource(null);setSelectedMenuId('');setSelectedMenuSnapshot(null)
    setMappings(emptyMenuMappings(POSTPARTUM_MEALS));setEditorOpen(true);setMessage('');setError('')
  }
  function openEdit(source:MenuSource){
    const next=emptyMenuMappings(POSTPARTUM_MEALS)
    for(const item of source.mappings)next[item.postpartum_meal]=item.menu_meal_type.id
    setDialogMonth(source.menu.start_date.slice(0,7));candidates.setSearch('')
    setEditingSource(source);setSelectedMenuId(source.menu.id);setSelectedMenuSnapshot(source.menu)
    setMappings(next);setEditorOpen(true);setMessage('');setError('')
  }
  function changeDialogMonth(month:string){setDialogMonth(month);clearCandidateSelection()}
  function changeCandidateSearch(search:string){candidates.setSearch(search);clearCandidateSelection()}
  function changeCandidatePage(page:number){candidates.setPage(page);clearCandidateSelection()}
  function changeMenu(menuId:string){
    setSelectedMenuSnapshot(menuOptions.find(item=>item.id===menuId)??null)
    setSelectedMenuId(menuId);setMappings(emptyMenuMappings(POSTPARTUM_MEALS));setMessage('');setError('')
  }
  async function save(){
    if(!canSave)return
    setSaving(true);setError('');setMessage('')
    const payload={menu_id:selectedMenuId,mappings:POSTPARTUM_MEALS
      .filter(item=>Boolean(mappings[item.value]))
      .map(item=>({postpartum_meal:item.value,menu_meal_type_id:mappings[item.value]}))}
    try{
      await apiRequest(editingSource?`/postpartum/menu-sources/${editingSource.id}`:'/postpartum/menu-sources',{
        method:editingSource?'PUT':'POST',body:JSON.stringify(payload),
      })
      await Promise.all([loadCoverageSources(),loadListSources()]);setEditorOpen(false);setMessage('菜單來源設定已儲存')
    }catch{setError('菜單來源設定儲存失敗，請確認日期沒有重疊，且菜單與已選餐別皆為啟用狀態')}
    finally{setSaving(false)}
  }

  return <section>
    <div className="section-heading"><div><h2>月子餐菜單來源／週期覆蓋</h2><small>可提前設定多週 ERP 菜單；每份來源至少對應一個月子餐餐次。</small></div><button type="button" onClick={()=>openCreate()}>新增菜單來源</button></div>
    {error&&<p className="error">{error}</p>}{message&&<p className="success">{message}</p>}
    <section className="postpartum-coverage-section"><div className="subsection-heading"><div><h3>月份週期覆蓋</h3><small>{coverageMonth.replace('-', '年')}月</small></div><MonthSelector label="週期覆蓋月份" value={coverageMonth} onChange={setCoverageMonth}/></div>
    {coverageError&&<p className="error">{coverageError}</p>}{coverageLoading?<p>週期覆蓋載入中…</p>:<div className="postpartum-menu-coverage" aria-label="月份菜單來源覆蓋">
      {coverage.map(period=><article className={`coverage-${period.status}`} key={period.index}><strong>第{period.index}週</strong><span>{period.start_date} ～ {period.end_date}</span><b>{statusLabels[period.status]}</b>{period.sources.map(source=><span className="coverage-source" key={source.id}>{source.menu.name}｜{source.menu.start_date}～{source.menu.end_date}<button type="button" className="secondary" onClick={()=>openEdit(source)}>編輯</button></span>)}{period.sources.length===0&&<button type="button" className="secondary" onClick={()=>openCreate(period.start_date.slice(0,7))}>新增設定</button>}</article>)}
    </div>}
    </section>
    <section className="postpartum-source-list-section"><div className="subsection-heading"><div><h3>已設定菜單來源</h3><small>只顯示與所選月份有交集的來源</small></div><MonthSelector label="已設定來源月份" value={listMonth} onChange={setListMonth}/></div>
    {listError&&<p className="error">{listError}</p>}
    {listLoading?<p>已設定菜單來源載入中…</p>:listSources.length===0?<p className="muted">此月份尚無已設定菜單來源。</p>:<div className="postpartum-menu-source-list">
      {listSources.map(source=><article className="postpartum-menu-source-card" key={source.id}>
        <header><div><strong>{source.menu.name}{!source.menu.is_active?'（已停用）':''}</strong><small>{source.menu.start_date} ～ {source.menu.end_date}</small></div><button type="button" onClick={()=>openEdit(source)}>編輯</button></header>
        {source.warnings.map(item=><p className="postpartum-menu-source-warning" key={`${item.code}-${item.postpartum_meal??'source'}`}>⚠ {item.message}</p>)}
        <div className="postpartum-menu-source-summary">{source.meal_statuses.map(status=>{const meal=POSTPARTUM_MEALS.find(item=>item.value===status.postpartum_meal);return <span key={status.postpartum_meal}><b>{meal?.label}</b>：{status.mapped?status.menu_meal_type?.name:'未設定'}{status.menu_meal_type&&!status.menu_meal_type.is_active?'（已停用）':''}</span>})}</div>
      </article>)}
    </div>
    }</section>
    {editorOpen&&<div className="modal-backdrop" role="presentation"><div className="modal postpartum-menu-source-dialog" role="dialog" aria-modal="true" aria-label={editingSource?'編輯月子餐菜單來源':'新增月子餐菜單來源'}>
      <div className="section-heading"><h3>{editingSource?'編輯':'新增'}月子餐菜單來源</h3><button type="button" className="secondary" onClick={()=>setEditorOpen(false)}>關閉</button></div>
      <div className="panel-form postpartum-menu-source-picker">
        <MonthSelector label="ERP 菜單候選月份" value={dialogMonth} onChange={changeDialogMonth}/>
        <label>搜尋 ERP 菜單<input value={candidates.search} onChange={event=>changeCandidateSearch(event.target.value)} placeholder="輸入菜單名稱"/></label>
        <label>ERP 菜單<select value={selectedMenuId} onChange={event=>changeMenu(event.target.value)}><option value="">請選擇菜單</option>{menuOptions.map(item=><option key={item.id} value={item.id}>{item.name}{!item.is_active?'（已停用）':''}｜{item.start_date}～{item.end_date}</option>)}</select></label>
        {candidates.loading&&<small>菜單候選載入中…</small>}{candidates.error&&<small className="error">{candidates.error}</small>}
        {!candidates.loading&&!candidates.error&&candidates.total===0&&<p className="muted">此月份沒有符合條件的 ERP 菜單</p>}
        <PaginationControls page={candidates.page} pageSize={candidates.pageSize} total={candidates.total} onPage={changeCandidatePage}/>
      </div>
      {mealLoading&&<p>菜單餐別載入中…</p>}
      {selectedMenuId&&<div className="postpartum-menu-source-grid" aria-label="六餐菜單餐別 mapping">
        {POSTPARTUM_MEALS.map(item=><label key={item.value}><span>{item.label}</span><select value={mappings[item.value]} disabled={mealLoading} onChange={event=>setMappings(value=>({...value,[item.value]:event.target.value}))}><option value="">未設定</option>{mealTypes.filter(meal=>meal.is_active||meal.id===mappings[item.value]).map(meal=><option key={meal.id} value={meal.id} disabled={mealTypeUsedByOtherMeal(mappings,item.value,meal.id)}>{meal.name}{!meal.is_active?'（已停用）':''}</option>)}</select></label>)}
      </div>}
      {selectedMenuId&&!mappingsValid&&<p className="muted">至少設定一餐；同一個 ERP 餐別只能使用一次。</p>}
      {selectedMenuId&&!selectedMenu?.is_active&&<p className="postpartum-menu-source-warning">⚠ 目前菜單已停用，請重新選擇啟用中的菜單。</p>}
      {selectedMenuId&&mappingsValid&&!allSelectedMealTypesActive&&<p className="postpartum-menu-source-warning">⚠ 已選 mapping 含已停用餐別，請重新選擇啟用中的餐別。</p>}
      <div className="modal-actions"><button type="button" className="secondary" onClick={()=>setEditorOpen(false)}>取消</button><button type="button" disabled={!canSave} onClick={()=>void save()}>{saving?'儲存中…':'儲存菜單來源'}</button></div>
    </div></div>}
  </section>
}
