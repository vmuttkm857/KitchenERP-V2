import uuid
from collections import defaultdict
from decimal import Decimal

from app.shared.domain.quantities import calculate_required_quantity,convert_quantity


def anomaly(code,severity,message,entity_id,entity_name,**context):
    return {"code":code,"severity":severity,"message":message,"related_entity_id":entity_id,"related_entity_name":entity_name,"context":context}


def calculate_requirement_rows(source_rows):
    aggregates={}; daily_aggregates={}; anomalies=[]
    inactive_seen=set(); missing_supplier_seen=set()
    for source in source_rows:
        source_context={"menu_id":str(source["menu_id"]),"menu_name":source["menu_name"],"menu_date":source["menu_date"].isoformat(),"meal_type":source["meal_type_name"],"dish_id":str(source["dish_id"]),"dish_name":source["dish_name"]}
        for entity_type,id_key,name_key,active_key in (("menu","menu_id","menu_name","menu_is_active"),("dish","dish_id","dish_name","dish_is_active")):
            if not source[active_key] and (entity_type,source[id_key]) not in inactive_seen:
                inactive_seen.add((entity_type,source[id_key])); anomalies.append(anomaly("INACTIVE_SOURCE","warning",f"Inactive {entity_type} is retained for historical calculation",source[id_key],source[name_key],entity_type=entity_type))
        if source["recipe_detail_id"] is None:
            anomalies.append(anomaly("MISSING_RECIPE","error","Scheduled dish has no recipe",source["dish_id"],source["dish_name"],**source_context)); continue
        if source["ingredient_id"] is None:
            anomalies.append(anomaly("MISSING_INGREDIENT","error","Recipe ingredient no longer exists",source["recipe_detail_id"],source["dish_name"],**source_context)); continue
        if source["recipe_quantity"] <= 0:
            anomalies.append(anomaly("ZERO_RECIPE_QUANTITY","error","Recipe quantity must be greater than zero for requirement calculation",source["recipe_detail_id"],source["dish_name"],ingredient_id=str(source["ingredient_id"]),**source_context)); continue
        if not source["ingredient_is_active"] and ("ingredient",source["ingredient_id"]) not in inactive_seen:
            inactive_seen.add(("ingredient",source["ingredient_id"])); anomalies.append(anomaly("INACTIVE_SOURCE","warning","Inactive ingredient is retained for historical calculation",source["ingredient_id"],source["ingredient_name"],entity_type="ingredient"))
        if source["supplier_id"] is None and source["ingredient_id"] not in missing_supplier_seen:
            missing_supplier_seen.add(source["ingredient_id"]); anomalies.append(anomaly("MISSING_SUPPLIER","warning","Ingredient has no primary supplier",source["ingredient_id"],source["ingredient_name"]))
        elif source["supplier_id"] is not None and source["supplier_is_active"] is False and ("supplier",source["supplier_id"]) not in inactive_seen:
            inactive_seen.add(("supplier",source["supplier_id"])); anomalies.append(anomaly("INACTIVE_SOURCE","warning","Inactive supplier is retained for historical display",source["supplier_id"],source["supplier_name"],entity_type="supplier"))
        with_loss=calculate_required_quantity(source["recipe_quantity"],source["diner_count"],source["loss_rate"])
        converted=convert_quantity(with_loss,source["recipe_unit"],source["base_unit"])
        convertible=converted.convertible and converted.quantity is not None
        final_unit=source["base_unit"] if convertible else source["recipe_unit"]
        quantity=converted.quantity if convertible else with_loss
        row_key=f"{source['ingredient_id']}:{final_unit}"
        if not convertible:
            anomalies.append(anomaly("INCOMPATIBLE_UNIT","error","Recipe unit cannot be safely converted to ingredient base unit",source["recipe_detail_id"],source["ingredient_name"],recipe_unit=source["recipe_unit"],base_unit=source["base_unit"],**source_context))
        target=aggregates.setdefault(row_key,{"row_key":row_key,"ingredient_id":source["ingredient_id"],"ingredient_code":source["ingredient_code"],"ingredient_name":source["ingredient_name"],"supplier_id":source["supplier_id"],"supplier_code":source.get("supplier_code"),"supplier_name":source["supplier_name"],"base_unit":source["base_unit"],"requirement_quantity":Decimal("0"),"requirement_unit":final_unit,"suggested_purchase_quantity":Decimal("0") if convertible else None,"suggested_purchase_unit":final_unit if convertible else None,"configured_purchase_unit":source["purchase_unit"],"package_size":source["package_size"],"minimum_order_quantity":source["minimum_order_quantity"],"current_price":source["current_price"],"estimated_cost":Decimal("0") if convertible and source["current_price"] is not None else None,"needs_review":not convertible,"total_diner_count":0,"source_count":0,"schedules":[]})
        target["requirement_quantity"]+=quantity; target["total_diner_count"]+=source["diner_count"]; target["source_count"]+=1
        target["schedules"].append({"menu_id":str(source["menu_id"]),"menu_name":source["menu_name"],"requirement_date":source["menu_date"].isoformat(),"meal_type_name":source["meal_type_name"],"dish_id":str(source["dish_id"]),"dish_name":source["dish_name"],"quantity":format(quantity,"f"),"unit":final_unit})
        daily_key=(source["menu_date"],source["menu_id"],source["supplier_id"],source["ingredient_id"],final_unit)
        daily=daily_aggregates.setdefault(daily_key,{"requirement_date":source["menu_date"],"menu_id":source["menu_id"],"menu_name":source["menu_name"],"supplier_id":source["supplier_id"],"supplier_code":source.get("supplier_code"),"supplier_name":source["supplier_name"],"ingredient_id":source["ingredient_id"],"ingredient_code":source["ingredient_code"],"ingredient_name":source["ingredient_name"],"quantity":Decimal("0"),"unit":final_unit})
        daily["quantity"]+=quantity
        if convertible:
            target["suggested_purchase_quantity"]+=quantity
            if source["current_price"] is None:
                target["estimated_cost"]=None; target["needs_review"]=True
                anomalies.append(anomaly("MISSING_PRICE","error","Ingredient has no current price",source["ingredient_id"],source["ingredient_name"]))
            elif target["estimated_cost"] is not None: target["estimated_cost"]+=quantity*source["current_price"]
    daily_rows=sorted(daily_aggregates.values(),key=lambda row:(row["requirement_date"],row["supplier_name"] or "未指定供應商",row["menu_name"],row["ingredient_code"],row["unit"],str(row["menu_id"]),str(row["ingredient_id"])))
    return list(aggregates.values()),daily_rows,anomalies


def supplier_groups(rows):
    grouped=defaultdict(list)
    for row in rows: grouped[(row["supplier_id"],row["supplier_name"] or "未指定供應商")].append(row)
    result=[]
    for (supplier_id,name),items in sorted(grouped.items(),key=lambda item:item[0][1]):
        needs=any(item["needs_review"] or item["estimated_cost"] is None for item in items)
        known=sum((item["estimated_cost"] or Decimal("0") for item in items),Decimal("0"))
        result.append({"supplier_id":supplier_id,"supplier_name":name,"row_keys":[item["row_key"] for item in items],"known_estimated_cost":known,"estimated_cost":None if needs else known,"needs_review":needs})
    return result
