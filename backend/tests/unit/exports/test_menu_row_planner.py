from copy import deepcopy

from app.domains.exports.menu_row_planner import plan_menu_dish_rows


COLUMNS = [
    {"id": "main-1", "name": "主菜1", "sort_order": 1},
    {"id": "main-2", "name": "主菜2", "sort_order": 2},
    {"id": "veg-1", "name": "青菜1", "sort_order": 3},
    {"id": "veg-2", "name": "青菜2", "sort_order": 4},
    {"id": "side-1", "name": "備菜1", "sort_order": 5},
    {"id": "soup", "name": "湯", "sort_order": 6},
]


def dish(name: str, order: int, column_id=None) -> dict:
    return {
        "dish_id": name,
        "dish_name": name,
        "sort_order": order,
        "menu_meal_type_column_id": column_id,
    }


def names(rows: list[dict | None]) -> list[str | None]:
    return [row["dish_name"] if row is not None else None for row in rows]


def test_all_null_keeps_legacy_sort_order_and_overflow() -> None:
    plan = plan_menu_dish_rows(COLUMNS[:2], {"day": [dish("C", 3), dish("A", 1), dish("B", 2)]})
    assert names(plan["slots"]["day"]) == ["A", "B", "C"]
    assert plan["row_count"] == 3


def test_assignment_keeps_soup_fixed_and_preserves_empty_columns() -> None:
    plan = plan_menu_dish_rows(COLUMNS, {"day": [dish("蘿蔔湯", 1, "soup")]})
    assert names(plan["slots"]["day"]) == [None, None, None, None, None, "蘿蔔湯"]


def test_mixed_assignment_fills_only_unoccupied_rows() -> None:
    plan = plan_menu_dish_rows(COLUMNS, {"day": [
        dish("A", 1, "main-1"), dish("B", 2), dish("C", 3), dish("D", 4, "soup"),
    ]})
    assert names(plan["slots"]["day"]) == ["A", "B", "C", None, None, "D"]


def test_duplicate_or_unknown_assignment_falls_back_without_hiding_dishes() -> None:
    plan = plan_menu_dish_rows(COLUMNS[:2], {"day": [
        dish("A", 1, "main-1"), dish("B", 2, "main-1"), dish("C", 3, "unknown"), dish("D", 4),
    ]})
    assert names(plan["slots"]["day"]) == ["A", "B", "C", "D"]


def test_seven_days_align_same_column_and_planner_does_not_mutate_input() -> None:
    dishes = {
        f"day-{index}": [dish(f"湯-{index}", 1, "soup"), dish(f"主菜-{index}", 2, "main-1")]
        for index in range(7)
    }
    original_columns = deepcopy(COLUMNS); original_dishes = deepcopy(dishes)
    plan = plan_menu_dish_rows(reversed(COLUMNS), dishes)
    assert [column["name"] for column in plan["columns"]] == ["主菜1", "主菜2", "青菜1", "青菜2", "備菜1", "湯"]
    assert all(names(rows)[0] == f"主菜-{index}" and names(rows)[5] == f"湯-{index}" for index, rows in enumerate(plan["slots"].values()))
    assert COLUMNS == original_columns and dishes == original_dishes
