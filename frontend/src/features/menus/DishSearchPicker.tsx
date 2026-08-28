import { RefObject } from 'react'
import { DishOption } from './types'

interface Props {
  search: string
  results: DishOption[]
  total: number
  page: number
  disabled: boolean
  loading: boolean
  inputRef: RefObject<HTMLInputElement | null>
  onSearch: (value: string) => void
  onPage: (page: number) => void
  onAdd: (dish: DishOption) => void
}

export function DishSearchPicker({ search, results, total, page, disabled, loading, inputRef, onSearch, onPage, onAdd }: Props) {
  return <section className="dish-picker" aria-labelledby="dish-search-title">
    <label id="dish-search-title">搜尋並加入菜色
      <input ref={inputRef} value={search} onChange={event => onSearch(event.target.value)} placeholder="輸入菜色名稱或代碼" autoComplete="off" disabled={disabled}/>
    </label>
    {search.trim() && <div className="dish-results" role="listbox" aria-label="菜色搜尋結果">
      {loading ? <p>搜尋中…</p> : results.length ? results.map(dish => <button key={dish.id} className="dish-result" role="option" onClick={() => onAdd(dish)} disabled={disabled}>
        <span><strong>{dish.name}</strong><small>{dish.code}{dish.category_name ? `・${dish.category_name}` : ''}</small></span><span aria-hidden="true">＋</span>
      </button>) : <p>沒有符合的啟用菜色。</p>}
    </div>}
    {total > 10 && <div className="dish-result-pages"><span>共 {total} 筆</span><button className="link-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>上一頁</button><button className="link-button" disabled={page * 10 >= total} onClick={() => onPage(page + 1)}>下一頁</button></div>}
  </section>
}
