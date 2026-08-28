from sqlalchemy import select
from app.domains.dishes.models import Dish
from app.domains.ingredients.models import Ingredient
from app.domains.menus.models import Menu,MenuDay,MenuDish,MenuMealType
from app.domains.recipes.models import DishIngredient
from app.domains.suppliers.models import Supplier

class KitchenOperationsRepository:
    def __init__(self,session):self.session=session
    def menu(self,menu_id):
        row=self.session.execute(select(Menu.id.label("menu_id"),Menu.name.label("menu_name"),Menu.start_date,Menu.end_date,Menu.is_active).where(Menu.id==menu_id)).mappings().first();return dict(row) if row else None
    def source_rows(self,criteria):
        statement=select(MenuDay.menu_date,MenuMealType.id.label("meal_type_id"),MenuMealType.name.label("meal_type_name"),MenuMealType.sort_order.label("meal_type_sort_order"),MenuMealType.is_active.label("meal_type_is_active"),MenuDish.id.label("menu_dish_id"),MenuDish.diner_count,MenuDish.notes.label("dish_notes"),MenuDish.sort_order.label("dish_sort_order"),Dish.id.label("dish_id"),Dish.code.label("dish_code"),Dish.name.label("dish_name"),Dish.is_active.label("dish_is_active"),DishIngredient.id.label("recipe_line_id"),DishIngredient.quantity.label("quantity_per_person"),DishIngredient.unit.label("recipe_unit"),DishIngredient.loss_rate,DishIngredient.notes.label("recipe_notes"),DishIngredient.sort_order.label("recipe_sort_order"),Ingredient.id.label("ingredient_id"),Ingredient.code.label("ingredient_code"),Ingredient.name.label("ingredient_name"),Ingredient.unit.label("base_unit"),Ingredient.notes.label("ingredient_notes"),Ingredient.is_active.label("ingredient_is_active"),Supplier.id.label("supplier_id"),Supplier.name.label("supplier_name")).join(MenuMealType,MenuMealType.id==MenuDay.menu_meal_type_id).join(MenuDish,MenuDish.menu_day_id==MenuDay.id).join(Dish,Dish.id==MenuDish.dish_id).outerjoin(DishIngredient,DishIngredient.dish_id==Dish.id).outerjoin(Ingredient,Ingredient.id==DishIngredient.ingredient_id).outerjoin(Supplier,Supplier.id==Ingredient.primary_supplier_id).where(MenuDay.menu_id==criteria.menu_id)
        if criteria.selected_dates is not None:statement=statement.where(MenuDay.menu_date.in_(criteria.selected_dates))
        elif criteria.start_date is not None:statement=statement.where(MenuDay.menu_date>=criteria.start_date,MenuDay.menu_date<=criteria.end_date)
        if criteria.meal_type_ids:statement=statement.where(MenuMealType.id.in_(criteria.meal_type_ids))
        statement=statement.order_by(MenuDay.menu_date,MenuMealType.sort_order,MenuMealType.id,MenuDish.sort_order,MenuDish.id,DishIngredient.sort_order,DishIngredient.id)
        return [dict(row) for row in self.session.execute(statement).mappings()]
