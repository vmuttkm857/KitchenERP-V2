from typing import Literal


Meal = Literal[
    "breakfast",
    "morning_snack",
    "lunch",
    "afternoon_snack",
    "dinner",
    "evening_snack",
]

MEAL_VALUES: tuple[Meal, ...] = (
    "breakfast",
    "morning_snack",
    "lunch",
    "afternoon_snack",
    "dinner",
    "evening_snack",
)
MEAL_ORDER = {meal: order for order, meal in enumerate(MEAL_VALUES)}
MEAL_LABELS: dict[Meal, str] = {
    "breakfast": "早餐",
    "morning_snack": "早點",
    "lunch": "午餐",
    "afternoon_snack": "午點",
    "dinner": "晚餐",
    "evening_snack": "晚點",
}


def meal_check(column: str) -> str:
    values = ",".join(f"'{meal}'" for meal in MEAL_VALUES)
    return f"{column} IN ({values})"
