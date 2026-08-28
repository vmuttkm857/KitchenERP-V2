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

def snapshot_fingerprint(criteria):
    payload={"calculation_version":"requirements-v1","criteria":normalize(criteria)}
    encoded=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
