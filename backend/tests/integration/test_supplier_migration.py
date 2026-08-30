import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text


def test_supplier_enhancement_migration_backfills_deterministic_order(migrated_test_database) -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    user_id = uuid.uuid4()
    first_id, second_id, third_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    command.downgrade(config, "20260830_0007")
    try:
        with migrated_test_database.begin() as connection:
            connection.execute(text("""
                INSERT INTO users(id, username, password_hash, display_name, role, is_active)
                VALUES (:id, 'supplier-migration-user', 'not-used', 'Migration User', 'admin', true)
            """), {"id": user_id})
            for supplier_id, code, created_at in (
                (third_id, "SUP-C", "2026-08-30 02:00:00+00"),
                (second_id, "SUP-B", "2026-08-30 01:00:00+00"),
                (first_id, "SUP-A", "2026-08-30 01:00:00+00"),
            ):
                connection.execute(text("""
                    INSERT INTO suppliers(id, code, name, created_at, updated_at, created_by, updated_by)
                    VALUES (:id, :code, :name, :created_at, :created_at, :user_id, :user_id)
                """), {"id": supplier_id, "code": code, "name": code, "created_at": created_at, "user_id": user_id})

        command.upgrade(config, "head")
        with migrated_test_database.connect() as connection:
            rows = connection.execute(text("SELECT id, address, sort_order FROM suppliers ORDER BY sort_order")).all()
            assert [row.id for row in rows] == [first_id, second_id, third_id]
            assert [row.sort_order for row in rows] == [1, 2, 3]
            assert all(row.address is None for row in rows)
            nullable = connection.execute(text("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'suppliers' AND column_name = 'sort_order'
            """)).scalar_one()
            assert nullable == "NO"
    finally:
        command.upgrade(config, "head")
