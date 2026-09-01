import uuid
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dishes.models import Dish
from app.domains.ingredients.models import Ingredient
from app.domains.menus.models import Menu,MenuDay,MenuDish,MenuMealType
from app.domains.production.models import DishProductionProfile,ProductionBatchIngredient,ProductionBatchVersion,ProductionProcessStep
from app.domains.recipes.models import DishIngredient

class ProductionRepository:
    def __init__(self,session:Session):self.session=session
    def add(self,value):self.session.add(value)
    def delete(self,value):self.session.delete(value)
    def dish(self,dish_id):return self.session.get(Dish,dish_id)
    def profile(self,dish_id):return self.session.scalar(select(DishProductionProfile).where(DishProductionProfile.dish_id==dish_id))
    def profiles(self,dish_ids):return list(self.session.scalars(select(DishProductionProfile).where(DishProductionProfile.dish_id.in_(dish_ids)))) if dish_ids else []
    def profile_by_id(self,profile_id):return self.session.get(DishProductionProfile,profile_id)
    def version(self,version_id):return self.session.get(ProductionBatchVersion,version_id)
    def step(self,step_id):return self.session.get(ProductionProcessStep,step_id)
    def ingredient(self,item_id):return self.session.get(ProductionBatchIngredient,item_id)
    def versions(self,profile_id):return list(self.session.scalars(select(ProductionBatchVersion).where(ProductionBatchVersion.profile_id==profile_id).order_by(ProductionBatchVersion.serving_count,ProductionBatchVersion.id)))
    def versions_for_profiles(self,profile_ids):return list(self.session.scalars(select(ProductionBatchVersion).where(ProductionBatchVersion.profile_id.in_(profile_ids)).order_by(ProductionBatchVersion.serving_count,ProductionBatchVersion.id))) if profile_ids else []
    def ingredients(self,version_ids):
        if not version_ids:return []
        return list(self.session.execute(select(ProductionBatchIngredient,Ingredient.code,Ingredient.name).join(Ingredient,Ingredient.id==ProductionBatchIngredient.ingredient_id).where(ProductionBatchIngredient.version_id.in_(version_ids)).order_by(ProductionBatchIngredient.sort_order,ProductionBatchIngredient.id)).all())
    def steps(self,version_ids):
        if not version_ids:return []
        return list(self.session.scalars(select(ProductionProcessStep).where(ProductionProcessStep.version_id.in_(version_ids)).order_by(ProductionProcessStep.step_order,ProductionProcessStep.id)))
    def recipe_rows(self,dish_id):
        return list(self.session.execute(select(DishIngredient,Ingredient).join(Ingredient,Ingredient.id==DishIngredient.ingredient_id).where(DishIngredient.dish_id==dish_id).order_by(DishIngredient.sort_order,DishIngredient.id)).all())
    def menu(self,menu_id):return self.session.get(Menu,menu_id)
    def meal(self,meal_id):return self.session.get(MenuMealType,meal_id)
    def menu_rows(self,menu_id:uuid.UUID,menu_date:date|None,meal_id:uuid.UUID|None):
        stmt=select(MenuDay.menu_date,MenuMealType.id.label("meal_id"),MenuMealType.name.label("meal_name"),MenuMealType.sort_order.label("meal_order"),MenuDish.dish_id,Dish.code.label("dish_code"),Dish.name.label("dish_name"),MenuDish.diner_count,MenuDish.sort_order,MenuDish.notes).join(MenuMealType,MenuMealType.id==MenuDay.menu_meal_type_id).join(MenuDish,MenuDish.menu_day_id==MenuDay.id).join(Dish,Dish.id==MenuDish.dish_id).where(MenuDay.menu_id==menu_id)
        if menu_date is not None:stmt=stmt.where(MenuDay.menu_date==menu_date)
        if meal_id is not None:stmt=stmt.where(MenuDay.menu_meal_type_id==meal_id)
        return list(self.session.execute(stmt.order_by(MenuDay.menu_date,MenuMealType.sort_order,MenuMealType.id,MenuDish.sort_order,MenuDish.id)).mappings())
