import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def config():
    root = Path(__file__).resolve().parents[2]
    value = Config(str(root / "alembic.ini"))
    value.set_main_option("script_location", str(root / "migrations"))
    return value


def test_0024_to_0025_upgrade_downgrade_preserves_existing_import_draft(migrated_test_database):
    command.downgrade(config(), "20261007_0024")
    user_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    line_id = uuid.uuid4()
    try:
        with migrated_test_database.begin() as connection:
            connection.execute(text(
                "INSERT INTO users(id,username,password_hash,display_name,role,is_active) "
                "VALUES (:id,'menu-import-0025-user','unused','Migration User','admin',true)"
            ), {"id": user_id})
            connection.execute(text(
                "INSERT INTO menu_import_batches("
                "id,status,original_filename,source_hash,parser_version,sheet_name,start_date,end_date,"
                "date_count,meal_count,column_count,dish_count,matched_count,review_required_count,layout,created_by,updated_by"
                ") VALUES ("
                ":id,'REVIEW_REQUIRED','legacy.xlsx',:hash,'1','Sheet','2026-10-05','2026-10-11',"
                "7,1,1,1,0,1,CAST(:layout AS jsonb),:user_id,:user_id)"
            ), {"id": batch_id, "hash": "a" * 64, "layout": '[{"meal_name":"早餐","meal_sort_order":1,"column_name":"主菜","column_sort_order":1}]', "user_id": user_id})
            connection.execute(text(
                "INSERT INTO menu_import_lines("
                "id,batch_id,line_key,source_row,source_column,menu_date,meal_name,meal_sort_order,column_name,column_sort_order,"
                "original_import_name,normalized_import_name,diner_count,review_required,resolution_status"
                ") VALUES ("
                ":id,:batch_id,:key,2,3,'2026-10-05','早餐',1,'主菜',1,'未知菜','未知菜',1,true,'UNMATCHED')"
            ), {"id": line_id, "batch_id": batch_id, "key": "b" * 64})

        command.upgrade(config(), "20261007_0025")
        inspector = inspect(migrated_test_database)
        batch_columns = {item["name"] for item in inspector.get_columns("menu_import_batches")}
        line_columns = {item["name"] for item in inspector.get_columns("menu_import_lines")}
        assert {"duplicate_conflict_count", "excluded_count"}.issubset(batch_columns)
        assert {"duplicate_conflict", "excluded_at", "excluded_by"}.issubset(line_columns)
        with migrated_test_database.connect() as connection:
            row = connection.execute(text(
                "SELECT duplicate_conflict_count,excluded_count FROM menu_import_batches WHERE id=:id"
            ), {"id": batch_id}).one()
            assert row == (0, 0)
            line = connection.execute(text(
                "SELECT original_import_name,resolution_status,duplicate_conflict FROM menu_import_lines WHERE id=:id"
            ), {"id": line_id}).one()
            assert line == ("未知菜", "UNMATCHED", False)
        with migrated_test_database.begin() as connection:
            connection.execute(text(
                "UPDATE menu_import_lines SET resolution_status='EXCLUDED',review_required=false,excluded_at=now(),excluded_by=:user_id "
                "WHERE id=:id"
            ), {"id": line_id, "user_id": user_id})
            connection.execute(text(
                "UPDATE menu_import_batches SET status='READY',review_required_count=0,excluded_count=1 WHERE id=:id"
            ), {"id": batch_id})

        command.downgrade(config(), "20261007_0024")
        inspector = inspect(migrated_test_database)
        assert "duplicate_conflict_count" not in {item["name"] for item in inspector.get_columns("menu_import_batches")}
        assert "excluded_at" not in {item["name"] for item in inspector.get_columns("menu_import_lines")}
        with migrated_test_database.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM menu_import_batches WHERE id=:id"), {"id": batch_id}) == 1
            assert connection.scalar(text("SELECT count(*) FROM menu_import_lines WHERE id=:id"), {"id": line_id}) == 1
            assert connection.execute(text(
                "SELECT resolution_status,review_required FROM menu_import_lines WHERE id=:id"
            ), {"id": line_id}).one() == ("UNMATCHED", True)
            assert connection.execute(text(
                "SELECT status,review_required_count FROM menu_import_batches WHERE id=:id"
            ), {"id": batch_id}).one() == ("REVIEW_REQUIRED", 1)
    finally:
        command.upgrade(config(), "head")
