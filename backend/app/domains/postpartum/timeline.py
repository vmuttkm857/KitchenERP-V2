from __future__ import annotations

from datetime import date, timedelta


MEAL_ORDER = {"breakfast": 0, "lunch": 1, "dinner": 2}


def service_moment(date_value: date, meal: str) -> tuple[date, int]:
    return date_value, MEAL_ORDER[meal]


def valid_interval(start_date: date, start_meal: str, end_date: date, end_meal: str) -> bool:
    return service_moment(start_date, start_meal) <= service_moment(end_date, end_meal)


def postpartum_week(delivery_date: date, as_of: date) -> int | str:
    elapsed = (as_of - delivery_date).days
    if elapsed < 0:
        return "before_delivery"
    if elapsed >= 28:
        return "after_week_4"
    return elapsed // 7 + 1


def postpartum_week_ranges(delivery_date: date) -> list[tuple[date, date]]:
    return [(delivery_date + timedelta(days=offset), delivery_date + timedelta(days=offset + 6)) for offset in range(0, 28, 7)]
