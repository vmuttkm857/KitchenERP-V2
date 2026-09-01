from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.domains.nutrition.exceptions import NutritionImportError
from app.domains.nutrition.importer import parse_tfda_xlsx


def workbook_bytes(headers=None, rows=None):
    workbook=Workbook();sheet=workbook.active;sheet.append(["每 100 g 說明"]);sheet.append(headers or ["整合編號","食品分類","樣品名稱","廢棄率(%)","熱量(kcal)","修正熱量(kcal)","粗蛋白(g)"])
    for row in rows or [["A1","肉類","雞肉","",100,90,0],["A2","肉類","雞肉",0,101,91,"Tr"]]:sheet.append(row)
    output=BytesIO();workbook.save(output);return output.getvalue()


def test_header_detection_identity_decimal_null_zero_and_canonical_mapping():
    parsed=parse_tfda_xlsx(workbook_bytes());assert parsed.header_row==2 and len(parsed.foods)==2
    first,second=parsed.foods;assert first.external_code!="" and first.name==second.name and first.external_code!=second.external_code
    assert first.waste_rate is None and second.waste_rate==Decimal("0")
    assert first.values["corrected_energy"]==Decimal("90") and first.values["energy"]==Decimal("100")
    assert first.values["protein"]==Decimal("0") and "protein" not in second.values
    assert parsed.errors==[{"row":4,"column":"粗蛋白(g)","value":"Tr"}]


@pytest.mark.parametrize("headers",[["食品分類","樣品名稱"],["整合編號","樣品名稱"],["整合編號","食品分類"]])
def test_missing_required_headers_rejected(headers):
    with pytest.raises(NutritionImportError):parse_tfda_xlsx(workbook_bytes(headers,[["x","y"]]))


def test_malformed_formula_and_non_xlsx_content_are_never_executed():
    parsed=parse_tfda_xlsx(workbook_bytes(rows=[["A1","類","食品","",1,"=1+1",2]]));assert "corrected_energy" not in parsed.foods[0].values and parsed.errors[0]["value"]=="formula"
    with pytest.raises(NutritionImportError):parse_tfda_xlsx(b"not-an-xlsx")
