"""Real PostgreSQL API/transaction tests; existing disposable-DB guard is mandatory."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from threading import Barrier
from uuid import UUID,uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session

from app.domains.snapshots.models import RequirementSnapshot,RequirementSnapshotItem
from app.domains.snapshots.service import SnapshotService
from app.domains.snapshots.exceptions import DuplicateSnapshotError
from app.domains.requirements.schemas import RequirementCriteria
from app.domains.purchases.models import PurchaseBatch
from app.domains.users.models import User
from app.domains.ingredients.models import Ingredient
from tests.api.requirements.test_requirements_api import auth,fixture
from tests.snapshot_comparison import assert_snapshot_unchanged


@pytest.fixture
def revision_data(client,db_session):
    headers=auth(client,db_session);menu,*_=fixture(client,headers)
    criteria={"menu_ids":[menu["id"]]}
    result=client.post("/api/v1/requirements/calculate",headers=headers,json=criteria)
    assert result.status_code==200,result.text
    payload={"criteria":criteria,"expected_result_fingerprint":result.json()["result_fingerprint"]}
    base=client.post("/api/v1/requirement-snapshots",headers=headers,json=payload)
    assert base.status_code==201,base.text
    request={**payload,"base_snapshot_id":base.json()["id"],"revision_intent_id":str(uuid4())}
    return headers,base.json(),request


def test_r2_r3_retry_normal_dedup_history_purchase_and_excel(client,db_session,revision_data):
    headers,base,request=revision_data
    purchase=client.post("/api/v1/purchases",headers=headers,json={"snapshot_id":base["id"]})
    assert purchase.status_code==201,purchase.text
    old=deepcopy(client.get(f"/api/v1/requirement-snapshots/{base['id']}",headers=headers).json())
    preview=client.get(f"/api/v1/requirement-snapshots/{base['id']}/revision-context",headers=headers)
    assert preview.status_code==200 and preview.json()["next_revision"]==2
    r2=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json=request)
    assert r2.status_code==201,r2.text
    retry=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json=request)
    assert retry.status_code==200 and retry.json()["id"]==r2.json()["id"]
    r3=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json={**request,"revision_intent_id":str(uuid4())})
    assert r3.status_code==201 and r3.json()["revision"]==3
    assert len({base["id"],r2.json()["id"],r3.json()["id"]})==3
    ordinary=client.post("/api/v1/requirement-snapshots",headers=headers,json={k:v for k,v in request.items() if k in ("criteria","expected_result_fingerprint")})
    assert ordinary.status_code==409 and ordinary.json()["detail"]["existing_snapshot_id"]==r3.json()["id"]
    assert_snapshot_unchanged(old,client.get(f"/api/v1/requirement-snapshots/{base['id']}",headers=headers).json())
    assert db_session.scalar(select(func.count()).select_from(PurchaseBatch))==1
    assert db_session.scalar(select(PurchaseBatch.source_snapshot_id))==UUID(base["id"])
    for item in r2.json()["items"]:
        assert all(source["source_order"]["version"]==1 for source in item["source_summary"])
    supplier=next(item["supplier_id"] for item in r2.json()["items"])
    def xlsx(snapshot):
        response=client.get(f"/api/v1/exports/requirement-snapshots/{snapshot}/suppliers/{supplier}/weekly-order.xlsx?breakfast_previous_day=true",headers=headers)
        assert response.status_code==200,response.text
        book=load_workbook(BytesIO(response.content))
        return [(sheet.title,list(sheet.values)) for sheet in book]
    assert xlsx(base["id"])==xlsx(r2.json()["id"])


def test_reused_intent_changed_payload_and_stale_new_intent_are_rejected(client,db_session,revision_data):
    headers,base,request=revision_data
    created=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json=request)
    assert created.status_code==201
    changed=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json={**request,"expected_result_fingerprint":"0"*64})
    assert changed.status_code==409 and changed.json()["detail"]["code"]=="SNAPSHOT_REVISION_INTENT_REUSED"
    stale=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json={**request,"revision_intent_id":str(uuid4()),"expected_result_fingerprint":"0"*64})
    assert stale.status_code==409 and stale.json()["detail"]["code"]=="SNAPSHOT_RESULT_CHANGED"
    assert db_session.scalar(select(func.count()).select_from(RequirementSnapshot))==2
    assert client.post("/api/v1/requirement-snapshots/new-revision",json=request).status_code==401


def test_write_failure_rolls_back_real_postgresql_header_items_and_intent(client,db_session,revision_data,monkeypatch):
    from app.domains.snapshots.repository import SnapshotRepository
    headers,base,request=revision_data
    counts=lambda: (db_session.scalar(select(func.count()).select_from(RequirementSnapshot)),
                    db_session.scalar(select(func.count()).select_from(RequirementSnapshotItem)))
    before=counts();db_session.commit()
    original=SnapshotRepository.add
    def fail_after_item_write(self,value):
        original(self,value)
        if isinstance(value,RequirementSnapshotItem):
            self.session.flush()
            raise RuntimeError("injected after real item insert")
    with monkeypatch.context() as patch:
        patch.setattr(SnapshotRepository,"add",fail_after_item_write)
        response=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json=request)
    assert response.status_code==400
    assert counts()==before
    assert db_session.scalar(select(RequirementSnapshot.id).where(RequirementSnapshot.revision_intent_id==UUID(request["revision_intent_id"]))) is None
    response=client.post("/api/v1/requirement-snapshots/new-revision",headers=headers,json=request)
    assert response.status_code==201 and response.json()["revision"]==2


@pytest.mark.parametrize("mode", ["different_intents","same_intent","ordinary_and_explicit"])
def test_real_postgresql_concurrent_creation(migrated_test_database,client,db_session,revision_data,mode):
    headers,base,request=revision_data
    if mode=="ordinary_and_explicit":
        ingredient=db_session.scalar(select(Ingredient).where(Ingredient.code=="REQ-I1"))
        ingredient.current_price+=1;db_session.commit()
        viewed=client.post("/api/v1/requirements/calculate",headers=headers,json=request["criteria"])
        assert viewed.status_code==200
        request={**request,"expected_result_fingerprint":viewed.json()["result_fingerprint"]}
    actor=db_session.scalar(select(User.id));db_session.commit();db_session.close()
    barrier=Barrier(2)
    ids=[UUID(request["revision_intent_id"]),uuid4()]
    if mode=="same_intent":ids[1]=ids[0]
    def worker(index):
        with Session(migrated_test_database,expire_on_commit=False) as session:
            session.execute(text("SET LOCAL statement_timeout = '15s'"))
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            service=SnapshotService(session)
            criteria=RequirementCriteria.model_validate(request["criteria"])
            barrier.wait(timeout=10)
            if mode=="ordinary_and_explicit" and index==0:
                try:
                    value=service.create(criteria,actor,expected_result_fingerprint=request["expected_result_fingerprint"])
                    return value["id"],value["revision"],False
                except DuplicateSnapshotError:return None
            value,replayed=service.create_revision(criteria,actor,base_snapshot_id=UUID(base["id"]),
                revision_intent_id=ids[index],expected_result_fingerprint=request["expected_result_fingerprint"])
            return value["id"],value["revision"],replayed
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(worker,index) for index in range(2)]
        outcomes=[job.result(timeout=30) for job in jobs]
    with Session(migrated_test_database) as session:
        revisions=list(session.scalars(select(RequirementSnapshot.revision).order_by(RequirementSnapshot.revision)))
        expected=[1,2,3] if mode=="different_intents" or (mode=="ordinary_and_explicit" and outcomes[0] is not None) else [1,2]
        assert revisions==expected
        assert session.scalar(select(func.count()).select_from(RequirementSnapshotItem))==len(base["items"])*len(expected)
    if mode=="same_intent":
        assert outcomes[0][:2]==outcomes[1][:2] and sorted(x[2] for x in outcomes)==[False,True]
    if mode=="ordinary_and_explicit":
        duplicate=client.post("/api/v1/requirement-snapshots",headers=headers,json={k:v for k,v in request.items() if k in ("criteria","expected_result_fingerprint")})
        assert duplicate.status_code==409
        assert duplicate.json()["detail"]["existing_snapshot_id"]==str(max((row for row in outcomes if row is not None),key=lambda row:row[1])[0])
