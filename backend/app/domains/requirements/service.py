from decimal import Decimal
from sqlalchemy.orm import Session

from app.domains.requirements.calculator import calculate_requirement_rows,supplier_groups,anomaly
from app.domains.requirements.exceptions import RequirementMenuNotFoundError
from app.domains.requirements.repository import RequirementRepository


class RequirementService:
    def __init__(self,session:Session):self.repository=RequirementRepository(session)
    def calculate(self,criteria):
        menus=self.repository.menus(criteria.menu_ids)
        if len(menus)!=len(criteria.menu_ids):raise RequirementMenuNotFoundError()
        source=self.repository.source_rows(criteria)
        rows,daily_rows,anomalies=calculate_requirement_rows(source)
        scheduled_menu_ids={row["menu_id"] for row in source}
        for menu in menus:
            # Source rows already report inactive menus. Report it here only when
            # the date criteria produced no source rows for that menu.
            if not menu["is_active"] and menu["menu_id"] not in scheduled_menu_ids: anomalies.append(anomaly("INACTIVE_SOURCE","warning","Inactive menu is retained for historical calculation",menu["menu_id"],menu["menu_name"],entity_type="menu"))
            if menu["menu_id"] not in scheduled_menu_ids: anomalies.append(anomaly("NO_SCHEDULED_DISHES","warning","No scheduled dishes matched the calculation criteria",menu["menu_id"],menu["menu_name"]))
        groups=supplier_groups(rows);known=sum((row["estimated_cost"] or Decimal("0") for row in rows),Decimal("0"))
        incomplete=any(row["estimated_cost"] is None or row["needs_review"] for row in rows) or any(item["severity"]=="error" for item in anomalies)
        return {"criteria":criteria,"source_menus":menus,"rows":rows,"daily_rows":daily_rows,"supplier_groups":groups,"known_estimated_cost":known,"total_estimated_cost":None if incomplete else known,"anomalies":anomalies,"anomaly_summary":{"total":len(anomalies),"errors":sum(a["severity"]=="error" for a in anomalies),"warnings":sum(a["severity"]=="warning" for a in anomalies)}}
