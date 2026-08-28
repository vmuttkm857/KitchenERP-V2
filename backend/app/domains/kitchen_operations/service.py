from app.domains.kitchen_operations.calculator import anomaly,build_preparation
from app.domains.kitchen_operations.exceptions import KitchenMenuNotFoundError
from app.domains.kitchen_operations.repository import KitchenOperationsRepository

class KitchenOperationsService:
    def __init__(self,session):self.repository=KitchenOperationsRepository(session)
    def calculate(self,criteria):
        menu=self.repository.menu(criteria.menu_id)
        if not menu:raise KitchenMenuNotFoundError()
        source=self.repository.source_rows(criteria);days,summary,anomalies=build_preparation(source,criteria.display_mode=="auto")
        if not menu["is_active"]:anomalies.insert(0,anomaly("INACTIVE_MENU","warning","Inactive menu is retained for scheduled kitchen work",menu["menu_id"],menu["menu_name"]))
        if not source:anomalies.append(anomaly("NO_SCHEDULED_DISHES","warning","No scheduled dishes matched the kitchen operation criteria",menu["menu_id"],menu["menu_name"]))
        grouped={}
        for item in summary:grouped.setdefault((item["supplier_id"],item["supplier_name"] or "未指定供應商"),[]).append(item)
        supplier_summary=[{"supplier_id":key[0],"supplier_name":key[1],"ingredients":values} for key,values in sorted(grouped.items(),key=lambda value:value[0][1])]
        return {"criteria":criteria,"menu":menu,"days":days,"ingredient_summary":summary,"supplier_summary":supplier_summary,"anomalies":anomalies,"anomaly_summary":{"total":len(anomalies),"errors":sum(a["severity"]=="error" for a in anomalies),"warnings":sum(a["severity"]=="warning" for a in anomalies)}}
