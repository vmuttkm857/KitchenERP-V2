from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Any


def _value(item: object, name: str, default=None):
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _dish_sort_key(item: object) -> tuple:
    identity = _value(item, "menu_dish_id") or _value(item, "id") or _value(item, "dish_id") or ""
    return (_value(item, "sort_order", 0), str(identity))


def plan_menu_dish_rows(
    columns: Iterable[object],
    dishes_by_slot: Mapping[Hashable, Sequence[object]],
) -> dict:
    """Arrange MenuDish values for display without mutating or inferring relationships."""
    ordered_columns = sorted(
        tuple(columns),
        key=lambda item: (_value(item, "sort_order", 0), str(_value(item, "id", ""))),
    )
    column_indexes: dict[Any, int] = {}
    for index, column in enumerate(ordered_columns):
        column_indexes.setdefault(_value(column, "id"), index)

    arranged_slots: dict[Hashable, list[object | None]] = {}
    for slot_key, source_dishes in dishes_by_slot.items():
        arranged: list[object | None] = [None] * len(ordered_columns)
        fallback: list[object] = []
        for dish in sorted(tuple(source_dishes), key=_dish_sort_key):
            assigned_index = column_indexes.get(_value(dish, "menu_meal_type_column_id"))
            if assigned_index is None or arranged[assigned_index] is not None:
                fallback.append(dish)
            else:
                arranged[assigned_index] = dish
        for dish in fallback:
            try:
                empty_index = arranged.index(None)
            except ValueError:
                arranged.append(dish)
            else:
                arranged[empty_index] = dish
        arranged_slots[slot_key] = arranged

    row_count = max(len(ordered_columns), *(len(rows) for rows in arranged_slots.values()), 1)
    for rows in arranged_slots.values():
        rows.extend([None] * (row_count - len(rows)))
    return {"columns": list(ordered_columns), "slots": arranged_slots, "row_count": row_count}
