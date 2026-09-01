from io import BytesIO
from urllib.parse import unquote

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.audit.models import AuditLog
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService

PASSWORD="correct horse battery staple"


def login(client:TestClient,session:Session,username:str,role:str):
    user=UserService(session).create_user(CreateUserCommand(username=username,password=PASSWORD,display_name=username,role=role))
    token=client.post("/api/v1/auth/login",json={"username":username,"password":PASSWORD}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def foundations(client,headers):
    ingredient_category=client.post("/api/v1/categories/ingredient",headers=headers,json={"name":"食材"}).json()
    dish_category=client.post("/api/v1/categories/dish",headers=headers,json={"name":"主菜"}).json()
    menu_category=client.post("/api/v1/categories/menu",headers=headers,json={"name":"團膳"}).json()
    ingredient=client.post("/api/v1/ingredients",headers=headers,json={"code":"P-I","name":"雞肉","category_id":ingredient_category["id"],"unit":"kg","current_price":"100"}).json()
    dishes=[]
    for code,name in (("P-D1","三杯雞"),("P-D2","時蔬"),("P-D3","冬瓜湯"),("P-D4","未排入菜單")):
        dishes.append(client.post("/api/v1/dishes",headers=headers,json={"code":code,"name":name,"category_id":dish_category["id"]}).json())
    recipe={"items":[{"ingredient_id":ingredient["id"],"quantity":"0.1","unit":"kg","loss_rate":"0","sort_order":1}]}
    assert client.put(f"/api/v1/dishes/{dishes[0]['id']}/recipe",headers=headers,json=recipe).status_code==200
    return menu_category,dishes


def test_profile_versions_ingredients_steps_permissions_and_audit(client:TestClient,db_session:Session):
    admin=login(client,db_session,"production_admin","admin");category,dishes=foundations(client,admin);dish=dishes[0]
    user=login(client,db_session,"production_reader","user")
    assert client.get(f"/api/v1/dishes/{dish['id']}/production-profile").status_code==401
    missing=client.get(f"/api/v1/dishes/{dish['id']}/production-profile",headers=admin)
    assert missing.status_code==404 and missing.json()["detail"]=="Production resource not found"
    recipe=client.get(f"/api/v1/dishes/{dish['id']}/recipe",headers=admin)
    assert recipe.status_code==200 and len(recipe.json()["items"])==1
    assert client.post(f"/api/v1/dishes/{dish['id']}/production-profile",headers=user,json={"max_batch_size":100}).status_code==403
    created=client.post(f"/api/v1/dishes/{dish['id']}/production-profile",headers=admin,json={"max_batch_size":100,"notes":"整體提醒"})
    assert created.status_code==201,created.text
    assert client.get(f"/api/v1/dishes/{dish['id']}/production-profile",headers=user).status_code==200
    version=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions",headers=admin,json={"serving_count":100,"name":"百人版","is_official":True})
    assert version.status_code==201,version.text
    assert client.patch(f"/api/v1/dishes/{dish['id']}/production-profile",headers=admin,json={"max_batch_size":99}).status_code==422
    body=version.json();batch=body["versions"][0]
    assert batch["ingredients"][0]["quantity"]=="10.0000000000"
    item=batch["ingredients"][0]
    changed=client.patch(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{batch['id']}/ingredients/{item['id']}",headers=admin,json={"quantity":"9.5","usage_category":"marinade","quantity_note":"分盆"})
    assert changed.status_code==200 and changed.json()["versions"][0]["ingredients"][0]["usage_category"]=="marinade"
    first=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{batch['id']}/steps",headers=admin,json={"step_order":1,"step_type":"marinate","title":"醃製","duration_seconds":600})
    assert first.status_code==201,first.text
    second=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{batch['id']}/steps",headers=admin,json={"step_order":2,"step_type":"stir_fry","title":"炒製","temperature_celsius":"180"})
    ids=[step["id"] for step in second.json()["versions"][0]["steps"]]
    reordered=client.put(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{batch['id']}/steps/reorder",headers=admin,json={"ordered_ids":list(reversed(ids))})
    assert [step["title"] for step in reordered.json()["versions"][0]["steps"]]==["炒製","醃製"]
    step_updated=client.patch(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{batch['id']}/steps/{ids[0]}",headers=admin,json={"instruction":"冷藏醃製"})
    assert next(step for step in step_updated.json()["versions"][0]["steps"] if step["id"]==ids[0])["instruction"]=="冷藏醃製"
    step_deleted=client.delete(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{batch['id']}/steps/{ids[1]}",headers=admin)
    assert [(step["id"],step["step_order"]) for step in step_deleted.json()["versions"][0]["steps"]]==[(ids[0],1)]
    copied=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{batch['id']}/copy",headers=admin,json={"serving_count":50,"name":"五十人版","is_official":True})
    assert copied.status_code==201 and len(copied.json()["versions"])==2
    ten=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions",headers=admin,json={"serving_count":10,"name":"十人版","is_official":True})
    thirty=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions",headers=admin,json={"serving_count":30,"name":"三十人版","is_official":True})
    assert ten.status_code==201 and thirty.status_code==201
    ten_id=next(item["id"] for item in thirty.json()["versions"] if item["serving_count"]==10)
    updated=client.patch(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{ten_id}",headers=admin,json={"name":"十人正式版","is_official":True})
    assert next(item for item in updated.json()["versions"] if item["id"]==ten_id)["name"]=="十人正式版"
    deleted=client.delete(f"/api/v1/dishes/{dish['id']}/production-profile/versions/{ten_id}",headers=admin)
    assert all(item["id"]!=ten_id for item in deleted.json()["versions"])
    assert client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions",headers=admin,json={"serving_count":101}).status_code==422
    duplicate=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/versions",headers=admin,json={"serving_count":50})
    assert duplicate.status_code==409
    assert len(client.get(f"/api/v1/dishes/{dish['id']}/production-profile",headers=admin).json()["versions"])==3
    preview=client.get(f"/api/v1/dishes/{dish['id']}/production-profile/preview?servings=286",headers=user).json()
    assert [(item["serving_count"],item["official"]) for item in preview["batches"]]==[(100,True),(100,True),(50,True),(30,True),(6,False)]
    actions=set(db_session.scalars(select(AuditLog.action).where(AuditLog.action.like("production_%"))))
    assert {"production_profile_create","production_version_create","production_ingredient_update","production_step_create","production_steps_reorder","production_version_copy"}<=actions


def test_image_validation_secure_read_and_replace(client:TestClient,db_session:Session,tmp_path,monkeypatch):
    admin=login(client,db_session,"image_admin","admin");_,dishes=foundations(client,admin);dish=dishes[0]
    monkeypatch.setattr(settings,"media_root",str(tmp_path))
    client.post(f"/api/v1/dishes/{dish['id']}/production-profile",headers=admin,json={"max_batch_size":100})
    assert client.post(f"/api/v1/dishes/{dish['id']}/production-profile/image",headers=admin,files={"file":("bad.png",b"not-an-image","image/png")}).status_code==422
    stream=BytesIO();Image.new("RGB",(12,12),(40,100,60)).save(stream,"PNG")
    uploaded=client.post(f"/api/v1/dishes/{dish['id']}/production-profile/image",headers=admin,files={"file":("dish.png",stream.getvalue(),"image/png")})
    assert uploaded.status_code==200 and uploaded.json()["has_image"] is True
    assert client.get(f"/api/v1/dishes/{dish['id']}/production-profile/image").status_code==401
    image=client.get(f"/api/v1/dishes/{dish['id']}/production-profile/image",headers=admin)
    assert image.status_code==200 and image.headers["content-type"].startswith("image/png") and image.headers["x-content-type-options"]=="nosniff"
    assert len(list((tmp_path/"dish-images").iterdir()))==1
    next((tmp_path/"dish-images").iterdir()).unlink()
    missing=client.get(f"/api/v1/dishes/{dish['id']}/production-profile",headers=admin)
    assert missing.status_code==200 and missing.json()["has_image"] is False
    assert client.get(f"/api/v1/dishes/{dish['id']}/production-profile/image",headers=admin).status_code==422
    assert client.delete(f"/api/v1/dishes/{dish['id']}/production-profile/image",headers=admin).json()["has_image"] is False
    assert list((tmp_path/"dish-images").iterdir())==[]


def test_menu_driven_plan_missing_profile_and_pdf(client:TestClient,db_session:Session):
    admin=login(client,db_session,"plan_admin","admin");category,dishes=foundations(client,admin)
    menu=client.post("/api/v1/menus",headers=admin,json={"name":"九月菜單","start_date":"2026-09-01","end_date":"2026-09-02","category_id":category["id"]}).json()
    meal=client.post(f"/api/v1/menus/{menu['id']}/meal-types",headers=admin,json={"name":"午餐","sort_order":1}).json()
    payload={"slots":[{"menu_date":"2026-09-01","menu_meal_type_id":meal["id"],"dishes":[{"dish_id":dishes[2]["id"],"diner_count":120,"sort_order":3},{"dish_id":dishes[1]["id"],"diner_count":80,"sort_order":2},{"dish_id":dishes[0]["id"],"diner_count":286,"sort_order":1}]}]}
    assert client.put(f"/api/v1/menus/{menu['id']}/editor",headers=admin,json=payload).status_code==200
    client.post(f"/api/v1/dishes/{dishes[0]['id']}/production-profile",headers=admin,json={"max_batch_size":100})
    client.post(f"/api/v1/dishes/{dishes[0]['id']}/production-profile/versions",headers=admin,json={"serving_count":100,"name":"百人正式版","is_official":True})
    draft=client.post(f"/api/v1/dishes/{dishes[0]['id']}/production-profile/versions",headers=admin,json={"serving_count":60,"name":"六十人草稿","is_official":False}).json()
    draft_id=next(item["id"] for item in draft["versions"] if not item["is_official"])
    assert any(item["id"]==draft_id for item in client.get(f"/api/v1/dishes/{dishes[0]['id']}/production-profile",headers=admin).json()["versions"])
    client.post(f"/api/v1/dishes/{dishes[1]['id']}/production-profile",headers=admin,json={"max_batch_size":50})
    plan=client.get(f"/api/v1/menus/{menu['id']}/production-plan?date=2026-09-01&meal_type_id={meal['id']}",headers=admin)
    assert plan.status_code==200,plan.text
    planned=plan.json()["days"][0]["meals"][0]["dishes"]
    assert [item["dish_name"] for item in planned]==["三杯雞","時蔬","冬瓜湯"]
    assert planned[0]["diner_count"]==286 and planned[0]["batch_count"]==3
    assert [(batch["serving_count"],batch["official"]) for batch in planned[0]["batches"]]==[(100,True),(100,True),(86,False)]
    assert all(batch["version_id"]!=draft_id for batch in planned[0]["batches"])
    assert [batch["serving_count"] for batch in planned[1]["batches"]]==[50,30]
    assert planned[2]["profile_missing"] is True
    assert planned[2]["batch_count"]==0 and planned[2]["batches"]==[]
    work_pdf=client.get(f"/api/v1/exports/menus/{menu['id']}/recipe-cards/pdf?date=2026-09-01&meal_type_id={meal['id']}&mode=work",headers=admin)
    detail_pdf=client.get(f"/api/v1/exports/menus/{menu['id']}/recipe-cards/pdf?date=2026-09-01&meal_type_id={meal['id']}&mode=detailed",headers=admin)
    for pdf,label in ((work_pdf,"廚房工作單"),(detail_pdf,"標準食譜詳細版")):
        assert pdf.status_code==200,pdf.text
        assert pdf.headers["content-type"]=="application/pdf" and pdf.content.startswith(b"%PDF")
        disposition=unquote(pdf.headers["content-disposition"])
        assert f"KitchenERP_{label}_2026-09-01_午餐.pdf" in disposition
    assert work_pdf.content!=detail_pdf.content
    assert client.get(f"/api/v1/exports/menus/{menu['id']}/recipe-cards/pdf?date=2026-09-01&mode=unknown",headers=admin).status_code==422
    assert client.get(f"/api/v1/menus/{menu['id']}/production-plan?date=2026-10-01",headers=admin).status_code==422


def test_selected_meal_uses_its_actual_diner_counts_sorting_and_per_dish_maximum(client:TestClient,db_session:Session):
    admin=login(client,db_session,"meal_count_admin","admin");category,dishes=foundations(client,admin)
    menu=client.post("/api/v1/menus",headers=admin,json={"name":"三餐人數測試","start_date":"2026-09-01","end_date":"2026-09-01","category_id":category["id"]}).json()
    meal_types=[]
    for order,name in enumerate(("早餐","午餐","晚餐"),1):
        meal_types.append(client.post(f"/api/v1/menus/{menu['id']}/meal-types",headers=admin,json={"name":name,"sort_order":order}).json())
    payload={"slots":[
        {"menu_date":"2026-09-01","menu_meal_type_id":meal_types[0]["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":30,"sort_order":1}]},
        {"menu_date":"2026-09-01","menu_meal_type_id":meal_types[1]["id"],"dishes":[{"dish_id":dishes[1]["id"],"diner_count":286,"sort_order":2},{"dish_id":dishes[0]["id"],"diner_count":286,"sort_order":1}]},
        {"menu_date":"2026-09-01","menu_meal_type_id":meal_types[2]["id"],"dishes":[{"dish_id":dishes[0]["id"],"diner_count":80,"sort_order":1}]},
    ]}
    assert client.put(f"/api/v1/menus/{menu['id']}/editor",headers=admin,json=payload).status_code==200
    client.post(f"/api/v1/dishes/{dishes[0]['id']}/production-profile",headers=admin,json={"max_batch_size":100})
    client.post(f"/api/v1/dishes/{dishes[1]['id']}/production-profile",headers=admin,json={"max_batch_size":50})

    response=client.get(f"/api/v1/menus/{menu['id']}/production-plan?date=2026-09-01&meal_type_id={meal_types[1]['id']}",headers=admin)
    assert response.status_code==200,response.text
    days=response.json()["days"]
    assert len(days)==1 and [meal["meal_type_name"] for meal in days[0]["meals"]]==["午餐"]
    planned=days[0]["meals"][0]["dishes"]
    assert [dish["dish_name"] for dish in planned]==["三杯雞","時蔬"]
    assert [dish["diner_count"] for dish in planned]==[286,286]
    assert [batch["serving_count"] for batch in planned[0]["batches"]]==[100,100,86]
    assert [batch["serving_count"] for batch in planned[1]["batches"]]==[50,50,50,50,50,36]
