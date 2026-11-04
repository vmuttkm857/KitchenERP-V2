// Palette choices are display settings, never mappings from category names.
export const DISH_BACKGROUND_COLORS = [
  { name: '淺粉', value: '#FCE4EC' }, { name: '淺橘', value: '#FFE0B2' },
  { name: '淺黃', value: '#FFF9C4' }, { name: '淺綠', value: '#DCEDC8' },
  { name: '薄荷', value: '#C8E6C9' }, { name: '青綠', value: '#B2DFDB' },
  { name: '淺藍', value: '#BBDEFB' }, { name: '淡紫', value: '#D1C4E9' },
  { name: '藕紫', value: '#E1BEE7' }, { name: '淺灰', value: '#ECEFF1' },
]

export function categoryRowStyle(categoryId, categories, enabled = false) {
  const value = enabled && categoryId ? categories.get(categoryId)?.background_color : null
  if (typeof value !== 'string' || !/^#[0-9a-f]{6}$/i.test(value)) return undefined
  // APIs can contain valid colors outside the preset palette; retain readable text.
  const channels = [1, 3, 5].map(offset => parseInt(value.slice(offset, offset + 2), 16) / 255)
    .map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
  const luminance = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
  return { '--dish-category-background': value.toUpperCase(), '--dish-category-text': luminance > 0.179 ? '#000000' : '#FFFFFF' }
}

export class CategoryLoadError extends Error {
  constructor(code, path, status) {
    super('Category loading failed')
    this.name = 'CategoryLoadError'
    this.code = code
    this.path = path
    this.status = status
  }
}

export function categoryLoadMessage(error, path) {
  const status = Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599 ? error.status : undefined
  const endpoint = error instanceof CategoryLoadError ? error.path : path
  const prefix = `分類載入失敗：${endpoint}${status ? `（HTTP ${status}）` : ''}。`
  if (error instanceof CategoryLoadError && error.code === 'format') return prefix + 'API 回應格式不符，請檢查前後端版本。'
  if (error instanceof CategoryLoadError && error.code === 'changed') return prefix + '分類分頁資料已變動，請重新載入。'
  if (status === 401) return prefix + '登入已失效，請重新登入。'
  if (status === 403) return prefix + '目前帳號沒有讀取分類的權限。'
  if (status && status >= 500) return prefix + '請檢查 Backend 錯誤及資料庫 Migration 版本。'
  return prefix + '請確認 Backend 連線正常後重試。'
}

export async function loadDishCategories(request, isCurrent = () => true) {
  async function readPage(path) {
    let value
    try { value = await request(path) }
    catch (error) { throw new CategoryLoadError('request', path, error?.status) }
    if (!Array.isArray(value?.items) || value.items.some(item => typeof item?.id !== 'string')
      || (value.pagination !== undefined && (!Number.isInteger(value.pagination?.total) || value.pagination.total < 0))) {
      throw new CategoryLoadError('format', path)
    }
    return value
  }
  let path = '/categories/dish?page_size=100'
  const first = await readPage(path)
  if (!isCurrent()) return []
  const items = [...first.items], total = first.pagination?.total ?? items.length
  for (let page = 2; items.length < total; page++) {
    path = `/categories/dish?page_size=100&page=${page}`
    const next = await readPage(path)
    if (!isCurrent()) return []
    if (!next.items.length || next.pagination?.total !== total) throw new CategoryLoadError('changed', path)
    items.push(...next.items)
  }
  if (items.length !== total || new Set(items.map(item => item.id)).size !== items.length) throw new CategoryLoadError('changed', path)
  return items
}
