from datetime import date

from app.domains.postpartum.timeline import postpartum_week, postpartum_week_ranges, valid_interval


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
    assert valid_interval(day, "breakfast", day, "dinner")
    assert not valid_interval(day, "dinner", day, "breakfast")
