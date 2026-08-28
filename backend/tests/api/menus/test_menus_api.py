from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService

PASSWORD="correct horse battery staple"


def auth(client:TestClient,session:Session):
    user=UserService(session).create_user(CreateUserCommand(username="menu_admin",password=PASSWORD,display_name="Menu Admin",role="admin"))
    token=client.post("/api/v1/auth/login",json={"username":user.username,"password":PASSWORD}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"},str(user.id)


def foundations(client,headers,dish_count=3):
    menu_category=client.post("/api/v1/categories/menu",headers=headers,json={"name":"團膳"}).json()
    dish_category=client.post("/api/v1/categories/dish",headers=headers,json={"name":"主菜"}).json()
    dishes=[]
    for i in range(dish_count):
        response=client.post("/api/v1/dishes",headers=headers,json={"code":f"MD-{i+1}","name":f"測試菜色{i+1}","category_id":dish_category["id"]})
        assert response.status_code==201,response.text; dishes.append(response.json())
    return menu_category,dishes


def menu(client,headers,category_id,name="三日菜單",start="2026-09-01",end="2026-09-03"):
    response=client.post("/api/v1/menus",headers=headers,json={"name":name,"start_date":start,"end_date":end,"category_id":category_id,"notes":"菜單備註"})
    assert response.status_code==201,response.text; return response.json()


def meals(client,headers,menu_id,names=("早餐","午餐","點心")):
    result=[]
    for order,name in enumerate(names,1):
        response=client.post(f"/api/v1/menus/{menu_id}/meal-types",headers=headers,json={"name":name,"sort_order":order})
        assert response.status_code==201,response.text; result.append(response.json())
    return result


def full_structure(menu_id,meal_types,dishes,days=3):
    slots=[]
    start=date(2026,9,1)
    for offset in range(days):
        for meal in meal_types:
            slots.append({"menu_date":str(start+timedelta(days=offset)),"menu_meal_type_id":meal["id"],"notes":f"slot-{offset}-{meal['name']}","dishes":[
                {"dish_id":dishes[0]["id"],"diner_count":100+offset,"notes":"第一道","sort_order":2},
                {"dish_id":dishes[1]["id"],"diner_count":80+offset,"notes":"第二道","sort_order":1},
            ]})
    return {"slots":slots}


def test_unauthorized_menu_requests(client):
    assert client.get("/api/v1/menus").status_code==401
    assert client.post("/api/v1/menus",json={"name":"x","start_date":"2026-01-01","end_date":"2026-01-01"}).status_code==401


def test_menu_crud_category_dates_actors_and_activation(client,db_session):
    headers,actor_id=auth(client,db_session); category,_=foundations(client,headers)
    created=menu(client,headers,category["id"])
    assert created["created_by"]==actor_id and created["category_name"]=="團膳"
    assert client.post("/api/v1/menus",headers=headers,json={"name":"壞日期","start_date":"2026-09-02","end_date":"2026-09-01"}).status_code==422
    changed=client.patch(f"/api/v1/menus/{created['id']}",headers=headers,json={"name":"修改菜單","notes":"更新"})
    assert changed.status_code==200 and changed.json()["updated_by"]==actor_id
    assert client.get("/api/v1/menus?search=修改&category_id="+category["id"],headers=headers).json()["pagination"]["total"]==1
    assert client.post(f"/api/v1/menus/{created['id']}/deactivate",headers=headers).json()["is_active"] is False
    assert client.post(f"/api/v1/menus/{created['id']}/reactivate",headers=headers).json()["is_active"] is True


def test_inactive_menu_category_rejected(client,db_session):
    headers,_=auth(client,db_session)
    category=client.post("/api/v1/categories/menu",headers=headers,json={"name":"停用菜單分類"}).json()
    client.post(f"/api/v1/categories/menu/{category['id']}/deactivate",headers=headers)
    assert client.post("/api/v1/menus",headers=headers,json={"name":"不可建立","start_date":"2026-09-01","end_date":"2026-09-03","category_id":category["id"]}).status_code==422


def test_custom_meal_types_rename_reorder_deactivate_reactivate(client,db_session):
    headers,actor_id=auth(client,db_session); category,_=foundations(client,headers); value=menu(client,headers,category["id"])
    values=meals(client,headers,value["id"])
    renamed=client.patch(f"/api/v1/menus/{value['id']}/meal-types/{values[2]['id']}",headers=headers,json={"name":"晚點"})
    assert renamed.json()["name"]=="晚點" and renamed.json()["updated_by"]==actor_id
    reordered=client.put(f"/api/v1/menus/{value['id']}/meal-types/reorder",headers=headers,json={"ordered_ids":[values[2]["id"],values[0]["id"],values[1]["id"]]})
    assert [item["sort_order"] for item in reordered.json()]==[1,2,3]
    assert client.post(f"/api/v1/menus/{value['id']}/meal-types/{values[0]['id']}/deactivate",headers=headers).json()["is_active"] is False
    assert client.post(f"/api/v1/menus/{value['id']}/meal-types/{values[0]['id']}/reactivate",headers=headers).json()["is_active"] is True


def test_controlled_hard_delete_for_empty_menu_and_unused_meal_type(client,db_session):
    headers,_=auth(client,db_session); category,_=foundations(client,headers); value=menu(client,headers,category["id"])
    meal=client.post(f"/api/v1/menus/{value['id']}/meal-types",headers=headers,json={"name":"宵夜","sort_order":1}).json()
    assert client.post(f"/api/v1/menus/{value['id']}/hard-delete",headers=headers,json={"password":PASSWORD}).status_code==409
    assert client.post(f"/api/v1/menus/{value['id']}/meal-types/{meal['id']}/hard-delete",headers=headers,json={"password":"wrong"}).status_code==401
    assert client.post(f"/api/v1/menus/{value['id']}/meal-types/{meal['id']}/hard-delete",headers=headers,json={"password":PASSWORD}).status_code==204
    assert client.post(f"/api/v1/menus/{value['id']}/hard-delete",headers=headers,json={"password":PASSWORD}).status_code==204


def test_three_days_three_meals_multiple_dishes_modify_remove_and_history_display(client,db_session):
    headers,actor_id=auth(client,db_session); category,dishes=foundations(client,headers); value=menu(client,headers,category["id"]); meal_types=meals(client,headers,value["id"])
    saved=client.put(f"/api/v1/menus/{value['id']}/editor",headers=headers,json=full_structure(value["id"],meal_types,dishes))
    assert saved.status_code==200,saved.text; body=saved.json()
    assert len(body["dates"])==3 and len(body["meal_types"])==3 and len(body["slots"])==9
    assert all(len(slot["dishes"])==2 for slot in body["slots"])
    assert body["slots"][0]["dishes"][0]["sort_order"]==1 and body["slots"][0]["dishes"][0]["dish_name"]=="測試菜色2"
    assert body["slots"][0]["dishes"][0]["created_by"]==actor_id
    first=body["slots"][0]; first["dishes"]=first["dishes"][:1]; first["dishes"][0]["diner_count"]=135; first["dishes"][0]["notes"]="修改後"
    payload={"slots":[{"menu_day_id":slot["menu_day_id"],"menu_date":slot["menu_date"],"menu_meal_type_id":slot["menu_meal_type_id"],"notes":slot["notes"],"dishes":[{"id":d["id"],"dish_id":d["dish_id"],"diner_count":d["diner_count"],"notes":d["notes"],"sort_order":d["sort_order"]} for d in slot["dishes"]]} for slot in body["slots"]]}
    updated=client.put(f"/api/v1/menus/{value['id']}/editor",headers=headers,json=payload)
    assert updated.status_code==200 and updated.json()["slots"][0]["dishes"][0]["diner_count"]==135
    assert client.get(f"/api/v1/dishes/{dishes[0]['id']}",headers=headers).status_code==200
    client.post(f"/api/v1/dishes/{dishes[1]['id']}/deactivate",headers=headers)
    historical=client.get(f"/api/v1/menus/{value['id']}/editor",headers=headers).json()
    assert any(d["dish_id"]==dishes[1]["id"] for slot in historical["slots"] for d in slot["dishes"])
    client.post(f"/api/v1/menus/{value['id']}/meal-types/{meal_types[0]['id']}/deactivate",headers=headers)
    historical=client.get(f"/api/v1/menus/{value['id']}/editor",headers=headers).json()
    assert next(m for m in historical["meal_types"] if m["id"]==meal_types[0]["id"])["is_active"] is False
    inactive_slot=next(slot for slot in historical["slots"] if slot["menu_meal_type_id"]==meal_types[0]["id"])
    inactive_slot["dishes"].append({"dish_id":dishes[2]["id"],"diner_count":1,"sort_order":3})
    payload={"slots":[{"menu_day_id":slot["menu_day_id"],"menu_date":slot["menu_date"],"menu_meal_type_id":slot["menu_meal_type_id"],"notes":slot["notes"],"dishes":[{"id":d.get("id"),"dish_id":d["dish_id"],"diner_count":d["diner_count"],"notes":d.get("notes"),"sort_order":d["sort_order"]} for d in slot["dishes"]]} for slot in historical["slots"]]}
    assert client.put(f"/api/v1/menus/{value['id']}/editor",headers=headers,json=payload).status_code==422


def test_inactive_new_assignments_duplicate_and_atomic_rollback(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers); value=menu(client,headers,category["id"]); meal_types=meals(client,headers,value["id"])
    client.post(f"/api/v1/dishes/{dishes[1]['id']}/deactivate",headers=headers)
    payload={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":meal_types[0]["id"],"dishes":[
        {"dish_id":dishes[0]["id"],"diner_count":1,"sort_order":1},{"dish_id":dishes[1]["id"],"diner_count":1,"sort_order":2}]}]}
    assert client.put(f"/api/v1/menus/{value['id']}/editor",headers=headers,json=payload).status_code==422
    assert client.get(f"/api/v1/menus/{value['id']}/editor",headers=headers).json()["slots"]==[]
    duplicate={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":meal_types[0]["id"],"dishes":[
        {"dish_id":dishes[0]["id"],"diner_count":1,"sort_order":1},{"dish_id":dishes[0]["id"],"diner_count":2,"sort_order":2}]}]}
    assert client.put(f"/api/v1/menus/{value['id']}/editor",headers=headers,json=duplicate).status_code==409


def test_copy_day_preserves_values_and_is_atomic(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"來源"); target=menu(client,headers,category["id"],"目的")
    source_meals=meals(client,headers,source["id"]); target_meals=meals(client,headers,target["id"])
    structure=full_structure(source["id"],source_meals,dishes,days=1)
    client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=structure)
    assert client.post(f"/api/v1/menus/{target['id']}/copy-day",headers=headers,json={"source_menu_id":source["id"],"source_date":"2026-09-01","destination_date":"2026-09-02","mode":"replace"}).status_code==422
    copied=client.post(f"/api/v1/menus/{target['id']}/copy-day",headers=headers,json={"source_menu_id":source["id"],"source_date":"2026-09-01","destination_date":"2026-09-02","mode":"replace","confirm_replace":True})
    assert copied.status_code==200,copied.text
    copied_slots=[slot for slot in copied.json()["slots"] if slot["menu_date"]=="2026-09-02"]
    assert len(copied_slots)==3 and all([d["diner_count"] for d in slot["dishes"]]==[80,100] for slot in copied_slots)
    client.post(f"/api/v1/menus/{target['id']}/meal-types/{target_meals[2]['id']}/deactivate",headers=headers)
    failed=client.post(f"/api/v1/menus/{target['id']}/copy-day",headers=headers,json={"source_menu_id":source["id"],"source_date":"2026-09-01","destination_date":"2026-09-03","mode":"replace","confirm_replace":True})
    assert failed.status_code==422
    assert not [slot for slot in client.get(f"/api/v1/menus/{target['id']}/editor",headers=headers).json()["slots"] if slot["menu_date"]=="2026-09-03"]


def test_exact_seven_day_week_copy(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"來源週","2026-09-01","2026-09-07"); target=menu(client,headers,category["id"],"目的週","2026-09-08","2026-09-14")
    source_meals=meals(client,headers,source["id"],("早餐","午餐")); meals(client,headers,target["id"],("早餐","午餐"))
    client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=full_structure(source["id"],source_meals,dishes,days=3))
    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==200,response.text
    assert len(response.json()["slots"])==6


def test_week_copy_rolls_back_when_later_day_is_invalid(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"原子來源","2026-09-01","2026-09-07"); target=menu(client,headers,category["id"],"原子目的","2026-09-08","2026-09-14")
    source_meals=meals(client,headers,source["id"],("早餐",)); meals(client,headers,target["id"],("早餐",))
    payload={"slots":[
        {"menu_date":"2026-09-01","menu_meal_type_id":source_meals[0]["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":10,"sort_order":1}]},
        {"menu_date":"2026-09-02","menu_meal_type_id":source_meals[0]["id"],"dishes":[{"dish_id":dishes[1]["id"],"diner_count":20,"sort_order":1}]},
    ]}
    client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload)
    client.post(f"/api/v1/dishes/{dishes[1]['id']}/deactivate",headers=headers)
    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==422
    assert client.get(f"/api/v1/menus/{target['id']}/editor",headers=headers).json()["slots"]==[]


def test_aggregate_query_count_constant_and_fk(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers); value=menu(client,headers,category["id"]); meal_types=meals(client,headers,value["id"])
    client.put(f"/api/v1/menus/{value['id']}/editor",headers=headers,json=full_structure(value["id"],meal_types,dishes))
    statements=[]
    def record(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try: response=client.get(f"/api/v1/menus/{value['id']}/editor",headers=headers)
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")])<=4
    fk=db_session.execute(text("SELECT confdeltype FROM pg_constraint WHERE conname='menu_days_menu_meal_type_id_fkey'")).scalar_one()
    assert fk=="r"
