import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import OperationalError

from app.domains.audit.models import AuditLog
from app.db.session import SessionLocal, engine as process_engine
from app.domains.ingredients.models import Ingredient
from app.domains.dishes.models import Dish
from app.domains.menus.models import MenuDay, MenuDish, MenuMealType
from app.domains.order_adjustments.models import OrderingAdjustmentLine, OrderingAdjustmentSheet
from app.domains.recipes.models import DishIngredient
from app.domains.requirements.repository import RequirementRepository
from app.domains.requirements.schemas import RequirementCriteria
from app.domains.snapshots.models import RequirementSnapshot, RequirementSnapshotItem
from app.domains.users.models import User
from tests.api.requirements.test_requirements_api import auth, fixture


def create_sheet(client,headers,menu):
    return client.post("/api/v1/order-adjustments",headers=headers,json={"criteria":{"menu_ids":[menu["id"]],"selected_dates":["2026-09-01"]},"notes":"第一版"})


def test_create_preserves_source_identity_and_atomic_baseline(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    response=create_sheet(client,headers,menu);assert response.status_code==201,response.text
    body=response.json();assert body["status"]=="draft" and body["lock_version"]==1
    assert len(body["lines"])==12
    assert len({line["source_line_key"] for line in body["lines"]})==12
    assert all(line["source_menu_dish_id"] and line["source_dish_ingredient_id"] for line in body["lines"])
    assert all(line["adjusted_quantity"] is None and line["effective_quantity"]==line["system_quantity"] for line in body["lines"])
    snapshot=db_session.get(RequirementSnapshot,body["baseline_snapshot_id"]);assert snapshot is not None
    items=list(db_session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==snapshot.id)))
    for item in items:
        lines=[line for line in body["lines"] if line["snapshot_item_id"]==str(item.id)]
        assert sum(Decimal(line["system_quantity"]) for line in lines)==item.requirement_quantity
    actions=set(db_session.scalars(select(AuditLog.action)))
    assert {"snapshot_create","ordering_adjustment_create"}.issubset(actions)


def test_batch_edit_is_independent_supports_zero_null_and_locking(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    chicken=[line for line in created["lines"] if line["ingredient_code_snapshot"]=="REQ-I1"]
    selected=chicken[:3];values=["2","3","5"]
    response=client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":1,"lines":[{"id":line["id"],"adjusted_quantity":value} for line,value in zip(selected,values)]})
    assert response.status_code==200,response.text;updated=response.json();assert updated["lock_version"]==2
    by_id={line["id"]:line for line in updated["lines"]}
    assert [Decimal(by_id[line["id"]]["adjusted_quantity"]) for line in selected]==[Decimal("2"),Decimal("3"),Decimal("5")]
    untouched=next(line for line in chicken if line["id"] not in {value["id"] for value in selected});assert by_id[untouched["id"]]["adjusted_quantity"] is None
    assert client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":1,"lines":[{"id":selected[0]["id"],"adjusted_quantity":"1"}]}).status_code==409
    zero=client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":2,"lines":[{"id":selected[0]["id"],"adjusted_quantity":"0"}]}).json()
    assert Decimal(next(line for line in zero["lines"] if line["id"]==selected[0]["id"])["effective_quantity"])==0
    restored=client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":3,"lines":[{"id":selected[0]["id"],"adjusted_quantity":None}]}).json()
    line=next(line for line in restored["lines"] if line["id"]==selected[0]["id"]);assert line["adjusted_quantity"] is None and line["effective_quantity"]==line["system_quantity"]
    assert client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":4,"lines":[{"id":selected[0]["id"],"adjusted_quantity":"-1"}]}).status_code==422


def test_confirm_aggregates_per_source_line_without_mutating_baseline(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    chicken=[line for line in created["lines"] if line["ingredient_code_snapshot"]=="REQ-I1"]
    updates=[{"id":line["id"],"adjusted_quantity":str(index+2)} for index,line in enumerate(chicken)]
    draft=client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":1,"lines":updates}).json()
    before=db_session.get(RequirementSnapshotItem,chicken[0]["snapshot_item_id"]);requirement=before.requirement_quantity;suggested=before.suggested_purchase_quantity
    response=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":draft["lock_version"]})
    assert response.status_code==200,response.text;assert response.json()["status"]=="confirmed"
    db_session.expire_all();item=db_session.get(RequirementSnapshotItem,chicken[0]["snapshot_item_id"])
    assert item.adjusted_quantity==sum((Decimal(value["adjusted_quantity"]) for value in updates),Decimal("0"))
    assert item.requirement_quantity==requirement and item.suggested_purchase_quantity==suggested
    assert client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":response.json()["lock_version"],"lines":[updates[0]]}).status_code==409


def test_stale_source_is_visible_and_blocks_confirmation(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    line=created["lines"][0]
    from app.domains.menus.models import MenuDish
    source=db_session.get(MenuDish,line["source_menu_dish_id"]);source.diner_count+=1;db_session.commit()
    detail=client.get(f"/api/v1/order-adjustments/{created['id']}",headers=headers).json()
    changed=next(item for item in detail["lines"] if item["id"]==line["id"])
    assert detail["stale"] is True and "DINER_COUNT_CHANGED" in changed["stale_reasons"]
    response=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":1})
    assert response.status_code==409 and response.json()["detail"]["code"]=="ADJUSTMENT_STALE"
    db_session.expire_all();sheet=db_session.get(OrderingAdjustmentSheet,created["id"]);assert sheet.status=="draft"


def test_create_failure_rolls_back_snapshot_and_sheet(client,db_session,monkeypatch):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    from app.domains.order_adjustments.repository import OrderingAdjustmentRepository
    original=OrderingAdjustmentRepository.add
    def fail(self,value):
        if isinstance(value,OrderingAdjustmentLine):raise RuntimeError("injected")
        return original(self,value)
    monkeypatch.setattr(OrderingAdjustmentRepository,"add",fail)
    assert create_sheet(client,headers,menu).status_code==400
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(RequirementSnapshot))==0
    assert db_session.scalar(select(func.count()).select_from(OrderingAdjustmentSheet))==0


def test_cancel_and_auth(client,db_session):
    assert client.get("/api/v1/order-adjustments/00000000-0000-0000-0000-000000000001").status_code==401
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    response=client.post(f"/api/v1/order-adjustments/{created['id']}/cancel",headers=headers,json={"lock_version":1})
    assert response.status_code==200 and response.json()["status"]=="cancelled"


def test_adjustment_owned_snapshot_cannot_bypass_draft_or_purchase_guard(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    line=created["lines"][0]
    direct=client.patch(f"/api/v1/requirement-snapshots/{created['baseline_snapshot_id']}/items/{line['snapshot_item_id']}",headers=headers,json={"adjusted_quantity":"999"})
    assert direct.status_code==409 and direct.json()["detail"]["code"]=="SNAPSHOT_LOCKED"
    purchase=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":created["baseline_snapshot_id"]})
    assert purchase.status_code==422 and purchase.json()["detail"]["blocking_issues"][0]["code"]=="ORDERING_ADJUSTMENT_NOT_CONFIRMED"
    confirmed=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":1})
    assert confirmed.status_code==200,confirmed.text
    purchase=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":created["baseline_snapshot_id"]})
    assert purchase.status_code==201,purchase.text


def test_recipe_source_replacement_and_new_line_are_stale_even_when_totals_can_match(client,db_session):
    headers=auth(client,db_session);menu,_,dishes,ingredients,_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    from app.domains.recipes.models import DishIngredient
    from app.domains.users.models import User
    old=db_session.scalar(select(DishIngredient).where(DishIngredient.dish_id==dishes[0]["id"],DishIngredient.ingredient_id==ingredients[0]["id"]));actor=db_session.scalar(select(User.id))
    quantity,unit,loss,sort_order=old.quantity,old.unit,old.loss_rate,old.sort_order
    db_session.delete(old);db_session.flush()
    db_session.add(DishIngredient(dish_id=dishes[0]["id"],ingredient_id=ingredients[0]["id"],quantity=quantity,unit=unit,loss_rate=loss,sort_order=sort_order,created_by=actor,updated_by=actor));db_session.commit()
    detail=client.get(f"/api/v1/order-adjustments/{created['id']}",headers=headers).json()
    assert detail["stale"] is True
    assert any("SOURCE_REMOVED" in line["stale_reasons"] for line in detail["lines"])
    assert any(warning["code"]=="NEW_SOURCE_LINE" for warning in detail["warnings"])
    response=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":1})
    assert response.status_code==409


def test_duplicate_create_is_resumable_and_cancelled_sheet_can_be_rebuilt(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    first=create_sheet(client,headers,menu);assert first.status_code==201,first.text
    duplicate=create_sheet(client,headers,menu)
    assert duplicate.status_code==409
    assert duplicate.json()["detail"]=={"code":"ADJUSTMENT_DRAFT_EXISTS","existing_sheet_id":first.json()["id"]}

    listed=client.get(f"/api/v1/order-adjustments?status=draft&menu_id={menu['id']}&start_date=2026-09-01&end_date=2026-09-01",headers=headers)
    assert listed.status_code==200,listed.text
    assert listed.json()["pagination"]["total"]==1
    assert listed.json()["items"][0]["id"]==first.json()["id"]

    cancelled=client.post(f"/api/v1/order-adjustments/{first.json()['id']}/cancel",headers=headers,json={"lock_version":1})
    assert cancelled.status_code==200,cancelled.text
    rebuilt=create_sheet(client,headers,menu);assert rebuilt.status_code==201,rebuilt.text
    assert rebuilt.json()["id"]!=first.json()["id"]
    assert rebuilt.json()["baseline_snapshot_id"]!=first.json()["baseline_snapshot_id"]
    assert rebuilt.json()["revision"]>first.json()["revision"]


def test_confirmed_identical_source_returns_existing_sheet(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    created=create_sheet(client,headers,menu).json()
    confirmed=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":1})
    assert confirmed.status_code==200,confirmed.text
    duplicate=create_sheet(client,headers,menu)
    assert duplicate.status_code==409
    assert duplicate.json()["detail"]=={"code":"ADJUSTMENT_ALREADY_CONFIRMED","existing_sheet_id":created["id"]}


def test_adjustment_snapshot_detail_is_locked_and_delete_is_guarded(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    snapshot_url=f"/api/v1/requirement-snapshots/{created['baseline_snapshot_id']}"
    draft=client.get(snapshot_url,headers=headers);assert draft.status_code==200,draft.text
    assert draft.json()["locked"] is True and draft.json()["purchase_ready"] is False
    assert draft.json()["ordering_adjustment_sheet_id"]==created["id"]
    assert draft.json()["ordering_adjustment_status"]=="draft"
    assert client.post(f"{snapshot_url}/hard-delete",headers=headers,json={"password":"correct horse battery staple"}).status_code==409

    confirmed=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":1})
    assert confirmed.status_code==200,confirmed.text
    ready=client.get(snapshot_url,headers=headers).json()
    assert ready["locked"] is True and ready["ordering_adjustment_status"]=="confirmed"
    assert not any(issue["code"]=="ORDERING_ADJUSTMENT_NOT_CONFIRMED" for issue in ready["blocking_issues"])


def test_lines_expose_deterministic_source_sort_metadata(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);body=create_sheet(client,headers,menu).json()
    keys=[
        (
            line["requirement_date"],line["meal_type_sort_order_snapshot"],
            line["menu_dish_sort_order_snapshot"],line["dish_ingredient_sort_order_snapshot"],
        )
        for line in body["lines"]
    ]
    assert keys==sorted(keys)
    assert all(isinstance(line["meal_type_sort_order_snapshot"],int) for line in body["lines"])
    assert all(isinstance(line["menu_dish_sort_order_snapshot"],int) for line in body["lines"])
    assert all(isinstance(line["dish_ingredient_sort_order_snapshot"],int) for line in body["lines"])


@pytest.mark.parametrize(
    ("change","reason"),
    [
        ("recipe_quantity","RECIPE_QUANTITY_CHANGED"),
        ("loss_rate","LOSS_RATE_CHANGED"),
        ("supplier","SUPPLIER_CHANGED"),
        ("purchase_unit","PURCHASING_DATA_CHANGED"),
        ("package_size","PURCHASING_DATA_CHANGED"),
        ("minimum_order_quantity","PURCHASING_DATA_CHANGED"),
        ("current_price","PURCHASING_DATA_CHANGED"),
        ("recipe_unit","UNIT_CHANGED"),
        ("base_unit","UNIT_CHANGED"),
    ],
)
def test_source_mutation_stale_reason_matrix(client,db_session,change,reason):
    headers=auth(client,db_session);menu,_,_,ingredients,suppliers=fixture(client,headers)
    created=create_sheet(client,headers,menu).json()
    ingredient=db_session.get(Ingredient,ingredients[0]["id"])
    recipe=db_session.scalar(select(DishIngredient).where(DishIngredient.ingredient_id==ingredient.id))
    if change=="recipe_quantity":recipe.quantity+=Decimal("0.1")
    elif change=="loss_rate":recipe.loss_rate+=Decimal("1")
    elif change=="supplier":ingredient.primary_supplier_id=uuid.UUID(suppliers[1]["id"])
    elif change=="purchase_unit":ingredient.purchase_unit="g"
    elif change=="package_size":ingredient.package_size+=Decimal("1")
    elif change=="minimum_order_quantity":ingredient.minimum_order_quantity+=Decimal("1")
    elif change=="current_price":ingredient.current_price+=Decimal("1")
    elif change=="recipe_unit":recipe.unit="kg"
    elif change=="base_unit":ingredient.unit="g"
    db_session.commit()
    detail=client.get(f"/api/v1/order-adjustments/{created['id']}",headers=headers)
    assert detail.status_code==200,detail.text
    reasons={value for line in detail.json()["lines"] for value in line["stale_reasons"]}
    assert detail.json()["stale"] is True and reason in reasons


def test_menu_dish_move_date_or_meal_is_stale(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    actor=db_session.scalar(select(User));source_line=created["lines"][0]
    meal=MenuMealType(menu_id=uuid.UUID(menu["id"]),name="移動測試餐",sort_order=99,is_active=True,created_by=actor.id,updated_by=actor.id)
    db_session.add(meal);db_session.flush()
    day=MenuDay(menu_id=uuid.UUID(menu["id"]),menu_date=date(2026,9,1),menu_meal_type_id=meal.id,created_by=actor.id,updated_by=actor.id)
    db_session.add(day);db_session.flush()
    db_session.get(MenuDish,source_line["source_menu_dish_id"]).menu_day_id=day.id;db_session.commit()
    detail=client.get(f"/api/v1/order-adjustments/{created['id']}",headers=headers).json()
    changed=next(line for line in detail["lines"] if line["id"]==source_line["id"])
    assert "MENU_DISH_MOVED" in changed["stale_reasons"]


def test_dish_replacement_with_retained_recipe_identity_is_stale(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    actor=db_session.scalar(select(User));source_line=created["lines"][0]
    source_menu_dish=db_session.get(MenuDish,source_line["source_menu_dish_id"]);old_dish=db_session.get(Dish,source_menu_dish.dish_id)
    replacement=Dish(code="REQ-REPLACED",name="替換菜色",category_id=old_dish.category_id,is_active=True,created_by=actor.id,updated_by=actor.id)
    db_session.add(replacement);db_session.flush()
    for recipe in db_session.scalars(select(DishIngredient).where(DishIngredient.dish_id==old_dish.id)):recipe.dish_id=replacement.id
    source_menu_dish.dish_id=replacement.id;db_session.commit()
    detail=client.get(f"/api/v1/order-adjustments/{created['id']}",headers=headers).json()
    changed=next(line for line in detail["lines"] if line["id"]==source_line["id"])
    assert "DISH_CHANGED" in changed["stale_reasons"]


def test_batch_patch_unknown_line_rolls_back_all_changes(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    first=created["lines"][0]
    response=client.patch(
        f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,
        json={"lock_version":1,"lines":[
            {"id":first["id"],"adjusted_quantity":"9"},
            {"id":str(uuid.uuid4()),"adjusted_quantity":"8"},
        ]},
    )
    assert response.status_code==404
    db_session.expire_all()
    line=db_session.get(OrderingAdjustmentLine,first["id"])
    sheet=db_session.get(OrderingAdjustmentSheet,created["id"])
    assert line.adjusted_quantity is None and sheet.lock_version==1
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="ordering_adjustment_lines_update"))==0


def test_concurrent_same_version_patch_only_one_succeeds(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    line_ids=[line["id"] for line in created["lines"][:2]]
    def patch(index):
        return client.patch(
            f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,
            json={"lock_version":1,"lines":[{"id":line_ids[index],"adjusted_quantity":str(index+1)}]},
        ).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:statuses=list(executor.map(patch,range(2)))
    assert sorted(statuses)==[200,409]


def test_concurrent_patch_and_confirm_same_version_only_one_succeeds(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    line_id=created["lines"][0]["id"]
    def patch():return client.patch(f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,json={"lock_version":1,"lines":[{"id":line_id,"adjusted_quantity":"2"}]}).status_code
    def confirm():return client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":1}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        first=executor.submit(patch);second=executor.submit(confirm);statuses=[first.result(),second.result()]
    assert sorted(statuses)==[200,409]


def test_concurrent_duplicate_create_has_one_active_draft(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    def create(_):return create_sheet(client,headers,menu)
    with ThreadPoolExecutor(max_workers=2) as executor:responses=list(executor.map(create,range(2)))
    assert sorted(response.status_code for response in responses)==[201,409]
    conflict=next(response for response in responses if response.status_code==409)
    assert conflict.json()["detail"]["code"]=="ADJUSTMENT_DRAFT_EXISTS"
    assert db_session.scalar(select(func.count()).select_from(OrderingAdjustmentSheet).where(OrderingAdjustmentSheet.status=="draft"))==1


def test_source_lock_blocks_concurrent_menu_dish_writer(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    criteria=RequirementCriteria(menu_ids=[menu["id"]],selected_dates=["2026-09-01"])
    locking=SessionLocal();writer=SessionLocal()
    try:
        RequirementRepository(locking).locked_source_rows(criteria)
        target=writer.scalar(select(MenuDish).join(MenuDay,MenuDay.id==MenuDish.menu_day_id).where(MenuDay.menu_date==criteria.selected_dates[0]))
        writer.execute(text("SET LOCAL lock_timeout = '250ms'"))
        target.diner_count+=1
        with pytest.raises(OperationalError):writer.flush()
        writer.rollback()
    finally:
        locking.rollback();locking.close();writer.close()


def test_confirm_converts_units_aggregates_once_and_preserves_zero(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    chicken_lines=[line for line in created["lines"] if line["ingredient_code_snapshot"]=="REQ-I1"]
    zero=client.patch(
        f"/api/v1/order-adjustments/{created['id']}/lines",headers=headers,
        json={"lock_version":1,"lines":[{"id":chicken_lines[0]["id"],"adjusted_quantity":"0"}]},
    ).json()
    item=db_session.get(RequirementSnapshotItem,chicken_lines[0]["snapshot_item_id"])
    item.purchase_unit_snapshot="g";db_session.commit()
    response=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":zero["lock_version"]})
    assert response.status_code==200,response.text
    db_session.expire_all();item=db_session.get(RequirementSnapshotItem,item.id)
    expected=sum((Decimal(line["system_quantity"])*Decimal("1000") for line in chicken_lines[1:]),Decimal("0"))
    assert item.adjusted_quantity==expected.quantize(Decimal("0.000001"))


def test_incompatible_confirm_rolls_back_items_sheet_and_audit(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);created=create_sheet(client,headers,menu).json()
    items=list(db_session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==created["baseline_snapshot_id"])))
    before={item.id:item.adjusted_quantity for item in items}
    items[-1].purchase_unit_snapshot="個";db_session.commit()
    response=client.post(f"/api/v1/order-adjustments/{created['id']}/confirm",headers=headers,json={"lock_version":1})
    assert response.status_code==422 and response.json()["detail"]["code"]=="SOURCE_TOTAL_MISMATCH"
    db_session.expire_all();sheet=db_session.get(OrderingAdjustmentSheet,created["id"])
    assert sheet.status=="draft" and sheet.confirmed_at is None
    assert {item.id:item.adjusted_quantity for item in db_session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==created["baseline_snapshot_id"]))}==before
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="ordering_adjustment_confirm"))==0


def test_multiline_rounding_boundary_does_not_create_false_total_mismatch(client,db_session):
    headers=auth(client,db_session);menu,_,dishes,ingredients,_=fixture(client,headers)
    salt_recipe=db_session.scalar(select(DishIngredient).where(DishIngredient.dish_id==dishes[0]["id"],DishIngredient.ingredient_id==ingredients[1]["id"]))
    salt_recipe.quantity=Decimal("0.000600");salt_recipe.loss_rate=Decimal("0")
    selected_day_ids=select(MenuDay.id).where(MenuDay.menu_id==menu["id"],MenuDay.menu_date==date(2026,9,1))
    for menu_dish in db_session.scalars(select(MenuDish).where(MenuDish.menu_day_id.in_(selected_day_ids),MenuDish.dish_id==dishes[0]["id"])):menu_dish.diner_count=1
    db_session.commit()
    created=create_sheet(client,headers,menu);assert created.status_code==201,created.text
    body=created.json();salt_lines=[line for line in body["lines"] if line["ingredient_code_snapshot"]=="REQ-I2"]
    assert len(salt_lines)==3 and {Decimal(line["system_quantity"]) for line in salt_lines}=={Decimal("0.000001")}
    snapshot_item=db_session.get(RequirementSnapshotItem,salt_lines[0]["snapshot_item_id"])
    assert snapshot_item.requirement_quantity==Decimal("0.000002")
    confirmed=client.post(f"/api/v1/order-adjustments/{body['id']}/confirm",headers=headers,json={"lock_version":1})
    assert confirmed.status_code==200,confirmed.text
    db_session.expire_all();snapshot_item=db_session.get(RequirementSnapshotItem,snapshot_item.id)
    assert snapshot_item.adjusted_quantity==Decimal("0.000003")


def test_list_is_authenticated_paginated_and_constant_query_count(client,db_session):
    assert client.get("/api/v1/order-adjustments").status_code==401
    headers=auth(client,db_session);menu,*_=fixture(client,headers);create_sheet(client,headers,menu)
    statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.get("/api/v1/order-adjustments?page=1&page_size=1",headers=headers)
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200 and response.json()["pagination"]["total"]==1
    assert response.json()["items"][0]["stale"] is None
    assert len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=3
