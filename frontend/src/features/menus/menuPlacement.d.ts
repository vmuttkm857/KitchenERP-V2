import type { MealTypeColumn, MenuDish } from './types'

export function arrangeMenuDishes(dishes:MenuDish[],labels:MealTypeColumn[]):Array<MenuDish|null>
export function reorderMenuDishesByColumns(dishes:MenuDish[],columns:MealTypeColumn[],mealTypeId:string):MenuDish[]
