import { FormEvent, useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'

type Kind = 'ingredient' | 'dish' | 'menu'
interface Category { id: string; name: string; sort_order: number; is_active: boolean }
interface CategoryList { items: Category[] }

export function CategoriesPage() {
  const [kind, setKind] = useState<Kind>('ingredient')
  const [items, setItems] = useState<Category[]>([])
  const [name, setName] = useState('')
  const [sortOrder, setSortOrder] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => { setLoading(true); try { setItems((await apiRequest<CategoryList>(`/categories/${kind}`)).items); setError('') } catch { setError('分類載入失敗') } finally { setLoading(false) } }, [kind])
  useEffect(() => { void load() }, [load])
  async function create(event: FormEvent) { event.preventDefault(); try { await apiRequest(`/categories/${kind}`, { method: 'POST', body: JSON.stringify({ name, sort_order: sortOrder }) }); setName(''); await load() } catch { setError('分類新增失敗') } }
  async function edit(item: Category) { const next = window.prompt('分類名稱', item.name); if (!next) return; await apiRequest(`/categories/${kind}/${item.id}`, { method: 'PATCH', body: JSON.stringify({ name: next }) }); await load() }
  async function toggle(item: Category) { await apiRequest(`/categories/${kind}/${item.id}/${item.is_active ? 'deactivate' : 'reactivate'}`, { method: 'POST' }); await load() }
  async function hardDelete(item: Category) { if (!window.confirm('永久刪除後無法復原')) return; const password = window.prompt('請重新輸入目前帳號密碼'); if (!password) return; try { await apiRequest(`/categories/${kind}/${item.id}/hard-delete`, { method: 'POST', body: JSON.stringify({ password }) }); await load() } catch { setError('資料被引用、密碼錯誤或不可永久刪除') } }
  return <section><h2>分類管理</h2><div className="toolbar"><select value={kind} onChange={e => setKind(e.target.value as Kind)}><option value="ingredient">食材分類</option><option value="dish">菜色分類</option><option value="menu">菜單分類</option></select></div><form className="panel-form" onSubmit={create}><label>名稱<input value={name} onChange={e => setName(e.target.value)} required /></label><label>排序<input type="number" min="0" value={sortOrder} onChange={e => setSortOrder(Number(e.target.value))} /></label><button>新增分類</button></form>{error && <p className="error">{error}</p>}{loading ? <p>載入中…</p> : <table><thead><tr><th>名稱</th><th>排序</th><th>狀態</th><th>操作</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{item.name}</td><td>{item.sort_order}</td><td>{item.is_active ? '啟用' : '停用'}</td><td className="actions"><button onClick={() => void edit(item)}>修改</button><button onClick={() => void toggle(item)}>{item.is_active ? '停用' : '恢復'}</button><button className="danger" onClick={() => void hardDelete(item)}>永久刪除</button></td></tr>)}</tbody></table>}</section>
}
