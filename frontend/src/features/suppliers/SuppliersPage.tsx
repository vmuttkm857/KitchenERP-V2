import { FormEvent, useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'

interface Supplier { id: string; code: string; name: string; phone: string | null; is_active: boolean }
interface SupplierList { items: Supplier[] }

export function SuppliersPage() {
  const [items, setItems] = useState<Supplier[]>([]); const [code, setCode] = useState(''); const [name, setName] = useState(''); const [phone, setPhone] = useState(''); const [error, setError] = useState(''); const [loading, setLoading] = useState(true)
  const load = useCallback(async () => { setLoading(true); try { setItems((await apiRequest<SupplierList>('/suppliers')).items); setError('') } catch { setError('供應商載入失敗') } finally { setLoading(false) } }, [])
  useEffect(() => { void load() }, [load])
  async function create(event: FormEvent) { event.preventDefault(); try { await apiRequest('/suppliers', { method: 'POST', body: JSON.stringify({ code, name, phone: phone || null }) }); setCode(''); setName(''); setPhone(''); await load() } catch { setError('供應商新增失敗') } }
  async function edit(item: Supplier) { const next = window.prompt('供應商名稱', item.name); if (!next) return; await apiRequest(`/suppliers/${item.id}`, { method: 'PATCH', body: JSON.stringify({ name: next }) }); await load() }
  async function toggle(item: Supplier) { await apiRequest(`/suppliers/${item.id}/${item.is_active ? 'deactivate' : 'reactivate'}`, { method: 'POST' }); await load() }
  async function hardDelete(item: Supplier) { if (!window.confirm('永久刪除後無法復原')) return; const password = window.prompt('請重新輸入目前帳號密碼'); if (!password) return; try { await apiRequest(`/suppliers/${item.id}/hard-delete`, { method: 'POST', body: JSON.stringify({ password }) }); await load() } catch { setError('供應商被引用、密碼錯誤或不可永久刪除') } }
  return <section><h2>供應商管理</h2><form className="panel-form" onSubmit={create}><label>代碼<input value={code} onChange={e => setCode(e.target.value)} required /></label><label>名稱<input value={name} onChange={e => setName(e.target.value)} required /></label><label>電話<input value={phone} onChange={e => setPhone(e.target.value)} /></label><button>新增供應商</button></form>{error && <p className="error">{error}</p>}{loading ? <p>載入中…</p> : <table><thead><tr><th>代碼</th><th>名稱</th><th>電話</th><th>狀態</th><th>操作</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{item.code}</td><td>{item.name}</td><td>{item.phone}</td><td>{item.is_active ? '啟用' : '停用'}</td><td className="actions"><button onClick={() => void edit(item)}>修改</button><button onClick={() => void toggle(item)}>{item.is_active ? '停用' : '恢復'}</button><button className="danger" onClick={() => void hardDelete(item)}>永久刪除</button></td></tr>)}</tbody></table>}</section>
}
