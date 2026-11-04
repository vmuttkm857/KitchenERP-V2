import type { CSSProperties } from 'react'
import type { DishCategoryOption } from '../menus/types'

export const DISH_BACKGROUND_COLORS: ReadonlyArray<{ name: string; value: string }>
export function categoryRowStyle(categoryId: string | null | undefined, categories: ReadonlyMap<string, DishCategoryOption>, enabled?: boolean): CSSProperties | undefined
export class CategoryLoadError extends Error {
  code: 'request' | 'format' | 'changed'
  path: string
  status?: number
  constructor(code: 'request' | 'format' | 'changed', path: string, status?: number)
}
export function categoryLoadMessage(error: unknown, path: string): string
export function loadDishCategories(request: <T>(path: string) => Promise<T>, isCurrent?: () => boolean): Promise<Array<DishCategoryOption & { sort_order: number }>>
