import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, apiDownload, apiRequest } from '../../api/client'
import { Feedback, LoadingState } from '../../components/ui/Page'
import { MenuEditorPanel } from './MenuEditorPanel'
import { MenuWeekGrid } from './MenuWeekGrid'
import { DishCategoryOption, DishOption, List, MealType, Menu, MenuAggregate, MenuDish, MenuSlot } from './types'
import { useEditorDirty } from '../../app/NavigationBlocker'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { useMenuCandidates } from './useMenuCandidates'

const slotKey = (date: string, mealId: string) => `${date}:${mealId}`
const displayDate = (value: string) => value.replaceAll('-', '/')
function shiftDate(value: string, days: number) {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + days))
  return date.toISOString().slice(0, 10)
}
interface Paged<T> { items: T[]; pagination: { total: number } }
type ConfirmState = { kind: 'discard-meal' } | { kind: 'remove-dish'; index: number }

function MenuConfirmDialog({ title, description, confirmLabel, onCancel, onConfirm }: { title: string; description: string; confirmLabel: string; onCancel: () => void; onConfirm: () => void }) {
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onCancel() }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close) }, [onCancel])
  return <div className="modal-backdrop"><section className="modal-panel danger-dialog" role="alertdialog" aria-modal="true" aria-labelledby="menu-confirm-title"><header><div><h2 id="menu-confirm-title">{title}</h2><p>{description}</p></div></header><footer><button autoFocus className="secondary" onClick={onCancel}>取消</button><button className="secondary-danger" onClick={onConfirm}>{confirmLabel}</button></footer></section></div>
}

export function MenuEditor({ menu, onClose }: { menu: Menu; onClose: () => void }) {
  const [data, setData] = useState<MenuAggregate | null>(null)
  const [dishCategories, setDishCategories] = useState<DishCategoryOption[]>([])
  const [slots, setSlots] = useState<Record<string, MenuSlot>>({})
  const [mealName, setMealName] = useState('')
  const [mealDrafts, setMealDrafts] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [dialog, setDialog] = useState<'meal' | 'copy' | 'export' | null>(null)
  const [exportLayout, setExportLayout] = useState<'full' | 'grid' | 'pretty'>('full')
  const [exportFormat, setExportFormat] = useState<'xlsx' | 'pdf'>('xlsx')
  const [exportVariant, setExportVariant] = useState<'single' | 'poster'>('single')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [mealDraft, setMealDraft] = useState<MenuSlot | null>(null)
  const [mealInitial, setMealInitial] = useState('')
  const [confirmation, setConfirmation] = useState<ConfirmState | null>(null)
  const [mealSaveError, setMealSaveError] = useState('')
  const [dishSearch, setDishSearch] = useState('')
  const [dishCategoryId, setDishCategoryId] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [dishPage, setDishPage] = useState(1)
  const [dishResults, setDishResults] = useState<DishOption[]>([])
  const [dishTotal, setDishTotal] = useState(0)
  const [dishLoading, setDishLoading] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const mealOpenerRef = useRef<HTMLElement | null>(null)
  const [sourceMenu, setSourceMenu] = useState(menu.id)
  const [sourceDate, setSourceDate] = useState(menu.start_date)
  const [sourceFilterStart, setSourceFilterStart] = useState(shiftDate(menu.start_date, -30))
  const [sourceFilterEnd, setSourceFilterEnd] = useState(shiftDate(menu.end_date, 30))
  const [destinationDate, setDestinationDate] = useState(menu.start_date)
  const [copyScope, setCopyScope] = useState<'day' | 'week'>('day')
  const [copyMode, setCopyMode] = useState<'add' | 'replace'>('add')
  const [confirmReplace, setConfirmReplace] = useState(false)
  const [copySaving, setCopySaving] = useState(false)
  const [copyError, setCopyError] = useState<{ scope: 'day' | 'week'; message: string } | null>(null)
  const mealDraftDirty = Boolean(mealDraft && JSON.stringify(mealDraft) !== mealInitial)
  const mealTypeDirty = Boolean(mealName.trim()) || Boolean(data?.meal_types.some(meal => (mealDrafts[meal.id] ?? meal.name) !== meal.name))
  useEditorDirty(mealDraftDirty || mealTypeDirty)

  const applyAggregate = useCallback((aggregate: MenuAggregate) => {
    setData(aggregate)
    setMealDrafts(Object.fromEntries(aggregate.meal_types.map(meal => [meal.id, meal.name])))
    setSlots(Object.fromEntries(aggregate.slots.map(slot => [slotKey(slot.menu_date, slot.menu_meal_type_id), slot])))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [aggregate, categories] = await Promise.all([
        apiRequest<MenuAggregate>(`/menus/${menu.id}/editor`),
        apiRequest<List<DishCategoryOption>>('/categories/dish?page_size=100'),
      ])
      applyAggregate(aggregate); setDishCategories(categories.items); setError('')
    } catch { setError('菜單工作區載入失敗') }
    finally { setLoading(false) }
  }, [applyAggregate, menu.id])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(dishSearch.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [dishSearch])
  useEffect(() => {
    if (!editingKey || confirmation) return
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') requestCloseMeal() }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [editingKey, mealDraft, mealInitial, confirmation, saving])
  useEffect(() => {
    if (!editingKey || (!debouncedSearch && !dishCategoryId)) {
      setDishResults([]); setDishTotal(0); setDishLoading(false); return
    }
    let active = true
    setDishLoading(true)
    const searchQuery = debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ''
    const categoryQuery = dishCategoryId ? `&category_id=${encodeURIComponent(dishCategoryId)}` : ''
    apiRequest<Paged<DishOption>>(`/dishes?active=true&page=${dishPage}&page_size=20${searchQuery}${categoryQuery}`)
      .then(result => { if (active) { setDishResults(result.items); setDishTotal(result.pagination.total) } })
      .catch(() => { if (active) setError('菜色搜尋失敗，請稍後再試') })
      .finally(() => { if (active) setDishLoading(false) })
    return () => { active = false }
  }, [debouncedSearch, dishCategoryId, dishPage, editingKey])

  const meals = useMemo(() => data?.meal_types.filter(meal => meal.is_active || Object.values(slots).some(slot => slot.menu_meal_type_id === meal.id)) ?? [], [data, slots])
  const incompleteSourceRange = !sourceFilterStart || !sourceFilterEnd
  const invalidSourceRange = !incompleteSourceRange && sourceFilterStart > sourceFilterEnd
  const sourceCandidates = useMenuCandidates({active:'true',startDate:sourceFilterStart,endDate:sourceFilterEnd,pageSize:20,enabled:!incompleteSourceRange&&!invalidSourceRange})
  const sourceMenus = useMemo(() => sourceCandidates.items.filter(item => item.id !== menu.id), [menu.id,sourceCandidates.items])
  useEffect(() => {
    const first=sourceMenus[0]
    setSourceMenu(first?.id ?? '')
    if (first) setSourceDate(first.start_date)
  }, [sourceMenus])
  function slotFor(date: string, meal: MealType): MenuSlot { return slots[slotKey(date, meal.id)] ?? { menu_date: date, menu_meal_type_id: meal.id, notes: null, dishes: [] } }
  function setMealDraftSlot(slot: MenuSlot) { setMealDraft(slot); setMessage('') }
  function updateDish(slot: MenuSlot, index: number, changes: Partial<MenuDish>) { setMealDraftSlot({ ...slot, dishes: slot.dishes.map((dish, dishIndex) => dishIndex === index ? { ...dish, ...changes } : dish) }) }
  function moveDish(slot: MenuSlot, index: number, direction: -1 | 1) {
    const target = index + direction
    if (target < 0 || target >= slot.dishes.length) return
    const dishes = [...slot.dishes]; [dishes[index], dishes[target]] = [dishes[target], dishes[index]]
    setMealDraftSlot({ ...slot, dishes: dishes.map((dish, order) => ({ ...dish, sort_order: order + 1 })) })
  }
  function removeDish(slot: MenuSlot, index: number) {
    setMealDraftSlot({ ...slot, dishes: slot.dishes.filter((_, dishIndex) => dishIndex !== index).map((item, order) => ({ ...item, sort_order: order + 1 })) })
  }
  function addDish(slot: MenuSlot, dish: DishOption) {
    if (slot.dishes.some(item => item.dish_id === dish.id)) { setError(`「${dish.name}」已在本餐中`); return }
    setMealDraftSlot({ ...slot, dishes: [...slot.dishes, { dish_id: dish.id, dish_code: dish.code, dish_name: dish.name, dish_category_name: dish.category_name, diner_count: 1, notes: null, sort_order: slot.dishes.length + 1 }] })
    setError('')
  }
  function closeMealEditor() { setEditingKey(null); setMealDraft(null); setMealInitial(''); setMealSaveError(''); setConfirmation(null); window.setTimeout(() => mealOpenerRef.current?.focus(), 0) }
  function selectCell(date: string, meal: MealType) {
    const draft = structuredClone(slotFor(date, meal))
    mealOpenerRef.current = document.activeElement as HTMLElement | null
    setEditingKey(slotKey(date, meal.id)); setMealDraft(draft); setMealInitial(JSON.stringify(draft)); setDishSearch(''); setDishCategoryId(''); setDishPage(1); setMealSaveError(''); setError('')
    window.setTimeout(() => searchInputRef.current?.focus(), 0)
  }
  function requestCloseMeal() { if (saving) return; if (mealDraft && JSON.stringify(mealDraft) !== mealInitial) setConfirmation({ kind: 'discard-meal' }); else closeMealEditor() }
  function openDialog(next: 'meal' | 'copy' | 'export') {
    if (next === 'copy') setCopyError(null)
    if (next === 'export') setExportError('')
    setDialog(next)
  }

  async function downloadMenu() {
    setExporting(true); setExportError('')
    try {
      await apiDownload(`/exports/menus/${menu.id}/${exportLayout}/${exportFormat}?variant=${exportVariant}`)
      setDialog(null)
    } catch { setExportError('菜單匯出失敗，請稍後再試。') }
    finally { setExporting(false) }
  }

  async function saveMealDraft() {
    if (!mealDraft) return
    const nextSlots = { ...slots, [slotKey(mealDraft.menu_date, mealDraft.menu_meal_type_id)]: mealDraft }
    setSaving(true); setMessage(''); setMealSaveError('')
    try {
      const payload = Object.values(nextSlots).filter(slot => slot.menu_day_id || slot.notes || slot.dishes.length).map(slot => ({ ...slot, dishes: slot.dishes.map(({ id, dish_id, diner_count, notes, sort_order }) => ({ id, dish_id, diner_count, notes, sort_order })) }))
      applyAggregate(await apiRequest<MenuAggregate>(`/menus/${menu.id}/editor`, { method: 'PUT', body: JSON.stringify({ slots: payload }) }))
      closeMealEditor(); setMessage('本餐已儲存')
    } catch (cause) {
      setMealSaveError(cause instanceof ApiError && cause.status < 500 ? `儲存失敗：${cause.message}` : '儲存本餐失敗，請稍後再試；目前輸入內容已保留。')
    }
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
  function copyErrorMessage(cause: unknown) {
    if (!(cause instanceof ApiError)) return '複製失敗，請稍後再試。'
    if (cause.message.includes('seven-day')) return '複製整週要求來源與目的菜單都必須剛好是七天。'
    return `複製失敗：${cause.message}`
  }
  async function copy() {
    const requestedScope = copyScope
    setCopySaving(true); setCopyError(null)
    try {
      const body = requestedScope === 'day' ? { source_menu_id: sourceMenu, source_date: sourceDate, destination_date: destinationDate, mode: copyMode, confirm_replace: confirmReplace } : { source_menu_id: sourceMenu, mode: copyMode, confirm_replace: confirmReplace }
      applyAggregate(await apiRequest<MenuAggregate>(`/menus/${menu.id}/copy-${requestedScope}`, { method: 'POST', body: JSON.stringify(body) }))
      setMessage(requestedScope === 'day' ? '日期複製完成' : '完整七日複製完成'); setDialog(null)
    } catch (cause) { setCopyError({ scope: requestedScope, message: copyErrorMessage(cause) }) }
    finally { setCopySaving(false) }
  }

  if (loading || !data) return <section><button className="secondary" onClick={onClose}>返回菜單</button>{loading ? <LoadingState label="菜單工作區載入中…"/> : <Feedback type="error">{error}</Feedback>}</section>
  const editing = editingKey && mealDraft ? (() => { const [date, mealId] = editingKey.split(':'); const meal = meals.find(item => item.id === mealId); return meal ? { date, meal, slot: mealDraft } : null })() : null
  const confirmationContent = confirmation?.kind === 'discard-meal' ? { title: '放棄本餐修改？', description: '尚未儲存的本餐內容將會遺失。', label: '放棄修改', action: closeMealEditor }
    : confirmation?.kind === 'remove-dish' && editing ? { title: '移除菜色？', description: `只會從本餐移除「${editing.slot.dishes[confirmation.index]?.dish_name ?? '此菜色'}」，不會刪除菜色主檔。`, label: '確認移除', action: () => { removeDish(editing.slot, confirmation.index); setConfirmation(null) } }
    : null
  const selectedSourceMenu = sourceMenus.find(item => item.id === sourceMenu)

  return <section className="menu-editor-page">
    <header className="page-header"><div><p className="eyebrow">菜單編輯</p><h1>{data.menu.name}</h1><p>{data.menu.start_date} ～ {data.menu.end_date}</p></div><div className="page-actions"><button className="secondary" onClick={() => openDialog('meal')}>餐別設定</button><button className="secondary" onClick={() => openDialog('copy')}>複製菜單</button><button className="secondary" onClick={() => openDialog('export')}>匯出</button><button className="secondary" onClick={onClose}>返回</button></div></header>
    {error && <Feedback type="error">{error}</Feedback>}{message && <Feedback type="success">{message}</Feedback>}
    {!meals.length ? <div className="state-panel">請先從「餐別設定」建立至少一個啟用餐別。</div> : <div className="menu-editor-workspace"><MenuWeekGrid dates={data.dates} meals={meals} selectedKey={editingKey} slotFor={slotFor} onSelect={selectCell}/></div>}
    {editing && <MenuEditorPanel date={editing.date} meal={editing.meal} slot={editing.slot} search={dishSearch} categoryId={dishCategoryId} categories={dishCategories} results={dishResults} searchTotal={dishTotal} searchPage={dishPage} searchLoading={dishLoading} searchInputRef={searchInputRef} onClose={requestCloseMeal} onSave={saveMealDraft} saving={saving} saveError={mealSaveError} onSlotNotes={notes => setMealDraftSlot({ ...editing.slot, notes })} onDishChange={(index, changes) => updateDish(editing.slot, index, changes)} onMove={(index, direction) => moveDish(editing.slot, index, direction)} onRemove={index => setConfirmation({ kind: 'remove-dish', index })} onSearch={value => { setDishSearch(value); setDishPage(1) }} onCategory={value => { setDishCategoryId(value); setDishPage(1) }} onSearchPage={setDishPage} onAdd={dish => addDish(editing.slot, dish)}/>}
    {dialog === 'meal' && <div className="modal-backdrop" onMouseDown={() => setDialog(null)}><section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="meal-title" onMouseDown={event => event.stopPropagation()}><header><h2 id="meal-title">餐別設定</h2><button className="secondary" onClick={() => setDialog(null)}>關閉</button></header><form className="inline-form" onSubmit={addMeal}><label>新餐別名稱<input autoFocus value={mealName} onChange={event => setMealName(event.target.value)} required/></label><button>新增餐別</button></form><div className="meal-list">{data.meal_types.map(meal => <div key={meal.id} className={!meal.is_active ? 'inactive' : ''}><label>名稱<input value={mealDrafts[meal.id] ?? meal.name} onChange={event => setMealDrafts({ ...mealDrafts, [meal.id]: event.target.value })}/></label><button className="secondary" aria-label={`${meal.name} 上移`} onClick={() => void moveMeal(meal, -1)}>上移</button><button className="secondary" aria-label={`${meal.name} 下移`} onClick={() => void moveMeal(meal, 1)}>下移</button><button onClick={() => void saveMeal(meal)}>儲存</button><button className="secondary" onClick={() => void toggleMeal(meal)}>{meal.is_active ? '停用' : '恢復'}</button></div>)}</div></section></div>}
    {dialog === 'copy' && <div className="modal-backdrop" onMouseDown={() => { if (!copySaving) setDialog(null) }}><section className="modal-panel copy-menu-dialog" role="dialog" aria-modal="true" aria-labelledby="copy-title" onMouseDown={event => event.stopPropagation()}><header><div><h2 id="copy-title">複製菜單</h2><p>清楚選擇要複製一天或整週，再決定目的已有內容時的處理方式。</p></div><button className="secondary" disabled={copySaving} onClick={() => setDialog(null)}>關閉</button></header>
      <fieldset className="copy-scope" disabled={copySaving}><legend>複製範圍</legend><label><input autoFocus type="radio" name="copy-scope" value="day" checked={copyScope === 'day'} onChange={() => { setCopyScope('day'); setCopyError(null) }}/>複製一天</label><label><input type="radio" name="copy-scope" value="week" checked={copyScope === 'week'} onChange={() => { setCopyScope('week'); setCopyError(null) }}/>複製整週</label></fieldset>
      <div className="copy-direction"><section><h3>來源</h3><div><strong>來源日期範圍</strong><label>開始日期<input disabled={copySaving} type="date" value={sourceFilterStart} onChange={event => { setSourceFilterStart(event.target.value); setCopyError(null) }}/></label><label>結束日期<input disabled={copySaving} type="date" value={sourceFilterEnd} onChange={event => { setSourceFilterEnd(event.target.value); setCopyError(null) }}/></label></div>{incompleteSourceRange ? <p className="field-hint">請選擇開始與結束日期。</p> : invalidSourceRange ? <p className="field-hint">開始日期不可晚於結束日期。</p> : null}<label>搜尋來源菜單<input disabled={copySaving||incompleteSourceRange||invalidSourceRange} value={sourceCandidates.search} onChange={event=>sourceCandidates.setSearch(event.target.value)}/></label><label>來源菜單<select disabled={copySaving || incompleteSourceRange || invalidSourceRange || sourceCandidates.loading || !sourceMenus.length} value={sourceMenu} onChange={event => { const value=event.target.value; const source=sourceMenus.find(item => item.id===value); setSourceMenu(value); if(source)setSourceDate(source.start_date); setCopyError(null) }}>{sourceMenus.map(item => <option key={item.id} value={item.id}>{item.name}（{displayDate(item.start_date)}～{displayDate(item.end_date)}）</option>)}</select></label>{sourceCandidates.error&&<p className="field-hint error">{sourceCandidates.error}</p>}{!incompleteSourceRange && !invalidSourceRange && !sourceCandidates.loading && !sourceMenus.length ? <p className="field-hint">這個日期範圍沒有可複製的菜單。</p> : selectedSourceMenu && copyScope === 'day' ? <label>來源日期<input disabled={copySaving} type="date" min={selectedSourceMenu.start_date} max={selectedSourceMenu.end_date} value={sourceDate} onChange={event => { setSourceDate(event.target.value); setCopyError(null) }}/></label> : selectedSourceMenu ? <p><strong>來源週</strong><span>{displayDate(selectedSourceMenu.start_date)} ～ {displayDate(selectedSourceMenu.end_date)}</span></p> : null}<PaginationControls page={sourceCandidates.page} pageSize={sourceCandidates.pageSize} total={sourceCandidates.total} onPage={sourceCandidates.setPage}/></section><span className="copy-arrow" aria-hidden="true">→</span><section><h3>複製到</h3><p><strong>{data.menu.name}</strong></p>{copyScope === 'day' ? <label>目的日期<input disabled={copySaving} type="date" value={destinationDate} onChange={event => { setDestinationDate(event.target.value); setCopyError(null) }}/></label> : <p><strong>目的週</strong><span>{displayDate(data.menu.start_date)} ～ {displayDate(data.menu.end_date)}</span></p>}</section></div>
      <Feedback type="info">複製時，目的菜單缺少的餐別會自動建立；目的既有的額外餐別會保留。</Feedback>
      <fieldset className="copy-conflict-mode" disabled={copySaving}><legend>目的已有內容時</legend><label><input type="radio" name="copy-mode" checked={copyMode === 'add'} onChange={() => { setCopyMode('add'); setConfirmReplace(false); setCopyError(null) }}/>加入並跳過重複</label><label><input type="radio" name="copy-mode" checked={copyMode === 'replace'} onChange={() => { setCopyMode('replace'); setCopyError(null) }}/>覆蓋目的內容</label></fieldset>
      {copyMode === 'replace' && <label className="confirm-box"><input disabled={copySaving} type="checkbox" checked={confirmReplace} onChange={event => setConfirmReplace(event.target.checked)}/>我了解目的{copyScope === 'day' ? '日期' : '整週'}原有餐格內容將被覆蓋。</label>}{copyError?.scope === copyScope && <Feedback type="error">{copyError.message}</Feedback>}
      <footer><button className="secondary" disabled={copySaving} onClick={() => setDialog(null)}>取消</button><button disabled={copySaving || incompleteSourceRange || invalidSourceRange || !sourceMenu || (copyMode === 'replace' && !confirmReplace)} onClick={() => void copy()}>{copySaving ? '複製中…' : copyScope === 'day' ? '複製這一天' : '複製整週'}</button></footer>
    </section></div>}
    {dialog === 'export' && <div className="modal-backdrop" onMouseDown={() => { if (!exporting) setDialog(null) }}><section className="modal-panel export-dialog" role="dialog" aria-modal="true" aria-labelledby="menu-export-title" onMouseDown={event => event.stopPropagation()}><header><div><h2 id="menu-export-title">匯出菜單</h2><p>選擇七日週表版型與單張或拼接列印方式。</p></div><button className="secondary" disabled={exporting} onClick={() => setDialog(null)}>關閉</button></header>
      <fieldset disabled={exporting}><legend>版型</legend><label><input autoFocus type="radio" name="menu-export-layout" checked={exportLayout === 'full'} onChange={() => { setExportLayout('full'); setExportError('') }}/>餐別合併週表</label><label><input type="radio" name="menu-export-layout" checked={exportLayout === 'grid'} onChange={() => { setExportLayout('grid'); setExportError('') }}/>菜色分格週表</label><label><input type="radio" name="menu-export-layout" checked={exportLayout === 'pretty'} onChange={() => { setExportLayout('pretty'); setExportVariant('single'); setExportError('') }}/>漂亮公告版</label></fieldset>
      <fieldset disabled={exporting}><legend>格式</legend><label><input type="radio" name="menu-export-format" checked={exportFormat === 'xlsx'} onChange={() => { setExportFormat('xlsx'); setExportError('') }}/>Excel</label><label><input type="radio" name="menu-export-format" checked={exportFormat === 'pdf'} onChange={() => { setExportFormat('pdf'); setExportVariant('single'); setExportError('') }}/>PDF（圖片型）</label></fieldset>
      {exportFormat === 'xlsx' && exportLayout !== 'pretty' && <fieldset disabled={exporting}><legend>紙張</legend><label><input type="radio" name="menu-export-variant" checked={exportVariant === 'single'} onChange={() => setExportVariant('single')}/>單張 A4</label><label><input type="radio" name="menu-export-variant" checked={exportVariant === 'poster'} onChange={() => setExportVariant('poster')}/>4張 A4 拼接放大</label></fieldset>}
      {exportError && <Feedback type="error">{exportError}</Feedback>}
      <footer><button className="secondary" disabled={exporting} onClick={() => setDialog(null)}>取消</button><button disabled={exporting} onClick={() => void downloadMenu()}>{exporting ? '匯出中…' : '匯出'}</button></footer>
    </section></div>}
    {confirmationContent && <MenuConfirmDialog title={confirmationContent.title} description={confirmationContent.description} confirmLabel={confirmationContent.label} onCancel={() => setConfirmation(null)} onConfirm={confirmationContent.action}/>}
  </section>
}
