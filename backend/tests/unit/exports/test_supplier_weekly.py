from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from app.api.v1.routes.exports import mapped
from app.domains.exports.exceptions import SupplierWeeklyExportError
from app.domains.exports.supplier_weekly import (
    rows_from_adjustment_lines,
    rows_from_snapshot_items,
    supplier_weekly_sheet_title,
    supplier_weekly_workbook,
)


def source(menu_id, menu_name, day, dish_id, dish_name, quantity="1.000000", unit="kg"):
    return {
        "menu_id": str(menu_id),
        "menu_name": menu_name,
        "requirement_date": day,
        "meal_type_name": "中餐",
        "dish_id": str(dish_id),
        "dish_name": dish_name,
        "quantity": quantity,
        "unit": unit,
    }


def item(supplier_id, sources, adjusted="3.000000"):
    return {
        "id": str(uuid4()),
        "supplier_id": str(supplier_id),
        "supplier_name_snapshot": "方豪",
        "ingredient_name_snapshot": "高麗菜",
        "requirement_unit": "kg",
        "purchase_unit_snapshot": "kg",
        "adjusted_quantity": adjusted,
        "source_summary": sources,
    }


def test_snapshot_sources_keep_same_ingredient_in_different_dishes_as_distinct_rows():
    supplier_id = uuid4()
    menu_id = uuid4()
    rows = rows_from_snapshot_items([
        item(supplier_id, [
            source(menu_id, "治療伙食單-2", "2026-11-02", uuid4(), "炒高麗菜", "1.000000"),
            source(menu_id, "治療伙食單-2", "2026-11-02", uuid4(), "高麗菜湯", "2.000000"),
        ])
    ], supplier_id)
    workbook = load_workbook(BytesIO(supplier_weekly_workbook(rows)))
    assert workbook.sheetnames == ["治療伙食單-2_1102"]
    sheet = workbook.active
    assert sheet["A1"].value == "供應商叫貨單"
    assert sheet["A2"].value == "供應商名稱：方豪"
    assert sheet["A3"].value == "送貨日期：2026 年 11 月 2 日（星期一）"
    assert sheet["A4"].value == "菜單名稱：治療伙食單-2"
    assert [sheet.cell(row, 2).value for row in (6, 7)] == ["高麗菜", "高麗菜"]
    assert [sheet.cell(row, 3).value for row in (6, 7)] == [1, 2]
    assert [sheet.cell(5, column).value for column in range(1, 5)] == ["項次", "訂購品名", "數量", "單位"]
    assert sheet.auto_filter.ref is None
    assert all(sheet.cell(5, column).fill.fill_type is None for column in range(1, 5))
    assert sheet.page_setup.paperSize == 9 and sheet.page_setup.orientation == "portrait"
    assert sheet.max_row == 12  # two actual rows plus five bordered manual-entry rows
    assert sheet["A1"].alignment.horizontal == "center"
    assert all(sheet.cell(5, column).alignment.horizontal == "left" for column in range(1, 5))
    assert all(sheet.cell(row, column).alignment.horizontal == "left" for row in range(6, 13) for column in range(1, 5))
    all_text = "\n".join(str(cell.value or "") for row in sheet.iter_rows() for cell in row)
    assert "醫院名稱" not in all_text and "未設定" not in all_text
    assert "菜餚說明" not in all_text and "是否裁切" not in all_text and "廚房" not in all_text


def test_workbook_groups_by_date_and_menu_id_not_display_name():
    supplier_id = uuid4()
    rows = rows_from_snapshot_items([
        item(supplier_id, [source(uuid4(), "同名菜單", "2026-11-02", uuid4(), "菜一")], "1.000000"),
        item(supplier_id, [source(uuid4(), "同名菜單", "2026-11-02", uuid4(), "菜二")], "1.000000"),
    ], supplier_id)
    workbook = load_workbook(BytesIO(supplier_weekly_workbook(rows)))
    assert workbook.sheetnames == ["同名菜單_1102", "同名菜單_1102_2"]
    assert all(sheet["A4"].value == "菜單名稱：同名菜單" for sheet in workbook.worksheets)


def test_each_sheet_uses_its_own_delivery_date_for_traditional_chinese_weekday():
    menu_id = str(uuid4())
    common = {
        "menu_id": menu_id,
        "menu_name": "星期驗證菜單",
        "meal_type_name": "中餐",
        "supplier_name": "方豪",
        "ingredient_name": "高麗菜",
        "quantity": Decimal("1"),
        "unit": "kg",
    }
    rows = [
        {**common, "requirement_date": day, "dish_id": str(uuid4()), "dish_name": f"菜色-{day}"}
        for day in (date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 8))
    ]
    workbook = load_workbook(BytesIO(supplier_weekly_workbook(rows)))
    assert [sheet["A3"].value for sheet in workbook.worksheets] == [
        "送貨日期：2026 年 11 月 2 日（星期一）",
        "送貨日期：2026 年 11 月 3 日（星期二）",
        "送貨日期：2026 年 11 月 8 日（星期日）",
    ]


def test_sheet_title_keeps_date_and_uniqueness_when_menu_name_is_long_or_invalid():
    used = set()
    first = supplier_weekly_sheet_title("超長/菜單名稱" * 5, date(2026, 11, 2), used)
    second = supplier_weekly_sheet_title("超長/菜單名稱" * 5, date(2026, 11, 2), used)
    assert len(first) <= 31 and first.endswith("_1102")
    assert len(second) <= 31 and second.endswith("_1102_2")
    assert first != second and "/" not in first


def test_aggregate_adjustment_that_cannot_be_allocated_to_dishes_is_rejected():
    supplier_id = uuid4()
    with pytest.raises(SupplierWeeklyExportError) as caught:
        rows_from_snapshot_items([
            item(supplier_id, [source(uuid4(), "菜單", "2026-11-02", uuid4(), "菜色", "3.000000")], "4.000000")
        ], supplier_id)
    assert caught.value.code == "SNAPSHOT_SOURCE_ALLOCATION_UNAVAILABLE"


def test_source_units_use_existing_weight_conversion_without_rounding():
    supplier_id = uuid4()
    rows = rows_from_snapshot_items([
        {
            **item(supplier_id, [
                source(uuid4(), "菜單", "2026-11-02", uuid4(), "菜一", "1500", "g"),
                source(uuid4(), "菜單", "2026-11-02", uuid4(), "菜二", "2", "斤"),
            ], "2.700000"),
            "purchase_unit_snapshot": "kg",
        }
    ], supplier_id)
    assert [(row["quantity"], row["unit"]) for row in rows] == [(Decimal("1.5"), "kg"), (Decimal("1.2"), "kg")]


def test_workbook_converts_all_supported_weight_units_to_numeric_kg_without_extra_rounding():
    menu_id = str(uuid4())
    common = {
        "menu_id": menu_id,
        "menu_name": "測試菜單",
        "requirement_date": date(2026, 11, 2),
        "meal_type_name": "中餐",
        "supplier_name": "方豪",
    }
    rows = [
        {**common, "dish_id": str(uuid4()), "dish_name": "菜一", "ingredient_name": "食材一", "quantity": Decimal("4000"), "unit": "g"},
        {**common, "dish_id": str(uuid4()), "dish_name": "菜二", "ingredient_name": "食材二", "quantity": Decimal("6500"), "unit": "g"},
        {**common, "dish_id": str(uuid4()), "dish_name": "菜三", "ingredient_name": "食材三", "quantity": Decimal("5.25"), "unit": "斤"},
        {**common, "dish_id": str(uuid4()), "dish_name": "菜四", "ingredient_name": "食材四", "quantity": Decimal("2.75"), "unit": "kg"},
    ]
    sheet = load_workbook(BytesIO(supplier_weekly_workbook(rows))).active
    exported={sheet.cell(row,2).value:sheet.cell(row,3).value for row in range(6,10)}
    assert exported == {"食材一":4,"食材二":6.5,"食材三":3.15,"食材四":2.75}
    assert [sheet.cell(row, 3).data_type for row in range(6, 10)] == ["n", "n", "n", "n"]
    assert [sheet.cell(row, 4).value for row in range(6, 10)] == ["kg", "kg", "kg", "kg"]


@pytest.mark.parametrize("unit", ["片", "個", "隻", "包", "盒", "袋", "箱", "ml", "L", "罐", "桶"])
def test_workbook_preserves_legal_non_weight_quantity_and_unit(unit):
    common = {
        "menu_id": str(uuid4()),
        "menu_name": "測試菜單",
        "requirement_date": date(2026, 11, 2),
        "meal_type_name": "中餐",
        "supplier_name": "方豪",
    }
    rows = [
        {**common, "dish_id": str(uuid4()), "dish_name": "重量菜色", "ingredient_name": "高麗菜", "quantity": Decimal("4000"), "unit": "g"},
        {**common, "dish_id": str(uuid4()), "dish_name": "非重量菜色", "ingredient_name": f"非重量-{unit}", "quantity": Decimal("10"), "unit": unit},
    ]
    sheet = load_workbook(BytesIO(supplier_weekly_workbook(rows))).active
    actual = {
        sheet.cell(row, 2).value: (sheet.cell(row, 3).value, sheet.cell(row, 4).value, sheet.cell(row, 3).data_type)
        for row in range(6, 8)
    }
    assert actual == {"高麗菜": (4, "kg", "n"), f"非重量-{unit}": (10, unit, "n")}


def test_workbook_with_only_piece_each_and_animal_units_is_exportable():
    menu_id = str(uuid4())
    rows = [
        {
            "menu_id": menu_id,
            "menu_name": "測試菜單",
            "requirement_date": date(2026, 11, 2),
            "meal_type_name": "中餐",
            "dish_id": str(uuid4()),
            "dish_name": "菜色",
            "ingredient_name": ingredient,
            "quantity": quantity,
            "unit": unit,
            "supplier_name": "方豪",
        }
        for ingredient, quantity, unit in (("雞排", Decimal("120"), "片"), ("雞蛋", Decimal("450"), "個"), ("柳葉魚", Decimal("210"), "隻"))
    ]
    sheet = load_workbook(BytesIO(supplier_weekly_workbook(rows))).active
    actual = {(sheet.cell(row, 2).value, sheet.cell(row, 3).value, sheet.cell(row, 4).value) for row in range(6, 9)}
    assert actual == {("雞排", 120, "片"), ("雞蛋", 450, "個"), ("柳葉魚", 210, "隻")}


def test_supplier_weekly_no_items_error_has_a_stable_client_code():
    response = mapped(SupplierWeeklyExportError("SUPPLIER_ORDER_NO_ITEMS"))
    assert response.status_code == 422
    assert response.detail == {"code": "SUPPLIER_ORDER_NO_ITEMS"}


def test_workbook_without_any_demand_rows_returns_clear_no_items_error():
    with pytest.raises(SupplierWeeklyExportError) as caught:
        supplier_weekly_workbook([])
    assert caught.value.code == "SUPPLIER_ORDER_NO_ITEMS"


@pytest.mark.parametrize("unit", [None, "", "   ", "公克", "damaged-unit"])
def test_workbook_rejects_missing_or_unknown_units_instead_of_silently_omitting(unit):
    with pytest.raises(SupplierWeeklyExportError) as caught:
        supplier_weekly_workbook([{
            "menu_id": str(uuid4()),
            "menu_name": "測試菜單",
            "requirement_date": date(2026, 11, 2),
            "meal_type_name": "中餐",
            "dish_id": str(uuid4()),
            "dish_name": "菜色",
            "ingredient_name": "資料異常食材",
            "quantity": Decimal("10"),
            "unit": unit,
            "supplier_name": "方豪",
        }])
    assert caught.value.code == "SUPPLIER_ORDER_UNIT_INVALID"


def test_non_weight_only_date_menu_group_creates_its_own_sheet():
    menu_id = str(uuid4())
    rows = [
        {
            "menu_id": menu_id,
            "menu_name": "重量菜單",
            "requirement_date": date(2026, 11, 2),
            "meal_type_name": "中餐",
            "dish_id": str(uuid4()),
            "dish_name": "重量菜色",
            "ingredient_name": "高麗菜",
            "quantity": Decimal("1"),
            "unit": "kg",
            "supplier_name": "方豪",
        },
        {
            "menu_id": menu_id,
            "menu_name": "非重量菜單",
            "requirement_date": date(2026, 11, 3),
            "meal_type_name": "中餐",
            "dish_id": str(uuid4()),
            "dish_name": "非重量菜色",
            "ingredient_name": "雞排",
            "quantity": Decimal("10"),
            "unit": "片",
            "supplier_name": "方豪",
        },
    ]
    workbook = load_workbook(BytesIO(supplier_weekly_workbook(rows)))
    assert workbook.sheetnames == ["重量菜單_1102", "非重量菜單_1103"]
    assert workbook["非重量菜單_1103"]["C6"].value == 10
    assert workbook["非重量菜單_1103"]["D6"].value == "片"


def test_non_weight_support_does_not_bypass_snapshot_source_reconciliation():
    supplier_id = uuid4()
    bad_item = item(
        supplier_id,
        [source(uuid4(), "菜單", "2026-11-02", uuid4(), "雞排", "10", "片")],
        "11",
    )
    bad_item["requirement_unit"] = "片"
    bad_item["purchase_unit_snapshot"] = "片"
    with pytest.raises(SupplierWeeklyExportError) as caught:
        rows_from_snapshot_items([bad_item], supplier_id)
    assert caught.value.code == "SNAPSHOT_SOURCE_ALLOCATION_UNAVAILABLE"


def test_adjustment_export_preserves_saved_effective_quantity_and_unit_for_every_legal_unit():
    supplier_id = uuid4()
    common = {
        "source_supplier_id": supplier_id,
        "source_menu_id": uuid4(),
        "menu_name_snapshot": "叫貨調整菜單",
        "requirement_date": date(2026, 11, 2),
        "meal_type_name_snapshot": "中餐",
        "supplier_name_snapshot": "方豪",
        "meal_type_sort_order_snapshot": 1,
        "menu_dish_sort_order_snapshot": 1,
        "dish_ingredient_sort_order_snapshot": 1,
    }
    lines = [
        SimpleNamespace(
            **common,
            id=uuid4(),
            source_dish_id=uuid4(),
            dish_name_snapshot="調整重量菜色",
            ingredient_name_snapshot="高麗菜",
            system_quantity=Decimal("4000"),
            system_unit="g",
            adjusted_quantity=Decimal("5.25"),
            adjusted_unit="斤",
        ),
        SimpleNamespace(
            **common,
            id=uuid4(),
            source_dish_id=uuid4(),
            dish_name_snapshot="調整非重量菜色",
            ingredient_name_snapshot="雞排",
            system_quantity=Decimal("1000"),
            system_unit="g",
            adjusted_quantity=Decimal("10"),
            adjusted_unit="片",
        ),
    ]
    rows = rows_from_adjustment_lines(lines, supplier_id)
    sheet = load_workbook(BytesIO(supplier_weekly_workbook(rows))).active
    actual = {
        sheet.cell(row, 2).value: (sheet.cell(row, 3).value, sheet.cell(row, 4).value)
        for row in range(6, 8)
    }
    assert actual == {"高麗菜": (3.15, "kg"), "雞排": (10, "片")}
