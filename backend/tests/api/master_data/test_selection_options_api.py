from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService

PASSWORD = "correct horse battery staple"


def auth(client, session):
    user = UserService(session).create_user(CreateUserCommand(
        username="selection_admin", password=PASSWORD, display_name="Selection Admin", role="admin",
    ))
    token = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_ingredient_selection_options_apply_search_category_active_and_stable_order(client, db_session):
    headers = auth(client, db_session)
    meat = client.post("/api/v1/categories/ingredient", headers=headers, json={"name":"肉類","sort_order":1}).json()
    seasoning = client.post("/api/v1/categories/ingredient", headers=headers, json={"name":"調味料","sort_order":2}).json()
    values = []
    for code, name, category in (("10","牛肉片",meat),("02","牛五花",meat),("1","牛腱",meat),("20","牛高湯",seasoning)):
        values.append(client.post("/api/v1/ingredients", headers=headers, json={"code":code,"name":name,"category_id":category["id"],"unit":"kg","current_price":"1"}).json())
    client.post(f"/api/v1/ingredients/{values[0]['id']}/deactivate", headers=headers)
    assert client.get("/api/v1/ingredients/selection-options").status_code == 401
    response = client.get(f"/api/v1/ingredients/selection-options?active=true&search=牛&category_id={meat['id']}", headers=headers)
    assert response.status_code == 200
    assert [(item["code"],item["name"]) for item in response.json()] == [("1","牛腱"),("02","牛五花")]
    assert all(set(item) == {"id","code","name","is_active"} and item["is_active"] for item in response.json())
    assert client.get("/api/v1/ingredients/selection-options?active=false", headers=headers).status_code == 422
    paged = client.get("/api/v1/ingredients?page=1&page_size=1&active=true", headers=headers).json()
    assert len(paged["items"]) == 1 and paged["pagination"]["total"] == 3


def test_dish_selection_options_apply_search_category_active_and_stable_order(client, db_session):
    headers = auth(client, db_session)
    soup = client.post("/api/v1/categories/dish", headers=headers, json={"name":"湯品","sort_order":1}).json()
    main = client.post("/api/v1/categories/dish", headers=headers, json={"name":"主菜","sort_order":2}).json()
    values = []
    for code, name, category in (("11","魚丸湯",soup),("02","鮮魚湯",soup),("1","魚片湯",soup),("20","清蒸魚",main)):
        values.append(client.post("/api/v1/dishes", headers=headers, json={"code":code,"name":name,"category_id":category["id"]}).json())
    client.post(f"/api/v1/dishes/{values[0]['id']}/deactivate", headers=headers)
    assert client.get("/api/v1/dishes/selection-options").status_code == 401
    response = client.get(f"/api/v1/dishes/selection-options?active=true&search=魚&category_id={soup['id']}", headers=headers)
    assert response.status_code == 200
    assert [(item["code"],item["name"]) for item in response.json()] == [("1","魚片湯"),("02","鮮魚湯")]
    assert all(set(item) == {"id","code","name","is_active"} and item["is_active"] for item in response.json())
    assert client.get("/api/v1/dishes/selection-options?active=false", headers=headers).status_code == 422
    paged = client.get("/api/v1/dishes?page=1&page_size=1&active=true", headers=headers).json()
    assert len(paged["items"]) == 1 and paged["pagination"]["total"] == 3
