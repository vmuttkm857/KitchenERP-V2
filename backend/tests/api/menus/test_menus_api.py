import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.db.session import engine as process_engine
from app.domains.audit.models import AuditLog
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


def test_meal_type_columns_are_independent_crud_and_do_not_touch_menu_dishes(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    value=menu(client,headers,category["id"]); breakfast,lunch,custom=meals(client,headers,value["id"],("早餐","午餐","董事長宵夜"))
    def create(meal,name,order):
        response=client.post(f"/api/v1/menus/{value['id']}/meal-types/{meal['id']}/columns",headers=headers,json={"name":name,"sort_order":order})
        assert response.status_code==201,response.text;return response.json()
    main=create(breakfast,"主菜",1);vegetable=create(breakfast,"青菜",2)
    lunch_main=create(lunch,"主菜",1);custom_column=create(custom,"特殊餐點",1)
    assert [item["name"] for item in client.get(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/columns",headers=headers).json()]==["主菜","青菜"]
    assert [item["id"] for item in client.get(f"/api/v1/menus/{value['id']}/meal-types/{lunch['id']}/columns",headers=headers).json()]==[lunch_main["id"]]
    assert client.post(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/columns",headers=headers,json={"name":"主菜","sort_order":3}).status_code==409
    renamed=client.patch(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/columns/{vegetable['id']}",headers=headers,json={"name":"青菜1"})
    assert renamed.status_code==200 and renamed.json()["name"]=="青菜1"
    reordered=client.put(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/columns/reorder",headers=headers,json={"ordered_ids":[vegetable["id"],main["id"]]})
    assert [item["id"] for item in reordered.json()]==[vegetable["id"],main["id"]]
    assert client.put(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/columns/reorder",headers=headers,json={"ordered_ids":[main["id"],main["id"]]}).status_code==422
    payload={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":breakfast["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":100,"sort_order":1}]}]}
    before=client.put(f"/api/v1/menus/{value['id']}/editor",headers=headers,json=payload).json()
    assert client.delete(f"/api/v1/menus/{value['id']}/meal-types/{breakfast['id']}/columns/{main['id']}",headers=headers).status_code==204
    after=client.get(f"/api/v1/menus/{value['id']}/editor",headers=headers).json()
    assert after["slots"]==before["slots"]
    assert {item["id"] for item in after["meal_type_columns"]}=={vegetable["id"],lunch_main["id"],custom_column["id"]}
    assert client.patch(f"/api/v1/menus/{value['id']}/meal-types/{lunch['id']}/columns/{vegetable['id']}",headers=headers,json={"name":"錯誤餐別"}).status_code==404


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


def test_menu_list_date_overlap_keyword_pagination_and_validation(client,db_session):
    headers,_=auth(client,db_session)
    category=client.post("/api/v1/categories/menu",headers=headers,json={"name":"日期篩選"}).json()
    values=[
        menu(client,headers,category["id"],"住院甲","2026-08-01","2026-08-07"),
        menu(client,headers,category["id"],"住院乙","2026-08-17","2026-08-23"),
        menu(client,headers,category["id"],"門診甲","2026-08-24","2026-08-30"),
        menu(client,headers,category["id"],"九月菜單","2026-09-01","2026-09-07"),
    ]

    unfiltered=client.get("/api/v1/menus?page_size=100",headers=headers)
    assert unfiltered.status_code==200 and unfiltered.json()["pagination"]["total"]==4
    start_only=client.get("/api/v1/menus?start_date=2026-08-20&page_size=100",headers=headers).json()
    assert [item["id"] for item in start_only["items"]]==[values[3]["id"],values[2]["id"],values[1]["id"]]
    end_only=client.get("/api/v1/menus?end_date=2026-08-20&page_size=100",headers=headers).json()
    assert {item["id"] for item in end_only["items"]}=={values[0]["id"],values[1]["id"]}
    overlap=client.get("/api/v1/menus?start_date=2026-08-20&end_date=2026-08-25&page_size=100",headers=headers).json()
    assert {item["id"] for item in overlap["items"]}=={values[1]["id"],values[2]["id"]}
    no_overlap=client.get("/api/v1/menus?start_date=2026-10-01&end_date=2026-10-31",headers=headers).json()
    assert no_overlap["items"]==[] and no_overlap["pagination"]["total"]==0
    combined=client.get("/api/v1/menus?search=住院&start_date=2026-08-20&end_date=2026-08-25",headers=headers).json()
    assert [item["id"] for item in combined["items"]]==[values[1]["id"]]
    paged=client.get("/api/v1/menus?start_date=2026-08-01&end_date=2026-09-30&page=2&page_size=1",headers=headers).json()
    assert paged["pagination"]=={"page":2,"page_size":1,"total":4} and len(paged["items"])==1
    invalid=client.get("/api/v1/menus?start_date=2026-09-01&end_date=2026-08-01",headers=headers)
    assert invalid.status_code==422 and invalid.json()["detail"]=="Start date cannot be later than end date"


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
    editor_log=db_session.scalar(select(AuditLog).where(AuditLog.action=="menu_editor_save",AuditLog.entity_id==uuid.UUID(value["id"])));assert editor_log is not None
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
    copied_again=client.post(f"/api/v1/menus/{target['id']}/copy-day",headers=headers,json={"source_menu_id":source["id"],"source_date":"2026-09-01","destination_date":"2026-09-03","mode":"replace","confirm_replace":True})
    assert copied_again.status_code==200,copied_again.text
    preserved=next(meal for meal in copied_again.json()["meal_types"] if meal["id"]==target_meals[2]["id"])
    assert preserved["is_active"] is False


def test_copy_day_creates_dynamic_and_inactive_source_meal_types(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"動態單日來源"); target=menu(client,headers,category["id"],"動態單日目的")
    names=("第一餐","下午點心","夜班餐")
    source_meals=meals(client,headers,source["id"],names)
    existing=meals(client,headers,target["id"],("第一餐",))[0]
    payload=full_structure(source["id"],source_meals,dishes,days=1)
    assert client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload).status_code==200
    assert client.post(f"/api/v1/menus/{source['id']}/meal-types/{source_meals[2]['id']}/deactivate",headers=headers).status_code==200

    response=client.post(f"/api/v1/menus/{target['id']}/copy-day",headers=headers,json={"source_menu_id":source["id"],"source_date":"2026-09-01","destination_date":"2026-09-02","mode":"add"})
    assert response.status_code==200,response.text
    by_name={meal["name"]:meal for meal in response.json()["meal_types"]}
    assert by_name["第一餐"]["id"]==existing["id"]
    assert by_name["下午點心"]["is_active"] is True
    assert by_name["夜班餐"]["is_active"] is False
    copied_slot=next(slot for slot in response.json()["slots"] if slot["menu_meal_type_id"]==by_name["夜班餐"]["id"])
    assert copied_slot["menu_meal_type_id"]!=source_meals[2]["id"]


def test_copy_day_add_skips_duplicate_dish_assignment(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"單日加入來源"); target=menu(client,headers,category["id"],"單日加入目的")
    source_meal=meals(client,headers,source["id"],("輪班餐",))[0]
    target_meal=meals(client,headers,target["id"],("輪班餐",))[0]
    source_payload={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":source_meal["id"],"dishes":[
        {"dish_id":dishes[0]["id"],"diner_count":100,"sort_order":1},{"dish_id":dishes[1]["id"],"diner_count":80,"sort_order":2}]}]}
    target_payload={"slots":[{"menu_date":"2026-09-02","menu_meal_type_id":target_meal["id"],"dishes":[
        {"dish_id":dishes[0]["id"],"diner_count":5,"sort_order":1}]}]}
    assert client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=source_payload).status_code==200
    assert client.put(f"/api/v1/menus/{target['id']}/editor",headers=headers,json=target_payload).status_code==200

    response=client.post(f"/api/v1/menus/{target['id']}/copy-day",headers=headers,json={"source_menu_id":source["id"],"source_date":"2026-09-01","destination_date":"2026-09-02","mode":"add"})
    assert response.status_code==200,response.text
    copied=response.json()["slots"][0]["dishes"]
    assert [dish["dish_id"] for dish in copied].count(dishes[0]["id"])==1
    assert next(dish for dish in copied if dish["dish_id"]==dishes[0]["id"])["diner_count"]==5
    assert next(dish for dish in copied if dish["dish_id"]==dishes[1]["id"])["diner_count"]==80


def test_exact_seven_day_week_copy(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"來源週","2026-09-01","2026-09-07"); target=menu(client,headers,category["id"],"目的週","2026-09-08","2026-09-14")
    source_meals=meals(client,headers,source["id"],("早餐","午餐")); meals(client,headers,target["id"],("早餐","午餐"))
    client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=full_structure(source["id"],source_meals,dishes,days=3))
    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==200,response.text
    assert len(response.json()["slots"])==6


def test_week_copy_creates_complete_meal_structure_for_empty_target(client,db_session):
    headers,actor_id=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"完整來源","2026-09-01","2026-09-07")
    target=menu(client,headers,category["id"],"空白目的","2026-09-08","2026-09-14")
    source_meals=meals(client,headers,source["id"],("早餐","午餐","晚點"))
    payload={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":source_meals[0]["id"],"notes":"早餐備註","dishes":[{"dish_id":dishes[0]["id"],"diner_count":120,"notes":"菜色備註","sort_order":1}]}]}
    assert client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload).status_code==200

    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==200,response.text
    target_meals=response.json()["meal_types"]
    assert [meal["name"] for meal in target_meals]==["早餐","午餐","晚點"]
    assert all(meal["created_by"]==actor_id and meal["updated_by"]==actor_id for meal in target_meals)
    copied=response.json()["slots"][0]
    assert copied["notes"]=="早餐備註" and copied["dishes"][0]["diner_count"]==120
    assert copied["dishes"][0]["notes"]=="菜色備註" and copied["dishes"][0]["sort_order"]==1


def test_week_copy_preserves_existing_case_insensitive_match_and_extra_meal(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"部分來源","2026-09-01","2026-09-07")
    target=menu(client,headers,category["id"],"部分目的","2026-09-08","2026-09-14")
    source_meals=meals(client,headers,source["id"],("BREAKFAST","午餐"))
    existing=meals(client,headers,target["id"],("breakfast","目的額外餐"))
    payload={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":source_meals[1]["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":1,"sort_order":1}]}]}
    client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload)

    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==200,response.text
    by_name={meal["name"].lower():meal for meal in response.json()["meal_types"]}
    assert by_name["breakfast"]["id"]==existing[0]["id"]
    assert "午餐" in by_name and by_name["目的額外餐"]["id"]==existing[1]["id"]


def test_week_copy_with_many_meals_preserves_partial_target_and_copies_all_days(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"六餐來源","2026-09-01","2026-09-07")
    target=menu(client,headers,category["id"],"部分六餐目的","2026-09-08","2026-09-14")
    names=("第一餐","下午點心","夜班餐","特殊餐A","員工餐B","臨時餐C")
    source_meals=meals(client,headers,source["id"],names)
    target_meals=meals(client,headers,target["id"],names[:3])
    payload=full_structure(source["id"],source_meals,dishes,days=7)
    assert client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload).status_code==200

    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==200,response.text
    aggregate=response.json()
    by_name={meal["name"]:meal for meal in aggregate["meal_types"]}
    assert [by_name[name]["id"] for name in names[:3]]==[meal["id"] for meal in target_meals]
    assert all(name in by_name for name in names)
    assert len(aggregate["slots"])==42
    assert all(len(slot["dishes"])==2 for slot in aggregate["slots"])


def test_week_copy_same_dates_mixed_active_meals_add_and_replace(client,db_session):
    headers,actor_id=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"同週六餐來源","2026-08-17","2026-08-23")
    add_target=menu(client,headers,category["id"],"同週加入目的","2026-08-17","2026-08-23")
    replace_target=menu(client,headers,category["id"],"同週覆蓋目的","2026-08-17","2026-08-23")
    names=("第一餐","下午點心","夜班餐","特殊餐A","員工餐B","臨時餐C")
    source_meals=meals(client,headers,source["id"],names)
    add_existing=meals(client,headers,add_target["id"],names[:3])
    replace_existing=meals(client,headers,replace_target["id"],names[:3])
    slots=[]
    for offset in range(7):
        for meal_type in source_meals:
            slots.append({"menu_date":str(date(2026,8,17)+timedelta(days=offset)),"menu_meal_type_id":meal_type["id"],"notes":f"餐次備註-{offset}","dishes":[
                {"dish_id":dishes[0]["id"],"diner_count":100+offset,"notes":"菜色一","sort_order":1},
                {"dish_id":dishes[1]["id"],"diner_count":80+offset,"notes":"菜色二","sort_order":2},
            ]})
    assert client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json={"slots":slots}).status_code==200
    for meal_type in source_meals[3:]:
        assert client.post(f"/api/v1/menus/{source['id']}/meal-types/{meal_type['id']}/deactivate",headers=headers).status_code==200
    existing_slot={"slots":[{"menu_date":"2026-08-17","menu_meal_type_id":replace_existing[0]["id"],"notes":"將被覆蓋","dishes":[{"dish_id":dishes[2]["id"],"diner_count":1,"sort_order":1}]}]}
    assert client.put(f"/api/v1/menus/{replace_target['id']}/editor",headers=headers,json=existing_slot).status_code==200

    add_response=client.post(f"/api/v1/menus/{add_target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    replace_response=client.post(f"/api/v1/menus/{replace_target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"replace","confirm_replace":True})
    assert add_response.status_code==200,add_response.text
    assert replace_response.status_code==200,replace_response.text
    for aggregate,existing in ((add_response.json(),add_existing),(replace_response.json(),replace_existing)):
        by_name={meal["name"]:meal for meal in aggregate["meal_types"]}
        assert [by_name[name]["id"] for name in names[:3]]==[meal["id"] for meal in existing]
        assert all(by_name[name]["is_active"] is True for name in names[:3])
        assert all(by_name[name]["is_active"] is False for name in names[3:])
        assert len(aggregate["slots"])==42
        assert all(len(slot["dishes"])==2 for slot in aggregate["slots"])
        assert all(slot["dishes"][0]["diner_count"]>=80 for slot in aggregate["slots"])
        target_ids={meal["id"] for meal in aggregate["meal_types"]}
        assert all(slot["menu_meal_type_id"] in target_ids for slot in aggregate["slots"])
        assert all(slot["notes"].startswith("餐次備註-") for slot in aggregate["slots"])
        assert all([dish["sort_order"] for dish in slot["dishes"]]==[1,2] for slot in aggregate["slots"])
        assert all([dish["notes"] for dish in slot["dishes"]]==["菜色一","菜色二"] for slot in aggregate["slots"])


def test_week_copy_copies_source_meal_deactivated_after_assignment(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"停用自訂餐別來源","2026-08-17","2026-08-23")
    target=menu(client,headers,category["id"],"停用自訂餐別目的","2026-08-17","2026-08-23")
    source_meal=meals(client,headers,source["id"],("夜班專用餐",))[0]
    payload={"slots":[{"menu_date":"2026-08-17","menu_meal_type_id":source_meal["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":25,"sort_order":1}]}]}
    assert client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload).status_code==200
    assert client.post(f"/api/v1/menus/{source['id']}/meal-types/{source_meal['id']}/deactivate",headers=headers).status_code==200

    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==200,response.text
    target_meal=next(meal for meal in response.json()["meal_types"] if meal["name"]=="夜班專用餐")
    assert target_meal["is_active"] is False and target_meal["id"]!=source_meal["id"]
    assert response.json()["slots"][0]["menu_meal_type_id"]==target_meal["id"]


def test_week_copy_preserves_existing_destination_active_state(client,db_session):
    headers,_=auth(client,db_session); category,_=foundations(client,headers)
    source=menu(client,headers,category["id"],"停用來源","2026-09-01","2026-09-07")
    target=menu(client,headers,category["id"],"停用目的","2026-09-08","2026-09-14")
    source_meals=meals(client,headers,source["id"],("夜班餐",)); target_meals=meals(client,headers,target["id"],("夜班餐",))
    payload={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":source_meals[0]["id"],"dishes":[]}]}
    assert client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload).status_code==200
    client.post(f"/api/v1/menus/{source['id']}/meal-types/{source_meals[0]['id']}/deactivate",headers=headers)
    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==200,response.text
    current=response.json()["meal_types"]
    assert len(current)==1 and current[0]["id"]==target_meals[0]["id"] and current[0]["is_active"] is True


def test_week_copy_rolls_back_created_meals_when_dish_copy_fails(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"回滾來源","2026-09-01","2026-09-07")
    target=menu(client,headers,category["id"],"回滾目的","2026-09-08","2026-09-14")
    source_meals=meals(client,headers,source["id"],("早餐","空白餐"))
    payload={"slots":[{"menu_date":"2026-09-02","menu_meal_type_id":source_meals[0]["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":1,"sort_order":1}]}]}
    client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=payload)
    client.post(f"/api/v1/dishes/{dishes[0]['id']}/deactivate",headers=headers)
    response=client.post(f"/api/v1/menus/{target['id']}/copy-week",headers=headers,json={"source_menu_id":source["id"],"mode":"add"})
    assert response.status_code==422
    assert client.get(f"/api/v1/menus/{target['id']}/meal-types",headers=headers).json()==[]
    assert client.get(f"/api/v1/menus/{target['id']}/editor",headers=headers).json()["slots"]==[]


def test_copy_day_creates_missing_target_meals(client,db_session):
    headers,_=auth(client,db_session); category,dishes=foundations(client,headers)
    source=menu(client,headers,category["id"],"單日來源"); target=menu(client,headers,category["id"],"單日空白目的")
    source_meals=meals(client,headers,source["id"],("第一餐","下午點心"))
    client.put(f"/api/v1/menus/{source['id']}/editor",headers=headers,json=full_structure(source["id"],source_meals,dishes,days=1))
    response=client.post(f"/api/v1/menus/{target['id']}/copy-day",headers=headers,json={"source_menu_id":source["id"],"source_date":"2026-09-01","destination_date":"2026-09-02","mode":"add"})
    assert response.status_code==200,response.text
    assert [meal["name"] for meal in response.json()["meal_types"]]==["第一餐","下午點心"]


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
