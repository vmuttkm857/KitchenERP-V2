import re
from urllib.parse import quote

FORMULA_PREFIXES=("=","+","-","@")
INVALID_FILENAME=re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def safe_cell_text(value):
    text="" if value is None else str(value)
    return "'"+text if text.startswith(FORMULA_PREFIXES) else text

def safe_filename(value:str,extension:str)->str:
    name=INVALID_FILENAME.sub("_",value).strip(" .") or "export"
    return f"{name[:120]}.{extension.lstrip('.')}"

def content_disposition(filename:str)->str:
    fallback="".join(c if ord(c)<128 else "_" for c in filename)
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename)}'
