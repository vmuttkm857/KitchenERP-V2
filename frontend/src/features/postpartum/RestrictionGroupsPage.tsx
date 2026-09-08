import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../../api/client'
import { EmptyState, Feedback, LoadingState, TableFrame } from '../../components/ui/Page'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { buildListQuery, PagedResponse, RequestSequence } from '../../utils/listQuery'
import { useDebouncedValue } from '../../utils/useDebouncedValue'
import { addTargets, bulkSelectionQuery, removeTargets, RestrictionGroup, RestrictionGroupDetail, RestrictionTarget, targetMap, toggleTarget } from './restrictionTypes'

interface Category { id:string; name:string; is_active:boolean }
interface SelectorProps {
  kind:'ingredient'|'dish'
  title:string
  selected:Map<string,RestrictionTarget>
  onSelected:(value:Map<string,RestrictionTarget>)=>void
  categories:Category[]
}

function TargetSelector({kind,title,selected,onSelected,categories}:SelectorProps){
  const [search,setSearch]=useState(''),[categoryId,setCategoryId]=useState(''),[page,setPage]=useState(1)
  const [items,setItems]=useState<RestrictionTarget[]>([]),[total,setTotal]=useState(0),[loading,setLoading]=useState(false),[bulkBusy,setBulkBusy]=useState(false),[error,setError]=useState('')
  const debounced=useDebouncedValue(search),sequence=useRef(new RequestSequence())
  useEffect(()=>setPage(1),[debounced,categoryId])
  useEffect(()=>{
    const request=sequence.current.next();setLoading(true)
    const query=buildListQuery({page,pageSize:20,search:debounced,active:'true',categoryId})
    void apiRequest<PagedResponse<RestrictionTarget>>(`/${kind==='ingredient'?'ingredients':'dishes'}?${query}`)
      .then(data=>{if(sequence.current.isCurrent(request)){setItems(data.items);setTotal(data.pagination.total);setError('')}})
      .catch(()=>{if(sequence.current.isCurrent(request))setError(`${title}候選載入失敗`)})
      .finally(()=>{if(sequence.current.isCurrent(request))setLoading(false)})
  },[categoryId,debounced,kind,page,title])
  async function changeFilteredSelection(action:'add'|'remove'){
    setBulkBusy(true);setError('')
    try{
      const matches=await apiRequest<RestrictionTarget[]>(`/${kind==='ingredient'?'ingredients':'dishes'}/selection-options?${bulkSelectionQuery(search,categoryId)}`)
      onSelected(action==='add'?addTargets(selected,matches):removeTargets(selected,matches))
    }catch(cause){setError(cause instanceof ApiError&&cause.status<500?cause.message:`${title}批次選取失敗`)}finally{setBulkBusy(false)}
  }
  return <section className="restriction-selector">
    <header><h3>{title}（已選 {selected.size}）</h3></header>
    <div className="restriction-selector-controls"><label>搜尋{title}<input value={search} onChange={event=>{setSearch(event.target.value);setPage(1)}} placeholder={`輸入${title}名稱或代碼`}/></label><label>分類<select value={categoryId} onChange={event=>{setCategoryId(event.target.value);setPage(1)}}><option value="">全部分類</option>{categories.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
    <div className="restriction-bulk-actions"><span>目前篩選共 {total} 筆</span><button type="button" className="secondary" disabled={bulkBusy||total===0} onClick={()=>void changeFilteredSelection('add')}>{bulkBusy?'處理中…':'全選目前篩選結果'}</button><button type="button" className="secondary" disabled={bulkBusy||total===0} onClick={()=>void changeFilteredSelection('remove')}>取消選取目前篩選結果</button></div>
    {error&&<Feedback type="error">{error}</Feedback>}
    <div className="restriction-results">{loading?<p>搜尋中…</p>:items.length?items.map(item=><label className="inline-check" key={item.id}><input type="checkbox" checked={selected.has(item.id)} onChange={()=>onSelected(toggleTarget(selected,item))}/><span>{item.code}　{item.name}</span></label>):<p>找不到符合條件的{title}</p>}</div>
    <PaginationControls page={page} pageSize={20} total={total} onPage={setPage}/>
    <div className="restriction-selected" aria-label={`已選${title}`}>{[...selected.values()].map(item=><span key={item.id}>{item.code}　{item.name}{!item.is_active&&<em>已停用</em>}<button type="button" aria-label={`移除 ${item.name}`} onClick={()=>onSelected(toggleTarget(selected,item))}>×</button></span>)}</div>
  </section>
}

function RestrictionGroupDialog({groupId,onClose,onSaved}:{groupId:string|null;onClose:()=>void;onSaved:()=>Promise<void>}){
  const [name,setName]=useState(''),[color,setColor]=useState('#FF0000'),[notes,setNotes]=useState('')
  const [ingredients,setIngredients]=useState<Map<string,RestrictionTarget>>(new Map()),[dishes,setDishes]=useState<Map<string,RestrictionTarget>>(new Map())
  const [ingredientCategories,setIngredientCategories]=useState<Category[]>([]),[dishCategories,setDishCategories]=useState<Category[]>([])
  const [loading,setLoading]=useState(Boolean(groupId)),[busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{
    let current=true
    void Promise.all([
      apiRequest<PagedResponse<Category>>('/categories/ingredient?active=true&page_size=100'),
      apiRequest<PagedResponse<Category>>('/categories/dish?active=true&page_size=100'),
    ]).then(([ingredient,dish])=>{if(current){setIngredientCategories(ingredient.items);setDishCategories(dish.items)}}).catch(()=>{if(current)setError('分類選項載入失敗')})
    return()=>{current=false}
  },[])
  useEffect(()=>{
    if(!groupId)return
    let current=true;setLoading(true)
    void apiRequest<RestrictionGroupDetail>(`/postpartum/restriction-groups/${groupId}`).then(detail=>{if(current){setName(detail.group.name);setColor(detail.group.color);setNotes(detail.group.notes??'');setIngredients(targetMap(detail.ingredients));setDishes(targetMap(detail.dishes));setError('')}}).catch(()=>{if(current)setError('禁忌群組明細載入失敗')}).finally(()=>{if(current)setLoading(false)})
    return()=>{current=false}
  },[groupId])
  async function save(event:FormEvent){
    event.preventDefault();setBusy(true);setError('')
    try{
      let id=groupId
      const body=JSON.stringify({name:name.trim(),color,notes:notes.trim()||null})
      if(id)await apiRequest(`/postpartum/restriction-groups/${id}`,{method:'PATCH',body})
      else{id=(await apiRequest<RestrictionGroup>('/postpartum/restriction-groups',{method:'POST',body})).id}
      await apiRequest(`/postpartum/restriction-groups/${id}/associations`,{method:'PUT',body:JSON.stringify({ingredient_ids:[...ingredients.keys()],dish_ids:[...dishes.keys()]})})
      await onSaved();onClose()
    }catch(cause){setError(cause instanceof ApiError&&cause.status<500?cause.message:'禁忌群組儲存失敗，請稍後再試。')}finally{setBusy(false)}
  }
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}><section className="modal-panel restriction-group-dialog" role="dialog" aria-modal="true" aria-labelledby="restriction-group-title">
    <header><div><h2 id="restriction-group-title">{groupId?'編輯禁忌群組':'新增禁忌群組'}</h2><p>人工指定需要避開的食材與菜色；兩者彼此獨立。</p></div><button type="button" className="secondary" disabled={busy} onClick={onClose}>關閉</button></header>
    {loading?<LoadingState label="禁忌群組載入中…"/>:<form onSubmit={save}><div className="restriction-basic-fields"><label>禁忌名稱<input autoFocus required maxLength={150} value={name} onChange={event=>setName(event.target.value)}/></label><label>顏色<input type="color" value={color} onChange={event=>setColor(event.target.value.toUpperCase())}/><code>{color}</code></label><label>備註<textarea maxLength={5000} value={notes} onChange={event=>setNotes(event.target.value)}/></label></div>
      <TargetSelector kind="ingredient" title="食材" selected={ingredients} onSelected={setIngredients} categories={ingredientCategories}/>
      <TargetSelector kind="dish" title="菜色" selected={dishes} onSelected={setDishes} categories={dishCategories}/>
      {error&&<Feedback type="error">{error}</Feedback>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>取消</button><button disabled={busy||!name.trim()}>{busy?'儲存中…':'儲存'}</button></footer>
    </form>}
  </section></div>
}

export function RestrictionGroupsPage(){
  const [items,setItems]=useState<RestrictionGroup[]>([]),[page,setPage]=useState(1),[total,setTotal]=useState(0)
  const [search,setSearch]=useState(''),[active,setActive]=useState('true'),[loading,setLoading]=useState(true),[error,setError]=useState('')
  const [creating,setCreating]=useState(false),[editingId,setEditingId]=useState<string|null>(null)
  const debounced=useDebouncedValue(search),sequence=useRef(new RequestSequence())
  useEffect(()=>setPage(1),[active,debounced])
  const load=useCallback(async()=>{const request=sequence.current.next();setLoading(true);const query=buildListQuery({page,pageSize:25,search:debounced,active});try{const data=await apiRequest<PagedResponse<RestrictionGroup>>(`/postpartum/restriction-groups?${query}`);if(sequence.current.isCurrent(request)){setItems(data.items);setTotal(data.pagination.total);setError('')}}catch{if(sequence.current.isCurrent(request))setError('禁忌群組載入失敗')}finally{if(sequence.current.isCurrent(request))setLoading(false)}},[active,debounced,page])
  useEffect(()=>{void load()},[load])
  async function toggle(item:RestrictionGroup){try{await apiRequest(`/postpartum/restriction-groups/${item.id}/${item.is_active?'deactivate':'reactivate'}`,{method:'POST'});await load()}catch{setError('禁忌群組狀態更新失敗')}}
  return <section><div className="section-heading"><div><h2>禁忌群組管理</h2><small>建立月子餐飲食禁忌，人工關聯既有食材與菜色。</small></div><button onClick={()=>setCreating(true)}>新增禁忌群組</button></div>
    <div className="toolbar"><label>搜尋<input value={search} onChange={event=>setSearch(event.target.value)}/></label><label>狀態<select value={active} onChange={event=>setActive(event.target.value)}><option value="">全部</option><option value="true">啟用</option><option value="false">停用</option></select></label></div>
    {error&&<Feedback type="error">{error}</Feedback>}{loading?<LoadingState/>:!items.length?<EmptyState title="找不到禁忌群組" description="請新增群組或調整搜尋條件。"/>:<TableFrame><table><thead><tr><th>顏色</th><th>名稱</th><th>食材</th><th>菜色</th><th>狀態</th><th>操作</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td><span className="restriction-color" style={{backgroundColor:item.color}} aria-label={item.color}/></td><td>{item.name}{item.notes&&<small>{item.notes}</small>}</td><td>{item.ingredient_count}</td><td>{item.dish_count}</td><td>{item.is_active?'啟用':'停用'}</td><td className="actions"><button onClick={()=>setEditingId(item.id)}>檢視／編輯</button><button className="secondary" onClick={()=>void toggle(item)}>{item.is_active?'停用':'恢復'}</button></td></tr>)}</tbody></table></TableFrame>}
    <PaginationControls page={page} pageSize={25} total={total} onPage={setPage}/>
    {creating&&<RestrictionGroupDialog key="create" groupId={null} onClose={()=>setCreating(false)} onSaved={load}/>} {editingId&&<RestrictionGroupDialog key={editingId} groupId={editingId} onClose={()=>setEditingId(null)} onSaved={load}/>} 
  </section>
}
