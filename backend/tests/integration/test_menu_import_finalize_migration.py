import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root=Path(__file__).resolve().parents[2]
    value=Config(str(root/"alembic.ini"));value.set_main_option("script_location",str(root/"migrations"))
    return value


def test_0025_to_0026_upgrade_downgrade_preserves_drafts_and_formal_menu(migrated_test_database):
    command.downgrade(config(),"20261007_0025")
    user_id,batch_id,menu_id=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
    try:
        with migrated_test_database.begin() as connection:
            connection.execute(text(
                "INSERT INTO users(id,username,password_hash,display_name,role,is_active) "
                "VALUES (:id,'menu-import-0026-user','unused','Migration User','admin',true)"
            ),{"id":user_id})
            connection.execute(text(
                "INSERT INTO menus(id,name,start_date,end_date,is_active,created_by,updated_by) "
                "VALUES (:id,'Imported Menu','2026-10-05','2026-10-11',true,:user_id,:user_id)"
            ),{"id":menu_id,"user_id":user_id})
            connection.execute(text(
                "INSERT INTO menu_import_batches(id,status,original_filename,source_hash,parser_version,sheet_name,"
                "start_date,end_date,date_count,meal_count,column_count,dish_count,matched_count,review_required_count,"
                "duplicate_conflict_count,excluded_count,layout,created_by,updated_by) VALUES ("
                ":id,'READY','legacy.xlsx',:hash,'1','Sheet','2026-10-05','2026-10-11',7,1,1,0,0,0,0,0,"
                "CAST(:layout AS jsonb),:user_id,:user_id)"
            ),{"id":batch_id,"hash":"c"*64,"layout":'[{"meal_name":"早餐","meal_sort_order":1,"column_name":"主菜","column_sort_order":1}]',"user_id":user_id})
        command.upgrade(config(),"20261007_0026")
        columns={item["name"] for item in inspect(migrated_test_database).get_columns("menu_import_batches")}
        assert {"finalized_at","finalized_by","finalized_menu_id"}.issubset(columns)
        with migrated_test_database.begin() as connection:
            connection.execute(text(
                "UPDATE menu_import_batches SET status='FINALIZED',finalized_at=now(),finalized_by=:user_id,"
                "finalized_menu_id=:menu_id WHERE id=:id"
            ),{"id":batch_id,"user_id":user_id,"menu_id":menu_id})
            connection.execute(text("DELETE FROM menus WHERE id=:menu_id"),{"menu_id":menu_id})
            assert connection.scalar(text(
                "SELECT finalized_menu_id FROM menu_import_batches WHERE id=:id"
            ),{"id":batch_id}) is None
            assert connection.scalar(text(
                "SELECT status FROM menu_import_batches WHERE id=:id"
            ),{"id":batch_id})=="FINALIZED"
            connection.execute(text(
                "INSERT INTO menus(id,name,start_date,end_date,is_active,created_by,updated_by) "
                "VALUES (:id,'Imported Menu','2026-10-05','2026-10-11',true,:user_id,:user_id)"
            ),{"id":menu_id,"user_id":user_id})
        command.downgrade(config(),"20261007_0025")
        assert "finalized_menu_id" not in {item["name"] for item in inspect(migrated_test_database).get_columns("menu_import_batches")}
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT status FROM menu_import_batches WHERE id=:id"),{"id":batch_id})=="READY"
            assert connection.scalar(text("SELECT count(*) FROM menus WHERE id=:id"),{"id":menu_id})==1
    finally:
        command.upgrade(config(),"head")
