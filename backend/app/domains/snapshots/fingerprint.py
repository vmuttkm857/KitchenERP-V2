import hashlib,json
from datetime import date,datetime
from decimal import Decimal
from uuid import UUID

def normalize(value):
    if isinstance(value,dict): return {key:normalize(value[key]) for key in sorted(value)}
    if isinstance(value,list): return sorted((normalize(item) for item in value),key=lambda item:json.dumps(item,sort_keys=True,separators=(",",":")))
    if isinstance(value,Decimal): return format(value.normalize(),"f")
    if isinstance(value,(date,datetime)): return value.isoformat()
    if isinstance(value,UUID): return str(value)
    return value

def hash_payload(payload):
    encoded=json.dumps(normalize(payload),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def snapshot_fingerprint(criteria):
    payload={"calculation_version":"requirements-v1","criteria":normalize(criteria)}
    return hash_payload(payload)

def content_fingerprint(result):
    rows=[]
    for row in sorted(result["rows"],key=lambda value:value["row_key"]):
        rows.append({key:row.get(key) for key in (
            "row_key","ingredient_id","ingredient_code","ingredient_name","supplier_id","supplier_code","supplier_name",
            "requirement_quantity","requirement_unit","suggested_purchase_quantity","suggested_purchase_unit",
            "configured_purchase_unit","package_size","minimum_order_quantity","current_price","estimated_cost","needs_review",
            "total_diner_count","source_count","schedules",
        )})
    return hash_payload({"calculation_version":"requirements-v1","source_menus":result["source_menus"],"rows":rows,
        "known_estimated_cost":result["known_estimated_cost"],"total_estimated_cost":result["total_estimated_cost"],"anomalies":result["anomalies"]})
