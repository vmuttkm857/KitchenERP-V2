"""Destructive DDL is limited to the separately approved migration test database."""
from pathlib import Path
from uuid import uuid4
import hashlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect,text
from sqlalchemy.exc import DBAPIError,IntegrityError


def config():
    root=Path(__file__).resolve().parents[2]
    value=Config(str(root/"alembic.ini"));value.set_main_option("script_location",str(root/"migrations"))
    return value


def legacy_row(engine):
    actor,snapshot=uuid4(),uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,username,password_hash,display_name,role) VALUES (:id,:name,'test-only-not-loginable','Migration test','admin')"),{"id":actor,"name":"revision-migration-"+actor.hex})
        conn.execute(text("""INSERT INTO requirement_snapshots
            (id,fingerprint,criteria_fingerprint,content_fingerprint,revision,snapshot_kind,
             criteria,source_menus,anomaly_snapshot,anomaly_summary,known_estimated_cost,total_estimated_cost,created_by)
            VALUES (:id,:fingerprint,:criteria,:content,1,'standard','{}','[]','[]','{}',0,0,:actor)"""),
            {"id":snapshot,"fingerprint":"a"*64,"criteria":"b"*64,"content":"c"*64,"actor":actor})
    return actor,snapshot


def test_upgrade_preserves_old_rows_and_clean_downgrade_is_possible(migrated_test_database):
    engine=migrated_test_database
    command.downgrade(config(),"20261008_0027")
    try:
        _,snapshot=legacy_row(engine)
        with engine.connect() as conn:
            before=conn.execute(text("SELECT fingerprint,criteria_fingerprint,content_fingerprint,revision,criteria,source_menus,created_at,created_by FROM requirement_snapshots WHERE id=:id"),{"id":snapshot}).one()
        command.upgrade(config(),"20261029_0028")
        with engine.connect() as conn:
            after=conn.execute(text("SELECT fingerprint,criteria_fingerprint,content_fingerprint,revision,criteria,source_menus,created_at,created_by FROM requirement_snapshots WHERE id=:id"),{"id":snapshot}).one()
            pair=conn.execute(text("SELECT revision_intent_id,revision_intent_request_hash FROM requirement_snapshots WHERE id=:id"),{"id":snapshot}).one()
        assert before==after and tuple(pair)==(None,None)
        command.downgrade(config(),"20261008_0027")
        assert "revision_intent_id" not in {column["name"] for column in inspect(engine).get_columns("requirement_snapshots")}
    finally:command.upgrade(config(),"head")


def test_new_constraints_and_downgrade_refusal_preserve_intent_history(migrated_test_database):
    engine=migrated_test_database
    actor,snapshot=legacy_row(engine)
    intent=uuid4()
    insert=text("""INSERT INTO requirement_snapshots
        (id,fingerprint,criteria_fingerprint,content_fingerprint,revision,snapshot_kind,
         criteria,source_menus,anomaly_snapshot,anomaly_summary,known_estimated_cost,total_estimated_cost,created_by,
         revision_intent_id,revision_intent_request_hash)
        VALUES (:id,:fingerprint,:criteria,:content,:revision,'standard','{}','[]','[]','{}',0,0,:actor,:intent,:request_hash)""")
    def values(**extra):
        return {"id":uuid4(),"fingerprint":hashlib.sha256(uuid4().bytes).hexdigest(),"criteria":"b"*64,"content":"c"*64,
                "revision":2,"actor":actor,"intent":intent,"request_hash":"e"*64,**extra}
    def rejected(constraint,**changes):
        with pytest.raises(IntegrityError) as caught:
            with engine.begin() as conn:conn.execute(insert,values(**changes))
        assert caught.value.orig.diag.constraint_name==constraint
    rejected("uq_requirement_snapshots_standard_content",intent=None,request_hash=None)
    rejected("ck_snapshots_revision_intent_pair",request_hash=None)
    with engine.begin() as conn:conn.execute(insert,values())  # explicit identical content
    rejected("uq_snapshots_actor_revision_intent",revision=3)
    rejected("uq_snapshots_criteria_revision",intent=uuid4())
    with pytest.raises(DBAPIError,match="SNAPSHOT_REVISION_INTENTS_PREVENT_DOWNGRADE"):
        command.downgrade(config(),"20261008_0027")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))=="20261029_0028"
        assert conn.scalar(text("SELECT count(*) FROM requirement_snapshots WHERE revision_intent_id=:id"),{"id":intent})==1
