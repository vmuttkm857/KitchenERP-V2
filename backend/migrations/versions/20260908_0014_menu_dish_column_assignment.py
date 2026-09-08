"""add menu dish column assignment

Revision ID: 20260908_0014
Revises: 20260903_0013
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260908_0014"
down_revision = "20260903_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menu_dishes",sa.Column("menu_meal_type_column_id",postgresql.UUID(as_uuid=True),nullable=True))
    op.create_foreign_key(
        "fk_menu_dishes_menu_meal_type_column_id_menu_meal_type_columns",
        "menu_dishes","menu_meal_type_columns",["menu_meal_type_column_id"],["id"],ondelete="SET NULL",
    )
    op.create_index("ix_menu_dishes_meal_type_column_id","menu_dishes",["menu_meal_type_column_id"])
    op.create_unique_constraint("uq_menu_dishes_day_meal_type_column","menu_dishes",["menu_day_id","menu_meal_type_column_id"])


def downgrade() -> None:
    op.drop_constraint("uq_menu_dishes_day_meal_type_column","menu_dishes",type_="unique")
    op.drop_index("ix_menu_dishes_meal_type_column_id",table_name="menu_dishes")
    op.drop_constraint("fk_menu_dishes_menu_meal_type_column_id_menu_meal_type_columns","menu_dishes",type_="foreignkey")
    op.drop_column("menu_dishes","menu_meal_type_column_id")
