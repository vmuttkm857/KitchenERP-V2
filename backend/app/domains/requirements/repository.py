from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dishes.models import Dish
from app.domains.ingredients.models import Ingredient
from app.domains.menus.models import Menu, MenuDay, MenuDish, MenuMealType, MenuMealTypeColumn
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
            MenuDay.id.label("menu_day_id"),MenuDay.menu_date,MenuMealType.id.label("meal_type_id"),MenuMealType.name.label("meal_type_name"),MenuMealType.sort_order.label("meal_type_sort_order"),MenuMealType.is_active.label("meal_type_is_active"),
            MenuDish.id.label("menu_dish_id"),MenuDish.menu_meal_type_column_id,MenuMealTypeColumn.sort_order.label("menu_meal_type_column_sort_order"),MenuDish.diner_count,MenuDish.sort_order.label("menu_dish_sort_order"),
            Dish.id.label("dish_id"),Dish.code.label("dish_code"),Dish.name.label("dish_name"),Dish.is_active.label("dish_is_active"),
            DishIngredient.id.label("recipe_detail_id"),DishIngredient.quantity.label("recipe_quantity"),DishIngredient.unit.label("recipe_unit"),DishIngredient.loss_rate,DishIngredient.sort_order.label("dish_ingredient_sort_order"),
            Ingredient.id.label("ingredient_id"),Ingredient.code.label("ingredient_code"),Ingredient.name.label("ingredient_name"),Ingredient.unit.label("base_unit"),
            Ingredient.current_price,Ingredient.primary_supplier_id.label("supplier_id"),Ingredient.purchase_unit,Ingredient.package_size,Ingredient.minimum_order_quantity,
            Ingredient.is_active.label("ingredient_is_active"),Supplier.code.label("supplier_code"),Supplier.name.label("supplier_name"),Supplier.is_active.label("supplier_is_active"),
        ).join(MenuDay,MenuDay.menu_id==Menu.id).join(MenuMealType,MenuMealType.id==MenuDay.menu_meal_type_id)
        statement=statement.join(MenuDish,MenuDish.menu_day_id==MenuDay.id).outerjoin(MenuMealTypeColumn,MenuMealTypeColumn.id==MenuDish.menu_meal_type_column_id).join(Dish,Dish.id==MenuDish.dish_id)
        statement=statement.outerjoin(DishIngredient,DishIngredient.dish_id==Dish.id).outerjoin(Ingredient,Ingredient.id==DishIngredient.ingredient_id).outerjoin(Supplier,Supplier.id==Ingredient.primary_supplier_id)
        statement=statement.where(Menu.id.in_(criteria.menu_ids),MenuMealType.is_active.is_(True))
        if criteria.selected_dates is not None: statement=statement.where(MenuDay.menu_date.in_(criteria.selected_dates))
        elif criteria.start_date is not None: statement=statement.where(MenuDay.menu_date>=criteria.start_date,MenuDay.menu_date<=criteria.end_date)
        statement=statement.order_by(Menu.id,MenuDay.menu_date,MenuMealType.sort_order,MenuDish.sort_order,DishIngredient.sort_order,DishIngredient.id)
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def locked_source_rows(self,criteria):
        """Lock exactly the selected source graph, then return one consistent read."""
        menu_ids=sorted(criteria.menu_ids,key=str)
        list(self.session.scalars(select(Menu).where(Menu.id.in_(menu_ids)).order_by(Menu.id).with_for_update()))
        date_filters=[MenuDay.menu_id.in_(menu_ids)]
        if criteria.selected_dates is not None:date_filters.append(MenuDay.menu_date.in_(criteria.selected_dates))
        elif criteria.start_date is not None:date_filters.extend((MenuDay.menu_date>=criteria.start_date,MenuDay.menu_date<=criteria.end_date))
        meal_ids=list(self.session.scalars(select(MenuMealType.id).where(MenuMealType.menu_id.in_(menu_ids),MenuMealType.is_active.is_(True)).order_by(MenuMealType.id)))
        if meal_ids:list(self.session.scalars(select(MenuMealType).where(MenuMealType.id.in_(meal_ids)).order_by(MenuMealType.id).with_for_update()))
        day_ids=list(self.session.scalars(select(MenuDay.id).where(*date_filters).order_by(MenuDay.id)))
        if day_ids:list(self.session.scalars(select(MenuDay).where(MenuDay.id.in_(day_ids)).order_by(MenuDay.id).with_for_update()))
        menu_dish_rows=list(self.session.execute(select(MenuDish.id,MenuDish.dish_id).where(MenuDish.menu_day_id.in_(day_ids)).order_by(MenuDish.id))) if day_ids else []
        menu_dish_ids=[row.id for row in menu_dish_rows];dish_ids=sorted({row.dish_id for row in menu_dish_rows},key=str)
        if dish_ids:list(self.session.scalars(select(Dish).where(Dish.id.in_(dish_ids)).order_by(Dish.id).with_for_update()))
        if menu_dish_ids:list(self.session.scalars(select(MenuDish).where(MenuDish.id.in_(menu_dish_ids)).order_by(MenuDish.id).with_for_update()))
        recipe_ids=list(self.session.scalars(select(DishIngredient.id).where(DishIngredient.dish_id.in_(dish_ids)).order_by(DishIngredient.id))) if dish_ids else []
        if recipe_ids:list(self.session.scalars(select(DishIngredient).where(DishIngredient.id.in_(recipe_ids)).order_by(DishIngredient.id).with_for_update()))
        ingredient_ids=list(self.session.scalars(select(DishIngredient.ingredient_id).where(DishIngredient.id.in_(recipe_ids)).order_by(DishIngredient.ingredient_id))) if recipe_ids else []
        ingredient_ids=sorted(set(ingredient_ids),key=str)
        if ingredient_ids:list(self.session.scalars(select(Ingredient).where(Ingredient.id.in_(ingredient_ids)).order_by(Ingredient.id).with_for_update()))
        rows=self.source_rows(criteria)
        supplier_ids=sorted({row["supplier_id"] for row in rows if row["supplier_id"] is not None},key=str)
        if supplier_ids:list(self.session.scalars(select(Supplier).where(Supplier.id.in_(supplier_ids)).order_by(Supplier.id).with_for_update()))
        return self.source_rows(criteria)
