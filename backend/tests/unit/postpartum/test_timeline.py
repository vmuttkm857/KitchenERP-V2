from datetime import date

from app.domains.postpartum.meals import MEAL_ORDER, MEAL_VALUES
from app.domains.postpartum.timeline import (
    moment_in_interval, postpartum_week, postpartum_week_ranges, service_is_eligible_at, valid_interval,
)


def test_four_postpartum_weeks_are_calculated_from_delivery_date():
    ranges = postpartum_week_ranges(date(2026, 9, 1))
    assert ranges == [
        (date(2026, 9, 1), date(2026, 9, 7)),
        (date(2026, 9, 8), date(2026, 9, 14)),
        (date(2026, 9, 15), date(2026, 9, 21)),
        (date(2026, 9, 22), date(2026, 9, 28)),
    ]
    assert postpartum_week(date(2026, 9, 1), date(2026, 8, 31)) == "before_delivery"
    assert postpartum_week(date(2026, 9, 1), date(2026, 9, 21)) == 3
    assert postpartum_week(date(2026, 9, 1), date(2026, 9, 29)) == "after_week_4"


def test_week_ranges_and_every_boundary_start_on_the_delivery_date():
    delivery = date(2026, 9, 8)
    assert postpartum_week_ranges(delivery) == [
        (date(2026, 9, 8), date(2026, 9, 14)),
        (date(2026, 9, 15), date(2026, 9, 21)),
        (date(2026, 9, 22), date(2026, 9, 28)),
        (date(2026, 9, 29), date(2026, 10, 5)),
    ]
    assert postpartum_week(delivery, date(2026, 9, 8)) == 1
    assert postpartum_week(delivery, date(2026, 9, 14)) == 1
    assert postpartum_week(delivery, date(2026, 9, 15)) == 2
    assert postpartum_week(delivery, date(2026, 10, 5)) == 4
    assert postpartum_week(delivery, date(2026, 10, 6)) == "after_week_4"


def test_meal_order_controls_same_day_interval_validation():
    day = date(2026, 9, 8)
    assert MEAL_VALUES == (
        "breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner", "evening_snack",
    )
    assert list(MEAL_ORDER.values()) == list(range(6))
    assert valid_interval(day, "breakfast", day, "evening_snack")
    assert not valid_interval(day, "afternoon_snack", day, "lunch")


def test_service_and_pause_interval_boundaries_are_inclusive_and_cross_day():
    day = date(2026, 9, 8)
    assert moment_in_interval(day, "afternoon_snack", day, "afternoon_snack", day, "evening_snack")
    assert moment_in_interval(day, "evening_snack", day, "afternoon_snack", day, "evening_snack")
    assert not moment_in_interval(day, "lunch", day, "afternoon_snack", day, "evening_snack")
    assert moment_in_interval(
        date(2026, 9, 9), "morning_snack",
        day, "afternoon_snack", date(2026, 9, 9), "morning_snack",
    )
    assert not moment_in_interval(
        date(2026, 9, 9), "lunch",
        day, "afternoon_snack", date(2026, 9, 9), "morning_snack",
    )


def test_service_eligibility_uses_inclusive_open_end_and_pause_boundaries():
    start = date(2026, 9, 8)
    assert service_is_eligible_at(start, "breakfast", start, "breakfast", None, None)
    assert not service_is_eligible_at(start, "breakfast", start, "morning_snack", None, None)
    assert service_is_eligible_at(start, "lunch", start, "breakfast", start, "lunch")
    assert not service_is_eligible_at(start, "afternoon_snack", start, "breakfast", start, "lunch")
    pauses = [(start, "lunch", start, "dinner")]
    assert not service_is_eligible_at(start, "lunch", start, "breakfast", None, None, pauses)
    assert not service_is_eligible_at(start, "dinner", start, "breakfast", None, None, pauses)
    assert service_is_eligible_at(start, "evening_snack", start, "breakfast", None, None, pauses)
