import uuid

from sqlalchemy import select

from app.domains.audit.models import AuditLog
from app.domains.audit.service import AuditLogService
from app.domains.menus.models import MenuDay, MenuDish
from tests.api.menus.test_menus_api import auth, foundations, meals, menu
from tests.api.postpartum.test_change_sheet_api import _configured_handlings
from tests.api.requirements.test_requirements_api import auth as requirements_auth, fixture as requirements_fixture
from tests.api.snapshots.test_snapshots_api import create_snapshot


def _column(client,headers,menu_id,meal,name,order):
    response=client.post(f"/api/v1/menus/{menu_id}/meal-types/{meal['id']}/columns",
        headers=headers,json={"name":name,"sort_order":order})
    assert response.status_code==201,response.text
    return response.json()


def _setup(client,db_session):
    headers,_=auth(client,db_session);category,dishes=foundations(client,headers,4)
    value=menu(client,headers,category["id"]);breakfast,lunch=meals(client,headers,value["id"],("早餐","午餐"))
    main=_column(client,headers,value["id"],breakfast,"主菜",1)
    side=_column(client,headers,value["id"],breakfast,"配菜",2)
    soup=_column(client,headers,value["id"],breakfast,"湯",3)
    lunch_main=_column(client,headers,value["id"],lunch,"午餐主菜",1)
    return headers,value,breakfast,lunch,(main,side,soup,lunch_main),dishes


def _save(client,headers,menu_id,slots):
    response=client.put(f"/api/v1/menus/{menu_id}/editor",headers=headers,json={"slots":slots})
    assert response.status_code==200,response.text
    return response.json()


def _slot(body,target_date,meal_id):
    return next(item for item in body["slots"] if item["menu_date"]==target_date and item["menu_meal_type_id"]==meal_id)


def _move(client,headers,menu_id,source,target_date,meal,insert_index,before=None,after=None):
    return client.post(f"/api/v1/menus/{menu_id}/dish-move",headers=headers,json={
        "source_menu_dish_id":source,"target_date":target_date,"target_meal_type_id":meal,
        "insert_index":insert_index,"before_menu_dish_id":before,"after_menu_dish_id":after,
    })


def test_cross_date_insert_between_dishes_moves_whole_item_without_overwrite(client,db_session):
    headers,value,breakfast,_,columns,dishes=_setup(client,db_session);main,side,soup,_=columns
    saved=_save(client,headers,value["id"],[
        {"menu_date":"2026-09-01","menu_meal_type_id":breakfast["id"],"dishes":[
            {"dish_id":dishes[0]["id"],"menu_meal_type_column_id":main["id"],"diner_count":300,"notes":"跟著走","sort_order":1}]},
        {"menu_date":"2026-09-02","menu_meal_type_id":breakfast["id"],"dishes":[
            {"dish_id":dishes[1]["id"],"menu_meal_type_column_id":main["id"],"diner_count":10,"sort_order":1},
            {"dish_id":dishes[2]["id"],"menu_meal_type_column_id":side["id"],"diner_count":20,"sort_order":2},
            {"dish_id":dishes[3]["id"],"menu_meal_type_column_id":soup["id"],"diner_count":30,"sort_order":3}]},
    ])
    source=_slot(saved,"2026-09-01",breakfast["id"])["dishes"][0]
    target=_slot(saved,"2026-09-02",breakfast["id"])["dishes"]
    response=_move(client,headers,value["id"],source["id"],"2026-09-02",breakfast["id"],1,target[0]["id"],target[1]["id"])
    assert response.status_code==200,response.text
    body=response.json()
    assert _slot(body,"2026-09-01",breakfast["id"])["dishes"]==[]
    result=_slot(body,"2026-09-02",breakfast["id"])["dishes"]
    assert [item["id"] for item in result]==[target[0]["id"],source["id"],target[1]["id"],target[2]["id"]]
    assert [item["sort_order"] for item in result]==[1,2,3,4]
    moved=result[1]
    assert moved["dish_id"]==source["dish_id"] and moved["diner_count"]==300 and moved["notes"]=="跟著走"
    assert [item["menu_meal_type_column_id"] for item in result]==[main["id"],side["id"],soup["id"],None]
    audit=db_session.scalar(select(AuditLog).where(AuditLog.action=="menu_dish_move"))
    assert audit is not None and audit.metadata_data["operation"]=="insert"


def test_insert_first_last_and_same_day_reorder_are_normalized(client,db_session):
    headers,value,breakfast,_,columns,dishes=_setup(client,db_session);main,side,soup,_=columns
    saved=_save(client,headers,value["id"],[{"menu_date":"2026-09-01","menu_meal_type_id":breakfast["id"],"dishes":[
        {"dish_id":dishes[0]["id"],"menu_meal_type_column_id":main["id"],"diner_count":10,"sort_order":1},
        {"dish_id":dishes[1]["id"],"menu_meal_type_column_id":side["id"],"diner_count":20,"sort_order":2},
        {"dish_id":dishes[2]["id"],"menu_meal_type_column_id":soup["id"],"diner_count":30,"sort_order":3}]}])
    items=_slot(saved,"2026-09-01",breakfast["id"])["dishes"]
    first=_move(client,headers,value["id"],items[2]["id"],"2026-09-01",breakfast["id"],0,None,items[0]["id"])
    assert first.status_code==200,first.text
    reordered=_slot(first.json(),"2026-09-01",breakfast["id"])["dishes"]
    assert [item["id"] for item in reordered]==[items[2]["id"],items[0]["id"],items[1]["id"]]
    last=_move(client,headers,value["id"],items[2]["id"],"2026-09-01",breakfast["id"],3,items[1]["id"],None)
    assert last.status_code==200,last.text
    final=_slot(last.json(),"2026-09-01",breakfast["id"])["dishes"]
    assert [item["id"] for item in final]==[items[0]["id"],items[1]["id"],items[2]["id"]]
    assert [item["sort_order"] for item in final]==[1,2,3]
    assert [item["diner_count"] for item in final]==[10,20,30]


def test_insert_into_empty_fixed_position_and_reject_stale_or_invalid_targets(client,db_session):
    headers,value,breakfast,lunch,columns,dishes=_setup(client,db_session);main,side,_,_=columns
    other=menu(client,headers,None,"其他菜單");other_meal=meals(client,headers,other["id"],("早餐",))[0]
    saved=_save(client,headers,value["id"],[{"menu_date":"2026-09-01","menu_meal_type_id":breakfast["id"],"dishes":[
        {"dish_id":dishes[0]["id"],"menu_meal_type_column_id":main["id"],"diner_count":10,"sort_order":1}]}])
    source=_slot(saved,"2026-09-01",breakfast["id"])["dishes"][0]
    moved=_move(client,headers,value["id"],source["id"],"2026-09-02",breakfast["id"],1,None,None)
    assert moved.status_code==200,moved.text
    result=_slot(moved.json(),"2026-09-02",breakfast["id"])["dishes"][0]
    assert result["menu_meal_type_column_id"]==side["id"]
    assert _move(client,headers,value["id"],result["id"],"2026-09-02",breakfast["id"],0,None,str(uuid.uuid4())).status_code==422
    assert _move(client,headers,value["id"],result["id"],"2026-09-04",breakfast["id"],0).status_code==422
    assert _move(client,headers,value["id"],result["id"],"2026-09-02",lunch["id"],2).status_code==422
    assert _move(client,headers,other["id"],result["id"],"2026-09-01",other_meal["id"],0).status_code==422


def test_final_duplicate_dish_is_rejected(client,db_session):
    headers,value,breakfast,_,columns,dishes=_setup(client,db_session);main,_,_,_=columns
    saved=_save(client,headers,value["id"],[
        {"menu_date":"2026-09-01","menu_meal_type_id":breakfast["id"],"dishes":[
            {"dish_id":dishes[0]["id"],"menu_meal_type_column_id":main["id"],"diner_count":10,"sort_order":1}]},
        {"menu_date":"2026-09-02","menu_meal_type_id":breakfast["id"],"dishes":[
            {"dish_id":dishes[0]["id"],"menu_meal_type_column_id":main["id"],"diner_count":20,"sort_order":1}]},
    ])
    source=_slot(saved,"2026-09-01",breakfast["id"])["dishes"][0]
    target=_slot(saved,"2026-09-02",breakfast["id"])["dishes"][0]
    assert _move(client,headers,value["id"],source["id"],"2026-09-02",breakfast["id"],0,None,target["id"]).status_code==409


def test_move_rolls_back_when_audit_fails(client,db_session,monkeypatch):
    headers,value,breakfast,_,columns,dishes=_setup(client,db_session);main,side,_,_=columns
    saved=_save(client,headers,value["id"],[{"menu_date":"2026-09-01","menu_meal_type_id":breakfast["id"],"dishes":[
        {"dish_id":dishes[0]["id"],"menu_meal_type_column_id":main["id"],"diner_count":10,"sort_order":1},
        {"dish_id":dishes[1]["id"],"menu_meal_type_column_id":side["id"],"diner_count":20,"sort_order":2}]}])
    first,second=_slot(saved,"2026-09-01",breakfast["id"])["dishes"]
    monkeypatch.setattr(AuditLogService,"record",lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError("audit failed")))
    response=_move(client,headers,value["id"],second["id"],"2026-09-01",breakfast["id"],0,None,first["id"])
    assert response.status_code==400
    db_session.expire_all()
    persisted=list(db_session.scalars(select(MenuDish).order_by(MenuDish.sort_order)))
    assert [str(item.id) for item in persisted]==[first["id"],second["id"]]
    assert [item.menu_meal_type_column_id for item in persisted]==[uuid.UUID(main["id"]),uuid.UUID(side["id"])]


def test_live_recalculation_follows_move_while_snapshot_and_purchase_stay_frozen(client,db_session):
    headers=requirements_auth(client,db_session);value,_,_,_,_=requirements_fixture(client,headers)
    aggregate=client.get(f"/api/v1/menus/{value['id']}/editor",headers=headers).json()
    meal_id=aggregate["meal_types"][0]["id"]
    source_slot=_slot(aggregate,"2026-09-01",meal_id);target_slot=_slot(aggregate,"2026-09-02",meal_id)
    source=source_slot["dishes"][0]
    target_slot["dishes"]=target_slot["dishes"][1:]
    target_slot["dishes"][0]["diner_count"]=25
    payload=[{"menu_day_id":slot["menu_day_id"],"menu_date":slot["menu_date"],"menu_meal_type_id":slot["menu_meal_type_id"],
        "notes":slot["notes"],"dishes":[{"id":dish["id"],"dish_id":dish["dish_id"],
            "menu_meal_type_column_id":dish["menu_meal_type_column_id"],"diner_count":dish["diner_count"],
            "notes":dish["notes"],"sort_order":index+1} for index,dish in enumerate(slot["dishes"])]}
        for slot in aggregate["slots"]]
    aggregate=_save(client,headers,value["id"],payload)
    source=_slot(aggregate,"2026-09-01",meal_id)["dishes"][0]
    target=_slot(aggregate,"2026-09-02",meal_id)["dishes"][0]
    criteria={"menu_ids":[value["id"]],"selected_dates":["2026-09-01"]}
    before=client.post("/api/v1/requirements/calculate",headers=headers,json=criteria).json()
    snapshot=create_snapshot(client,headers,{"id":value["id"]});assert snapshot.status_code==201,snapshot.text
    purchase=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot.json()["id"]});assert purchase.status_code==201,purchase.text
    frozen=client.get(f"/api/v1/requirement-snapshots/{snapshot.json()['id']}",headers=headers).json()
    purchase_before=client.get(f"/api/v1/purchases/{purchase.json()['id']}",headers=headers).json()
    moved=_move(client,headers,value["id"],source["id"],"2026-09-02",meal_id,0,None,target["id"])
    assert moved.status_code==200,moved.text
    after=client.post("/api/v1/requirements/calculate",headers=headers,json=criteria).json()
    assert before["rows"]!=after["rows"]
    kitchen=client.post("/api/v1/kitchen-operations/calculate",headers=headers,json={"menu_id":value["id"],"selected_dates":["2026-09-02"]}).json()
    moved_view=next(dish for meal in kitchen["days"][0]["meals"] for dish in meal["dishes"] if dish["dish_id"]==source["dish_id"])
    assert moved_view["diner_count"]==source["diner_count"]
    assert client.get(f"/api/v1/requirement-snapshots/{snapshot.json()['id']}",headers=headers).json()==frozen
    assert client.get(f"/api/v1/purchases/{purchase.json()['id']}",headers=headers).json()==purchase_before


def test_moving_handled_menu_dish_keeps_postpartum_reconfirmation_safety(client,db_session):
    headers,_,_,first_items,_,_,_=_configured_handlings(client,db_session)
    source=db_session.get(MenuDish,uuid.UUID(first_items[0]["original_menu_dish_id"]))
    source_day=db_session.get(MenuDay,source.menu_day_id);menu_id=str(source_day.menu_id)
    editor=client.get(f"/api/v1/menus/{menu_id}/editor",headers=headers).json()
    lunch=next(meal for meal in editor["meal_types"] if meal["id"]==str(source_day.menu_meal_type_id))
    assert client.patch(f"/api/v1/menus/{menu_id}",headers=headers,json={"end_date":"2026-09-11"}).status_code==200
    moved=_move(client,headers,menu_id,first_items[0]["original_menu_dish_id"],"2026-09-11",lunch["id"],0,None,None)
    assert moved.status_code==200,moved.text
    sheet=client.get("/api/v1/postpartum/change-sheet/daily?target_date=2026-09-10",headers=headers).json()
    stale=[item for meal in sheet["meals"] for item in meal["requires_reconfirmation"]]
    assert any(item["original_menu_dish_id"]==first_items[0]["original_menu_dish_id"] for item in stale)
