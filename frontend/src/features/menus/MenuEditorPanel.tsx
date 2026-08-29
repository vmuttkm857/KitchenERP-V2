import { KeyboardEvent, RefObject, useRef } from 'react'
import { Feedback } from '../../components/ui/Page'
import { DishCategoryOption, DishOption, MealType, MenuDish, MenuSlot } from './types'
import { DishSearchPicker } from './DishSearchPicker'

interface Props {
  date: string
  meal: MealType
  slot: MenuSlot
  search: string
  categoryId: string
  categories: DishCategoryOption[]
  results: DishOption[]
  searchTotal: number
  searchPage: number
  searchLoading: boolean
  searchInputRef: RefObject<HTMLInputElement | null>
  onClose: () => void
  onSave: () => Promise<void>
  saving: boolean
  saveError: string
  onSlotNotes: (notes: string | null) => void
  onDishChange: (index: number, changes: Partial<MenuDish>) => void
  onMove: (index: number, direction: -1 | 1) => void
  onRemove: (index: number) => void
  onSearch: (value: string) => void
  onCategory: (value: string) => void
  onSearchPage: (page: number) => void
  onAdd: (dish: DishOption) => void
}

function headerDate(date: string) {
  const value = new Date(`${date}T00:00:00`)
  return `${date}　${value.toLocaleDateString('zh-TW', { weekday: 'long' })}`
}

export function MenuEditorPanel(props: Props) {
  const { date, meal, slot } = props
  const dialogRef = useRef<HTMLElement>(null)
  function keepFocusInside(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== 'Tab' || !dialogRef.current) return
    const controls = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'))
    if (!controls.length) return
    const first = controls[0], last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  return <div className="modal-backdrop"><section ref={dialogRef} className="modal-panel meal-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="cell-editor-title" onKeyDown={keepFocusInside}>
    <header><div><p className="eyebrow">編輯餐次</p><h2 id="cell-editor-title">{headerDate(date)}</h2><strong>{meal.name}</strong></div><button autoFocus className="secondary drawer-close" onClick={props.onClose} aria-label="關閉餐次編輯器">關閉</button></header>
    <label className="slot-note meal-slot-note">本餐備註<input value={slot.notes ?? ''} onChange={event => props.onSlotNotes(event.target.value || null)} placeholder="例如：本餐供應時間調整"/></label>
    <div className="meal-editor-content"><div className="meal-editor-panes">
      <section className="scheduled-pane" aria-labelledby="scheduled-title"><h3 id="scheduled-title">已排菜色 {slot.dishes.length} 道</h3><div className="scheduled-list">
        {slot.dishes.length ? slot.dishes.map((dish, index) => <article className="scheduled-dish" key={dish.id ?? dish.dish_id}>
          <div className="scheduled-dish-title" title={dish.dish_name}><strong>{dish.dish_name}</strong><small>{dish.dish_code}{dish.dish_category_name ? `・${dish.dish_category_name}` : ''}</small></div>
          <div className="dish-order-actions"><button className="secondary compact" disabled={index === 0} onClick={() => props.onMove(index, -1)} aria-label={`${dish.dish_name} 上移`}>↑ 上移</button><button className="secondary compact" disabled={index === slot.dishes.length - 1} onClick={() => props.onMove(index, 1)} aria-label={`${dish.dish_name} 下移`}>↓ 下移</button></div>
          <div className="dish-fields"><label>人數<input type="number" min="0" step="1" inputMode="numeric" value={dish.diner_count} onChange={event => props.onDishChange(index, { diner_count: Math.max(0, Number.parseInt(event.target.value || '0', 10)) })}/></label><label>菜色備註<input value={dish.notes ?? ''} onChange={event => props.onDishChange(index, { notes: event.target.value || null })} placeholder="此菜色的備註"/></label></div>
          <button className="remove-dish-button" title="移除菜色" onClick={() => props.onRemove(index)} aria-label={`移除菜色：${dish.dish_name}`}>×</button>
        </article>) : <p className="drawer-empty">本餐尚未安排菜色，可從右側搜尋加入。</p>}
      </div></section>
      <div className="dish-search-pane"><DishSearchPicker search={props.search} categoryId={props.categoryId} categories={props.categories} results={props.results} addedIds={new Set(slot.dishes.map(item => item.dish_id))} total={props.searchTotal} page={props.searchPage} disabled={!meal.is_active} loading={props.searchLoading} inputRef={props.searchInputRef} onSearch={props.onSearch} onCategory={props.onCategory} onPage={props.onSearchPage} onAdd={props.onAdd}/>{!meal.is_active && <p className="feedback feedback-info">此餐別已停用，只能查看或修改既有內容，不能新增菜色。</p>}</div>
    </div></div>
    {props.saveError && <Feedback type="error">{props.saveError}</Feedback>}
    <footer><button className="secondary" disabled={props.saving} onClick={props.onClose}>取消</button><button disabled={props.saving} onClick={() => void props.onSave()}>{props.saving ? '儲存中…' : '儲存本餐'}</button></footer>
  </section></div>
}
