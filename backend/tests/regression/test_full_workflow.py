from decimal import Decimal

from tests.api.requirements.test_requirements_api import auth, fixture


def test_authenticated_master_data_to_confirmed_purchase_and_exports(client, db_session):
    headers = auth(client, db_session)
    menu, meal, dishes, ingredients, suppliers = fixture(client, headers)

    kitchen = client.post(
        "/api/v1/kitchen-operations/calculate",
        headers=headers,
        json={"menu_id": menu["id"]},
    )
    assert kitchen.status_code == 200
    kitchen_rows = kitchen.json()["ingredient_summary"]
    assert {row["ingredient_code"] for row in kitchen_rows} == {"REQ-I1", "REQ-I2", "REQ-I3"}

    requirements = client.post(
        "/api/v1/requirements/calculate",
        headers=headers,
        json={"menu_ids": [menu["id"]]},
    )
    assert requirements.status_code == 200
    requirement = requirements.json()
    chicken = next(row for row in requirement["rows"] if row["ingredient_code"] == "REQ-I1")
    assert Decimal(chicken["requirement_quantity"]) == Decimal("18.9")
    assert chicken["supplier_name"] == "供應商1"

    snapshot_response = client.post(
        "/api/v1/requirement-snapshots",
        headers=headers,
        json={"criteria": {"menu_ids": [menu["id"]]}},
    )
    assert snapshot_response.status_code == 201
    snapshot = snapshot_response.json()
    frozen_item = next(item for item in snapshot["items"] if item["ingredient_code_snapshot"] == "REQ-I1")
    assert snapshot["revision"] == 1 and snapshot["locked"] is False

    adjusted = client.patch(
        f"/api/v1/requirement-snapshots/{snapshot['id']}/items/{frozen_item['id']}",
        headers=headers,
        json={"adjusted_quantity": "31.5", "purchase_unit": "斤"},
    )
    assert adjusted.status_code == 200
    assert Decimal(adjusted.json()["adjusted_quantity"]) == Decimal("31.5")

    client.patch(
        f"/api/v1/ingredients/{ingredients[0]['id']}",
        headers=headers,
        json={"name": "主檔修改後名稱", "current_price": "999"},
    )
    frozen = client.get(f"/api/v1/requirement-snapshots/{snapshot['id']}", headers=headers).json()
    frozen_item = next(item for item in frozen["items"] if item["ingredient_code_snapshot"] == "REQ-I1")
    assert frozen_item["ingredient_name_snapshot"] == "雞肉"
    assert Decimal(frozen_item["unit_price_snapshot"]) == Decimal("200")

    purchase_response = client.post(
        "/api/v1/purchases",
        headers=headers,
        json={"snapshot_id": snapshot["id"], "notes": "完整流程測試"},
    )
    assert purchase_response.status_code == 201
    purchase = purchase_response.json()
    assert purchase["status"] == "draft" and len(purchase["orders"]) == 2
    assert {order["supplier_name_snapshot"] for order in purchase["orders"]} == {supplier["name"] for supplier in suppliers}

    locked = client.get(f"/api/v1/requirement-snapshots/{snapshot['id']}", headers=headers).json()
    assert locked["locked"] is True and locked["purchase_id"] == purchase["id"]
    assert client.patch(
        f"/api/v1/requirement-snapshots/{snapshot['id']}/items/{frozen_item['id']}",
        headers=headers,
        json={"adjusted_quantity": "1"},
    ).status_code == 409

    confirmed = client.post(f"/api/v1/purchases/{purchase['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"

    downloads = [
        client.post("/api/v1/exports/kitchen-operations/xlsx", headers=headers, json={"menu_id": menu["id"]}),
        client.post("/api/v1/exports/requirements/xlsx", headers=headers, json={"menu_ids": [menu["id"]]}),
        client.get(f"/api/v1/exports/requirement-snapshots/{snapshot['id']}/xlsx", headers=headers),
        client.get(f"/api/v1/exports/purchases/{purchase['id']}/xlsx", headers=headers),
        client.get(f"/api/v1/exports/purchases/{purchase['id']}/pdf", headers=headers),
    ]
    assert all(response.status_code == 200 for response in downloads), [response.status_code for response in downloads]
    assert all("attachment" in response.headers["content-disposition"] for response in downloads)
