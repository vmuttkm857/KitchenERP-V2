import { FormEvent, useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'

interface Category { id: string; name: string; is_active: boolean }
export interface Dish { id: string; code: string; name: string; category_id: string | null; category_name: string | null; notes: string | null; is_active: boolean }
interface List<T> { items: T[] }

export function DishesPage({ onEditRecipe }: { onEditRecipe: (dish: Dish) => void }) {
  const [items, setItems] = useState<Dish[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [notes, setNotes] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [dishes, dishCategories] = await Promise.all([
        apiRequest<List<Dish>>(`/dishes?page_size=100&search=${encodeURIComponent(search)}`),
        apiRequest<List<Category>>('/categories/dish?active=true&page_size=100'),
      ])
      setItems(dishes.items)
      setCategories(dishCategories.items)
      setError('')
    } catch { setError('菜色資料載入失敗') }
    finally { setLoading(false) }
  }, [search])

  useEffect(() => { void load() }, [load])

  async function create(event: FormEvent) {
    event.preventDefault()
    try {
      await apiRequest('/dishes', { method: 'POST', body: JSON.stringify({ code, name, category_id: categoryId || null, notes: notes || null }) })
      setCode(''); setName(''); setNotes(''); await load()
    } catch { setError('菜色新增失敗，請確認代碼、名稱與分類') }
  }

  async function edit(item: Dish) {
    const nextName = window.prompt('菜色名稱', item.name)
    if (!nextName) return
    const nextNotes = window.prompt('備註', item.notes ?? '')
    if (nextNotes === null) return
    try { await apiRequest(`/dishes/${item.id}`, { method: 'PATCH', body: JSON.stringify({ name: nextName, notes: nextNotes || null }) }); await load() }
    catch { setError('菜色修改失敗') }
  }

  async function toggle(item: Dish) {
    try { await apiRequest(`/dishes/${item.id}/${item.is_active ? 'deactivate' : 'reactivate'}`, { method: 'POST' }); await load() }
    catch { setError('菜色狀態更新失敗') }
  }

  async function hardDelete(item: Dish) {
    if (!window.confirm('永久刪除菜色後無法復原；已有配方或其他引用時會拒絕')) return
    const password = window.prompt('請重新輸入目前帳號密碼')
    if (!password) return
    try { await apiRequest(`/dishes/${item.id}/hard-delete`, { method: 'POST', body: JSON.stringify({ password }) }); await load() }
    catch { setError('菜色已有配方或其他引用，無法永久刪除') }
  }

  return <section>
    <h2>菜色管理</h2>
    <form className="panel-form" onSubmit={create}>
      <label>代碼<input value={code} onChange={event => setCode(event.target.value)} required /></label>
      <label>名稱<input value={name} onChange={event => setName(event.target.value)} required /></label>
      <label>分類<select value={categoryId} onChange={event => setCategoryId(event.target.value)}><option value="">未分類</option>{categories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>備註<input value={notes} onChange={event => setNotes(event.target.value)} /></label>
      <button>新增菜色</button>
    </form>
    <div className="toolbar"><label>搜尋<input value={search} onChange={event => setSearch(event.target.value)} /></label><button type="button" onClick={() => void load()}>重新整理</button></div>
    {error && <p className="error">{error}</p>}
    {loading ? <p>載入中…</p> : <table><thead><tr><th>代碼</th><th>名稱</th><th>分類</th><th>狀態</th><th>操作</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{item.code}</td><td>{item.name}</td><td>{item.category_name ?? '未分類'}</td><td>{item.is_active ? '啟用' : '停用'}</td><td className="actions"><button onClick={() => onEditRecipe(item)}>標準配方</button><button onClick={() => void edit(item)}>修改</button><button onClick={() => void toggle(item)}>{item.is_active ? '停用' : '恢復'}</button><button className="danger" onClick={() => void hardDelete(item)}>永久刪除</button></td></tr>)}</tbody></table>}
  </section>
}
