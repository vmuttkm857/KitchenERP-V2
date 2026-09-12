from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.domains.postpartum.catering_overview import build_catering_overview, paginate_catering_items


def case(room, number, *, start_meal="breakfast", end_meal="evening_snack"):
    return SimpleNamespace(
        id=uuid4(), case_number=number, name=f"個案{number}", current_room=room,
        service_start_date=date(2026, 9, 12), service_start_meal=start_meal,
        service_end_date=date(2026, 9, 12), service_end_meal=end_meal,
        preparation_mode="no_herbal", service_note=None,
    )


def test_overview_uses_six_meal_eligibility_and_natural_room_order():
    room_10, room_2, paused = case("10", "C10"), case("2", "C02", start_meal="lunch"), case("3", "C03")
    pauses = [SimpleNamespace(
        case_id=paused.id, start_date=date(2026, 9, 12), start_meal="breakfast",
        end_date=date(2026, 9, 12), end_meal="evening_snack",
    )]
    groups = [{
        "case_id": room_2.id, "restriction_group_id": uuid4(), "name": "不牛",
        "color": "#aa0000", "is_active": False,
    }]
    result = build_catering_overview(date(2026, 9, 12), [room_10, paused, room_2], pauses, groups)
    assert [item["current_room"] for item in result["items"]] == ["2", "10"]
    assert [meal["meal"] for meal in result["items"][0]["service_meals"]] == [
        "lunch", "afternoon_snack", "dinner", "evening_snack",
    ]
    assert result["items"][0]["restriction_groups"][0]["is_active"] is False
    assert result["items"][0]["service_start_date"] == date(2026, 9, 12)
    assert result["items"][0]["service_start_meal_label"] == "午餐"
    assert result["items"][0]["service_end_date"] == date(2026, 9, 12)
    assert result["items"][0]["service_end_meal_label"] == "晚點"
    assert [meal["label"] for meal in result["items"][1]["service_meals"]] == [
        "早餐", "早點", "午餐", "午點", "晚餐", "晚點",
    ]
    assert result["weekday_label"] == "星期六"


def test_start_and_stop_meals_are_inclusive_for_whole_day_membership():
    starts_late = case("1", "START", start_meal="evening_snack")
    stops_early = case("2", "STOP", end_meal="breakfast")
    result = build_catering_overview(date(2026, 9, 12), [starts_late, stops_early], [], [])
    assert [[meal["meal"] for meal in value["service_meals"]] for value in result["items"]] == [
        ["evening_snack"], ["breakfast"],
    ]


def test_stop_date_still_controls_overview_eligibility_after_presentation_hides_it():
    stops_today = case("1", "STOP-TODAY")
    stops_today.service_start_date = date(2026, 9, 11)
    assert build_catering_overview(date(2026, 9, 12), [stops_today], [], [])["total"] == 1
    assert build_catering_overview(date(2026, 9, 13), [stops_today], [], [])["total"] == 0


def test_logical_pagination_is_deterministic_and_keeps_rows_whole():
    items = [{"restriction_groups": [], "service_note": None} for _ in range(24)]
    pages = paginate_catering_items(items)
    assert list(map(len, pages)) == [12, 12]
    long_item = {"restriction_groups": [{"name": "很長的禁忌名稱" * 8}], "service_note": "長備註" * 30}
    assert paginate_catering_items([items[0], long_item, items[1]], capacity=2) == [[items[0]], [long_item], [items[1]]]


def test_twenty_four_normal_or_moderate_rows_prefer_two_pages_but_extreme_can_use_three():
    normal = [{"restriction_groups": [{"name": "不牛、不魚、不奶"}], "service_note": "飯八分滿，青菜加量"} for _ in range(24)]
    moderate = [{"restriction_groups": [{"name": "不牛、不羊、不魚、不奶、不甲殼類"}], "service_note": "分開包裝並再次核對床號，送達前通知護理站"} for _ in range(24)]
    assert list(map(len, paginate_catering_items(normal))) == [12, 12]
    assert list(map(len, paginate_catering_items(moderate))) == [12, 12]
    extreme = [dict(item) for item in normal]
    extreme[5] = {"restriction_groups": [{"name": "極長禁忌" * 10}], "service_note": "極長備註" * 22}
    assert len(paginate_catering_items(extreme)) == 3
