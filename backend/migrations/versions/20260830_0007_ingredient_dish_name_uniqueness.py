"""enforce normalized ingredient and dish name uniqueness

Revision ID: 20260830_0007
Revises: 20260828_0006
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260830_0007"
down_revision: str | None = "20260828_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _duplicate_rows(table_name: str) -> list[dict[str, object]]:
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"""
        SELECT name, id::text AS id, code, is_active
        FROM {table_name}
        WHERE lower(btrim(name)) IN (
            SELECT lower(btrim(name))
            FROM {table_name}
            GROUP BY lower(btrim(name))
            HAVING count(*) > 1
        )
        ORDER BY lower(btrim(name)), code, id
    """)).mappings()
    return [dict(row) for row in rows]


def upgrade() -> None:
    duplicates = {
        "ingredients": _duplicate_rows("ingredients"),
        "dishes": _duplicate_rows("dishes"),
    }
    if any(duplicates.values()):
        details = "; ".join(
            f"{table}: " + ", ".join(
                f"name={row['name']!r} id={row['id']} code={row['code']!r} active={row['is_active']}"
                for row in rows
            )
            for table, rows in duplicates.items() if rows
        )
        raise RuntimeError(f"Duplicate names must be resolved before migration: {details}")

    op.create_index("uq_ingredients_name_normalized", "ingredients", [sa.text("lower(btrim(name))")], unique=True)
    op.create_index("uq_dishes_name_normalized", "dishes", [sa.text("lower(btrim(name))")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_dishes_name_normalized", table_name="dishes")
    op.drop_index("uq_ingredients_name_normalized", table_name="ingredients")
