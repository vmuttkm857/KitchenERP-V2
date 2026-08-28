import json,uuid
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import text

def test_0005_snapshot_data_is_backfilled_during_0006_upgrade(migrated_test_database):
    root=Path(__file__).resolve().parents[2];config=Config(str(root/"alembic.ini"));config.set_main_option("script_location",str(root/"migrations"))
    user_id,snapshot_id,item_id=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
    command.downgrade(config,"20260828_0005")
    try:
        with migrated_test_database.begin() as connection:
            connection.execute(text("INSERT INTO users(id,username,password_hash,display_name,role,is_active) VALUES (:id,'migration-user','not-used','Migration User','admin',true)"),{"id":user_id})
            connection.execute(text("INSERT INTO requirement_snapshots(id,fingerprint,criteria,source_menus,anomaly_snapshot,anomaly_summary,known_estimated_cost,total_estimated_cost,created_by) VALUES (:id,:fingerprint,CAST(:criteria AS jsonb),CAST(:menus AS jsonb),'[]'::jsonb,CAST(:summary AS jsonb),220,220,:user_id)"),{"id":snapshot_id,"fingerprint":"a"*64,"criteria":json.dumps({"menu_ids":[str(uuid.uuid4())]}),"menus":json.dumps([{"menu_id":str(uuid.uuid4()),"menu_name":"舊快照菜單","start_date":"2026-09-01","end_date":"2026-09-01","is_active":True}]),"summary":json.dumps({"total":0,"errors":0,"warnings":0}),"user_id":user_id})
            connection.execute(text("INSERT INTO requirement_snapshot_items(id,snapshot_id,row_key,ingredient_code_snapshot,ingredient_name_snapshot,supplier_code_snapshot,supplier_name_snapshot,requirement_quantity,requirement_unit,suggested_purchase_quantity,adjusted_quantity,suggested_purchase_unit_snapshot,purchase_unit_snapshot,package_size_snapshot,minimum_order_quantity_snapshot,unit_price_snapshot,estimated_cost_snapshot,needs_review,total_diner_count,source_count,anomaly_snapshot,source_summary,updated_by) VALUES (:id,:snapshot_id,'legacy-row','I1','雞肉','S1','供應商',1.1,'kg',1.1,1.1,'kg','箱',10,5,200,220,false,10,1,'[]'::jsonb,'[]'::jsonb,:user_id)"),{"id":item_id,"snapshot_id":snapshot_id,"user_id":user_id})
        command.upgrade(config,"head")
        with migrated_test_database.connect() as connection:
            header=connection.execute(text("SELECT criteria_fingerprint,content_fingerprint,revision FROM requirement_snapshots WHERE id=:id"),{"id":snapshot_id}).one()
            item=connection.execute(text("SELECT purchase_unit_snapshot,configured_purchase_unit_snapshot FROM requirement_snapshot_items WHERE id=:id"),{"id":item_id}).one()
            assert len(header.criteria_fingerprint)==64 and len(header.content_fingerprint)==64 and header.revision==1
            assert item.purchase_unit_snapshot=="kg" and item.configured_purchase_unit_snapshot=="箱"
    finally:
        command.upgrade(config,"head")
