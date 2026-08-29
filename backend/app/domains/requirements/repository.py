from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dishes.models import Dish
from app.domains.ingredients.models import Ingredient
from app.domains.menus.models import Menu, MenuDay, MenuDish, MenuMealType
from app.domains.recipes.models import DishIngredient
from app.domains.suppliers.models import Supplier


class RequirementRepository:
    def __init__(self,session:Session): self.session=session
    def menus(self,menu_ids):
        return [dict(row) for row in self.session.execute(select(
            Menu.id.label("menu_id"),Menu.name.label("menu_name"),Menu.start_date,Menu.end_date,Menu.is_active
        ).where(Menu.id.in_(menu_ids)).order_by(Menu.start_date,Menu.id)).mappings()]
    def source_rows(self,criteria):
        statement=select(
            Menu.id.label("menu_id"),Menu.name.label("menu_name"),Menu.is_active.label("menu_is_active"),
            MenuDay.menu_date,MenuMealType.id.label("meal_type_id"),MenuMealType.name.label("meal_type_name"),MenuMealType.is_active.label("meal_type_is_active"),
            MenuDish.id.label("menu_dish_id"),MenuDish.diner_count,
            Dish.id.label("dish_id"),Dish.code.label("dish_code"),Dish.name.label("dish_name"),Dish.is_active.label("dish_is_active"),
            DishIngredient.id.label("recipe_detail_id"),DishIngredient.quantity.label("recipe_quantity"),DishIngredient.unit.label("recipe_unit"),DishIngredient.loss_rate,
            Ingredient.id.label("ingredient_id"),Ingredient.code.label("ingredient_code"),Ingredient.name.label("ingredient_name"),Ingredient.unit.label("base_unit"),
            Ingredient.current_price,Ingredient.primary_supplier_id.label("supplier_id"),Ingredient.purchase_unit,Ingredient.package_size,Ingredient.minimum_order_quantity,
            Ingredient.is_active.label("ingredient_is_active"),Supplier.code.label("supplier_code"),Supplier.name.label("supplier_name"),Supplier.is_active.label("supplier_is_active"),
        ).join(MenuDay,MenuDay.menu_id==Menu.id).join(MenuMealType,MenuMealType.id==MenuDay.menu_meal_type_id)
        statement=statement.join(MenuDish,MenuDish.menu_day_id==MenuDay.id).join(Dish,Dish.id==MenuDish.dish_id)
        statement=statement.outerjoin(DishIngredient,DishIngredient.dish_id==Dish.id).outerjoin(Ingredient,Ingredient.id==DishIngredient.ingredient_id).outerjoin(Supplier,Supplier.id==Ingredient.primary_supplier_id)
        statement=statement.where(Menu.id.in_(criteria.menu_ids),MenuMealType.is_active.is_(True))
        if criteria.selected_dates is not None: statement=statement.where(MenuDay.menu_date.in_(criteria.selected_dates))
        elif criteria.start_date is not None: statement=statement.where(MenuDay.menu_date>=criteria.start_date,MenuDay.menu_date<=criteria.end_date)
        statement=statement.order_by(Menu.id,MenuDay.menu_date,MenuMealType.sort_order,MenuDish.sort_order,DishIngredient.sort_order,DishIngredient.id)
        return [dict(row) for row in self.session.execute(statement).mappings()]
