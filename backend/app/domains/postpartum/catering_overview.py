from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict

from app.domains.postpartum.meals import MEAL_LABELS, MEAL_VALUES
from app.domains.postpartum.timeline import service_is_eligible_at


PREPARATION_MODE_LABELS = {
    "no_herbal": "不中藥",
    "herbal": "要中藥",
    "rice_wine_sesame": "米酒水＋麻油",
    "no_rice_wine_sesame": "不米酒水＋麻油",
}
WEEKDAY_LABELS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _natural_key(value: str | None):
    text = (value or "").strip()
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text))


def build_catering_overview(target_date, cases, pauses, group_rows):
    pauses_by_case = defaultdict(list)
    for pause in pauses:
        pauses_by_case[pause.case_id].append(
            (pause.start_date, pause.start_meal, pause.end_date, pause.end_meal)
        )
    groups_by_case = defaultdict(list)
    for row in group_rows:
        groups_by_case[row["case_id"]].append({
            "id": row["restriction_group_id"],
            "name": row["name"],
            "color": row["color"],
            "is_active": row["is_active"],
        })

    items = []
    for case in cases:
        eligible_meals = [
            meal for meal in MEAL_VALUES
            if service_is_eligible_at(
                target_date, meal, case.service_start_date, case.service_start_meal,
                case.service_end_date, case.service_end_meal, pauses_by_case[case.id],
            )
        ]
        if not eligible_meals:
            continue
        items.append({
            "case_id": case.id,
            "case_number": case.case_number,
            "name": case.name,
            "current_room": case.current_room,
            "preparation_mode": case.preparation_mode,
            "preparation_mode_label": PREPARATION_MODE_LABELS[case.preparation_mode],
            "service_start_date": case.service_start_date,
            "service_start_meal": case.service_start_meal,
            "service_start_meal_label": MEAL_LABELS[case.service_start_meal],
            "service_end_date": case.service_end_date,
            "service_end_meal": case.service_end_meal,
            "service_end_meal_label": MEAL_LABELS[case.service_end_meal] if case.service_end_meal else None,
            "restriction_groups": groups_by_case[case.id],
            "service_note": case.service_note,
            "service_meals": [
                {"meal": meal, "label": MEAL_LABELS[meal]} for meal in eligible_meals
            ],
        })
    items.sort(key=lambda item: (
        not bool((item["current_room"] or "").strip()),
        _natural_key(item["current_room"]),
        (item["case_number"] or "").casefold(),
        (item["name"] or "").casefold(),
        str(item["case_id"]),
    ))
    return {
        "target_date": target_date,
        "weekday_label": WEEKDAY_LABELS[target_date.weekday()],
        "total": len(items),
        "items": items,
    }


def _display_width(value: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in "WFA" else 1 for char in value)


def catering_row_weight(item) -> int:
    restriction_text = "、".join(group["name"] for group in item.get("restriction_groups", []))
    restriction_lines = math.ceil(_display_width(restriction_text) / 32) if restriction_text else 0
    note_lines = math.ceil(_display_width(item.get("service_note") or "") / 32) if item.get("service_note") else 0
    preparation_lines = math.ceil(_display_width(item.get("preparation_mode_label") or "") / 10) or 1
    estimated_lines = max(restriction_lines + note_lines, preparation_lines, 3)
    # Ordinary content up to four wrapped lines remains one normal row. Only genuinely
    # long content consumes extra page capacity, without truncating or shrinking text.
    return 1 + max(0, estimated_lines - 4)


def paginate_catering_items(items, capacity: int = 16, max_cases: int = 12):
    pages, current, weight = [], [], 0
    for item in items:
        item_weight = catering_row_weight(item)
        if current and (len(current) >= max_cases or weight + item_weight > capacity):
            pages.append(current)
            current, weight = [], 0
        current.append(item)
        weight += item_weight
    if current or not pages:
        pages.append(current)
    return pages
