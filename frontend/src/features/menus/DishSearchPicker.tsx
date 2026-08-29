import { RefObject } from 'react'
import { DishCategoryOption, DishOption } from './types'

interface Props {
  search: string
  categoryId: string
  categories: DishCategoryOption[]
  results: DishOption[]
  addedIds: Set<string>
  total: number
  page: number
  disabled: boolean
  loading: boolean
  inputRef: RefObject<HTMLInputElement | null>
  onSearch: (value: string) => void
  onCategory: (value: string) => void
  onPage: (page: number) => void
  onAdd: (dish: DishOption) => void
}

const PAGE_SIZE = 20

export function DishSearchPicker({ search, categoryId, categories, results, addedIds, total, page, disabled, loading, inputRef, onSearch, onCategory, onPage, onAdd }: Props) {
  const first = total ? (page - 1) * PAGE_SIZE + 1 : 0
  const last = Math.min(page * PAGE_SIZE, total)
  const hasCriteria = Boolean(search.trim() || categoryId)
  return <section className="dish-picker" aria-labelledby="dish-search-title">
    <h3 id="dish-search-title">搜尋並加入菜色</h3>
    <div className="dish-search-controls"><label>菜色分類<select value={categoryId} onChange={event => onCategory(event.target.value)} disabled={disabled}><option value="">全部分類</option>{categories.filter(item => item.is_active).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>菜名或代碼<input ref={inputRef} value={search} onChange={event => onSearch(event.target.value)} placeholder="輸入菜色名稱或代碼" autoComplete="off" disabled={disabled}/></label></div>
    {!hasCriteria ? <p className="dish-search-hint">請選擇分類或輸入關鍵字開始搜尋。</p> : <><div className="dish-result-toolbar"><div className="dish-result-summary" aria-live="polite">{loading ? '搜尋中…' : `找到 ${total} 道${total ? `｜${first}–${last} / ${total}` : ''}`}</div>{total > PAGE_SIZE && <div className="dish-result-pages"><button className="link-button" disabled={loading || page <= 1} onClick={() => onPage(page - 1)}>上一頁</button><button className="link-button" disabled={loading || page * PAGE_SIZE >= total} onClick={() => onPage(page + 1)}>下一頁</button></div>}</div><div className="dish-results" aria-label="菜色搜尋結果">
      {loading ? <p>搜尋中…</p> : results.length ? results.map(dish => { const added = addedIds.has(dish.id); return <div key={dish.id} className="dish-result">
        <span><strong>{dish.name}</strong><small>{dish.code}{dish.category_name ? `・${dish.category_name}` : ''}{`・${dish.recipe_ingredient_count} 項配料`}</small></span><button className="secondary compact" onClick={() => onAdd(dish)} disabled={disabled || added}>{added ? '已加入' : '加入'}</button>
      </div> }) : <p>找不到符合條件的菜色</p>}
    </div></>}
  </section>
}
