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

export async function loadDishCategories(request, isCurrent = () => true) {
  const first = await request('/categories/dish?page_size=100')
  if (!isCurrent()) return []
  const items = [...first.items], total = first.pagination?.total ?? items.length
  for (let page = 2; items.length < total; page++) {
    const next = await request(`/categories/dish?page_size=100&page=${page}`)
    if (!isCurrent()) return []
    if (!next.items.length || next.pagination?.total !== total) throw new Error('Category list changed; reload')
    items.push(...next.items)
  }
  if (new Set(items.map(item => item.id)).size !== items.length) throw new Error('Category list changed; reload')
  return items
}
