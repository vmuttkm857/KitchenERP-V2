from app.domains.exports.exceptions import EmptyExportError
from app.domains.exports.excel import kitchen_workbook,purchase_workbook,requirements_workbook,snapshot_workbook
from app.domains.exports.kitchen_a4 import kitchen_a4_workbook
from app.domains.exports.kitchen_simple import kitchen_simple_pdf,kitchen_simple_workbook,simple_page_plan
from app.domains.exports.menu_exports import menu_full_pdf,menu_full_workbook,menu_grid_pdf,menu_grid_workbook,menu_nutrition_pdf,menu_nutrition_workbook,menu_pretty_pdf,menu_pretty_workbook
from app.domains.exports.pdf import kitchen_pdf,purchase_pdf
from app.domains.kitchen_operations.service import KitchenOperationsService
from app.domains.menus.service import MenuService
from app.domains.nutrition.dish_service import DishNutritionService
from app.domains.purchases.service import PurchaseService
from app.domains.requirements.service import RequirementService
from app.domains.snapshots.service import SnapshotService

class ExportService:
    def __init__(self,session):self.session=session
    def kitchen(self,criteria,format):
        result=KitchenOperationsService(self.session).calculate(criteria)
        if not result["days"]:raise EmptyExportError("No kitchen operation rows matched the criteria")
        return (kitchen_workbook if format=="xlsx" else kitchen_pdf)(result),result["menu"]["menu_name"]
    def kitchen_a4(self,criteria):
        result=KitchenOperationsService(self.session).calculate(criteria)
        if not result["days"]:raise EmptyExportError("No kitchen operation rows matched the criteria")
        return kitchen_a4_workbook(result),result["menu"]["menu_name"]
    def kitchen_simple(self,criteria,format,variant="single"):
        result=KitchenOperationsService(self.session).calculate(criteria)
        if not simple_page_plan(result):raise EmptyExportError("No kitchen operation rows matched the criteria")
        builder=kitchen_simple_workbook if format=="xlsx" else kitchen_simple_pdf
        return (builder(result,variant) if format=="xlsx" else builder(result)),result["menu"]["menu_name"]
    def menu(self,menu_id,layout,format,variant="single",nutrition="none"):
        result=MenuService(self.session).aggregate(menu_id)
        used_meals={slot["menu_meal_type_id"] for slot in result["slots"]}
        if not result["dates"] or not any(meal.is_active or meal.id in used_meals for meal in result["meal_types"]):raise EmptyExportError("Menu has no exportable schedule")
        normalized="merged" if layout=="full" else layout
        if nutrition != "none":
            dish_ids={item["dish_id"] for slot in result["slots"] for item in slot["dishes"]}
            nutrient_definitions,nutrition_results=DishNutritionService(self.session).bulk_report(dish_ids)
            builder=menu_nutrition_workbook if format=="xlsx" else menu_nutrition_pdf
            return (builder(result,normalized,nutrition,variant,nutrition_results,nutrient_definitions) if format=="xlsx" else builder(result,normalized,nutrition,nutrition_results,nutrient_definitions)),result["menu"]["name"]
        builders={("merged","xlsx"):menu_full_workbook,("merged","pdf"):menu_full_pdf,("grid","xlsx"):menu_grid_workbook,("grid","pdf"):menu_grid_pdf,("pretty","xlsx"):menu_pretty_workbook,("pretty","pdf"):menu_pretty_pdf}
        builder=builders[(normalized,format)]
        return (builder(result,variant) if format=="xlsx" and normalized!="pretty" else builder(result)),result["menu"]["name"]
    def requirements(self,criteria):
        result=RequirementService(self.session).calculate(criteria)
        if not result["rows"]:raise EmptyExportError("No requirement rows matched the criteria")
        return requirements_workbook(result),"需求量報表"
    def snapshot(self,snapshot_id):
        result=SnapshotService(self.session).detail(snapshot_id)
        if not result["items"]:raise EmptyExportError("Snapshot has no items")
        return snapshot_workbook(result),f'需求快照_R{result["revision"]}'
    def purchase(self,purchase_id,format):
        result=PurchaseService(self.session).detail(purchase_id)
        if not result["orders"]:raise EmptyExportError("Purchase has no supplier orders")
        return (purchase_workbook if format=="xlsx" else purchase_pdf)(result),result["purchase_number"]
