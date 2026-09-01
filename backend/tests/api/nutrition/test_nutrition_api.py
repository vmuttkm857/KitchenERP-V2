from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import event,func,select

from app.db.session import engine as process_engine
from app.domains.audit.models import AuditLog
from app.domains.ingredients.models import Ingredient
from app.domains.nutrition.models import NutritionFood,NutritionFoodValue,NutritionImportBatch
from app.domains.nutrition.service import NutritionService
from tests.api.auth.test_users_audit import create_login


def xlsx(rows=None):
    workbook=Workbook();sheet=workbook.active;sheet.append(["說明"]);sheet.append(["整合編號","食品分類","樣品名稱","內容物描述","俗名","廢棄率(%)","熱量(kcal)","修正熱量(kcal)","粗蛋白(g)","鈉(mg)"])
    for row in rows or [["A1","肉類","雞肉","生","雞腿",0,100,90,0,""],["A2","肉類","雞肉","熟","",None,110,95,"Tr",5]]:sheet.append(row)
    output=BytesIO();workbook.save(output);return output.getvalue()


def create_ingredient(client,headers,name="ERP 去骨雞腿"):
    category=client.post("/api/v1/categories/ingredient",headers=headers,json={"name":"營養測試分類"}).json()
    response=client.post("/api/v1/ingredients",headers=headers,json={"code":"NUT-I1","name":name,"category_id":category["id"],"unit":"kg","current_price":"123"})
    assert response.status_code==201,response.text;return response.json()


def import_foods(client,headers,payload=None):
    payload=payload or xlsx();preview=client.post("/api/v1/nutrition/imports/preview",headers=headers,files={"file":("tfda.xlsx",payload,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert preview.status_code==200,preview.text
    confirmed=client.post("/api/v1/nutrition/imports/confirm",headers=headers,files={"file":("tfda.xlsx",payload,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},data={"version_label":"2025 UPDATE1"})
    assert confirmed.status_code==201,confirmed.text;return preview.json(),confirmed.json()


def test_preview_confirm_repeat_update_missing_null_zero_audit_and_read_access(client,db_session):
    admin,headers=create_login(client,db_session,"nutrition-admin");payload=xlsx()
    before=db_session.scalar(select(func.count()).select_from(NutritionFood));preview=client.post("/api/v1/nutrition/imports/preview",headers=headers,files={"file":("safe.xlsx",payload)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["header_row"]==2 and preview.json()["total_rows"]==2 and preview.json()["inserted_count"]==2 and preview.json()["error_count"]==1
    assert db_session.scalar(select(func.count()).select_from(NutritionFood))==before
    summary,batch=import_foods(client,headers,payload);assert batch["inserted_count"]==2 and batch["status"]=="completed_with_warnings"
    db_session.expire_all();foods=list(db_session.scalars(select(NutritionFood).order_by(NutritionFood.external_code)));assert len(foods)==2 and foods[0].name==foods[1].name
    zero=db_session.scalar(select(NutritionFoodValue.value).where(NutritionFoodValue.food_id==foods[0].id, NutritionFoodValue.value==0));assert zero==0
    ingredient=create_ingredient(client,headers,"保留對應的 ERP 食材");assert client.patch(f"/api/v1/ingredients/{ingredient['id']}/nutrition",headers=headers,json={"nutrition_food_id":str(foods[1].id)}).status_code==200
    repeat,_=import_foods(client,headers,payload);assert repeat["inserted_count"]==0 and repeat["unchanged_count"]==2
    changed=xlsx([["A1","肉類","雞肉新版","生","雞腿",0,100,99,0,""],["A3","蔬菜類","甘藍","","高麗菜",0,20,18,1,3]])
    update,_=import_foods(client,headers,changed);assert update["inserted_count"]==1 and update["updated_count"]==1 and update["missing_count"]==1
    db_session.expire_all();missing=db_session.scalar(select(NutritionFood).where(NutritionFood.external_code=="A2"));assert missing and not missing.active_in_latest_import
    assert db_session.get(Ingredient,ingredient["id"]).nutrition_food_id==missing.id
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="nutrition_import_confirm"))==3
    _,user_headers=create_login(client,db_session,"nutrition-reader",role="user");assert client.get("/api/v1/nutrition/foods?source=tfda",headers=user_headers).status_code==200
    assert client.post("/api/v1/nutrition/imports/preview",headers=user_headers,files={"file":("safe.xlsx",payload)}).status_code==403


def test_manual_crud_mapping_transitions_filter_reference_protection_and_no_erp_mutation(client,db_session):
    admin,headers=create_login(client,db_session,"nutrition-mapping-admin");ingredient=create_ingredient(client,headers);import_foods(client,headers)
    official=client.get("/api/v1/nutrition/foods?source=tfda",headers=headers).json()["items"][0]
    manual=client.post("/api/v1/nutrition/manual-foods",headers=headers,json={"name":"品牌冷凍雞塊","brand":"品牌甲","nutrients":{"corrected_energy":"250"}});assert manual.status_code==201,manual.text
    manual_id=manual.json()["id"];assert manual.json()["external_code"] is None and len(manual.json()["values"])==1
    original={key:ingredient[key] for key in ("name","code","category_id","current_price","unit")}
    for target,status in ((official["id"],"official"),(manual_id,"manual"),(None,"none"),(official["id"],"official"),(manual_id,"manual")):
        response=client.patch(f"/api/v1/ingredients/{ingredient['id']}/nutrition",headers=headers,json={"nutrition_food_id":target});assert response.status_code==200,response.text;assert response.json()["nutrition_status"]==status
        assert {key:response.json()[key] for key in original}==original
    listed=client.get("/api/v1/ingredients?nutrition_status=manual",headers=headers).json();assert listed["pagination"]["total"]==1 and listed["items"][0]["nutrition_food_name"]=="品牌冷凍雞塊"
    updated=client.patch(f"/api/v1/nutrition/manual-foods/{manual_id}",headers=headers,json={"name":"新版冷凍雞塊","nutrients":{"corrected_energy":"260","sodium":None}});assert updated.status_code==200 and updated.json()["name"]=="新版冷凍雞塊"
    assert client.post(f"/api/v1/nutrition/manual-foods/{manual_id}/deactivate",headers=headers).status_code==200
    assert client.post(f"/api/v1/nutrition/manual-foods/{manual_id}/reactivate",headers=headers).status_code==200
    assert client.post(f"/api/v1/nutrition/manual-foods/{manual_id}/hard-delete",headers=headers,json={"password":"correct horse battery staple"}).status_code==409
    cleared=client.patch(f"/api/v1/ingredients/{ingredient['id']}/nutrition",headers=headers,json={"nutrition_food_id":None});assert cleared.status_code==200
    assert client.post(f"/api/v1/nutrition/manual-foods/{manual_id}/hard-delete",headers=headers,json={"password":"correct horse battery staple"}).status_code==204
    db_session.expire_all();assert db_session.get(Ingredient,ingredient["id"]).name=="ERP 去骨雞腿"
    actions=set(db_session.scalars(select(AuditLog.action)));assert {"nutrition_manual_create","nutrition_manual_update","ingredient_nutrition_mapping_change","nutrition_hard_delete"}.issubset(actions)


def test_food_lists_and_ingredient_status_use_bounded_queries(client,db_session):
    _,headers=create_login(client,db_session,"nutrition-query-admin");ingredient=create_ingredient(client,headers);import_foods(client,headers);statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:
        assert client.get("/api/v1/nutrition/foods?source=tfda&page_size=25",headers=headers).status_code==200
        assert client.get("/api/v1/ingredients?nutrition_status=none&page_size=25",headers=headers).status_code==200
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=7


def test_upload_validation_auth_and_official_read_only(client,db_session):
    _,headers=create_login(client,db_session,"nutrition-security-admin");assert client.get("/api/v1/nutrition/foods").status_code==401
    assert client.post("/api/v1/nutrition/imports/preview",headers=headers,files={"file":("bad.csv",b"x")}).status_code==422
    import_foods(client,headers);official=client.get("/api/v1/nutrition/foods?source=tfda",headers=headers).json()["items"][0]
    assert client.patch(f"/api/v1/nutrition/manual-foods/{official['id']}",headers=headers,json={"name":"不可改"}).status_code==422


def test_import_failure_rolls_back_batch_foods_and_values(client,db_session,monkeypatch):
    _,headers=create_login(client,db_session,"nutrition-rollback-admin")
    def fail(_service,_parsed=None):raise RuntimeError("forced failure")
    monkeypatch.setattr(NutritionService,"_ensure_nutrients",fail)
    response=client.post("/api/v1/nutrition/imports/confirm",headers=headers,files={"file":("safe.xlsx",xlsx())})
    assert response.status_code==400
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(NutritionImportBatch))==0
    assert db_session.scalar(select(func.count()).select_from(NutritionFood))==0
    assert db_session.scalar(select(func.count()).select_from(NutritionFoodValue))==0
