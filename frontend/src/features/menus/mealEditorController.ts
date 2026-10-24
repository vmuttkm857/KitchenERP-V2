import type { DishCategoryOption, DishOption, List, MenuAggregate, MenuDish, MenuMealSlotDetail, MenuMealSlotSave, MenuSlot, MenuMealAdjustmentContext } from './types'
import { reorderMenuDishesByColumns } from './menuPlacement.js'

export type MealEditorRequest = <T>(path: string, init?: RequestInit) => Promise<T>
interface State {
  aggregate: MenuAggregate | null
  slot: MenuSlot | null
  loading: boolean
  saving: boolean
  dirty: boolean
  error: string
  conflict: boolean
  contextBlocked: boolean
  categories: DishCategoryOption[]
  results: DishOption[]
  total: number
  searchLoading: boolean
  searchError: string
}

// A single session owns its draft and version. No parent aggregate is ever submitted.
export class MealEditorController {
  private state: State = { aggregate: null, slot: null, loading: true, saving: false, dirty: false, error: '', conflict: false, contextBlocked: false, categories: [], results: [], total: 0, searchLoading: false, searchError: '' }
  private listeners = new Set<() => void>()
  private generation = 0
  private searchGeneration = 0
  private initial = ''
  private fingerprint = ''

  readonly menuId: string
  readonly date: string
  readonly mealTypeId: string
  private request: MealEditorRequest
  private adjustmentContext?: MenuMealAdjustmentContext
  constructor(menuId: string, date: string, mealTypeId: string, request: MealEditorRequest, adjustmentContext?: MenuMealAdjustmentContext) {
    this.menuId = menuId; this.date = date; this.mealTypeId = mealTypeId; this.request = request
    this.adjustmentContext = adjustmentContext
  }
  getSnapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private publish(changes: Partial<State>) { this.state = { ...this.state, ...changes }; this.listeners.forEach(listener => listener()) }
  private get path() { return `/menus/${this.menuId}/meal-slots/${this.mealTypeId}/${this.date}` }
  dispose() { this.generation++; this.searchGeneration++ }

  async load() {
    if (this.state.saving) return
    const generation = ++this.generation
    this.searchGeneration++
    this.publish({ loading: true, error: '', searchLoading: false, results: [], total: 0 })
    try {
      // Read the version first. Later metadata reads cannot accidentally upgrade an old draft's token.
      const source = await this.request<MenuMealSlotDetail>(this.path)
      if (generation !== this.generation) return
      const [aggregate, categories] = await Promise.all([
        this.request<MenuAggregate>(`/menus/${this.menuId}/editor`),
        this.request<List<DishCategoryOption>>('/categories/dish?page_size=100'),
      ])
      if (generation !== this.generation) return
      if (source.menu_date !== this.date || source.menu_meal_type_id !== this.mealTypeId || aggregate.menu.id !== this.menuId || !aggregate.meal_types.some(meal => meal.id === this.mealTypeId)) throw new Error('Invalid meal source')
      const { slot_fingerprint, ...slot } = source
      this.fingerprint = slot_fingerprint
      this.initial = JSON.stringify(slot)
      this.publish({ aggregate, categories: categories.items, slot, dirty: false, conflict: false, contextBlocked: false })
    } catch {
      if (generation === this.generation) this.publish({ error: '餐次載入失敗，請重試；尚未儲存的內容仍保留。' })
    } finally {
      if (generation === this.generation) this.publish({ loading: false })
    }
  }

  change(slot: MenuSlot) {
    if (this.state.saving || this.state.loading || this.state.conflict) return
    this.publish({ slot, dirty: JSON.stringify(slot) !== this.initial, error: '' })
  }
  updateDish(index: number, changes: Partial<MenuDish>) {
    const slot = this.state.slot
    if (!slot) return
    const changed = slot.dishes.map((dish, dishIndex) => dishIndex === index ? { ...dish, ...changes } : dish)
    const dishes = Object.prototype.hasOwnProperty.call(changes, 'menu_meal_type_column_id')
      ? reorderMenuDishesByColumns(changed, this.state.aggregate?.meal_type_columns ?? [], slot.menu_meal_type_id)
      : changed
    this.change({ ...slot, dishes })
  }
  move(index: number, direction: -1 | 1) {
    const slot = this.state.slot, target = index + direction
    if (!slot || target < 0 || target >= slot.dishes.length) return
    const dishes = [...slot.dishes]
    ;[dishes[index], dishes[target]] = [dishes[target], dishes[index]]
    this.change({ ...slot, dishes: dishes.map((dish, order) => ({ ...dish, sort_order: order + 1 })) })
  }
  remove(index: number) {
    const slot = this.state.slot
    if (slot) this.change({ ...slot, dishes: slot.dishes.filter((_, i) => i !== index).map((dish, i) => ({ ...dish, sort_order: i + 1 })) })
  }
  add(dish: DishOption) {
    const slot = this.state.slot
    if (!slot || !dish.is_active || !this.state.aggregate?.meal_types.find(meal => meal.id === this.mealTypeId)?.is_active) return
    if (slot.dishes.some(item => item.dish_id === dish.id)) { this.publish({ error: `「${dish.name}」已在本餐中` }); return }
    this.change({ ...slot, dishes: [...slot.dishes, { dish_id: dish.id, menu_meal_type_column_id: null, dish_code: dish.code, dish_name: dish.name, dish_category_name: dish.category_name, diner_count: 1, notes: null, sort_order: slot.dishes.length + 1 }] })
  }

  async search(search: string, categoryId: string, page: number) {
    const generation = ++this.searchGeneration
    if (!search.trim() && !categoryId) { this.publish({ results: [], total: 0, searchLoading: false, searchError: '' }); return }
    this.publish({ searchLoading: true, searchError: '' })
    const query = new URLSearchParams({ active: 'true', page: String(page), page_size: '20' })
    if (search.trim()) query.set('search', search.trim())
    if (categoryId) query.set('category_id', categoryId)
    try {
      const result = await this.request<{ items: DishOption[]; pagination: { total: number } }>(`/dishes?${query}`)
      if (generation === this.searchGeneration) this.publish({ results: result.items, total: result.pagination.total })
    } catch {
      if (generation === this.searchGeneration) this.publish({ results: [], total: 0, searchError: '菜色搜尋失敗，請稍後再試。' })
    } finally {
      if (generation === this.searchGeneration) this.publish({ searchLoading: false })
    }
  }

  async save(): Promise<MenuAggregate | null> {
    const { slot, loading, saving, conflict } = this.state
    if (!slot || loading || saving || conflict) return null
    const usedDishes = new Set<string>(), usedColumns = new Set<string>()
    const columns = new Set(this.state.aggregate?.meal_type_columns.filter(column => column.menu_meal_type_id === this.mealTypeId).map(column => column.id))
    for (const dish of slot.dishes) {
      const column = dish.menu_meal_type_column_id
      if (!Number.isInteger(dish.diner_count) || dish.diner_count < 0 || (dish.notes?.length ?? 0) > 1000 || usedDishes.has(dish.dish_id) || (column && (usedColumns.has(column) || !columns.has(column)))) {
        this.publish({ error: '請檢查重複菜色、菜單欄位、人數與備註（最多 1000 字）。' }); return null
      }
      usedDishes.add(dish.dish_id)
      if (column) usedColumns.add(column)
    }
    if ((slot.notes?.length ?? 0) > 1000 || slot.dishes.length > 200) { this.publish({ error: '本餐備註最多 1000 字，菜色最多 200 道。' }); return null }
    const payload: MenuMealSlotSave = {
      expected_slot_fingerprint: this.fingerprint, menu_day_id: slot.menu_day_id, notes: slot.notes,
      ...(this.adjustmentContext ? { ordering_adjustment_context: this.adjustmentContext } : {}),
      dishes: slot.dishes.map(({ id, dish_id, menu_meal_type_column_id, diner_count, notes }, index) => ({ id, dish_id, menu_meal_type_column_id, diner_count, notes, sort_order: index + 1 })),
    }
    const generation = this.generation
    this.publish({ saving: true, error: '' })
    try {
      const aggregate = await this.request<MenuAggregate>(this.path, { method: 'PUT', body: JSON.stringify(payload) })
      if (generation !== this.generation) return null
      this.publish({ dirty: false })
      return aggregate
    } catch (cause) {
      if (generation !== this.generation) return null
      const failure = cause as { status?: number; detail?: { code?: string }; message?: string }
      const conflict = failure?.status === 409
      const contextMessage: Record<string,string> = {
        ADJUSTMENT_NOT_FOUND: '來源叫貨工作表已不存在，不能由此入口儲存。請關閉視窗。',
        INVALID_ADJUSTMENT_STATUS: '叫貨工作表已確認或取消，不能由此入口儲存菜單。請關閉後重新載入工作表。',
        LOCK_VERSION_CONFLICT: '叫貨工作表已被其他操作更新，請關閉後重新載入；本餐輸入仍保留。',
        SNAPSHOT_LOCKED: '工作表已被正式採購使用，不能由此入口修改菜單。',
        ADJUSTMENT_MENU_OUT_OF_SCOPE: '此餐次不在工作表的來源範圍，不能儲存。',
      }
      const contextError=contextMessage[failure?.detail?.code ?? '']
      this.publish({ conflict: conflict||Boolean(contextError), contextBlocked: Boolean(contextError), error: contextError ?? (conflict
        ? '此餐次或欄位已被其他操作更新，本次未覆蓋伺服器資料。輸入仍保留；請選擇「重新載入最新餐次」後重新編輯。'
        : failure?.status && failure.status < 500 ? `儲存失敗：${failure.message}` : '儲存本餐失敗，請稍後再試；目前輸入內容已保留。') })
      return null
    } finally {
      if (generation === this.generation) this.publish({ saving: false })
    }
  }
}
