export interface Menu { id:string; name:string; start_date:string; end_date:string; category_id:string|null; category_name:string|null; notes:string|null; is_active:boolean }
export interface MealType { id:string; menu_id:string; name:string; sort_order:number; is_active:boolean }
export interface MealTypeColumn { id:string; menu_meal_type_id:string; name:string; sort_order:number }
export interface DishOption { id:string; code:string; name:string; category_id?:string|null; category_name?:string|null; recipe_ingredient_count:number; is_active:boolean }
export interface DishCategoryOption { id:string; name:string; is_active:boolean }
export interface MenuDish { id?:string; dish_id:string; dish_code?:string; dish_name?:string; dish_category_name?:string|null; diner_count:number; notes:string|null; sort_order:number }
export interface MenuSlot { menu_day_id?:string; menu_date:string; menu_meal_type_id:string; notes:string|null; dishes:MenuDish[] }
export interface MenuAggregate { menu:Menu; dates:string[]; meal_types:MealType[]; meal_type_columns:MealTypeColumn[]; slots:MenuSlot[] }
export interface List<T> { items:T[] }
