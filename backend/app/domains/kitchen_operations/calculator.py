from collections import OrderedDict
from decimal import Decimal
from app.shared.domain.quantities import calculate_required_quantity,convert_quantity,preparation_display

def anomaly(code,severity,message,entity_id,entity_name,**context):return {"code":code,"severity":severity,"message":message,"related_entity_id":entity_id,"related_entity_name":entity_name,"context":context}

def build_preparation(source_rows,automatic_display=True):
    days=OrderedDict();all_anomalies=[];summaries={}
    for row in source_rows:
        day=days.setdefault(row["menu_date"],{"menu_date":row["menu_date"],"meals":OrderedDict(),"anomalies":[]})
        meal=day["meals"].setdefault(row["meal_type_id"],{"meal_type_id":row["meal_type_id"],"meal_type_name":row["meal_type_name"],"sort_order":row["meal_type_sort_order"],"dishes":OrderedDict(),"anomalies":[]})
        dish=meal["dishes"].setdefault(row["menu_dish_id"],{"dish_id":row["dish_id"],"dish_code":row["dish_code"],"dish_name":row["dish_name"],"diner_count":row["diner_count"],"notes":row["dish_notes"],"sort_order":row["dish_sort_order"],"recipe_ready":True,"ingredients":[],"anomalies":[]})
        context={"menu_date":row["menu_date"].isoformat(),"meal_type_id":str(row["meal_type_id"]),"meal_type_name":row["meal_type_name"],"dish_id":str(row["dish_id"])}
        if not row["meal_type_is_active"] and not any(a["code"]=="INACTIVE_MEAL_TYPE" for a in meal["anomalies"]):meal["anomalies"].append(anomaly("INACTIVE_MEAL_TYPE","warning","Inactive meal type is retained for scheduled kitchen work",row["meal_type_id"],row["meal_type_name"],**context))
        if not row["dish_is_active"] and not any(a["code"]=="INACTIVE_DISH" for a in dish["anomalies"]):dish["anomalies"].append(anomaly("INACTIVE_DISH","warning","Inactive dish is retained for scheduled kitchen work",row["dish_id"],row["dish_name"],**context))
        if row["recipe_line_id"] is None:
            issue=anomaly("MISSING_RECIPE","error","Scheduled dish has no recipe",row["dish_id"],row["dish_name"],**context);dish["recipe_ready"]=False;dish["anomalies"].append(issue);continue
        line_anomalies=[]
        if row["ingredient_id"] is None:
            issue=anomaly("MISSING_INGREDIENT","error","Recipe ingredient no longer exists",row["recipe_line_id"],row["dish_name"],**context);line_anomalies.append(issue);dish["recipe_ready"]=False
            required=base_quantity=display_quantity=None;required_unit=base_unit=display_unit=None
        elif row["quantity_per_person"]<=0:
            issue=anomaly("ZERO_RECIPE_QUANTITY","error","Recipe quantity must be greater than zero for kitchen preparation",row["recipe_line_id"],row["ingredient_name"],**context);line_anomalies.append(issue);dish["recipe_ready"]=False
            required=base_quantity=display_quantity=None;required_unit=row["recipe_unit"];base_unit=row["base_unit"];display_unit=row["recipe_unit"]
        else:
            required=calculate_required_quantity(row["quantity_per_person"],row["diner_count"],row["loss_rate"]);required_unit=row["recipe_unit"]
            converted=convert_quantity(required,required_unit,row["base_unit"]);base_quantity=converted.quantity if converted.convertible else None;base_unit=row["base_unit"] if converted.convertible else None
            if not converted.convertible:
                issue=anomaly("INCOMPATIBLE_UNIT","error","Recipe unit cannot be safely converted to ingredient base unit",row["recipe_line_id"],row["ingredient_name"],recipe_unit=required_unit,base_unit=row["base_unit"],**context);line_anomalies.append(issue);dish["recipe_ready"]=False
            if not row["ingredient_is_active"]:line_anomalies.append(anomaly("INACTIVE_INGREDIENT","warning","Inactive ingredient is retained for scheduled kitchen work",row["ingredient_id"],row["ingredient_name"],**context))
            display_quantity,display_unit=preparation_display(required,required_unit,automatic_display)
            summary_quantity=base_quantity if base_quantity is not None else required;summary_unit=base_unit or required_unit;key=f"{row['ingredient_id']}:{summary_unit}"
            target=summaries.setdefault(key,{"row_key":key,"ingredient_id":row["ingredient_id"],"ingredient_code":row["ingredient_code"],"ingredient_name":row["ingredient_name"],"supplier_id":row["supplier_id"],"supplier_name":row["supplier_name"],"required_quantity":Decimal("0"),"required_unit":summary_unit,"source_count":0,"anomalies":[]})
            target["required_quantity"]+=summary_quantity;target["source_count"]+=1;target["anomalies"].extend(line_anomalies)
        dish["ingredients"].append({"ingredient_id":row["ingredient_id"],"ingredient_code":row["ingredient_code"],"ingredient_name":row["ingredient_name"],"supplier_id":row["supplier_id"],"supplier_name":row["supplier_name"],"quantity_per_person":row["quantity_per_person"],"recipe_unit":row["recipe_unit"],"loss_rate":row["loss_rate"],"required_quantity":required,"required_unit":required_unit,"base_quantity":base_quantity,"base_unit":base_unit,"display_quantity":display_quantity,"display_unit":display_unit,"notes":row["recipe_notes"],"ingredient_notes":row["ingredient_notes"],"sort_order":row["recipe_sort_order"],"anomalies":line_anomalies})
    result_days=[]
    for day in days.values():
        day["meals"]=[dict(meal,dishes=list(meal["dishes"].values())) for meal in day["meals"].values()]
        for meal in day["meals"]:
            all_anomalies.extend(meal["anomalies"])
            for dish in meal["dishes"]:all_anomalies.extend(dish["anomalies"]);all_anomalies.extend(a for line in dish["ingredients"] for a in line["anomalies"])
        result_days.append(day)
    summary=[]
    for value in summaries.values():
        value["display_quantity"],value["display_unit"]=preparation_display(value["required_quantity"],value["required_unit"],automatic_display);summary.append(value)
    return result_days,summary,all_anomalies
