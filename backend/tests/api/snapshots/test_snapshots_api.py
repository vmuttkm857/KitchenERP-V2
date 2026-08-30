import uuid
from datetime import UTC,datetime
from decimal import Decimal
from sqlalchemy import event
from sqlalchemy import func,select
from concurrent.futures import ThreadPoolExecutor
from app.db.session import engine as process_engine
from tests.api.requirements.test_requirements_api import auth,fixture
from app.domains.snapshots.models import RequirementSnapshot,RequirementSnapshotItem
from app.domains.snapshots.repository import SnapshotRepository
from app.domains.ingredients.models import Ingredient
from app.domains.recipes.models import DishIngredient
from app.domains.menus.models import MenuDish
from app.domains.users.models import User

def create_snapshot(client,headers,menu):
    return client.post("/api/v1/requirement-snapshots",headers=headers,json={"criteria":{"menu_ids":[menu["id"]]}})

def test_snapshot_known_answer_hard_copy_adjustment_and_immutability(client,db_session):
    headers=auth(client,db_session);menu,_,dishes,ingredients,suppliers=fixture(client,headers)
    response=create_snapshot(client,headers,menu);assert response.status_code==201,response.text
    body=response.json();rows={row["ingredient_code_snapshot"]:row for row in body["items"]}
    assert Decimal(rows["REQ-I1"]["requirement_quantity"])==Decimal("18.9")
    assert Decimal(rows["REQ-I2"]["requirement_quantity"])==Decimal("0.45")
    assert Decimal(rows["REQ-I3"]["requirement_quantity"])==Decimal("11.25")
    assert Decimal(body["total_estimated_cost"])==Decimal("3811.5")
    chicken=rows["REQ-I1"];assert chicken["adjusted_quantity"]==chicken["suggested_purchase_quantity"]
    updated=client.patch(f"/api/v1/requirement-snapshots/{body['id']}/items/{chicken['id']}",headers=headers,json={"adjusted_quantity":"0"})
    assert updated.status_code==200 and Decimal(updated.json()["adjusted_quantity"])==0
    assert updated.json()["requirement_quantity"]==chicken["requirement_quantity"] and updated.json()["suggested_purchase_quantity"]==chicken["suggested_purchase_quantity"]
    client.patch(f"/api/v1/ingredients/{ingredients[0]['id']}",headers=headers,json={"name":"新雞肉名稱"})
    client.post(f"/api/v1/ingredients/{ingredients[0]['id']}/price",headers=headers,json={"price":"999","effective_date":"2026-09-10"})
    client.patch(f"/api/v1/suppliers/{suppliers[0]['id']}",headers=headers,json={"name":"新供應商名稱"})
    client.put(f"/api/v1/dishes/{dishes[0]['id']}/recipe",headers=headers,json={"items":[{"ingredient_id":ingredients[0]["id"],"quantity":"999","unit":"kg","loss_rate":"0","sort_order":1}]})
    client.patch(f"/api/v1/menus/{menu['id']}",headers=headers,json={"name":"新菜單名稱"})
    frozen=client.get(f"/api/v1/requirement-snapshots/{body['id']}",headers=headers).json();frozen_chicken=next(row for row in frozen["items"] if row["ingredient_code_snapshot"]=="REQ-I1")
    assert frozen_chicken["ingredient_name_snapshot"]=="雞肉" and frozen_chicken["supplier_name_snapshot"]=="供應商1"
    assert Decimal(frozen_chicken["unit_price_snapshot"])==200 and Decimal(frozen_chicken["requirement_quantity"])==Decimal("18.9")
    assert frozen["source_menus"][0]["menu_name"]=="三日需求菜單"

def test_duplicate_list_negative_and_unauthorized(client,db_session):
    assert client.get("/api/v1/requirement-snapshots").status_code==401
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    first=create_snapshot(client,headers,menu);second=create_snapshot(client,headers,menu)
    assert first.status_code==201 and second.status_code==409 and second.json()["detail"]["code"]=="DUPLICATE_SNAPSHOT"
    assert second.json()["detail"]["existing_snapshot_id"]==first.json()["id"]
    listed=client.get("/api/v1/requirement-snapshots?page=1&page_size=1",headers=headers).json();assert listed["pagination"]["total"]==1
    item=first.json()["items"][0]
    assert client.patch(f"/api/v1/requirement-snapshots/{first.json()['id']}/items/{item['id']}",headers=headers,json={"adjusted_quantity":"-1"}).status_code==422

def test_snapshot_list_date_filters_end_inclusive_pagination_order_and_query_budget(client,db_session):
    headers=auth(client,db_session);actor=db_session.scalar(select(User));ids=[]
    values=[
        ("before",datetime(2026,8,9,15,59,tzinfo=UTC)),
        ("start",datetime(2026,8,9,16,0,tzinfo=UTC)),
        ("end",datetime(2026,8,10,15,59,tzinfo=UTC)),
        ("after",datetime(2026,8,10,16,0,tzinfo=UTC)),
    ]
    for index,(label,created_at) in enumerate(values,1):
        value=RequirementSnapshot(id=uuid.uuid4(),fingerprint=f"f{index:063d}",criteria_fingerprint=f"c{index:063d}",content_fingerprint=f"x{index:063d}",revision=1,criteria={},source_menus=[],anomaly_snapshot=[],anomaly_summary={"total":0},known_estimated_cost=Decimal("0"),total_estimated_cost=Decimal("0"),created_at=created_at,created_by=actor.id)
        db_session.add(value);ids.append((label,str(value.id)))
    db_session.commit();by_label=dict(ids)

    start_only=client.get("/api/v1/requirement-snapshots?start_date=2026-08-10&page_size=100",headers=headers).json()
    assert start_only["pagination"]["total"]==3
    end_only=client.get("/api/v1/requirement-snapshots?end_date=2026-08-10&page_size=100",headers=headers).json()
    assert end_only["pagination"]["total"]==3
    ranged=client.get("/api/v1/requirement-snapshots?start_date=2026-08-10&end_date=2026-08-10&page=1&page_size=1",headers=headers).json()
    assert ranged["pagination"]["total"]==2
    assert ranged["items"][0]["id"]==by_label["end"]
    second=client.get("/api/v1/requirement-snapshots?start_date=2026-08-10&end_date=2026-08-10&page=2&page_size=1",headers=headers).json()
    assert second["items"][0]["id"]==by_label["start"]
    assert client.get("/api/v1/requirement-snapshots?start_date=2026-08-11&end_date=2026-08-10",headers=headers).status_code==422

    statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.get("/api/v1/requirement-snapshots?start_date=2026-08-10&end_date=2026-08-10&page=1&page_size=25",headers=headers)
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200
    assert len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=3

def test_detail_query_count_is_constant(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_snapshot(client,headers,menu).json();statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.get(f"/api/v1/requirement-snapshots/{created['id']}",headers=headers)
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200
    assert len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=4

def test_concurrent_duplicate_is_constraint_backed(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    def send(_):return create_snapshot(client,headers,menu).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:statuses=list(executor.map(send,range(2)))
    assert sorted(statuses)==[201,409]
    assert client.get("/api/v1/requirement-snapshots",headers=headers).json()["pagination"]["total"]==1

def test_item_failure_rolls_back_header_and_all_items(client,db_session,monkeypatch):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);original=SnapshotRepository.add;calls=0
    def fail_during_items(self,value):
        nonlocal calls;calls+=1
        if isinstance(value,RequirementSnapshotItem):raise RuntimeError("injected item failure")
        return original(self,value)
    monkeypatch.setattr(SnapshotRepository,"add",fail_during_items)
    assert create_snapshot(client,headers,menu).status_code==400
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(RequirementSnapshot))==0
    assert db_session.scalar(select(func.count()).select_from(RequirementSnapshotItem))==0

def test_same_criteria_content_duplicate_but_source_changes_create_revisions(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    first=create_snapshot(client,headers,menu);assert first.status_code==201 and first.json()["revision"]==1
    assert create_snapshot(client,headers,menu).status_code==409
    ingredient=db_session.scalar(select(Ingredient).where(Ingredient.code=="REQ-I1"));ingredient.current_price=Decimal("201");db_session.commit()
    second=create_snapshot(client,headers,menu);assert second.status_code==201 and second.json()["revision"]==2
    recipe=db_session.scalar(select(DishIngredient).where(DishIngredient.ingredient_id==ingredient.id));recipe.quantity=recipe.quantity+Decimal("1");db_session.commit()
    third=create_snapshot(client,headers,menu);assert third.status_code==201 and third.json()["revision"]==3
    menu_dish=db_session.scalar(select(MenuDish));menu_dish.diner_count+=1;db_session.commit()
    fourth=create_snapshot(client,headers,menu);assert fourth.status_code==201 and fourth.json()["revision"]==4
    assert create_snapshot(client,headers,menu).status_code==409
