from dataclasses import dataclass
import uuid

from app.domains.menus.models import MenuDish, MenuMealTypeColumn


@dataclass(frozen=True)
class MenuDishVisualRow:
    column_id: uuid.UUID | None
    dish: MenuDish | None


def menu_dish_visual_rows(
    columns: list[MenuMealTypeColumn], dishes: list[MenuDish],
) -> list[MenuDishVisualRow]:
    """Mirror the weekly grid's assignment/fallback/overflow presentation plan."""
    ordered_columns = sorted(columns, key=lambda item: (item.sort_order, item.id))
    ordered_dishes = sorted(dishes, key=lambda item: (item.sort_order, item.id))
    indexes = {column.id: index for index, column in enumerate(ordered_columns)}
    arranged: list[MenuDish | None] = [None] * len(ordered_columns)
    fallback: list[MenuDish] = []
    for dish in ordered_dishes:
        index = indexes.get(dish.menu_meal_type_column_id)
        if index is None or arranged[index] is not None:
            fallback.append(dish)
        else:
            arranged[index] = dish
    for dish in fallback:
        try:
            index = arranged.index(None)
        except ValueError:
            arranged.append(dish)
        else:
            arranged[index] = dish
    row_count = max(len(ordered_columns), len(arranged), 1)
    return [MenuDishVisualRow(
        column_id=ordered_columns[index].id if index < len(ordered_columns) else None,
        dish=arranged[index] if index < len(arranged) else None,
    ) for index in range(row_count)]
