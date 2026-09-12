from datetime import date
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

from docx import Document

from app.domains.postpartum.catering_overview_docx import render_catering_overview_docx


def item(index, *, restriction="不牛", note="少鹽"):
    return {
        "case_id": uuid4(), "case_number": f"C{index:03}", "name": f"個案{index}",
        "current_room": str(index), "preparation_mode": "herbal", "preparation_mode_label": "要中藥",
        "service_start_date": date(2026, 8, 23), "service_start_meal": "lunch", "service_start_meal_label": "午餐",
        "service_end_date": date(2026, 9, 2), "service_end_meal": "morning_snack", "service_end_meal_label": "早點",
        "restriction_groups": [{"id": uuid4(), "name": restriction, "color": "#AA0000", "is_active": True}],
        "service_note": note, "service_meals": [],
    }


def payload(items):
    return {"target_date": date(2026, 9, 7), "weekday_label": "星期一", "total": len(items), "items": items}


def xml_for(content):
    return ZipFile(BytesIO(content)).read("word/document.xml").decode("utf-8")


def main_tables(document):
    return [table for table in document.tables if table.rows[0].cells[0].text == "床號"]


def header_tables(document):
    return [table for table in document.tables if table.rows[0].cells[0].text.startswith("2026 年")]


def test_docx_is_editable_a4_portrait_with_four_operational_columns():
    case = item(501)
    content = render_catering_overview_docx(payload([case]))
    document = Document(BytesIO(content))
    section = document.sections[0]
    xml = xml_for(content)
    assert round(section.page_width.cm, 1) == 21.0 and round(section.page_height.cm, 1) == 29.7
    assert len(main_tables(document)) == 1 and len(main_tables(document)[0].columns) == 4
    assert [cell.text for cell in main_tables(document)[0].rows[0].cells] == ["床號", "姓名", "調理方式", "飲食禁忌／備註"]
    assert len(header_tables(document)) == 1 and len(header_tables(document)[0].rows) == 1
    assert len(header_tables(document)[0].columns) == 3
    assert [cell.text for cell in header_tables(document)[0].rows[0].cells] == [
        "2026 年 09 月 07 日（星期一）", "供餐總床數：1 床", "第 1 頁 / 共 1 頁",
    ]
    for value in ("2026 年 09 月 07 日（星期一）", "供餐總床數：1 床", "第 1 頁 / 共 1 頁", "床號", "姓名", "要中藥", "起伙：8/23 午餐", "不牛", "少鹽"):
        assert value in xml
    assert "停伙：" not in xml
    assert "月子餐個案供餐總覽表" not in xml
    assert "C501" not in xml
    assert ">起伙<" not in xml and ">停伙<" not in xml
    assert str(case["case_id"]) not in xml and str(case["restriction_groups"][0]["id"]) not in xml
    assert 'w:sz w:val="30"' in xml  # 15 pt one-row date
    assert 'w:sz w:val="30"' in xml  # 15 pt case name and room
    assert 'w:sz w:val="19"' in xml  # 9.5 pt start and stop
    assert 'w:sz w:val="30"' in xml  # 15 pt room
    assert 'w:color w:val="A61B1B"' in xml
    assert 'w:color w:val="1F4E79"' in xml
    assert "紅色代表" not in xml and "UUID" not in xml
    assert xml.count("w:noWrap") == 3

    person_cell = main_tables(document)[0].rows[1].cells[1]
    paragraphs = person_cell.paragraphs
    assert len(paragraphs) == 2
    name_run = next(run for run in paragraphs[0].runs if run.text)
    start_run = next(run for run in paragraphs[1].runs if run.text)
    assert "<w:b" in name_run._r.xml
    assert name_run.font.size.pt == 15
    assert start_run.font.size.pt == 9.5
    assert name_run.font.size.pt > start_run.font.size.pt
    person_xml = person_cell._tc.xml
    assert person_xml.count("<w:pBdr>") == 1
    assert "<w:pBdr>" in paragraphs[0]._p.xml
    assert "<w:pBdr>" not in paragraphs[1]._p.xml


def test_docx_logical_pages_repeat_report_header_and_keep_long_text():
    items = [item(index) for index in range(1, 25)]
    long_text = "不牛、不羊、不內臟、不魚、不甲殼類、不奶、不花生、不芝麻、不芒果"
    long_note = "每餐分開包裝，送達前通知護理站並再次核對床號。" * 4
    items[5] = item(6, restriction=long_text, note=long_note)
    content = render_catering_overview_docx(payload(items))
    xml = xml_for(content)
    assert "月子餐個案供餐總覽表" not in xml
    page_count = xml.count("2026 年 09 月 07 日（星期一）")
    assert page_count == 2
    assert xml.count("2026 年 09 月 07 日（星期一）") == page_count
    assert xml.count("供餐總床數：24 床") == page_count
    document = Document(BytesIO(content))
    assert len(header_tables(document)) == page_count
    assert len(main_tables(document)) == page_count
    assert all(len(table.columns) == 4 for table in main_tables(document))
    assert f"第 {page_count} 頁 / 共 {page_count} 頁" in xml
    assert long_text in xml and long_note in xml
    assert xml.count("w:cantSplit") >= len(items) + page_count


def test_stop_data_and_case_number_are_not_rendered():
    case = item(501)
    content = render_catering_overview_docx(payload([case]))
    document = Document(BytesIO(content))
    cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    assert not any("停伙：" in value for value in cells)
    assert case["case_number"] not in xml_for(content)


def test_combined_cell_handles_restriction_only_note_only_and_empty_without_blank_lines():
    restriction_only = item(501, note="")
    note_only = item(502, restriction="", note="青菜加量")
    note_only["restriction_groups"] = []
    empty = item(503, restriction="", note="")
    empty["restriction_groups"] = []
    content = render_catering_overview_docx(payload([restriction_only, note_only, empty]))
    document = Document(BytesIO(content))
    rows = main_tables(document)[0].rows[1:]
    assert rows[0].cells[3].text == "不牛"
    assert rows[1].cells[3].text == "青菜加量"
    assert rows[2].cells[3].text == "—"
    xml = xml_for(content)
    assert 'w:color w:val="A61B1B"' in xml and 'w:color w:val="1F4E79"' in xml
    note_run = next(run for run in rows[1].cells[3].paragraphs[0].runs if run.text)
    assert 'w:color w:val="1F4E79"' in note_run._r.xml
    assert "<w:b" in note_run._r.xml


def test_empty_docx_is_valid_and_explicit():
    content = render_catering_overview_docx(payload([]))
    Document(BytesIO(content))
    assert "本日沒有符合供餐條件的月子餐個案" in xml_for(content)
