import { RefObject } from 'react'
import { DishOption, MealType, MenuDish, MenuSlot } from './types'
import { DishSearchPicker } from './DishSearchPicker'

interface Props {
  date: string
  meal: MealType
  slot: MenuSlot
  search: string
  results: DishOption[]
  searchTotal: number
  searchPage: number
  searchLoading: boolean
  searchInputRef: RefObject<HTMLInputElement | null>
  onClose: () => void
  onSlotNotes: (notes: string | null) => void
  onDishChange: (index: number, changes: Partial<MenuDish>) => void
  onMove: (index: number, direction: -1 | 1) => void
  onRemove: (index: number) => void
  onSearch: (value: string) => void
  onSearchPage: (page: number) => void
  onAdd: (dish: DishOption) => void
}

function headerDate(date: string) {
  const value = new Date(`${date}T00:00:00`)
  return `${date}　${value.toLocaleDateString('zh-TW', { weekday: 'long' })}`
}

export function MenuEditorPanel(props: Props) {
  const { date, meal, slot } = props
  return <aside className="menu-editor-drawer" aria-labelledby="cell-editor-title">
    <header><div><p className="eyebrow">正在編輯</p><h2 id="cell-editor-title">{headerDate(date)}</h2><strong>{meal.name}</strong></div><button className="secondary drawer-close" onClick={props.onClose} aria-label="關閉餐格編輯器">關閉</button></header>
    <label className="slot-note">本餐備註<input value={slot.notes ?? ''} onChange={event => props.onSlotNotes(event.target.value || null)} placeholder="例如：本餐供應時間調整"/></label>
    <section className="scheduled-list" aria-labelledby="scheduled-title"><div className="drawer-section-title"><h3 id="scheduled-title">已排菜色</h3><span>{slot.dishes.length} 道</span></div>
      {slot.dishes.length ? slot.dishes.map((dish, index) => <article className="scheduled-dish" key={dish.id ?? dish.dish_id}>
        <div className="scheduled-dish-title"><div><strong>{dish.dish_name}</strong><small>{dish.dish_code}{dish.dish_category_name ? `・${dish.dish_category_name}` : ''}</small></div><div className="dish-order-actions"><button className="secondary compact" disabled={index === 0} onClick={() => props.onMove(index, -1)} aria-label={`${dish.dish_name} 上移`}>↑ 上移</button><button className="secondary compact" disabled={index === slot.dishes.length - 1} onClick={() => props.onMove(index, 1)} aria-label={`${dish.dish_name} 下移`}>↓ 下移</button></div></div>
        <div className="dish-fields"><label>人數<input type="number" min="0" step="1" inputMode="numeric" value={dish.diner_count} onChange={event => props.onDishChange(index, { diner_count: Math.max(0, Number.parseInt(event.target.value || '0', 10)) })}/></label><label>菜色備註<input value={dish.notes ?? ''} onChange={event => props.onDishChange(index, { notes: event.target.value || null })} placeholder="此菜色的備註"/></label></div>
        <button className="remove-relation" onClick={() => props.onRemove(index)} aria-label={`移除 ${dish.dish_name}`}>移除 {dish.dish_name}</button>
      </article>) : <p className="drawer-empty">本餐尚未安排菜色，可從下方搜尋加入。</p>}
    </section>
    <DishSearchPicker search={props.search} results={props.results} total={props.searchTotal} page={props.searchPage} disabled={!meal.is_active} loading={props.searchLoading} inputRef={props.searchInputRef} onSearch={props.onSearch} onPage={props.onSearchPage} onAdd={props.onAdd}/>
    {!meal.is_active && <p className="feedback feedback-info">此餐別已停用，只能查看或修改既有內容，不能新增菜色。</p>}
  </aside>
}
