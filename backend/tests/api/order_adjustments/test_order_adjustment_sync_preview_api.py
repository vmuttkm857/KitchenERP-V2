from decimal import Decimal

from sqlalchemy import func, select

from app.domains.audit.models import AuditLog
from app.domains.ingredients.models import Ingredient
from app.domains.menus.models import MenuDay, MenuDish
from app.domains.order_adjustments.models import OrderingAdjustmentLine, OrderingAdjustmentSheet
from app.domains.recipes.models import DishIngredient
from app.domains.snapshots.models import RequirementSnapshot, RequirementSnapshotItem
from app.domains.audit.service import AuditLogService
from tests.api.order_adjustments.test_order_adjustments_api import create_sheet
from tests.api.requirements.test_requirements_api import auth, fixture


def _new_dish(client, headers, *, code, name, ingredient_id, quantity="100", unit="g"):
    dish=client.post("/api/v1/dishes",headers=headers,json={"code":code,"name":name}).json()
    recipe=client.put(
        f"/api/v1/dishes/{dish['id']}/recipe",headers=headers,
        json={"items":[{"ingredient_id":ingredient_id,"quantity":quantity,"unit":unit,"loss_rate":"0","sort_order":1}]},
    )
    assert recipe.status_code==200,recipe.text
    return dish


def _editor_payload(aggregate, replacements):
    slots=[]
    for slot in aggregate["slots"]:
        dishes=[]
        for dish in slot["dishes"]:
            replacement_id=replacements.get(dish["id"])
            dishes.append({
                **({} if replacement_id else {"id":dish["id"]}),
                "dish_id":replacement_id or dish["dish_id"],
                "menu_meal_type_column_id":dish["menu_meal_type_column_id"],
                "diner_count":dish["diner_count"],"notes":dish["notes"],"sort_order":dish["sort_order"],
            })
        slots.append({
            "menu_day_id":slot["menu_day_id"],"menu_date":slot["menu_date"],
            "menu_meal_type_id":slot["menu_meal_type_id"],"notes":slot["notes"],"dishes":dishes,
        })
    return {"slots":slots}


def _sync(client,headers,sheet,preview,*,removed=None,resets=None):
    return client.post(
        f"/api/v1/order-adjustments/{sheet['id']}/sync",headers=headers,
        json={
            "lock_version":sheet["lock_version"],
            "expected_source_fingerprint":preview["preview_source_fingerprint"],
            "accepted_removed_source_line_keys":removed if removed is not None else [item["previous"]["source_line_key"] for item in preview["removed_ingredients"]],
            "reset_adjustment_line_ids":resets if resets is not None else [item["previous"]["line_id"] for item in preview["unit_conflicts"]],
        },
    )


def test_sync_preview_treats_dish_replacement_as_removed_and_added_without_reusing_adjustment(client,db_session):
    headers=auth(client,db_session);menu,_,_,ingredients,_=fixture(client,headers)
    sheet=create_sheet(client,headers,menu).json();old_line=sheet["lines"][0]
    saved=client.patch(
        f"/api/v1/order-adjustments/{sheet['id']}/lines",headers=headers,
        json={"lock_version":sheet["lock_version"],"lines":[{"id":old_line["id"],"adjusted_quantity":"25","adjusted_unit":"kg"}]},
    ).json()
    confirmed=client.post(f"/api/v1/order-adjustments/{sheet['id']}/confirm",headers=headers,json={"lock_version":saved["lock_version"]}).json()
    replacement=_new_dish(client,headers,code="SYNC-PORK",name="炸豬排",ingredient_id=ingredients[1]["id"],quantity="80")
    aggregate=client.get(f"/api/v1/menus/{menu['id']}/editor",headers=headers).json()
    target=next(dish for slot in aggregate["slots"] if slot["menu_date"]=="2026-09-01" for dish in slot["dishes"] if dish["id"]==old_line["source_menu_dish_id"])
    changed=client.put(f"/api/v1/menus/{menu['id']}/editor",headers=headers,json=_editor_payload(aggregate,{target["id"]:replacement["id"]}))
    assert changed.status_code==200,changed.text
    line_count=db_session.scalar(select(func.count()).select_from(OrderingAdjustmentLine).where(OrderingAdjustmentLine.sheet_id==sheet["id"]))
    audit_count=db_session.scalar(select(func.count()).select_from(AuditLog))

    response=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":confirmed["lock_version"]})
    assert response.status_code==200,response.text;body=response.json()
    assert body["status"]=="confirmed" and body["changed"] is True
    assert body["lock_version"]==confirmed["lock_version"]
    assert body["summary"]["removed_dishes"]==1 and body["summary"]["added_dishes"]==1
    assert body["summary"]["possible_dish_replacements"]==1
    replacement_hint=body["possible_dish_replacements"][0]
    assert replacement_hint["previous"]["source_dish_id"]==old_line["source_dish_id"]
    assert replacement_hint["current"]["source_dish_id"]==replacement["id"]
    assert replacement_hint["preserves_adjustment"] is False and replacement_hint["requires_confirmation"] is True
    removed=next(item for item in body["removed_ingredients"] if item["previous"]["source_line_key"]==old_line["source_line_key"])
    assert Decimal(removed["previous"]["adjusted_quantity"])==Decimal("25") and removed["previous"]["adjusted_unit"]=="kg"
    assert all(item["current"]["source_line_key"]!=old_line["source_line_key"] for item in body["added_ingredients"])

    db_session.expire_all();persisted=db_session.get(OrderingAdjustmentSheet,sheet["id"])
    assert persisted.status=="confirmed" and persisted.lock_version==confirmed["lock_version"]
    assert db_session.scalar(select(func.count()).select_from(OrderingAdjustmentLine).where(OrderingAdjustmentLine.sheet_id==sheet["id"]))==line_count
    assert db_session.scalar(select(func.count()).select_from(AuditLog))==audit_count


def test_sync_preview_detects_complete_selected_menu_replacement_deterministically(client,db_session):
    headers=auth(client,db_session);menu,_,_,ingredients,_=fixture(client,headers)
    sheet=create_sheet(client,headers,menu).json()
    replacements=[
        _new_dish(client,headers,code="SYNC-A",name="新主菜",ingredient_id=ingredients[0]["id"],quantity="120"),
        _new_dish(client,headers,code="SYNC-B",name="新副菜",ingredient_id=ingredients[2]["id"],quantity="0.3",unit="L"),
    ]
    aggregate=client.get(f"/api/v1/menus/{menu['id']}/editor",headers=headers).json()
    selected=[(dish,replacements[index%2]) for slot in aggregate["slots"] if slot["menu_date"]=="2026-09-01" for index,dish in enumerate(slot["dishes"])]
    mapping={dish["id"]:replacement["id"] for dish,replacement in selected}
    changed=client.put(f"/api/v1/menus/{menu['id']}/editor",headers=headers,json=_editor_payload(aggregate,mapping))
    assert changed.status_code==200,changed.text

    first=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":sheet["lock_version"]})
    second=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":sheet["lock_version"]})
    assert first.status_code==200,first.text
    assert second.status_code==200,second.text
    body=first.json()
    assert body==second.json()
    assert body["summary"]["removed_dishes"]==6
    assert body["summary"]["added_dishes"]==6
    assert body["summary"]["possible_dish_replacements"]==6
    assert {item["source_menu_dish_id"] for item in body["removed_dishes"]}.isdisjoint({item["source_menu_dish_id"] for item in body["added_dishes"]})
    assert all(item["preserves_adjustment"] is False for item in body["possible_dish_replacements"])
    applied=_sync(client,headers,sheet,body)
    assert applied.status_code==200,applied.text
    assert len(applied.json()["lines"])==len(body["added_ingredients"])
    assert not {line["source_menu_dish_id"] for line in applied.json()["lines"]}&{item["source_menu_dish_id"] for item in body["removed_dishes"]}


def test_sync_preview_reports_retained_identity_changes_and_rejects_invalid_state_or_version(client,db_session):
    headers=auth(client,db_session);menu,_,dishes,_,_=fixture(client,headers);sheet=create_sheet(client,headers,menu).json()
    line=sheet["lines"][0]
    renamed=client.patch(f"/api/v1/dishes/{line['source_dish_id']}",headers=headers,json={"name":"雞肉餐（新版名稱）"})
    assert renamed.status_code==200,renamed.text
    response=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":sheet["lock_version"]})
    assert response.status_code==200,response.text
    change=next(item for item in response.json()["line_changes"] if item["source_line_key"]==line["source_line_key"])
    assert "dish_name_changed" in change["change_types"] and change["preserves_adjustment"] is True
    assert change["previous"]["source_dish_id"]==change["current"]["source_dish_id"]==dishes[0]["id"]
    applied=_sync(client,headers,sheet,response.json())
    assert applied.status_code==200,applied.text
    assert next(item for item in applied.json()["lines"] if item["id"]==line["id"])["dish_name_snapshot"]=="雞肉餐（新版名稱）"

    old=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":99})
    assert old.status_code==409 and old.json()["detail"]["code"]=="LOCK_VERSION_CONFLICT"
    cancelled=client.post(f"/api/v1/order-adjustments/{sheet['id']}/cancel",headers=headers,json={"lock_version":applied.json()["lock_version"]}).json()
    invalid=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":cancelled["lock_version"]})
    assert invalid.status_code==409 and invalid.json()["detail"]["code"]=="INVALID_ADJUSTMENT_STATUS"


def test_sync_apply_replaces_dish_without_transferring_adjustment_and_reconciles_baseline(client,db_session):
    headers=auth(client,db_session);menu,_,_,ingredients,_=fixture(client,headers)
    sheet=create_sheet(client,headers,menu).json();old=sheet["lines"][0]
    unaffected=next(line for line in sheet["lines"] if line["source_menu_dish_id"]!=old["source_menu_dish_id"])
    saved=client.patch(
        f"/api/v1/order-adjustments/{sheet['id']}/lines",headers=headers,
        json={"lock_version":sheet["lock_version"],"lines":[
            {"id":old["id"],"adjusted_quantity":"25","adjusted_unit":"kg"},
            {"id":unaffected["id"],"adjusted_quantity":"3","adjusted_unit":"kg"},
        ]},
    ).json()
    confirmed=client.post(f"/api/v1/order-adjustments/{sheet['id']}/confirm",headers=headers,json={"lock_version":saved["lock_version"]}).json()
    standard=client.post("/api/v1/requirement-snapshots",headers=headers,json={"criteria":{"menu_ids":[menu["id"]],"selected_dates":["2026-09-01"],"ordering_adjustment_sheet_ids":[sheet["id"]]}}).json()
    standard_values={item["id"]:item["requirement_quantity"] for item in standard["items"]}
    replacement=_new_dish(client,headers,code="APPLY-PORK",name="炸豬排",ingredient_id=ingredients[1]["id"],quantity="80")
    aggregate=client.get(f"/api/v1/menus/{menu['id']}/editor",headers=headers).json()
    changed=client.put(f"/api/v1/menus/{menu['id']}/editor",headers=headers,json=_editor_payload(aggregate,{old["source_menu_dish_id"]:replacement["id"]}))
    assert changed.status_code==200,changed.text
    reopened=client.post(f"/api/v1/order-adjustments/{sheet['id']}/reopen",headers=headers,json={"lock_version":confirmed["lock_version"]})
    assert reopened.status_code==200 and reopened.json()["stale"] is True
    draft=reopened.json();preview=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":draft["lock_version"]}).json()
    rejected=_sync(client,headers,draft,preview,removed=[])
    assert rejected.status_code==409 and rejected.json()["detail"]["code"]=="SYNC_REMOVALS_NOT_ACCEPTED"
    applied=_sync(client,headers,draft,preview)
    assert applied.status_code==200,applied.text;body=applied.json()
    assert body["stale"] is False and body["source_fingerprint"]==preview["preview_source_fingerprint"]
    assert all(line["id"]!=old["id"] for line in body["lines"])
    added=next(line for line in body["lines"] if line["source_dish_id"]==replacement["id"])
    assert added["adjusted_quantity"] is None and added["adjusted_unit"] is None and added["review_required"] is True
    retained=next(line for line in body["lines"] if line["id"]==unaffected["id"])
    assert retained["adjusted_quantity"]=="3.000000" and retained["adjusted_unit"]=="kg"
    item_ids={str(item.id) for item in db_session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==body["baseline_snapshot_id"]))}
    assert {line["snapshot_item_id"] for line in body["lines"]}.issubset(item_ids)
    requirements=client.post("/api/v1/requirements/calculate",headers=headers,json={"menu_ids":[menu["id"]],"selected_dates":["2026-09-01"],"ordering_adjustment_sheet_ids":[sheet["id"]]})
    assert requirements.status_code==200,requirements.text
    current_standard=client.get(f"/api/v1/requirement-snapshots/{standard['id']}",headers=headers).json()
    assert {item["id"]:item["requirement_quantity"] for item in current_standard["items"]}==standard_values
    no_change=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":body["lock_version"]}).json()
    repeated=_sync(client,headers,body,no_change)
    assert repeated.status_code==200 and repeated.json()["lock_version"]==body["lock_version"]
    assert len(repeated.json()["lines"])==len(body["lines"])
    reconfirmed=client.post(f"/api/v1/order-adjustments/{sheet['id']}/confirm",headers=headers,json={"lock_version":body["lock_version"]})
    assert reconfirmed.status_code==200,reconfirmed.text
    baseline_items=list(db_session.scalars(select(RequirementSnapshotItem).where(RequirementSnapshotItem.snapshot_id==body["baseline_snapshot_id"])))
    assert all(item.adjusted_quantity is not None for item in baseline_items)
    preview_again=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":reconfirmed.json()["lock_version"]}).json()
    assert preview_again["changed"] is False


def test_sync_apply_preserves_retained_line_and_updates_recipe_reference_data(client,db_session):
    headers=auth(client,db_session);menu,_,_,ingredients,_=fixture(client,headers);sheet=create_sheet(client,headers,menu).json()
    target=sheet["lines"][0]
    saved=client.patch(f"/api/v1/order-adjustments/{sheet['id']}/lines",headers=headers,json={"lock_version":sheet["lock_version"],"lines":[{"id":target["id"],"adjusted_quantity":"18","adjusted_unit":"kg"}]}).json()
    recipe=db_session.get(DishIngredient,target["source_dish_ingredient_id"]);recipe.quantity*=2;recipe.loss_rate+=1
    ingredient=db_session.get(Ingredient,target["source_ingredient_id"]);ingredient.name="更新食材名稱"
    removed=next(line for line in sheet["lines"] if line["source_menu_dish_id"]==target["source_menu_dish_id"] and line["id"]!=target["id"])
    db_session.delete(db_session.get(DishIngredient,removed["source_dish_ingredient_id"]))
    extra=DishIngredient(dish_id=target["source_dish_id"],ingredient_id=ingredients[-1]["id"],quantity=1,unit="g",loss_rate=0,sort_order=99,created_by=recipe.created_by,updated_by=recipe.updated_by)
    db_session.add(extra);db_session.commit()
    preview=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":saved["lock_version"]}).json()
    applied=_sync(client,headers,saved,preview)
    assert applied.status_code==200,applied.text;body=applied.json()
    retained=next(line for line in body["lines"] if line["id"]==target["id"])
    assert retained["adjusted_quantity"]=="18.000000" and retained["adjusted_unit"]=="kg"
    assert retained["ingredient_name_snapshot"]=="更新食材名稱"
    assert retained["quantity_per_person_snapshot"]!=target["quantity_per_person_snapshot"]
    added=next(line for line in body["lines"] if line["source_dish_ingredient_id"]==str(extra.id))
    assert added["adjusted_quantity"] is None and added["review_required"] is True
    assert all(line["id"]!=removed["id"] for line in body["lines"])


def test_sync_apply_rejects_changed_preview_and_stale_mutations(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);sheet=create_sheet(client,headers,menu).json();target=sheet["lines"][0]
    source=db_session.get(MenuDish,target["source_menu_dish_id"]);source.diner_count+=1;db_session.commit()
    preview=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":sheet["lock_version"]}).json()
    update=client.patch(f"/api/v1/order-adjustments/{sheet['id']}/lines",headers=headers,json={"lock_version":sheet["lock_version"],"lines":[{"id":target["id"],"adjusted_quantity":"2"}]})
    assert update.status_code==409 and update.json()["detail"]["code"]=="ADJUSTMENT_STALE"
    conversion=client.post(f"/api/v1/order-adjustments/{sheet['id']}/convert-units",headers=headers,json={"lock_version":sheet["lock_version"],"conversion":"g_to_kg"})
    assert conversion.status_code==409 and conversion.json()["detail"]["code"]=="ADJUSTMENT_STALE"
    source.diner_count+=1;db_session.commit()
    rejected=_sync(client,headers,sheet,preview)
    assert rejected.status_code==409 and rejected.json()["detail"]["code"]=="SYNC_SOURCE_CHANGED"
    db_session.expire_all();persisted=db_session.get(OrderingAdjustmentSheet,sheet["id"])
    assert persisted.lock_version==sheet["lock_version"] and persisted.source_fingerprint==sheet["source_fingerprint"]


def test_sync_apply_requires_explicit_reset_for_incompatible_adjustment_unit(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);sheet=create_sheet(client,headers,menu).json();target=sheet["lines"][0]
    saved=client.patch(f"/api/v1/order-adjustments/{sheet['id']}/lines",headers=headers,json={"lock_version":sheet["lock_version"],"lines":[{"id":target["id"],"adjusted_quantity":"2","adjusted_unit":"kg"}]}).json()
    ingredient=db_session.get(Ingredient,target["source_ingredient_id"]);ingredient.unit="L"
    recipe=db_session.get(DishIngredient,target["source_dish_ingredient_id"]);recipe.unit="L"
    db_session.commit()
    preview=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":saved["lock_version"]}).json()
    assert [item["previous"]["line_id"] for item in preview["unit_conflicts"]]==[target["id"]]
    rejected=_sync(client,headers,saved,preview,resets=[])
    assert rejected.status_code==409 and rejected.json()["detail"]["code"]=="SYNC_UNIT_CONFLICT"
    applied=_sync(client,headers,saved,preview)
    assert applied.status_code==200,applied.text
    reset=next(line for line in applied.json()["lines"] if line["id"]==target["id"])
    assert reset["adjusted_quantity"] is None and reset["adjusted_unit"] is None and reset["review_required"] is True


def test_sync_apply_preserves_identity_when_menu_dish_moves_date_and_meal(client,db_session):
    headers=auth(client,db_session);menu,_,_,_,_=fixture(client,headers)
    sheet=client.post("/api/v1/order-adjustments",headers=headers,json={"criteria":{"menu_ids":[menu["id"]],"start_date":"2026-09-01","end_date":"2026-09-02"}}).json()
    target=sheet["lines"][0]
    saved=client.patch(f"/api/v1/order-adjustments/{sheet['id']}/lines",headers=headers,json={"lock_version":sheet["lock_version"],"lines":[{"id":target["id"],"adjusted_quantity":"7","adjusted_unit":"kg"}]}).json()
    meal=client.post(f"/api/v1/menus/{menu['id']}/meal-types",headers=headers,json={"name":"新增餐別","sort_order":9}).json()
    source=db_session.get(MenuDish,target["source_menu_dish_id"]);old_day=db_session.get(MenuDay,source.menu_day_id)
    new_day=MenuDay(menu_id=old_day.menu_id,menu_date=old_day.menu_date.replace(day=2),menu_meal_type_id=meal["id"],created_by=old_day.created_by,updated_by=old_day.updated_by)
    db_session.add(new_day);db_session.flush();source.menu_day_id=new_day.id;db_session.commit()
    preview=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":saved["lock_version"]}).json()
    change=next(item for item in preview["line_changes"] if item["previous"]["line_id"]==target["id"])
    assert "menu_position_changed" in change["change_types"] and change["preserves_adjustment"] is True
    applied=_sync(client,headers,saved,preview)
    assert applied.status_code==200,applied.text
    moved=next(line for line in applied.json()["lines"] if line["id"]==target["id"])
    assert moved["requirement_date"]=="2026-09-02" and moved["source_meal_type_id"]==meal["id"]
    assert moved["adjusted_quantity"]=="7.000000" and moved["adjusted_unit"]=="kg"


def test_sync_apply_rolls_back_all_changes_when_audit_fails(client,db_session,monkeypatch):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);sheet=create_sheet(client,headers,menu).json();target=sheet["lines"][0]
    source=db_session.get(MenuDish,target["source_menu_dish_id"]);source.diner_count+=1;db_session.commit()
    preview=client.post(f"/api/v1/order-adjustments/{sheet['id']}/sync-preview",headers=headers,json={"lock_version":sheet["lock_version"]}).json()
    baseline=db_session.get(RequirementSnapshot,sheet["baseline_snapshot_id"]);old_content=baseline.content_fingerprint
    old_quantity=db_session.get(OrderingAdjustmentLine,target["id"]).system_quantity
    monkeypatch.setattr(AuditLogService,"record",lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError("audit failed")))
    failed=_sync(client,headers,sheet,preview)
    assert failed.status_code==400
    db_session.expire_all();persisted=db_session.get(OrderingAdjustmentSheet,sheet["id"])
    assert persisted.lock_version==sheet["lock_version"] and persisted.source_fingerprint==sheet["source_fingerprint"]
    assert db_session.get(OrderingAdjustmentLine,target["id"]).system_quantity==old_quantity
    assert db_session.get(RequirementSnapshot,sheet["baseline_snapshot_id"]).content_fingerprint==old_content


def test_sync_apply_rejects_another_draft_with_same_live_fingerprint(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers);first=create_sheet(client,headers,menu).json()
    confirmed=client.post(f"/api/v1/order-adjustments/{first['id']}/confirm",headers=headers,json={"lock_version":first["lock_version"]}).json()
    source=db_session.get(MenuDish,first["lines"][0]["source_menu_dish_id"]);source.diner_count+=1;db_session.commit()
    second=create_sheet(client,headers,menu)
    assert second.status_code==201,second.text;second=second.json()
    reopened=client.post(f"/api/v1/order-adjustments/{first['id']}/reopen",headers=headers,json={"lock_version":confirmed["lock_version"]}).json()
    preview=client.post(f"/api/v1/order-adjustments/{first['id']}/sync-preview",headers=headers,json={"lock_version":reopened["lock_version"]}).json()
    conflict=_sync(client,headers,reopened,preview)
    assert conflict.status_code==409
    assert conflict.json()["detail"]=={"code":"ADJUSTMENT_DRAFT_EXISTS","existing_sheet_id":second["id"]}
    db_session.expire_all();persisted=db_session.get(OrderingAdjustmentSheet,first["id"])
    assert persisted.source_fingerprint==first["source_fingerprint"] and persisted.lock_version==reopened["lock_version"]
