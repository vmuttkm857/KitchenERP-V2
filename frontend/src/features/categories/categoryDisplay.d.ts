import type { CSSProperties } from 'react'
import type { DishCategoryOption } from '../menus/types'

export const DISH_BACKGROUND_COLORS: ReadonlyArray<{ name: string; value: string }>
export function categoryRowStyle(categoryId: string | null | undefined, categories: ReadonlyMap<string, DishCategoryOption>, enabled?: boolean): CSSProperties | undefined
export function loadDishCategories(request: <T>(path: string) => Promise<T>, isCurrent?: () => boolean): Promise<Array<DishCategoryOption & { sort_order: number }>>
