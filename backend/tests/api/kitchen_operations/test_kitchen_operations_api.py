import uuid
from decimal import Decimal
from sqlalchemy import event,select
from app.db.session import engine as process_engine
from app.domains.ingredients.models import Ingredient
from app.domains.recipes.models import DishIngredient
from app.domains.users.models import User
from tests.api.requirements.test_requirements_api import auth

def kitchen_fixture(client,headers,db_session):
    ingredient_category=client.post("/api/v1/categories/ingredient",headers=headers,json={"name":"廚房食材"}).json()
    dish_category=client.post("/api/v1/categories/dish",headers=headers,json={"name":"廚房菜色"}).json()
    ingredients=[]
    for code,name,unit in (("K-I1","雞肉","kg"),("K-I2","香料","kg"),("K-I3","高湯","L"),("K-I4","錯誤單位食材","kg")):
        ingredients.append(client.post("/api/v1/ingredients",headers=headers,json={"code":code,"name":name,"category_id":ingredient_category["id"],"unit":unit,"current_price":"1","notes":f"{name}主檔備註"}).json())
    dishes=[]
    for code,name in (("K-D1","紅燒雞腿"),("K-D2","高湯"),("K-D3","無配方菜"),("K-D4","零量菜"),("K-D5","錯誤單位菜")):
        dishes.append(client.post("/api/v1/dishes",headers=headers,json={"code":code,"name":name,"category_id":dish_category["id"]}).json())
    recipes=[
        {"items":[{"ingredient_id":ingredients[0]["id"],"quantity":"150","unit":"g","loss_rate":"10","notes":"雞肉先醃製","sort_order":1},{"ingredient_id":ingredients[1]["id"],"quantity":"0.5","unit":"斤","loss_rate":"0","notes":"香料後下","sort_order":2}]},
        {"items":[{"ingredient_id":ingredients[2]["id"],"quantity":"250","unit":"ml","loss_rate":"0","notes":"保留高湯","sort_order":1}]},
        None,
        {"items":[{"ingredient_id":ingredients[0]["id"],"quantity":"0","unit":"g","loss_rate":"0","sort_order":1}]},
        None,
    ]
    for dish,recipe in zip(dishes,recipes):
        if recipe is not None:assert client.put(f"/api/v1/dishes/{dish['id']}/recipe",headers=headers,json=recipe).status_code==200
    actor_id=db_session.scalar(select(User.id))
    db_session.add(DishIngredient(id=uuid.uuid4(),dish_id=uuid.UUID(dishes[4]["id"]),ingredient_id=uuid.UUID(ingredients[3]["id"]),quantity=Decimal("1"),unit="個",loss_rate=Decimal("0"),sort_order=1,created_by=actor_id,updated_by=actor_id))
    db_session.commit()
    menu=client.post("/api/v1/menus",headers=headers,json={"name":"廚房兩日菜單","start_date":"2026-10-01","end_date":"2026-10-02"}).json()
    lunch=client.post(f"/api/v1/menus/{menu['id']}/meal-types",headers=headers,json={"name":"午餐","sort_order":1}).json();dinner=client.post(f"/api/v1/menus/{menu['id']}/meal-types",headers=headers,json={"name":"晚餐","sort_order":2}).json()
    slots=[{"menu_date":"2026-10-01","menu_meal_type_id":lunch["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":100,"notes":"先處理雞肉","sort_order":1},{"dish_id":dishes[2]["id"],"diner_count":3,"sort_order":2},{"dish_id":dishes[3]["id"],"diner_count":3,"sort_order":3},{"dish_id":dishes[4]["id"],"diner_count":3,"sort_order":4}]},{"menu_date":"2026-10-01","menu_meal_type_id":dinner["id"],"dishes":[{"dish_id":dishes[1]["id"],"diner_count":4,"sort_order":1}]},{"menu_date":"2026-10-02","menu_meal_type_id":lunch["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":10,"sort_order":1}]}]
    assert client.put(f"/api/v1/menus/{menu['id']}/editor",headers=headers,json={"slots":slots}).status_code==200
    return menu,lunch,dinner,dishes,ingredients

def test_known_answer_hierarchy_decimal_notes_sort_and_units(client,db_session):
    headers=auth(client,db_session);menu,lunch,dinner,_,_=kitchen_fixture(client,headers,db_session)
    response=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"],"selected_dates":["2026-10-01"]});assert response.status_code==200,response.text
    body=response.json();assert len(body["days"])==1 and [meal["meal_type_name"] for meal in body["days"][0]["meals"]]==["午餐","晚餐"]
    lunch_view=body["days"][0]["meals"][0];dish=lunch_view["dishes"][0];assert dish["dish_name"]=="紅燒雞腿" and dish["diner_count"]==100 and dish["notes"]=="先處理雞肉" and dish["sort_order"]==1
    chicken,spice=dish["ingredients"];assert chicken["notes"]=="雞肉先醃製" and chicken["sort_order"]==1
    assert Decimal(chicken["required_quantity"])==Decimal("16500") and chicken["required_unit"]=="g"
    assert Decimal(chicken["base_quantity"])==Decimal("16.5") and chicken["base_unit"]=="kg" and Decimal(chicken["display_quantity"])==Decimal("16.5") and chicken["display_unit"]=="kg"
    assert Decimal(spice["required_quantity"])==Decimal("50") and spice["required_unit"]=="斤" and Decimal(spice["base_quantity"])==30
    broth=body["days"][0]["meals"][1]["dishes"][0]["ingredients"][0];assert Decimal(broth["required_quantity"])==1000 and broth["display_unit"]=="L" and Decimal(broth["display_quantity"])==1
    codes={value["code"] for value in body["anomalies"]};assert {"MISSING_RECIPE","ZERO_RECIPE_QUANTITY","INCOMPATIBLE_UNIT"}.issubset(codes)
    incompatible=next(value for value in body["anomalies"] if value["code"]=="INCOMPATIBLE_UNIT")
    assert incompatible["context"]["dish_name"]=="錯誤單位菜"


def test_nutrition_conversion_does_not_change_kitchen_calculation(client,db_session):
    headers=auth(client,db_session);menu,_,_,_,ingredients=kitchen_fixture(client,headers,db_session)
    before=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"]}).json()
    created=client.post(f"/api/v1/ingredients/{ingredients[3]['id']}/nutrition-unit-conversions",headers=headers,json={"unit":"個","grams_per_unit":"180"})
    assert created.status_code==201,created.text
    after=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"]}).json()
    assert after==before

def test_date_meal_filter_raw_display_and_summary(client,db_session):
    headers=auth(client,db_session);menu,lunch,_,_,_=kitchen_fixture(client,headers,db_session)
    body=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"],"start_date":"2026-10-02","end_date":"2026-10-02","meal_type_ids":[lunch["id"]],"display_mode":"raw"}).json()
    assert len(body["days"])==1 and body["days"][0]["menu_date"]=="2026-10-02" and len(body["days"][0]["meals"])==1
    chicken=body["days"][0]["meals"][0]["dishes"][0]["ingredients"][0];assert Decimal(chicken["required_quantity"])==1650 and chicken["display_unit"]=="g" and Decimal(chicken["display_quantity"])==1650
    summary={row["ingredient_code"]:row for row in body["ingredient_summary"]};assert Decimal(summary["K-I1"]["required_quantity"])==Decimal("1.65") and summary["K-I1"]["required_unit"]=="kg"

def test_inactive_ingredient_and_dish_warn_without_supplier_or_price_validation(client,db_session):
    headers=auth(client,db_session);menu,_,_,dishes,ingredients=kitchen_fixture(client,headers,db_session)
    client.post(f"/api/v1/ingredients/{ingredients[0]['id']}/deactivate",headers=headers);client.post(f"/api/v1/dishes/{dishes[0]['id']}/deactivate",headers=headers)
    body=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"],"selected_dates":["2026-10-01"]}).json();codes={value["code"] for value in body["anomalies"]}
    assert {"INACTIVE_INGREDIENT","INACTIVE_DISH"}.issubset(codes) and "MISSING_SUPPLIER" not in codes and "MISSING_PRICE" not in codes

def test_auth_query_budget_read_only_and_no_snapshot_purchase_dependency(client,db_session):
    assert client.post("/api/v1/kitchen-operations/calculate",json={"menu_id":"00000000-0000-0000-0000-000000000001"}).status_code==401
    headers=auth(client,db_session);menu,*_=kitchen_fixture(client,headers,db_session);statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"]})
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200
    selects=[sql for sql in statements if sql.lstrip().upper().startswith("SELECT")];assert len(selects)<=3
    assert not [sql for sql in statements if sql.lstrip().upper().startswith(("INSERT","UPDATE","DELETE"))]
    combined=" ".join(selects).lower();assert "requirement_snapshot" not in combined and "purchase_" not in combined


def test_inactive_meal_type_is_excluded_from_kitchen_preparation(client,db_session):
    headers=auth(client,db_session);menu,lunch,dinner,_,_=kitchen_fixture(client,headers,db_session)
    assert client.post(f"/api/v1/menus/{menu['id']}/meal-types/{dinner['id']}/deactivate",headers=headers).status_code==200
    body=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"],"selected_dates":["2026-10-01"]}).json()
    assert [meal["meal_type_id"] for meal in body["days"][0]["meals"]]==[lunch["id"]]
    assert not any(item["code"]=="INACTIVE_MEAL_TYPE" for item in body["anomalies"])
    assert "K-I3" not in {item["ingredient_code"] for item in body["ingredient_summary"]}


def test_all_inactive_meal_types_return_empty_kitchen_preparation(client,db_session):
    headers=auth(client,db_session);menu,lunch,dinner,_,_=kitchen_fixture(client,headers,db_session)
    for meal in (lunch,dinner):assert client.post(f"/api/v1/menus/{menu['id']}/meal-types/{meal['id']}/deactivate",headers=headers).status_code==200
    body=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":menu["id"]}).json()
    assert body["days"]==[] and body["ingredient_summary"]==[] and body["supplier_summary"]==[]
    assert any(item["code"]=="NO_SCHEDULED_DISHES" for item in body["anomalies"])
    assert not any(item["code"]=="INACTIVE_MEAL_TYPE" for item in body["anomalies"])
