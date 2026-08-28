from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from sqlalchemy import event,func,select
from app.db.session import engine as process_engine
from app.domains.purchases.models import PurchaseBatch,PurchaseOrder,PurchaseOrderItem
from app.domains.purchases.repository import PurchaseRepository
from app.domains.snapshots.models import RequirementSnapshotItem
from tests.api.requirements.test_requirements_api import auth,fixture
from tests.api.snapshots.test_snapshots_api import create_snapshot

def setup_snapshot(client,db_session):
    headers=auth(client,db_session);menu,*rest=fixture(client,headers);snapshot=create_snapshot(client,headers,menu)
    assert snapshot.status_code==201,snapshot.text
    return headers,menu,rest,snapshot.json()

def test_known_answer_supplier_grouping_units_cost_lock_and_hard_copy(client,db_session):
    headers,menu,rest,snapshot=setup_snapshot(client,db_session);_,dishes,ingredients,suppliers=rest
    chicken=next(item for item in snapshot["items"] if item["ingredient_code_snapshot"]=="REQ-I1")
    water=next(item for item in snapshot["items"] if item["ingredient_code_snapshot"]=="REQ-I3")
    changed=client.patch(f"/api/v1/requirement-snapshots/{snapshot['id']}/items/{chicken['id']}",headers=headers,json={"purchase_unit":"斤"}).json()
    assert Decimal(changed["adjusted_quantity"])==Decimal("31.5") and Decimal(changed["adjusted_estimated_cost"])==3780
    changed=client.patch(f"/api/v1/requirement-snapshots/{snapshot['id']}/items/{chicken['id']}",headers=headers,json={"adjusted_quantity":"31.5","purchase_unit":"kg"}).json()
    assert Decimal(changed["adjusted_quantity"])==Decimal("18.9")
    changed=client.patch(f"/api/v1/requirement-snapshots/{snapshot['id']}/items/{chicken['id']}",headers=headers,json={"adjusted_quantity":"18.9","purchase_unit":"斤"}).json()
    assert Decimal(changed["adjusted_quantity"])==Decimal("31.5")
    changed_water=client.patch(f"/api/v1/requirement-snapshots/{snapshot['id']}/items/{water['id']}",headers=headers,json={"purchase_unit":"ml"}).json()
    assert Decimal(changed_water["adjusted_quantity"])==11250 and Decimal(changed_water["adjusted_estimated_cost"])==Decimal("22.5")
    response=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"],"notes":"正式採購"});assert response.status_code==201,response.text
    body=response.json();assert body["status"]=="draft" and body["purchase_number"].startswith("PO-")
    assert len(body["orders"])==2 and sorted(len(order["items"]) for order in body["orders"])==[1,2]
    rows={item["ingredient_code_snapshot"]:item for order in body["orders"] for item in order["items"]}
    assert Decimal(rows["REQ-I1"]["final_purchase_quantity"])==Decimal("31.5") and rows["REQ-I1"]["purchase_unit_snapshot"]=="斤"
    assert Decimal(rows["REQ-I1"]["purchase_cost_snapshot"])==3780 and Decimal(body["total_cost"])==Decimal("3811.5")
    assert "PURCHASE_RULE_REFERENCE_ONLY" in {a["code"] for a in rows["REQ-I1"]["anomaly_snapshot"]}
    locked=client.get(f"/api/v1/requirement-snapshots/{snapshot['id']}",headers=headers).json();assert locked["locked"] is True and locked["purchase_id"]==body["id"]
    assert client.patch(f"/api/v1/requirement-snapshots/{snapshot['id']}/items/{chicken['id']}",headers=headers,json={"adjusted_quantity":"1"}).status_code==409
    client.patch(f"/api/v1/ingredients/{ingredients[0]['id']}",headers=headers,json={"name":"採購後新食材"});client.patch(f"/api/v1/suppliers/{suppliers[0]['id']}",headers=headers,json={"name":"採購後新供應商"})
    frozen=client.get(f"/api/v1/purchases/{body['id']}",headers=headers).json();frozen_rows={i["ingredient_code_snapshot"]:i for o in frozen["orders"] for i in o["items"]}
    assert frozen_rows["REQ-I1"]["ingredient_name_snapshot"]=="雞肉" and frozen_rows["REQ-I1"]["supplier_name_snapshot"]=="供應商1"

def test_readiness_blocks_missing_supplier_and_incompatible_unit(client,db_session):
    headers,_,_,snapshot=setup_snapshot(client,db_session);item_id=snapshot["items"][0]["id"]
    item=db_session.get(RequirementSnapshotItem,item_id);item.supplier_id=None;item.purchase_unit_snapshot="個";db_session.commit()
    detail=client.get(f"/api/v1/requirement-snapshots/{snapshot['id']}",headers=headers).json();codes={issue["code"] for issue in detail["blocking_issues"]}
    assert {"UNASSIGNED_SUPPLIER","INCOMPATIBLE_PURCHASE_UNIT"}.issubset(codes) and detail["purchase_ready"] is False
    response=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"]});assert response.status_code==422 and response.json()["detail"]["code"]=="SNAPSHOT_NOT_READY"

def test_unknown_cost_known_total_status_duplicate_delete_and_auth(client,db_session):
    assert client.post("/api/v1/purchases",json={"snapshot_id":"00000000-0000-0000-0000-000000000001"}).status_code==401
    headers,_,_,snapshot=setup_snapshot(client,db_session);item=db_session.get(RequirementSnapshotItem,snapshot["items"][0]["id"]);item.unit_price_snapshot=None;db_session.commit()
    created=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"]});assert created.status_code==201
    body=created.json();assert body["total_cost"] is None and Decimal(body["known_total_cost"])>0
    duplicate=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"]});assert duplicate.status_code==409
    confirmed=client.post(f"/api/v1/purchases/{body['id']}/confirm",headers=headers);assert confirmed.status_code==200 and confirmed.json()["status"]=="confirmed"
    assert client.post(f"/api/v1/purchases/{body['id']}/confirm",headers=headers).status_code==409
    cancelled=client.post(f"/api/v1/purchases/{body['id']}/cancel",headers=headers);assert cancelled.status_code==200 and cancelled.json()["status"]=="cancelled"
    assert client.post(f"/api/v1/requirement-snapshots/{snapshot['id']}/hard-delete",headers=headers,json={"password":"correct horse battery staple"}).status_code==409

def test_unlinked_snapshot_admin_password_delete(client,db_session):
    headers,_,_,snapshot=setup_snapshot(client,db_session)
    assert client.post(f"/api/v1/requirement-snapshots/{snapshot['id']}/hard-delete",headers=headers,json={"password":"wrong"}).status_code==401
    assert client.post(f"/api/v1/requirement-snapshots/{snapshot['id']}/hard-delete",headers=headers,json={"password":"correct horse battery staple"}).status_code==204

def test_concurrent_duplicate_and_atomic_rollback(client,db_session,monkeypatch):
    headers,_,_,snapshot=setup_snapshot(client,db_session)
    def send(_):return client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"]}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:statuses=list(executor.map(send,range(2)))
    assert sorted(statuses)==[201,409] and db_session.scalar(select(func.count()).select_from(PurchaseBatch))==1

def test_creation_failure_rolls_back_all_supplier_orders(client,db_session,monkeypatch):
    headers,_,_,snapshot=setup_snapshot(client,db_session);original=PurchaseRepository.add;seen_order=False
    def fail_second_layer(self,value):
        nonlocal seen_order
        if isinstance(value,PurchaseOrder):
            if seen_order:raise RuntimeError("injected supplier failure")
            seen_order=True
        return original(self,value)
    monkeypatch.setattr(PurchaseRepository,"add",fail_second_layer)
    assert client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"]}).status_code==400
    db_session.expire_all();assert db_session.scalar(select(func.count()).select_from(PurchaseBatch))==0;assert db_session.scalar(select(func.count()).select_from(PurchaseOrder))==0;assert db_session.scalar(select(func.count()).select_from(PurchaseOrderItem))==0

def test_list_pagination_filters_and_detail_query_budget(client,db_session):
    headers,_,_,snapshot=setup_snapshot(client,db_session);created=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"]}).json()
    listing=client.get(f"/api/v1/purchases?page=1&page_size=1&purchase_status=draft&search={created['purchase_number']}",headers=headers).json();assert listing["pagination"]["total"]==1 and len(listing["items"][0]["supplier_summary"])==2
    statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.get(f"/api/v1/purchases/{created['id']}",headers=headers)
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200 and len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=5

def test_creation_query_count_does_not_scale_per_item(client,db_session):
    headers,_,_,snapshot=setup_snapshot(client,db_session);statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":snapshot["id"]})
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==201 and len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=7
