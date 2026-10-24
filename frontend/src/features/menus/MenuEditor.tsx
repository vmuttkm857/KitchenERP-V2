import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiDownload, apiRequest } from '../../api/client'
import { Feedback, LoadingState } from '../../components/ui/Page'
import { MenuMealEditorDialog } from './MenuMealEditorDialog'
import { MenuColumnDialog } from './MenuColumnDialog'
import { MenuWeekGrid } from './MenuWeekGrid'
import { menuDishMovePayload, menuSlotsVisuallyEquivalent, mergeAuthoritativeSlotMetadata, optimisticallyInsertMenuDish } from './menuDrag'
import type { MenuDishInsertTarget } from './menuDrag'
import { MealType, Menu, MenuAggregate, MenuSlot } from './types'
import { useEditorDirty } from '../../app/NavigationBlocker'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { useMenuCandidates } from './useMenuCandidates'
import { MenuProductionDialog } from '../production/MenuProductionDialog'

const slotKey = (date: string, mealId: string) => `${date}:${mealId}`
const displayDate = (value: string) => value.replaceAll('-', '/')
function shiftDate(value: string, days: number) {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + days))
  return date.toISOString().slice(0, 10)
}

export function MenuEditor({ menu, onClose }: { menu: Menu; onClose: () => void }) {
  const [data, setData] = useState<MenuAggregate | null>(null)
  const [slots, setSlots] = useState<Record<string, MenuSlot>>({})
  const [mealName, setMealName] = useState('')
  const [mealDrafts, setMealDrafts] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [movingDish,setMovingDish]=useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [dialog, setDialog] = useState<'meal' | 'copy' | 'export' | 'production' | null>(null)
  const [exportLayout, setExportLayout] = useState<'full' | 'grid' | 'pretty'>('full')
  const [exportFormat, setExportFormat] = useState<'xlsx' | 'pdf'>('xlsx')
  const [exportVariant, setExportVariant] = useState<'single' | 'poster'>('single')
  const [exportNutrition, setExportNutrition] = useState<'none' | 'calories' | 'detailed'>('none')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [columnMealId,setColumnMealId]=useState<string|null>(null)
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
  const mealTypeDirty = Boolean(mealName.trim()) || Boolean(data?.meal_types.some(meal => (mealDrafts[meal.id] ?? meal.name) !== meal.name))
  useEditorDirty(mealTypeDirty)

  const applyAggregate = useCallback((aggregate: MenuAggregate) => {
    setData(aggregate)
    setMealDrafts(Object.fromEntries(aggregate.meal_types.map(meal => [meal.id, meal.name])))
    setSlots(Object.fromEntries(aggregate.slots.map(slot => [slotKey(slot.menu_date, slot.menu_meal_type_id), slot])))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      applyAggregate(await apiRequest<MenuAggregate>(`/menus/${menu.id}/editor`)); setError('')
    } catch { setError('菜單工作區載入失敗') }
    finally { setLoading(false) }
  }, [applyAggregate, menu.id])

  useEffect(() => { void load() }, [load])

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
  function selectCell(date: string, meal: MealType) {
    setEditingKey(slotKey(date, meal.id)); setError('')
  }
  function openDialog(next: 'meal' | 'copy' | 'export' | 'production') {
    if (next === 'copy') setCopyError(null)
    if (next === 'export') setExportError('')
    setDialog(next)
  }

  async function downloadMenu() {
    setExporting(true); setExportError('')
    try {
      const nutritionQuery=exportNutrition==='none'?'':`&nutrition=${exportNutrition}`
      await apiDownload(`/exports/menus/${menu.id}/${exportLayout}/${exportFormat}?variant=${exportVariant}${nutritionQuery}`)
      setDialog(null)
    } catch { setExportError('菜單匯出失敗，請稍後再試。') }
    finally { setExporting(false) }
  }

  function mealSaved(aggregate: MenuAggregate) {
    // Applying a slot response must not discard unsaved meal-type names in the parent.
    setMealDrafts(current => Object.fromEntries(aggregate.meal_types.map(meal => {
      const previous = data?.meal_types.find(item => item.id === meal.id)
      return [meal.id, previous && current[meal.id] !== undefined && current[meal.id] !== previous.name ? current[meal.id] : meal.name]
    })))
    setData(aggregate)
    setSlots(Object.fromEntries(aggregate.slots.map(slot => [slotKey(slot.menu_date, slot.menu_meal_type_id), slot])))
    setMessage('本餐已儲存')
  }
  async function moveMenuDish(sourceMenuDishId:string,target:MenuDishInsertTarget){
    if(movingDish)return
    const optimistic=optimisticallyInsertMenuDish(slots,data?.meal_type_columns??[],sourceMenuDishId,target)
    if(!optimistic){setError('此位置無法安全移動菜色，請重新載入後再試。');return}
    setSlots(optimistic)
    setMovingDish(true);setError('');setMessage('')
    try{
      const aggregate=await apiRequest<MenuAggregate>(`/menus/${menu.id}/dish-move`,{method:'POST',body:JSON.stringify(menuDishMovePayload(sourceMenuDishId,target))})
      if(menuSlotsVisuallyEquivalent(optimistic,aggregate.slots)){
        setSlots(current=>mergeAuthoritativeSlotMetadata(current,aggregate.slots))
      }else applyAggregate(aggregate)
      setMessage('菜色已移動')
    }catch{
      setError('菜色移動失敗，已重新載入目前菜單。')
      try{applyAggregate(await apiRequest<MenuAggregate>(`/menus/${menu.id}/editor`))}catch{setError('菜色移動失敗，且重新載入菜單失敗；請重新開啟菜單。')}
    }finally{setMovingDish(false)}
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
  const editing = editingKey ? { date: editingKey.split(':')[0], mealId: editingKey.split(':')[1] } : null
  const selectedSourceMenu = sourceMenus.find(item => item.id === sourceMenu)

  return <section className="menu-editor-page">
    <header className="page-header"><div><p className="eyebrow">菜單編輯</p><h1>{data.menu.name}</h1><p>{data.menu.start_date} ～ {data.menu.end_date}</p></div><div className="page-actions"><button className="secondary" onClick={() => openDialog('meal')}>餐別設定</button><button className="secondary" onClick={() => openDialog('copy')}>複製菜單</button><button className="secondary" onClick={() => openDialog('export')}>匯出</button><button onClick={() => openDialog('production')}>標準食譜卡／廚房製作單</button><button className="secondary" onClick={onClose}>返回</button></div></header>
    {error && <Feedback type="error">{error}</Feedback>}{message && <Feedback type="success">{message}</Feedback>}
    {!meals.length ? <div className="state-panel">請先從「餐別設定」建立至少一個啟用餐別。</div> : <div className="menu-editor-workspace"><MenuWeekGrid dates={data.dates} meals={meals} columns={data.meal_type_columns} selectedKey={editingKey} slotFor={slotFor} onSelect={selectCell} onEditColumns={meal=>setColumnMealId(meal.id)} onMoveDish={moveMenuDish} movingDish={movingDish}/></div>}
    {columnMealId&&<MenuColumnDialog menuId={menu.id} meal={data.meal_types.find(meal=>meal.id===columnMealId)!} columns={data.meal_type_columns.filter(column=>column.menu_meal_type_id===columnMealId)} onChanged={load} onClose={()=>setColumnMealId(null)}/>}
    {editing && <MenuMealEditorDialog menuId={menu.id} date={editing.date} mealTypeId={editing.mealId} onSaved={mealSaved} onClose={() => setEditingKey(null)}/>}
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
      <fieldset disabled={exporting}><legend>顯示營養資訊</legend><label><input type="radio" name="menu-export-nutrition" checked={exportNutrition === 'none'} onChange={() => setExportNutrition('none')}/>不顯示（維持原版）</label><label><input type="radio" name="menu-export-nutrition" checked={exportNutrition === 'calories'} onChange={() => setExportNutrition('calories')}/>熱量版</label><label><input type="radio" name="menu-export-nutrition" checked={exportNutrition === 'detailed'} onChange={() => { setExportNutrition('detailed'); setExportVariant('single') }}/>熱量＋詳細營養</label></fieldset>
      {exportFormat === 'xlsx' && exportLayout !== 'pretty' && <fieldset disabled={exporting}><legend>紙張</legend><label><input type="radio" name="menu-export-variant" checked={exportVariant === 'single'} onChange={() => setExportVariant('single')}/>單張 A4</label><label><input type="radio" name="menu-export-variant" disabled={exportNutrition === 'detailed'} checked={exportVariant === 'poster'} onChange={() => setExportVariant('poster')}/>4張 A4 拼接放大{exportNutrition === 'detailed'?'（詳細營養不支援）':''}</label></fieldset>}
      {exportError && <Feedback type="error">{exportError}</Feedback>}
      <footer><button className="secondary" disabled={exporting} onClick={() => setDialog(null)}>取消</button><button disabled={exporting} onClick={() => void downloadMenu()}>{exporting ? '匯出中…' : '匯出'}</button></footer>
    </section></div>}
    {dialog === 'production' && <MenuProductionDialog menu={data.menu} dates={data.dates} meals={data.meal_types} onClose={()=>setDialog(null)}/>}
  </section>
}
