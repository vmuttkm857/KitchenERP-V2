"""Real service/writer with I/O doubles. These do not certify PostgreSQL locking."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import importlib.util
from pathlib import Path
from io import StringIO

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.schema import CreateIndex
from sqlalchemy.dialects import postgresql

from app.domains.snapshots import service as snapshots
from app.domains.snapshots.models import RequirementSnapshot,RequirementSnapshotItem
from app.domains.snapshots.exceptions import (
    DuplicateSnapshotError,SnapshotResultChangedError,SnapshotRevisionIntentConflictError,
    SnapshotRevisionBaseError,SnapshotRevisionIntentProtectedError,
)
from app.domains.snapshots.fingerprint import snapshot_fingerprint,normalize
from app.domains.requirements.source_order import attach_source_order
from tests.unit.snapshots.test_result_consistency import flow  # shared real calculator/writer fixture


@pytest.fixture
def revision_flow(flow):
    committed=[]
    def headers():return [value for value in committed if isinstance(value,RequirementSnapshot)]
    def commit():
        committed[:]=list(flow.added)
        flow.operations.append("commit")
    def rollback():
        flow.added[:]=committed
        flow.operations.append("rollback")
    flow.session.commit=commit;flow.session.rollback=rollback
    repo=flow.repository
    repo.next_revision=lambda key:max((h.revision for h in headers() if h.criteria_fingerprint==key),default=0)+1
    repo.by_content=lambda criteria,content:next(iter(sorted((h for h in headers() if h.criteria_fingerprint==criteria and h.content_fingerprint==content and h.snapshot_kind=="standard"),key=lambda h:h.revision,reverse=True)),None)
    repo.lock_revision_intent=lambda actor,intent:flow.operations.append("intent_lock")
    repo.by_revision_intent=lambda actor,intent:next((h for h in headers() if h.created_by==actor and h.revision_intent_id==intent),None)
    repo.revision_base=lambda key:next((h for h in headers() if h.id==key),None)
    repo.get=repo.revision_base
    flow.headers=headers
    flow.service=snapshots.SnapshotService(flow.session)
    flow.world.live=attach_source_order([flow.world.row(_menu_columns=[])])
    flow.viewed=flow.world.calculate()
    flow.service.create(flow.viewed["criteria"],flow.actor.id,expected_result_fingerprint=flow.viewed["result_fingerprint"])
    flow.base=flow.headers()[0]
    def create(intent=None,viewed=None,actor=None,base=None):
        value=viewed or flow.viewed
        return flow.service.create_revision(value["criteria"],actor or flow.actor.id,
            base_snapshot_id=base or flow.base.id,revision_intent_id=intent or uuid4(),
            expected_result_fingerprint=value["result_fingerprint"])
    flow.create_revision=create
    return flow


def test_explicit_r2_r3_preserve_r1_and_source_order(revision_flow):
    f=revision_flow
    before=deepcopy(f.base.criteria),deepcopy(f.base.content_fingerprint)
    f.create_revision();f.create_revision()
    assert [h.revision for h in f.headers()]==[1,2,3]
    assert len({h.id for h in f.headers()})==3
    assert len({h.content_fingerprint for h in f.headers()})==1
    assert len({h.criteria_fingerprint for h in f.headers()})==1
    assert len({h.fingerprint for h in f.headers()})==3
    assert (f.base.criteria,f.base.content_fingerprint)==before
    assert f.base.revision_intent_id is None
    items=[x for x in f.added if isinstance(x,RequirementSnapshotItem)]
    assert len(items)==3 and all(x.source_summary[0]["source_order"]["version"]==1 for x in items)
    assert all(x.__class__.__module__.endswith("snapshots.models") for x in f.added)


def test_same_intent_replay_after_live_changes_returns_same_commit(revision_flow):
    f=revision_flow;intent=uuid4()
    original,replayed=f.create_revision(intent)
    audits=len(f.audits);count=len(f.added)
    f.world.live[0]["diner_count"]+=99
    retry,replayed=f.create_revision(intent)
    assert retry==original and replayed and len(f.headers())==2
    assert len(f.added)==count and len(f.audits)==audits


def test_new_revision_uses_current_verified_result_not_old_snapshot(revision_flow):
    f=revision_flow
    original=next(x for x in f.added if isinstance(x,RequirementSnapshotItem))
    before=original.requirement_quantity,deepcopy(original.source_summary)
    f.world.live[0]["recipe_quantity"]*=2
    f.world.live[0]["source_order"]["visual_position"]+=1
    viewed=f.world.calculate()
    f.create_revision(viewed=viewed)
    current=[x for x in f.added if isinstance(x,RequirementSnapshotItem)][-1]
    assert current.requirement_quantity==viewed["rows"][0]["requirement_quantity"]
    assert current.requirement_quantity!=before[0]
    assert current.source_summary==snapshots.normalize(viewed["rows"][0]["schedules"])
    assert (original.requirement_quantity,original.source_summary)==before


@pytest.mark.parametrize("replayed",[False,True])
def test_revision_route_preserves_creation_and_replay_status(revision_flow,replayed,monkeypatch):
    from fastapi import Response
    from app.api.v1.routes import snapshots as routes
    from app.domains.snapshots.schemas import SnapshotRevisionCreate
    f=revision_flow
    data=SnapshotRevisionCreate(criteria=f.viewed["criteria"],base_snapshot_id=f.base.id,
        revision_intent_id=uuid4(),expected_result_fingerprint=f.viewed["result_fingerprint"])
    value={"id":uuid4()};calls=[]
    def create(self,criteria,actor_id,**kwargs):
        calls.append((criteria,actor_id,kwargs))
        return value,replayed
    monkeypatch.setattr(snapshots.SnapshotService,"create_revision",create)
    response=Response(status_code=201)
    assert routes.create_revision(data,response,f.actor,f.session)==value
    assert response.status_code==(200 if replayed else 201)
    assert calls==[(data.criteria,f.actor.id,{"base_snapshot_id":data.base_snapshot_id,
        "revision_intent_id":data.revision_intent_id,
        "expected_result_fingerprint":data.expected_result_fingerprint})]


@pytest.mark.parametrize("changed",["fingerprint","criteria","base"])
def test_same_intent_changed_request_rejected(revision_flow,changed):
    f=revision_flow;intent=uuid4();f.create_revision(intent)
    value=f.viewed;base=f.base.id
    if changed=="fingerprint":
        f.world.live[0]["diner_count"]+=1
        value=f.world.calculate()
    elif changed=="criteria":
        value=deepcopy(f.viewed)
        value["criteria"]=value["criteria"].model_copy(update={"menu_ids":[uuid4()]})
    else:base=uuid4()
    with pytest.raises(SnapshotRevisionIntentConflictError):
        f.create_revision(intent,viewed=value,base=base)
    assert len(f.headers())==2


def test_intent_scope_is_authenticated_actor(revision_flow):
    f=revision_flow;intent=uuid4()
    f.create_revision(intent)
    f.create_revision(intent,actor=uuid4())
    assert [h.revision for h in f.headers()]==[1,2,3]
    assert f.headers()[1].created_by!=f.headers()[2].created_by


def test_ordinary_dedup_includes_explicit_latest_revision(revision_flow):
    f=revision_flow;f.create_revision()
    with pytest.raises(DuplicateSnapshotError) as caught:
        f.service.create(f.viewed["criteria"],f.actor.id,expected_result_fingerprint=f.viewed["result_fingerprint"])
    assert caught.value.snapshot_id==f.headers()[-1].id
    assert len(f.headers())==2


def test_stale_first_intent_does_not_add_snapshot(revision_flow):
    f=revision_flow;f.world.live[0]["source_order"]["visual_position"]+=1
    with pytest.raises(SnapshotResultChangedError):f.create_revision()
    assert len(f.headers())==1 and "rollback" in f.operations


def test_wrong_base_group_rejected(revision_flow):
    f=revision_flow
    f.base.criteria_fingerprint="0"*64
    with pytest.raises(SnapshotRevisionBaseError):f.create_revision()
    assert len(f.headers())==1


def test_failed_item_write_rolls_back_entire_new_revision(revision_flow):
    f=revision_flow;original=f.repository.add
    def fail(item):
        if isinstance(item,RequirementSnapshotItem):raise RuntimeError("injected write failure")
        original(item)
    f.repository.add=fail
    with pytest.raises(RuntimeError):f.create_revision()
    assert len(f.headers())==1
    assert len([x for x in f.added if isinstance(x,RequirementSnapshot)])==1
    assert len([x for x in f.added if isinstance(x,RequirementSnapshotItem)])==1


def test_lock_order_and_current_group_revision_are_authoritative(revision_flow):
    f=revision_flow
    preview=2
    f.create_revision();f.create_revision()
    assert f.headers()[-1].revision==3 and f.headers()[-1].revision!=preview
    intent_index=f.operations.index("intent_lock")
    assert f.operations[intent_index+1]=="creation_lock"


def test_preview_is_non_reserving_and_reports_actual_latest(revision_flow,monkeypatch):
    f=revision_flow
    monkeypatch.setattr(f.service,"_purchase",lambda key:None)
    first=f.service.revision_context(f.base.id)
    assert first["latest_revision"]==1 and first["next_revision"]==2
    assert len(f.headers())==1
    f.create_revision();f.create_revision()
    assert f.service.revision_context(f.base.id)["next_revision"]==4


def test_explicit_intent_history_cannot_be_hard_deleted(revision_flow):
    f=revision_flow;f.create_revision()
    with pytest.raises(SnapshotRevisionIntentProtectedError):
        f.service.delete(f.headers()[-1].id,f.actor.id,"not-used")


def test_ordinary_index_remains_unique_and_revision_constraint_remains():
    table=RequirementSnapshot.__table__
    indexes={i.name:i for i in table.indexes}
    normal=indexes["uq_requirement_snapshots_standard_content"]
    assert normal.unique and "revision_intent_id IS NULL" in str(CreateIndex(normal).compile(dialect=postgresql.dialect()))
    assert indexes["uq_snapshots_actor_revision_intent"].unique
    assert any(c.name=="uq_snapshots_criteria_revision" for c in table.constraints)


def test_migration_offline_sql_and_safe_downgrade_guard():
    path=Path(__file__).resolve().parents[3]/"migrations/versions/20261029_0028_snapshot_revision_intents.py"
    spec=importlib.util.spec_from_file_location("revision_migration",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=StringIO()
    context=MigrationContext.configure(dialect_name="postgresql",opts={"as_sql":True,"output_buffer":output})
    module.op=Operations(context)
    module.upgrade()
    sql=output.getvalue()
    assert "revision_intent_id UUID" in sql and "revision_intent_id IS NULL" in sql
    assert "UPDATE " not in sql and "DELETE " not in sql
    output.seek(0);output.truncate(0);module.downgrade();sql=output.getvalue()
    assert sql.index("LOCK TABLE")<sql.index("SNAPSHOT_REVISION_INTENTS_PREVENT_DOWNGRADE")<sql.index("DROP INDEX")
    assert "DELETE " not in sql
