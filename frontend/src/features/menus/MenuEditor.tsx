import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiRequest } from '../../api/client'
import { Feedback, LoadingState } from '../../components/ui/Page'
import { MenuEditorPanel } from './MenuEditorPanel'
import { MenuWeekGrid } from './MenuWeekGrid'
import { DishOption, List, MealType, Menu, MenuAggregate, MenuDish, MenuSlot } from './types'

const slotKey = (date: string, mealId: string) => `${date}:${mealId}`
interface Paged<T> { items: T[]; pagination: { total: number } }

export function MenuEditor({ menu, onClose }: { menu: Menu; onClose: () => void }) {
  const [data, setData] = useState<MenuAggregate | null>(null)
  const [menus, setMenus] = useState<Menu[]>([])
  const [slots, setSlots] = useState<Record<string, MenuSlot>>({})
  const [mealName, setMealName] = useState('')
  const [mealDrafts, setMealDrafts] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [dialog, setDialog] = useState<'meal' | 'copy' | null>(null)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [dishSearch, setDishSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [dishPage, setDishPage] = useState(1)
  const [dishResults, setDishResults] = useState<DishOption[]>([])
  const [dishTotal, setDishTotal] = useState(0)
  const [dishLoading, setDishLoading] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const [sourceMenu, setSourceMenu] = useState(menu.id)
  const [sourceDate, setSourceDate] = useState(menu.start_date)
  const [destinationDate, setDestinationDate] = useState(menu.start_date)
  const [copyMode, setCopyMode] = useState<'add' | 'replace'>('add')
  const [confirmReplace, setConfirmReplace] = useState(false)

  const applyAggregate = useCallback((aggregate: MenuAggregate) => {
    setData(aggregate)
    setMealDrafts(Object.fromEntries(aggregate.meal_types.map(meal => [meal.id, meal.name])))
    setSlots(Object.fromEntries(aggregate.slots.map(slot => [slotKey(slot.menu_date, slot.menu_meal_type_id), slot])))
    setDirty(false)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [aggregate, list] = await Promise.all([
        apiRequest<MenuAggregate>(`/menus/${menu.id}/editor`),
        apiRequest<List<Menu>>('/menus?active=true&page_size=100'),
      ])
      applyAggregate(aggregate); setMenus(list.items); setError('')
    } catch { setError('菜單工作區載入失敗') }
    finally { setLoading(false) }
  }, [applyAggregate, menu.id])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(dishSearch.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [dishSearch])
  useEffect(() => {
    if (!editingKey || !debouncedSearch) {
      setDishResults([]); setDishTotal(0); setDishLoading(false); return
    }
    let active = true
    setDishLoading(true)
    apiRequest<Paged<DishOption>>(`/dishes?active=true&page=${dishPage}&page_size=10&search=${encodeURIComponent(debouncedSearch)}`)
      .then(result => { if (active) { setDishResults(result.items); setDishTotal(result.pagination.total) } })
      .catch(() => { if (active) setError('菜色搜尋失敗，請稍後再試') })
      .finally(() => { if (active) setDishLoading(false) })
    return () => { active = false }
  }, [debouncedSearch, dishPage, editingKey])

  const meals = useMemo(() => data?.meal_types.filter(meal => meal.is_active || Object.values(slots).some(slot => slot.menu_meal_type_id === meal.id)) ?? [], [data, slots])
  function slotFor(date: string, meal: MealType): MenuSlot { return slots[slotKey(date, meal.id)] ?? { menu_date: date, menu_meal_type_id: meal.id, notes: null, dishes: [] } }
  function setDraftSlot(slot: MenuSlot) { setSlots(current => ({ ...current, [slotKey(slot.menu_date, slot.menu_meal_type_id)]: slot })); setDirty(true); setMessage('') }
  function updateDish(slot: MenuSlot, index: number, changes: Partial<MenuDish>) { setDraftSlot({ ...slot, dishes: slot.dishes.map((dish, dishIndex) => dishIndex === index ? { ...dish, ...changes } : dish) }) }
  function moveDish(slot: MenuSlot, index: number, direction: -1 | 1) {
    const target = index + direction
    if (target < 0 || target >= slot.dishes.length) return
    const dishes = [...slot.dishes]; [dishes[index], dishes[target]] = [dishes[target], dishes[index]]
    setDraftSlot({ ...slot, dishes: dishes.map((dish, order) => ({ ...dish, sort_order: order + 1 })) })
  }
  function removeDish(slot: MenuSlot, index: number) {
    const dish = slot.dishes[index]
    if (!window.confirm(`只會從本餐移除「${dish.dish_name}」，不會刪除菜色主檔。確定移除？`)) return
    setDraftSlot({ ...slot, dishes: slot.dishes.filter((_, dishIndex) => dishIndex !== index).map((item, order) => ({ ...item, sort_order: order + 1 })) })
  }
  function addDish(slot: MenuSlot, dish: DishOption) {
    if (slot.dishes.some(item => item.dish_id === dish.id)) { setError(`「${dish.name}」已在本餐中`); return }
    setDraftSlot({ ...slot, dishes: [...slot.dishes, { dish_id: dish.id, dish_code: dish.code, dish_name: dish.name, dish_category_name: dish.category_name, diner_count: 1, notes: null, sort_order: slot.dishes.length + 1 }] })
    setDishSearch(''); setDebouncedSearch(''); setDishPage(1); setDishResults([]); setDishTotal(0); setError('')
    window.setTimeout(() => searchInputRef.current?.focus(), 0)
  }
  function selectCell(date: string, meal: MealType) { setEditingKey(slotKey(date, meal.id)); setDishSearch(''); setDishPage(1); setError(''); window.setTimeout(() => searchInputRef.current?.focus(), 0) }
  function openDialog(next: 'meal' | 'copy') {
    if (dirty) { setError('請先儲存菜單，再開啟餐別設定或複製菜單，以免尚未儲存的變更遺失。'); return }
    setDialog(next)
  }

  async function save() {
    if (!dirty) return
    setSaving(true); setMessage(''); setError('')
    try {
      const payload = Object.values(slots).filter(slot => slot.menu_day_id || slot.notes || slot.dishes.length).map(slot => ({ ...slot, dishes: slot.dishes.map(({ id, dish_id, diner_count, notes, sort_order }) => ({ id, dish_id, diner_count, notes, sort_order })) }))
      applyAggregate(await apiRequest<MenuAggregate>(`/menus/${menu.id}/editor`, { method: 'PUT', body: JSON.stringify({ slots: payload }) }))
      setMessage('菜單已儲存')
    } catch { setError('儲存失敗；資料庫未接受任何部分變更，請檢查停用資料、重複菜色與人數') }
    finally { setSaving(false) }
  }
  async function addMeal(event: FormEvent) { event.preventDefault(); try { await apiRequest(`/menus/${menu.id}/meal-types`, { method: 'POST', body: JSON.stringify({ name: mealName, sort_order: (data?.meal_types.length ?? 0) + 1 }) }); setMealName(''); await load() } catch { setError('餐別新增失敗，名稱不可重複') } }
  async function saveMeal(meal: MealType) { try { await apiRequest(`/menus/${menu.id}/meal-types/${meal.id}`, { method: 'PATCH', body: JSON.stringify({ name: mealDrafts[meal.id] }) }); await load() } catch { setError('餐別修改失敗') } }
  async function toggleMeal(meal: MealType) { try { await apiRequest(`/menus/${menu.id}/meal-types/${meal.id}/${meal.is_active ? 'deactivate' : 'reactivate'}`, { method: 'POST' }); await load() } catch { setError('餐別狀態更新失敗') } }
  async function moveMeal(meal: MealType, direction: -1 | 1) {
    if (!data) return
    const ordered = [...data.meal_types].sort((a, b) => a.sort_order - b.sort_order), index = ordered.findIndex(item => item.id === meal.id), target = index + direction
    if (target < 0 || target >= ordered.length) return
    ;[ordered[index], ordered[target]] = [ordered[target], ordered[index]]
    await apiRequest(`/menus/${menu.id}/meal-types/reorder`, { method: 'PUT', body: JSON.stringify({ ordered_ids: ordered.map(item => item.id) }) }); await load()
  }
  async function copy(kind: 'day' | 'week') {
    try {
      const body = kind === 'day' ? { source_menu_id: sourceMenu, source_date: sourceDate, destination_date: destinationDate, mode: copyMode, confirm_replace: confirmReplace } : { source_menu_id: sourceMenu, mode: copyMode, confirm_replace: confirmReplace }
      applyAggregate(await apiRequest<MenuAggregate>(`/menus/${menu.id}/copy-${kind}`, { method: 'POST', body: JSON.stringify(body) }))
      setMessage(kind === 'day' ? '日期複製完成' : '完整七日複製完成'); setDialog(null)
    } catch { setError('複製失敗；請確認日期、餐別與覆蓋確認') }
  }

  if (loading || !data) return <section><button className="secondary" onClick={onClose}>返回菜單</button>{loading ? <LoadingState label="菜單工作區載入中…"/> : <Feedback type="error">{error}</Feedback>}</section>
  const editing = editingKey ? (() => { const [date, mealId] = editingKey.split(':'); const meal = meals.find(item => item.id === mealId); return meal ? { date, meal, slot: slotFor(date, meal) } : null })() : null

  return <section className="menu-editor-page">
    <header className="page-header"><div><p className="eyebrow">菜單編輯</p><h1>{data.menu.name}</h1><p>{data.menu.start_date} ～ {data.menu.end_date}</p>{dirty && <span className="unsaved-indicator" role="status">● 有尚未儲存的變更</span>}</div><div className="page-actions"><button className="secondary" onClick={() => openDialog('meal')}>餐別設定</button><button className="secondary" onClick={() => openDialog('copy')}>複製菜單</button><button className="secondary" onClick={onClose}>返回</button><button onClick={() => void save()} disabled={!dirty || saving}>{saving ? '儲存中…' : '儲存菜單'}</button></div></header>
    {error && <Feedback type="error">{error}</Feedback>}{message && <Feedback type="success">{message}</Feedback>}
    {!meals.length ? <div className="state-panel">請先從「餐別設定」建立至少一個啟用餐別。</div> : <div className={`menu-editor-workspace${editing ? ' has-drawer' : ''}`}><MenuWeekGrid dates={data.dates} meals={meals} selectedKey={editingKey} slotFor={slotFor} onSelect={selectCell}/>{editing && <MenuEditorPanel date={editing.date} meal={editing.meal} slot={editing.slot} search={dishSearch} results={dishResults.filter(dish => !editing.slot.dishes.some(item => item.dish_id === dish.id))} searchTotal={dishTotal} searchPage={dishPage} searchLoading={dishLoading} searchInputRef={searchInputRef} onClose={() => setEditingKey(null)} onSlotNotes={notes => setDraftSlot({ ...editing.slot, notes })} onDishChange={(index, changes) => updateDish(editing.slot, index, changes)} onMove={(index, direction) => moveDish(editing.slot, index, direction)} onRemove={index => removeDish(editing.slot, index)} onSearch={value => { setDishSearch(value); setDishPage(1) }} onSearchPage={setDishPage} onAdd={dish => addDish(editing.slot, dish)}/>}</div>}
    {dialog === 'meal' && <div className="modal-backdrop" onMouseDown={() => setDialog(null)}><section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="meal-title" onMouseDown={event => event.stopPropagation()}><header><h2 id="meal-title">餐別設定</h2><button className="secondary" onClick={() => setDialog(null)}>關閉</button></header><form className="inline-form" onSubmit={addMeal}><label>新餐別名稱<input autoFocus value={mealName} onChange={event => setMealName(event.target.value)} required/></label><button>新增餐別</button></form><div className="meal-list">{data.meal_types.map(meal => <div key={meal.id} className={!meal.is_active ? 'inactive' : ''}><label>名稱<input value={mealDrafts[meal.id] ?? meal.name} onChange={event => setMealDrafts({ ...mealDrafts, [meal.id]: event.target.value })}/></label><button className="secondary" aria-label={`${meal.name} 上移`} onClick={() => void moveMeal(meal, -1)}>上移</button><button className="secondary" aria-label={`${meal.name} 下移`} onClick={() => void moveMeal(meal, 1)}>下移</button><button onClick={() => void saveMeal(meal)}>儲存</button><button className="secondary" onClick={() => void toggleMeal(meal)}>{meal.is_active ? '停用' : '恢復'}</button></div>)}</div></section></div>}
    {dialog === 'copy' && <div className="modal-backdrop" onMouseDown={() => setDialog(null)}><section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="copy-title" onMouseDown={event => event.stopPropagation()}><header><div><h2 id="copy-title">複製菜單</h2><p>可複製單日或完整七日；覆蓋模式會先要求確認。</p></div><button className="secondary" onClick={() => setDialog(null)}>關閉</button></header><div className="form-grid"><label>來源菜單<select autoFocus value={sourceMenu} onChange={event => setSourceMenu(event.target.value)}>{menus.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>來源日期<input type="date" value={sourceDate} onChange={event => setSourceDate(event.target.value)}/></label><label>目的日期<input type="date" value={destinationDate} onChange={event => setDestinationDate(event.target.value)}/></label><label>模式<select value={copyMode} onChange={event => { setCopyMode(event.target.value as 'add' | 'replace'); setConfirmReplace(false) }}><option value="add">加入（跳過重複）</option><option value="replace">覆蓋目的資料</option></select></label></div>{copyMode === 'replace' && <label className="confirm-box"><input type="checkbox" checked={confirmReplace} onChange={event => setConfirmReplace(event.target.checked)}/>我了解目的日期原有餐格內容將被覆蓋。</label>}<footer><button className="secondary" disabled={copyMode === 'replace' && !confirmReplace} onClick={() => void copy('day')}>複製一天</button><button disabled={copyMode === 'replace' && !confirmReplace} onClick={() => void copy('week')}>複製完整七日</button></footer></section></div>}
  </section>
}
