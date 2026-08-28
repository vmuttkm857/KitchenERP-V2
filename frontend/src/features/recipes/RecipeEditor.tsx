import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api/client'
import type { Dish } from '../dishes/DishesPage'

interface Ingredient { id: string; code: string; name: string; unit: string; supplier_name: string | null }
interface RecipeItem { id?: string; ingredient_id: string; ingredient_code?: string; ingredient_name?: string; ingredient_unit?: string; supplier_name?: string | null; quantity: string; unit: string; loss_rate: string; sort_order: number; notes: string | null; item_cost?: string | null; cost_needs_review?: boolean }
interface Recipe { dish: Dish; items: RecipeItem[]; total_cost: string | null; cost_needs_review: boolean; requirement_ready: boolean }
interface List<T> { items: T[] }

export function RecipeEditor({ dish, onClose }: { dish: Dish; onClose: () => void }) {
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [ingredients, setIngredients] = useState<Ingredient[]>([])
  const [selectedIngredient, setSelectedIngredient] = useState('')
  const [ingredientSearch, setIngredientSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [current, candidates] = await Promise.all([
        apiRequest<Recipe>(`/dishes/${dish.id}/recipe`),
        apiRequest<List<Ingredient>>(`/ingredients?active=true&page_size=100&search=${encodeURIComponent(ingredientSearch)}`),
      ])
      setRecipe(current)
      setIngredients(candidates.items)
      setError('')
    } catch { setError('配方資料載入失敗') }
    finally { setLoading(false) }
  }, [dish.id, ingredientSearch])

  useEffect(() => { void load() }, [load])

  function addIngredient() {
    const ingredient = ingredients.find(item => item.id === selectedIngredient)
    if (!ingredient || !recipe || recipe.items.some(item => item.ingredient_id === ingredient.id)) return
    setRecipe({ ...recipe, items: [...recipe.items, {
      ingredient_id: ingredient.id, ingredient_code: ingredient.code, ingredient_name: ingredient.name,
      ingredient_unit: ingredient.unit, supplier_name: ingredient.supplier_name,
      quantity: '0', unit: ingredient.unit, loss_rate: '0', sort_order: recipe.items.length + 1, notes: null,
    }] })
    setSelectedIngredient('')
  }

  function update(index: number, changes: Partial<RecipeItem>) {
    if (!recipe) return
    setRecipe({ ...recipe, items: recipe.items.map((item, position) => position === index ? { ...item, ...changes } : item) })
  }

  function remove(index: number) {
    if (!recipe || !window.confirm('只移除此配方關聯，不會刪除食材主檔。確定移除？')) return
    setRecipe({ ...recipe, items: recipe.items.filter((_, position) => position !== index) })
  }

  async function save() {
    if (!recipe) return
    setSaving(true); setMessage('')
    try {
      const saved = await apiRequest<Recipe>(`/dishes/${dish.id}/recipe`, { method: 'PUT', body: JSON.stringify({ items: recipe.items.map(item => ({ id: item.id, ingredient_id: item.ingredient_id, quantity: item.quantity, unit: item.unit, loss_rate: item.loss_rate, sort_order: item.sort_order, notes: item.notes })) }) })
      setRecipe(saved); setError(''); setMessage('配方已完整儲存')
    } catch { setError('配方儲存失敗；所有變更均未寫入，請檢查食材、數量、單位與耗損率') }
    finally { setSaving(false) }
  }

  if (loading || !recipe) return <section><button onClick={onClose}>返回菜色</button><p>{loading ? '配方載入中…' : error}</p></section>
  return <section>
    <div className="section-heading"><div><p className="eyebrow">標準配方</p><h2>{dish.code}｜{dish.name}</h2></div><button onClick={onClose}>返回菜色</button></div>
    <div className="recipe-picker"><label>搜尋候選食材<input value={ingredientSearch} onChange={event => setIngredientSearch(event.target.value)} /></label><label>選擇食材<select value={selectedIngredient} onChange={event => setSelectedIngredient(event.target.value)}><option value="">請選擇</option>{ingredients.filter(candidate => !recipe.items.some(item => item.ingredient_id === candidate.id)).map(item => <option key={item.id} value={item.id}>{item.code}｜{item.name}｜{item.supplier_name ?? '無供應商'}</option>)}</select></label><button type="button" onClick={addIngredient} disabled={!selectedIngredient}>加入配方</button></div>
    {error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}
    <table><thead><tr><th>順序</th><th>食材</th><th>每人用量</th><th>配方單位</th><th>耗損率 %</th><th>備註</th><th>成本</th><th>操作</th></tr></thead><tbody>{recipe.items.map((item, index) => <tr key={item.id ?? item.ingredient_id}><td><input type="number" min="0" value={item.sort_order} onChange={event => update(index, { sort_order: Number(event.target.value) })} /></td><td>{item.ingredient_code}｜{item.ingredient_name}<small>{item.supplier_name ? `｜${item.supplier_name}` : ''}</small></td><td><input type="number" min="0" step="0.000001" value={item.quantity} onChange={event => update(index, { quantity: event.target.value })} /></td><td><input value={item.unit} onChange={event => update(index, { unit: event.target.value })} /></td><td><input type="number" min="0" step="0.000001" value={item.loss_rate} onChange={event => update(index, { loss_rate: event.target.value })} /></td><td><input value={item.notes ?? ''} onChange={event => update(index, { notes: event.target.value || null })} /></td><td>{item.cost_needs_review ? '待確認' : item.item_cost ?? '儲存後計算'}</td><td><button className="danger" onClick={() => remove(index)}>移除關聯</button></td></tr>)}</tbody></table>
    <div className="recipe-summary"><strong>單份成本：{recipe.cost_needs_review ? '待確認' : recipe.total_cost ?? '0'}</strong><span>{recipe.requirement_ready ? '可供需求計算' : '草稿：尚有 quantity = 0，不可供需求計算'}</span><button onClick={() => void save()} disabled={saving}>{saving ? '儲存中…' : '儲存完整配方'}</button></div>
  </section>
}
