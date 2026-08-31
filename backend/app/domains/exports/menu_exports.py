from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.pagebreak import Break
from PIL import Image, ImageDraw

from app.domains.exports.raster_pdf import GREEN, INK, LINE, PALE_GREEN, font, images_to_pdf, page_image, wrap_text
from app.domains.exports.safety import safe_cell_text

WEEKDAYS = "一二三四五六日"
THIN = Side(style="thin", color="C9D6CC")


def _date_text(value: date) -> str:
    return f"{value.month}/{value.day}（{WEEKDAYS[value.weekday()]}）"


def menu_week_plan(result: dict) -> list[dict]:
    used = {slot["menu_meal_type_id"] for slot in result["slots"]}
    meals = sorted(
        ({"id": meal.id, "name": str(meal.name), "sort_order": meal.sort_order} for meal in result["meal_types"] if meal.is_active or meal.id in used),
        key=lambda item: (item["sort_order"], str(item["id"])),
    )
    slots = {}
    for slot in result["slots"]:
        slots[(slot["menu_date"], slot["menu_meal_type_id"])] = [str(item["dish_name"]) for item in sorted(slot["dishes"], key=lambda item: (item["sort_order"], str(item["dish_id"])))]
    dates = list(result["dates"])
    return [{"dates": dates[start:start + 7], "meals": meals, "slots": slots} for start in range(0, len(dates), 7)] or [{"dates": [], "meals": meals, "slots": slots}]


def full_page_plan(result: dict) -> list[dict]: return menu_week_plan(result)
def pretty_page_plan(result: dict) -> list[dict]: return menu_week_plan(result)


def _density(plan: dict, grid: bool = False) -> tuple[float, float]:
    maximum = max((len(plan["slots"].get((day, meal["id"]), [])) for day in plan["dates"] for meal in plan["meals"]), default=1)
    pressure = len(plan["meals"]) + maximum * (1.25 if grid else .7)
    return (11, 42) if pressure <= 7 else ((9.5, 32) if pressure <= 11 else (8, 24))


def _sheet(workbook: Workbook, title: str):
    sheet = workbook.create_sheet(title[:31]); sheet.sheet_view.showGridLines = False
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4; sheet.page_setup.orientation = sheet.ORIENTATION_LANDSCAPE
    sheet.page_margins.left = sheet.page_margins.right = .18; sheet.page_margins.top = sheet.page_margins.bottom = .25
    sheet.column_dimensions["A"].width = 12
    for column in "BCDEFGH": sheet.column_dimensions[column].width = 20
    return sheet


def _single(sheet, last_row: int):
    sheet.page_setup.fitToWidth = sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True; sheet.print_area = f"A1:H{last_row}"


def _poster(sheet, last_row: int, ends: list[int]):
    sheet.sheet_properties.pageSetUpPr.fitToPage = False; sheet.page_setup.scale = 175
    sheet.page_setup.fitToWidth = sheet.page_setup.fitToHeight = 0; sheet.page_setup.pageOrder = "overThenDown"
    sheet.print_area = f"A1:H{last_row}"; sheet.col_breaks.append(Break(id=4))
    sheet.row_breaks.append(Break(id=ends[(len(ends)-1)//2] if len(ends) > 1 else max(3, last_row//2)))


def _header(sheet, title: str, plan: dict, pretty: bool):
    sheet.merge_cells("A1:H1"); sheet["A1"] = safe_cell_text(title)
    sheet["A1"].font = Font(size=17 if pretty else 15, bold=True, color="244B32"); sheet["A1"].alignment = Alignment(horizontal="center", vertical="center"); sheet.row_dimensions[1].height = 30
    headers = ["餐別"] + [_date_text(day) for day in plan["dates"]] + [""] * (7-len(plan["dates"]))
    for column, value in enumerate(headers, 1):
        cell = sheet.cell(2, column, value); cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="42725A" if pretty else "356B48")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True); cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    sheet.row_dimensions[2].height = 27


def menu_workbook(result: dict, layout: str = "merged", variant: str = "single") -> bytes:
    workbook = Workbook(); del workbook["Sheet"]; plans = menu_week_plan(result)
    label = {"merged": "餐別合併週表", "grid": "菜色分格週表", "pretty": "漂亮公告版"}[layout]
    for index, plan in enumerate(plans, 1):
        sheet = _sheet(workbook, label if len(plans) == 1 else f"{label}-{index}"); _header(sheet, f'{result["menu"]["name"]} {label}', plan, layout == "pretty")
        size, height = _density(plan, layout == "grid")
        if variant == "poster": size, height = size + 2, height * 1.45
        row, ends = 3, []
        for meal in plan["meals"]:
            counts = [len(plan["slots"].get((day, meal["id"]), [])) for day in plan["dates"]]
            rows = max(1, max(counts, default=0)) if layout == "grid" else 1
            for offset in range(rows):
                sheet.cell(row, 1, safe_cell_text(meal["name"]) if offset == 0 else "")
                for day_index in range(7):
                    dishes = plan["slots"].get((plan["dates"][day_index], meal["id"]), []) if day_index < len(plan["dates"]) else []
                    value = dishes[offset] if layout == "grid" and offset < len(dishes) else ("\n".join(dishes) if offset == 0 else "")
                    sheet.cell(row, day_index + 2, safe_cell_text(value))
                for column in range(1, 9):
                    cell = sheet.cell(row, column); cell.font = Font(size=size + (1 if column == 1 else 0), bold=column == 1, color="244B32" if column == 1 else INK.lstrip("#"))
                    cell.fill = PatternFill("solid", fgColor="F3F8F4" if column == 1 else ("FAFCFA" if layout == "pretty" else "FFFFFF"))
                    cell.alignment = Alignment(horizontal="center" if column == 1 or layout == "pretty" else "left", vertical="center", wrap_text=True); cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
                sheet.row_dimensions[row].height = height/rows if layout == "grid" else height; row += 1
            ends.append(row-1)
        last = max(2, row-1); _poster(sheet, last, ends) if variant == "poster" else _single(sheet, last)
    stream = BytesIO(); workbook.save(stream); return stream.getvalue()


def menu_full_workbook(result: dict, variant: str = "single") -> bytes: return menu_workbook(result, "merged", variant)
def menu_grid_workbook(result: dict, variant: str = "single") -> bytes: return menu_workbook(result, "grid", variant)
def menu_pretty_workbook(result: dict) -> bytes: return menu_workbook(result, "pretty")


def menu_pdf(result: dict, layout: str) -> bytes:
    images: list[Image.Image] = []; label = {"merged": "餐別合併週表", "grid": "菜色分格週表", "pretty": "漂亮公告版"}[layout]
    for plan in menu_week_plan(result):
        image = page_image("landscape"); draw = ImageDraw.Draw(image); margin, top = 65, 105
        draw.text((image.width//2, 42), f'{result["menu"]["name"]} {label}', font=font(17), fill=GREEN, anchor="ma")
        meal_w = 150; day_w = (image.width-margin*2-meal_w)/7; header_h = 60
        headers = ["餐別"] + [_date_text(day) for day in plan["dates"]] + [""]*(7-len(plan["dates"])); x = margin
        for i, value in enumerate(headers):
            width = meal_w if i == 0 else day_w; draw.rectangle((x, top, x+width, top+header_h), fill=GREEN, outline=LINE, width=2)
            draw.text((x+width/2, top+header_h/2), value, font=font(8.5), fill="white", anchor="mm"); x += width
        row_h = (image.height-top-header_h-55)/max(1, len(plan["meals"])); body_size = max(7, min(11, row_h/8)); y = top+header_h
        for meal in plan["meals"]:
            draw.rectangle((margin, y, margin+meal_w, y+row_h), fill=PALE_GREEN, outline=LINE, width=2); draw.text((margin+meal_w/2, y+row_h/2), meal["name"], font=font(body_size+1), fill=GREEN, anchor="mm")
            for day_i in range(7):
                left = margin+meal_w+day_i*day_w; draw.rectangle((left, y, left+day_w, y+row_h), fill="#FAFCFA" if layout == "pretty" else "white", outline=LINE, width=2)
                dishes = plan["slots"].get((plan["dates"][day_i], meal["id"]), []) if day_i < len(plan["dates"]) else []
                if layout == "grid" and dishes:
                    part = row_h/len(dishes)
                    for j, dish in enumerate(dishes):
                        if j: draw.line((left, y+j*part, left+day_w, y+j*part), fill=LINE, width=1)
                        lines = wrap_text(draw, dish, font(body_size), day_w-18); draw.multiline_text((left+day_w/2, y+(j+.5)*part), "\n".join(lines), font=font(body_size), fill=INK, anchor="mm", align="center", spacing=3)
                else: draw.multiline_text((left+day_w/2, y+row_h/2), "\n".join(dishes), font=font(body_size), fill=INK, anchor="mm", align="center", spacing=5)
            y += row_h
        images.append(image)
    return images_to_pdf(images, "landscape")


def menu_full_pdf(result: dict) -> bytes: return menu_pdf(result, "merged")
def menu_grid_pdf(result: dict) -> bytes: return menu_pdf(result, "grid")
def menu_pretty_pdf(result: dict) -> bytes: return menu_pdf(result, "pretty")
