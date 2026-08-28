from app.domains.exports.exceptions import EmptyExportError
from app.domains.exports.excel import kitchen_workbook,purchase_workbook,requirements_workbook,snapshot_workbook
from app.domains.exports.pdf import kitchen_pdf,purchase_pdf
from app.domains.kitchen_operations.service import KitchenOperationsService
from app.domains.purchases.service import PurchaseService
from app.domains.requirements.service import RequirementService
from app.domains.snapshots.service import SnapshotService

class ExportService:
    def __init__(self,session):self.session=session
    def kitchen(self,criteria,format):
        result=KitchenOperationsService(self.session).calculate(criteria)
        if not result["days"]:raise EmptyExportError("No kitchen operation rows matched the criteria")
        return (kitchen_workbook if format=="xlsx" else kitchen_pdf)(result),result["menu"]["menu_name"]
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
