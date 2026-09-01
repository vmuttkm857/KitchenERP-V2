from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.nutrition.models import NutritionFoodValue, NutritionNutrient
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


PASSWORD = "correct horse battery staple"


def auth_headers(client: TestClient, session: Session):
    user = UserService(session).create_user(CreateUserCommand(
        username="nutrition_calc", password=PASSWORD, display_name="Nutrition Calc", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def setup_dish(client: TestClient, headers: dict[str, str]):
    ingredient_category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "營養食材"}).json()
    dish_category = client.post("/api/v1/categories/dish", headers=headers, json={"name": "營養菜色"}).json()
    food = client.post("/api/v1/nutrition/manual-foods", headers=headers, json={
        "name": "雞肉營養", "nutrients": {"corrected_energy": "200", "energy": "999", "protein": "20"},
    }).json()
    ingredient = client.post("/api/v1/ingredients", headers=headers, json={
        "code": "NC-I", "name": "營養雞肉", "category_id": ingredient_category["id"], "unit": "g", "current_price": "1",
    }).json()
    client.patch(f"/api/v1/ingredients/{ingredient['id']}/nutrition", headers=headers, json={"nutrition_food_id": food["id"]})
    dish = client.post("/api/v1/dishes", headers=headers, json={
        "code": "NC-D", "name": "營養雞肉料理", "category_id": dish_category["id"],
    }).json()
    client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{
        "ingredient_id": ingredient["id"], "quantity": "150", "unit": "g", "loss_rate": "80",
    }]})
    return dish, ingredient, food, dish_category


def test_dish_nutrition_requires_authentication(client: TestClient):
    assert client.get("/api/v1/dishes/00000000-0000-0000-0000-000000000001/nutrition").status_code == 401
    assert client.post("/api/v1/dishes/nutrition/bulk", json={"dish_ids": ["00000000-0000-0000-0000-000000000001"]}).status_code == 401


def test_dish_nutrition_response_is_live_read_only_and_does_not_apply_loss(client: TestClient, db_session: Session):
    headers = auth_headers(client, db_session); dish, ingredient, food, _ = setup_dish(client, headers)
    first = client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["basis"] == "per_person_recipe"
    assert Decimal(first.json()["calorie_value"]) == Decimal("300")
    assert Decimal(first.json()["nutrients"]["protein"]["value"]) == Decimal("30")

    recipe = client.get(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers).json()
    item = recipe["items"][0]
    client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{
        "id": item["id"], "ingredient_id": ingredient["id"], "quantity": "100", "unit": "g", "loss_rate": "80",
    }]})
    assert Decimal(client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()["calorie_value"]) == Decimal("200")

    client.patch(f"/api/v1/nutrition/manual-foods/{food['id']}", headers=headers, json={
        "nutrients": {"corrected_energy": "250", "protein": "20"},
    })
    assert Decimal(client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()["calorie_value"]) == Decimal("250")
    client.post(f"/api/v1/nutrition/manual-foods/{food['id']}/deactivate", headers=headers)
    assert Decimal(client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()["calorie_value"]) == Decimal("250")

    client.patch(f"/api/v1/ingredients/{ingredient['id']}/nutrition", headers=headers, json={"nutrition_food_id": None})
    missing = client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()
    assert missing["calorie_value"] is None and missing["calorie_complete"] is False
    assert missing["missing_calorie_ingredients"][0]["reason"] == "no_nutrition_mapping"


def test_zero_calorie_is_serialized_as_available_not_null(client: TestClient, db_session: Session):
    headers = auth_headers(client, db_session)
    ingredient_category = client.post("/api/v1/categories/ingredient", headers=headers, json={"name": "零值食材"}).json()
    dish_category = client.post("/api/v1/categories/dish", headers=headers, json={"name": "零值菜色"}).json()
    food = client.post("/api/v1/nutrition/manual-foods", headers=headers, json={"name": "零熱量", "nutrients": {"corrected_energy": "0"}}).json()
    ingredient = client.post("/api/v1/ingredients", headers=headers, json={"code": "ZERO-N", "name": "零值營養食材", "category_id": ingredient_category["id"], "unit": "g", "current_price": "0"}).json()
    client.patch(f"/api/v1/ingredients/{ingredient['id']}/nutrition", headers=headers, json={"nutrition_food_id": food["id"]})
    dish = client.post("/api/v1/dishes", headers=headers, json={"code": "ZERO-D", "name": "零熱量菜色", "category_id": dish_category["id"]}).json()
    client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{"ingredient_id": ingredient["id"], "quantity": "100", "unit": "g"}]})
    result = client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()
    assert result["calorie_complete"] is True and Decimal(result["calorie_value"]) == Decimal("0")


def test_explicit_conversion_crud_is_validated_and_reflected_immediately(client: TestClient, db_session: Session):
    headers = auth_headers(client, db_session); dish, ingredient, _, _ = setup_dish(client, headers)
    assert client.patch(f"/api/v1/ingredients/{ingredient['id']}", headers=headers, json={"unit": "包"}).status_code == 200
    recipe = client.get(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers).json()["items"][0]
    replaced = client.put(f"/api/v1/dishes/{dish['id']}/recipe", headers=headers, json={"items": [{
        "id": recipe["id"], "ingredient_id": ingredient["id"], "quantity": "1", "unit": "包",
    }]})
    assert replaced.status_code == 200, replaced.text
    unavailable = client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()
    assert unavailable["calorie_value"] is None
    assert unavailable["missing_calorie_ingredients"][0]["reason"] == "unsafe_unit_conversion"

    created = client.post(f"/api/v1/ingredients/{ingredient['id']}/nutrition-unit-conversions", headers=headers, json={
        "unit": " 包　", "grams_per_unit": "180",
    })
    assert created.status_code == 201, created.text
    assert created.json()["unit"] == "包" and Decimal(created.json()["grams_per_unit"]) == Decimal("180")
    assert Decimal(client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()["calorie_value"]) == Decimal("360")

    duplicate = client.post(f"/api/v1/ingredients/{ingredient['id']}/nutrition-unit-conversions", headers=headers, json={
        "unit": "包", "grams_per_unit": "190",
    })
    assert duplicate.status_code == 409
    for invalid in ("0", "-1", "NaN", "Infinity"):
        assert client.post(f"/api/v1/ingredients/{ingredient['id']}/nutrition-unit-conversions", headers=headers, json={
            "unit": "個", "grams_per_unit": invalid,
        }).status_code == 422

    conversion_id = created.json()["id"]
    updated = client.patch(f"/api/v1/ingredients/{ingredient['id']}/nutrition-unit-conversions/{conversion_id}", headers=headers, json={
        "grams_per_unit": "200",
    })
    assert updated.status_code == 200
    assert Decimal(client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()["calorie_value"]) == Decimal("400")
    assert client.delete(f"/api/v1/ingredients/{ingredient['id']}/nutrition-unit-conversions/{conversion_id}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()["calorie_value"] is None


def test_dynamic_reportable_nutrients_and_detail_api_are_not_truncated(client: TestClient, db_session: Session):
    headers = auth_headers(client, db_session); dish, _, food, _ = setup_dish(client, headers)
    for index in range(105):
        nutrient = NutritionNutrient(code=f"synthetic_{index:03}", name=f"合成營養素 {index:03}", unit="mg", sort_order=1000 + index)
        db_session.add(nutrient); db_session.flush()
        db_session.add(NutritionFoodValue(food_id=food["id"], nutrient_id=nutrient.id, value=Decimal(index)))
    db_session.commit()
    result = client.get(f"/api/v1/dishes/{dish['id']}/nutrition", headers=headers).json()
    assert len(result["nutrients"]) >= 105
    assert list(result["nutrients"])[-1] == "synthetic_104"
    assert Decimal(result["nutrients"]["synthetic_000"]["value"]) == 0
    detail = client.get(f"/api/v1/nutrition/foods/{food['id']}", headers=headers).json()
    assert len(detail["values"]) >= 105


def test_bulk_nutrition_has_constant_query_count_and_reuses_duplicate_dish(client: TestClient, db_session: Session):
    headers = auth_headers(client, db_session); dish, _, _, dish_category = setup_dish(client, headers)
    second = client.post("/api/v1/dishes", headers=headers, json={
        "code": "NC-D2", "name": "空白營養料理", "category_id": dish_category["id"],
    }).json()
    statements = []
    def record_query(conn, cursor, statement, parameters, context, executemany): statements.append(statement)
    event.listen(process_engine, "before_cursor_execute", record_query)
    try:
        response = client.post("/api/v1/dishes/nutrition/bulk", headers=headers, json={
            "dish_ids": [dish["id"], second["id"], dish["id"]],
        })
    finally:
        event.remove(process_engine, "before_cursor_execute", record_query)
    assert response.status_code == 200, response.text
    assert [item["dish_id"] for item in response.json()["items"]] == [dish["id"], second["id"], dish["id"]]
    assert response.json()["items"][1]["missing_calorie_ingredients"][0]["reason"] == "no_recipe"
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 5  # current user + definitions + recipe inputs + conversions + all food values
