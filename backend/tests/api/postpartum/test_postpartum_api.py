from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService
from app.domains.postpartum.service import PostpartumService
from app.domains.postpartum.models import PostpartumRoomHistory
from app.domains.postpartum.schemas import RoomChangeCreate

PASSWORD = "correct horse battery staple"


def auth(client, session):
    user = UserService(session).create_user(CreateUserCommand(username="postpartum_admin", password=PASSWORD, display_name="Postpartum Admin", role="admin"))
    token = client.post("/api/v1/auth/login", json={"username": user.username, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def payload(number="0012"):
    return {"case_number":number,"name":"王小美","current_room":"A-101","delivery_type":"cesarean","delivery_date":"2026-09-01","service_start_date":"2026-09-02","service_start_meal":"lunch","service_end_date":"2026-09-28","service_end_meal":"dinner","status":"active","preparation_mode":"no_rice_wine_sesame","service_note":"少鹽"}


def test_case_crud_room_history_pause_and_non_unique_number(client, db_session):
    headers=auth(client,db_session)
    first=client.post("/api/v1/postpartum/cases",headers=headers,json=payload())
    assert first.status_code==201,first.text
    value=first.json(); assert value["case_number"]=="0012" and value["current_room"]=="A-101"
    assert value["delivery_type"]=="cesarean" and value["preparation_mode"]=="no_rice_wine_sesame"
    assert value["created_by"]==value["updated_by"]
    second=client.post("/api/v1/postpartum/cases",headers=headers,json={**payload(),"name":"陳小姐"})
    assert second.status_code==201
    listing=client.get("/api/v1/postpartum/cases?search=0012&status=active",headers=headers).json()
    assert listing["pagination"]["total"]==2
    assert len(client.get("/api/v1/postpartum/cases?page=2&page_size=1",headers=headers).json()["items"])==1
    updated_case=client.patch(f"/api/v1/postpartum/cases/{value['id']}",headers=headers,json={"name":"王小玉","status":"paused","preparation_mode":"herbal"})
    assert updated_case.status_code==200 and updated_case.json()["name"]=="王小玉"
    detail=client.get(f"/api/v1/postpartum/cases/{value['id']}",headers=headers).json()
    assert [(x["room"],x["effective_meal"]) for x in detail["room_history"]]==[("A-101","lunch")]
    changed=client.post(f"/api/v1/postpartum/cases/{value['id']}/room-changes",headers=headers,json={"room":"B-202","effective_date":"2026-09-05","effective_meal":"breakfast"})
    assert changed.status_code==201
    assert client.get(f"/api/v1/postpartum/cases/{value['id']}",headers=headers).json()["case"]["current_room"]=="B-202"
    assert next(item for item in client.get("/api/v1/postpartum/cases",headers=headers).json()["items"] if item["id"]==value["id"])["current_room"]=="B-202"
    invalid=client.post(f"/api/v1/postpartum/cases/{value['id']}/pauses",headers=headers,json={"start_date":"2026-09-08","start_meal":"dinner","end_date":"2026-09-08","end_meal":"breakfast"})
    assert invalid.status_code==422
    pause=client.post(f"/api/v1/postpartum/cases/{value['id']}/pauses",headers=headers,json={"start_date":"2026-09-08","start_meal":"lunch","end_date":"2026-09-09","end_meal":"breakfast","note":"返院"})
    assert pause.status_code==201,pause.text
    updated=client.patch(f"/api/v1/postpartum/cases/{value['id']}/pauses/{pause.json()['id']}",headers=headers,json={"note":"門診"})
    assert updated.status_code==200 and updated.json()["note"]=="門診"
    assert client.delete(f"/api/v1/postpartum/cases/{value['id']}/pauses/{pause.json()['id']}",headers=headers).status_code==204
    assert client.post(f"/api/v1/postpartum/cases/{value['id']}/deactivate",headers=headers).json()["is_active"] is False


def test_past_today_and_future_room_changes_are_immediate_and_repeatable(client, db_session):
    headers=auth(client,db_session)
    value=client.post("/api/v1/postpartum/cases",headers=headers,json=payload("0088")).json()
    today=datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    first={"room":"503","effective_date":today,"effective_meal":"lunch"}
    second={"room":"505","effective_date":today,"effective_meal":"lunch"}
    assert client.post(f"/api/v1/postpartum/cases/{value['id']}/room-changes",headers=headers,json=first).status_code==201
    assert client.post(f"/api/v1/postpartum/cases/{value['id']}/room-changes",headers=headers,json=second).status_code==201
    assert client.post(f"/api/v1/postpartum/cases/{value['id']}/room-changes",headers=headers,json={"room":"507","effective_date":today,"effective_meal":"dinner"}).status_code==201
    past=client.post(f"/api/v1/postpartum/cases/{value['id']}/room-changes",headers=headers,json={"room":"509","effective_date":"2025-01-01","effective_meal":"breakfast"})
    assert past.status_code==201

    detail=client.get(f"/api/v1/postpartum/cases/{value['id']}",headers=headers).json()
    assert detail["case"]["current_room"]=="509"
    same_meal=[item["room"] for item in detail["room_history"] if item["effective_date"]==today and item["effective_meal"]=="lunch"]
    assert same_meal==["503","505"]
    listing=client.get("/api/v1/postpartum/cases",headers=headers).json()
    assert next(item for item in listing["items"] if item["id"]==value["id"])["current_room"]=="509"

    future=client.post(f"/api/v1/postpartum/cases/{value['id']}/room-changes",headers=headers,json={"room":"999","effective_date":"2099-01-01","effective_meal":"breakfast"})
    assert future.status_code==201
    detail=client.get(f"/api/v1/postpartum/cases/{value['id']}",headers=headers).json()
    assert detail["case"]["current_room"]=="999"
    assert any(item["room"]=="999" and item["effective_date"]=="2099-01-01" for item in detail["room_history"])
    assert next(item for item in client.get("/api/v1/postpartum/cases",headers=headers).json()["items"] if item["id"]==value["id"])["current_room"]=="999"


def test_room_change_is_atomic_and_get_requests_do_not_recalculate_room(client, db_session, monkeypatch):
    headers=auth(client,db_session)
    value=client.post("/api/v1/postpartum/cases",headers=headers,json=payload("0089")).json()
    model=PostpartumService(db_session).case(value["id"])
    model.current_room="MANUAL-CACHE"
    db_session.commit()
    assert client.get(f"/api/v1/postpartum/cases/{value['id']}",headers=headers).json()["case"]["current_room"]=="MANUAL-CACHE"
    assert next(item for item in client.get("/api/v1/postpartum/cases",headers=headers).json()["items"] if item["id"]==value["id"])["current_room"]=="MANUAL-CACHE"

    service=PostpartumService(db_session)
    before_count=db_session.scalar(select(func.count()).select_from(PostpartumRoomHistory).where(PostpartumRoomHistory.case_id==value["id"]))
    def fail_audit(**_kwargs): raise RuntimeError("audit failure")
    monkeypatch.setattr(service.audit,"record",fail_audit)
    with pytest.raises(RuntimeError):
        service.change_room(value["id"],RoomChangeCreate(room="BROKEN",effective_date=date(2026,9,8),effective_meal="dinner"),value["created_by"])
    db_session.expire_all()
    assert PostpartumService(db_session).case(value["id"]).current_room=="MANUAL-CACHE"
    assert db_session.scalar(select(func.count()).select_from(PostpartumRoomHistory).where(PostpartumRoomHistory.case_id==value["id"]))==before_count


def test_case_validation_and_authentication(client, db_session):
    headers=auth(client,db_session)
    assert client.get("/api/v1/postpartum/cases").status_code==401
    bad={**payload(),"service_start_date":"2026-09-10","service_start_meal":"dinner","service_end_date":"2026-09-10","service_end_meal":"breakfast"}
    assert client.post("/api/v1/postpartum/cases",headers=headers,json=bad).status_code==422
    missing_pair={**payload(),"service_end_meal":None}
    assert client.post("/api/v1/postpartum/cases",headers=headers,json=missing_pair).status_code==422
    assert client.post("/api/v1/postpartum/cases",headers=headers,json={**payload(),"delivery_type":"unknown"}).status_code==422
    assert client.post("/api/v1/postpartum/cases",headers=headers,json={**payload(),"preparation_mode":"unknown"}).status_code==422


def test_service_end_is_optional_but_date_and_meal_are_a_pair(client, db_session):
    headers=auth(client,db_session)
    open_ended={**payload("0070"),"service_end_date":None,"service_end_meal":None}
    response=client.post("/api/v1/postpartum/cases",headers=headers,json=open_ended)
    assert response.status_code==201,response.text
    assert response.json()["service_end_date"] is None
    assert response.json()["service_end_meal"] is None

    missing_meal={**payload("0071"),"service_end_meal":None}
    assert client.post("/api/v1/postpartum/cases",headers=headers,json=missing_meal).status_code==422
    missing_date={**payload("0072"),"service_end_date":None}
    assert client.post("/api/v1/postpartum/cases",headers=headers,json=missing_date).status_code==422

    historical={**payload("0073"),"delivery_date":"2025-01-01","service_start_date":"2025-01-02","service_start_meal":"breakfast","service_end_date":"2025-01-03","service_end_meal":"lunch"}
    assert client.post("/api/v1/postpartum/cases",headers=headers,json=historical).status_code==201
    reversed_range={**historical,"case_number":"0074","service_end_date":"2025-01-01"}
    assert client.post("/api/v1/postpartum/cases",headers=headers,json=reversed_range).status_code==422


@pytest.mark.parametrize("meal", ["morning_snack", "afternoon_snack", "evening_snack"])
def test_case_create_accepts_each_snack_meal(client, db_session, meal):
    headers=auth(client,db_session)
    value={**payload(f"snack-{meal}"),"service_start_meal":meal,"service_end_meal":"evening_snack"}
    response=client.post("/api/v1/postpartum/cases",headers=headers,json=value)
    assert response.status_code==201,response.text
    assert response.json()["service_start_meal"]==meal


def test_case_update_pause_and_room_history_accept_six_meals(client, db_session):
    headers=auth(client,db_session)
    created=client.post("/api/v1/postpartum/cases",headers=headers,json=payload("six-meals")).json()
    updated=client.patch(
        f"/api/v1/postpartum/cases/{created['id']}",headers=headers,
        json={"service_start_meal":"morning_snack","service_end_meal":"evening_snack"},
    )
    assert updated.status_code==200,updated.text
    assert updated.json()["service_start_meal"]=="morning_snack"
    assert updated.json()["service_end_meal"]=="evening_snack"

    pause=client.post(
        f"/api/v1/postpartum/cases/{created['id']}/pauses",headers=headers,
        json={"start_date":"2026-09-12","start_meal":"afternoon_snack",
              "end_date":"2026-09-13","end_meal":"morning_snack"},
    )
    assert pause.status_code==201,pause.text
    assert pause.json()["start_meal"]=="afternoon_snack"
    assert pause.json()["end_meal"]=="morning_snack"

    room=client.post(
        f"/api/v1/postpartum/cases/{created['id']}/room-changes",headers=headers,
        json={"room":"S-601","effective_date":"2026-09-12","effective_meal":"evening_snack"},
    )
    assert room.status_code==201,room.text
    detail=client.get(f"/api/v1/postpartum/cases/{created['id']}",headers=headers).json()
    assert detail["room_history"][-1]["effective_meal"]=="evening_snack"


def test_invalid_meal_remains_rejected(client, db_session):
    headers=auth(client,db_session)
    response=client.post(
        "/api/v1/postpartum/cases",headers=headers,
        json={**payload("invalid-meal"),"service_start_meal":"brunch"},
    )
    assert response.status_code==422
