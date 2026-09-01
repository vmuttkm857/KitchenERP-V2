import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import event,select
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.recipes.models import DishIngredient
from app.domains.users.models import User
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService

PASSWORD="correct horse battery staple"


def auth(client:TestClient,session:Session):
    user=UserService(session).create_user(CreateUserCommand(username="requirements_admin",password=PASSWORD,display_name="Requirements Admin",role="admin"))
    token=client.post("/api/v1/auth/login",json={"username":user.username,"password":PASSWORD}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def fixture(client,headers):
    ingredient_category=client.post("/api/v1/categories/ingredient",headers=headers,json={"name":"需求食材"}).json()
    dish_category=client.post("/api/v1/categories/dish",headers=headers,json={"name":"需求菜色"}).json()
    menu_category=client.post("/api/v1/categories/menu",headers=headers,json={"name":"需求菜單"}).json()
    suppliers=[client.post("/api/v1/suppliers",headers=headers,json={"code":f"REQ-S{i}","name":f"供應商{i}"}).json() for i in (1,2)]
    ingredient_specs=[("REQ-I1","雞肉","kg","200",suppliers[0]["id"],"箱","10","5"),("REQ-I2","鹽","kg","20",suppliers[0]["id"],"kg","1","0"),("REQ-I3","水","L","2",suppliers[1]["id"],"L","1","0")]
    ingredients=[]
    for code,name,unit,price,supplier,purchase_unit,package,min_order in ingredient_specs:
        response=client.post("/api/v1/ingredients",headers=headers,json={"code":code,"name":name,"category_id":ingredient_category["id"],"unit":unit,"current_price":price,"primary_supplier_id":supplier,"purchase_unit":purchase_unit,"package_size":package,"minimum_order_quantity":min_order})
        assert response.status_code==201,response.text;ingredients.append(response.json())
    dishes=[]
    for i,name in enumerate(("雞肉餐","雞肉湯"),1):
        dishes.append(client.post("/api/v1/dishes",headers=headers,json={"code":f"REQ-D{i}","name":name,"category_id":dish_category["id"]}).json())
    recipes=[
        {"items":[{"ingredient_id":ingredients[0]["id"],"quantity":"100","unit":"g","loss_rate":"10","sort_order":1},{"ingredient_id":ingredients[1]["id"],"quantity":"5","unit":"g","loss_rate":"0","sort_order":2}]},
        {"items":[{"ingredient_id":ingredients[0]["id"],"quantity":"0.2","unit":"kg","loss_rate":"0","sort_order":1},{"ingredient_id":ingredients[2]["id"],"quantity":"0.25","unit":"L","loss_rate":"0","sort_order":2}]},
    ]
    for dish,recipe in zip(dishes,recipes): assert client.put(f"/api/v1/dishes/{dish['id']}/recipe",headers=headers,json=recipe).status_code==200
    menu=client.post("/api/v1/menus",headers=headers,json={"name":"三日需求菜單","start_date":"2026-09-01","end_date":"2026-09-03","category_id":menu_category["id"]}).json()
    meals=[client.post(f"/api/v1/menus/{menu['id']}/meal-types",headers=headers,json={"name":name,"sort_order":i}).json() for i,name in enumerate(("早餐","午餐","晚餐"),1)]
    slots=[]
    for day in ("2026-09-01","2026-09-02","2026-09-03"):
        for meal in meals:
            slots.append({"menu_date":day,"menu_meal_type_id":meal["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":10,"sort_order":1},{"dish_id":dishes[1]["id"],"diner_count":5,"sort_order":2}]})
    assert client.put(f"/api/v1/menus/{menu['id']}/editor",headers=headers,json={"slots":slots}).status_code==200
    return menu,meals,dishes,ingredients,suppliers


def test_unauthorized_requirement_calculation(client):
    assert client.post("/api/v1/requirements/calculate",json={"menu_ids":["00000000-0000-0000-0000-000000000001"]}).status_code==401


def test_known_three_day_three_meal_manual_totals_supplier_groups_and_purchase_rule(client,db_session):
    headers=auth(client,db_session);menu,_,_,_,suppliers=fixture(client,headers)
    response=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu["id"]]})
    assert response.status_code==200,response.text;body=response.json();rows={row["ingredient_code"]:row for row in body["rows"]}
    assert Decimal(rows["REQ-I1"]["requirement_quantity"])==Decimal("18.9")
    assert Decimal(rows["REQ-I2"]["requirement_quantity"])==Decimal("0.45")
    assert Decimal(rows["REQ-I3"]["requirement_quantity"])==Decimal("11.25")
    assert Decimal(rows["REQ-I1"]["suggested_purchase_quantity"])==Decimal("18.9")
    assert rows["REQ-I1"]["suggested_purchase_unit"]=="kg" and rows["REQ-I1"]["configured_purchase_unit"]=="箱"
    assert Decimal(rows["REQ-I1"]["package_size"])==10 and Decimal(rows["REQ-I1"]["minimum_order_quantity"])==5
    assert Decimal(rows["REQ-I1"]["estimated_cost"])==3780
    assert Decimal(body["total_estimated_cost"])==Decimal("3811.5") and body["anomaly_summary"]=={"total":0,"errors":0,"warnings":0}
    assert {group["supplier_id"] for group in body["supplier_groups"]}=={supplier["id"] for supplier in suppliers}


def test_selected_date_filter_and_decimal_known_answer(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    body=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu["id"]],"selected_dates":["2026-09-01"]}).json();rows={row["ingredient_code"]:row for row in body["rows"]}
    assert Decimal(rows["REQ-I1"]["requirement_quantity"])==Decimal("6.3")
    assert Decimal(body["total_estimated_cost"])==Decimal("1270.5")


def test_missing_recipe_zero_quantity_incompatible_unit_missing_supplier_and_inactive_source(client,db_session):
    headers=auth(client,db_session);menu,meals,dishes,ingredients,_=fixture(client,headers)
    no_recipe=client.post("/api/v1/dishes",headers=headers,json={"code":"REQ-MISS","name":"無配方","category_id":client.get("/api/v1/categories/dish?active=true",headers=headers).json()["items"][0]["id"]}).json()
    bad_ingredient=client.post("/api/v1/ingredients",headers=headers,json={"code":"REQ-BAD","name":"無供應商食材","category_id":client.get("/api/v1/categories/ingredient?active=true",headers=headers).json()["items"][0]["id"],"unit":"kg","current_price":"10"}).json()
    bad_dish=client.post("/api/v1/dishes",headers=headers,json={"code":"REQ-BAD-D","name":"壞單位菜色"}).json()
    actor_id=db_session.scalar(select(User.id))
    db_session.add(DishIngredient(id=uuid.uuid4(),dish_id=uuid.UUID(bad_dish["id"]),ingredient_id=uuid.UUID(bad_ingredient["id"]),quantity=Decimal("1"),unit="個",loss_rate=Decimal("0"),sort_order=1,created_by=actor_id,updated_by=actor_id))
    db_session.commit()
    conversion=client.post(f"/api/v1/ingredients/{bad_ingredient['id']}/nutrition-unit-conversions",headers=headers,json={"unit":"個","grams_per_unit":"180"})
    assert conversion.status_code==201,conversion.text
    aggregate=client.get(f"/api/v1/menus/{menu['id']}/editor",headers=headers).json();slot=aggregate["slots"][0]
    slot["dishes"].extend([{"dish_id":no_recipe["id"],"diner_count":1,"sort_order":3},{"dish_id":bad_dish["id"],"diner_count":1,"sort_order":4}])
    payload={"slots":[{"menu_day_id":s["menu_day_id"],"menu_date":s["menu_date"],"menu_meal_type_id":s["menu_meal_type_id"],"notes":s["notes"],"dishes":[{"id":d.get("id"),"dish_id":d["dish_id"],"diner_count":d["diner_count"],"notes":d.get("notes"),"sort_order":d["sort_order"]} for d in s["dishes"]]} for s in aggregate["slots"]]}
    assert client.put(f"/api/v1/menus/{menu['id']}/editor",headers=headers,json=payload).status_code==200
    client.post(f"/api/v1/ingredients/{ingredients[0]['id']}/deactivate",headers=headers)
    body=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu["id"]],"selected_dates":["2026-09-01"]}).json();codes={item["code"] for item in body["anomalies"]}
    assert {"MISSING_RECIPE","INCOMPATIBLE_UNIT","MISSING_SUPPLIER","INACTIVE_SOURCE"}.issubset(codes)
    bad_row=next(row for row in body["rows"] if row["ingredient_code"]=="REQ-BAD")
    assert bad_row["suggested_purchase_quantity"] is None and bad_row["estimated_cost"] is None and body["total_estimated_cost"] is None


def test_requirement_query_count_is_constant_and_read_only(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu["id"]]})
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200
    assert len([value for value in statements if value.lstrip().upper().startswith("SELECT")])<=3
    assert not [value for value in statements if value.lstrip().upper().startswith(("INSERT","UPDATE","DELETE"))]


def test_inactive_meal_types_are_excluded_before_requirement_calculation(client,db_session):
    headers=auth(client,db_session);menu,meals,*_=fixture(client,headers)
    assert client.post(f"/api/v1/menus/{menu['id']}/meal-types/{meals[2]['id']}/deactivate",headers=headers).status_code==200
    body=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu["id"]]}).json()
    rows={row["ingredient_code"]:row for row in body["rows"]}
    assert Decimal(rows["REQ-I1"]["requirement_quantity"])==Decimal("12.6")
    assert all(schedule["meal_type_name"]!="晚餐" for row in body["rows"] for schedule in row["schedules"])
    assert {row["menu_id"] for row in body["daily_rows"]}=={menu["id"]}
    assert all(row["requirement_date"] in {"2026-09-01","2026-09-02","2026-09-03"} for row in body["daily_rows"])
    assert not any(item["code"]=="INACTIVE_SOURCE" and item["context"].get("entity_type")=="meal_type" for item in body["anomalies"])


def test_all_inactive_meal_types_return_empty_requirements_and_no_scheduled_warning(client,db_session):
    headers=auth(client,db_session);menu,meals,*_=fixture(client,headers)
    for meal in meals:assert client.post(f"/api/v1/menus/{menu['id']}/meal-types/{meal['id']}/deactivate",headers=headers).status_code==200
    body=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu["id"]]}).json()
    assert body["rows"]==[]
    assert body["daily_rows"]==[]
    assert any(item["code"]=="NO_SCHEDULED_DISHES" for item in body["anomalies"])
    assert not any(item["code"]=="INACTIVE_SOURCE" and item["context"].get("entity_type")=="meal_type" for item in body["anomalies"])


def test_same_named_meal_type_is_filtered_per_menu_active_state(client,db_session):
    headers=auth(client,db_session);menu_a,meals,dishes,*_=fixture(client,headers)
    for meal in meals:assert client.post(f"/api/v1/menus/{menu_a['id']}/meal-types/{meal['id']}/deactivate",headers=headers).status_code==200
    menu_b=client.post("/api/v1/menus",headers=headers,json={"name":"第二份需求菜單","start_date":"2026-09-01","end_date":"2026-09-01"}).json()
    breakfast_b=client.post(f"/api/v1/menus/{menu_b['id']}/meal-types",headers=headers,json={"name":"早餐","sort_order":1}).json()
    slots=[{"menu_date":"2026-09-01","menu_meal_type_id":breakfast_b["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":10,"sort_order":1}]}]
    assert client.put(f"/api/v1/menus/{menu_b['id']}/editor",headers=headers,json={"slots":slots}).status_code==200
    body=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu_a["id"],menu_b["id"]]}).json()
    chicken=next(row for row in body["rows"] if row["ingredient_code"]=="REQ-I1")
    assert Decimal(chicken["requirement_quantity"])==Decimal("1.1")
    assert {schedule["menu_id"] for schedule in chicken["schedules"]}=={menu_b["id"]}
    assert {row["menu_id"] for row in body["daily_rows"]}=={menu_b["id"]}
    assert any(item["code"]=="NO_SCHEDULED_DISHES" and item["related_entity_id"]==menu_a["id"] for item in body["anomalies"])
