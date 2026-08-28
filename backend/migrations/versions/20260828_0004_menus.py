"""create menus meal types days and dishes

Revision ID: 20260828_0004
Revises: 20260828_0003
Create Date: 2026-08-28
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0004"
down_revision: str | None = "20260828_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def audit():
    return [
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),
        sa.Column("created_by",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("updated_by",postgresql.UUID(as_uuid=True),nullable=False),
        sa.ForeignKeyConstraint(["created_by"],["users.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"],["users.id"],ondelete="RESTRICT"),
    ]


def upgrade():
    op.create_table("menus",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("name",sa.String(150),nullable=False),
        sa.Column("start_date",sa.Date(),nullable=False),sa.Column("end_date",sa.Date(),nullable=False),
        sa.Column("category_id",postgresql.UUID(as_uuid=True)),sa.Column("notes",sa.String(1000)),
        sa.Column("is_active",sa.Boolean(),server_default=sa.text("true"),nullable=False),*audit(),
        sa.CheckConstraint("end_date >= start_date",name="ck_menus_date_range"),
        sa.ForeignKeyConstraint(["category_id"],["menu_categories.id"],ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id",name="pk_menus"))
    op.create_index("ix_menus_start_date","menus",["start_date"]);op.create_index("ix_menus_end_date","menus",["end_date"])
    op.create_index("ix_menus_category_id","menus",["category_id"]);op.create_index("ix_menus_is_active","menus",["is_active"])
    op.create_table("menu_meal_types",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("menu_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("name",sa.String(100),nullable=False),sa.Column("sort_order",sa.Integer(),server_default="1",nullable=False),
        sa.Column("is_active",sa.Boolean(),server_default=sa.text("true"),nullable=False),*audit(),
        sa.CheckConstraint("sort_order >= 1",name="ck_menu_meal_types_sort_order_positive"),
        sa.ForeignKeyConstraint(["menu_id"],["menus.id"],ondelete="RESTRICT"),sa.PrimaryKeyConstraint("id",name="pk_menu_meal_types"),
        sa.UniqueConstraint("menu_id","name",name="uq_menu_meal_types_menu_name"))
    op.create_index("ix_menu_meal_types_menu_id","menu_meal_types",["menu_id"])
    op.create_index("ix_menu_meal_types_menu_order","menu_meal_types",["menu_id","sort_order","id"])
    op.create_table("menu_days",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("menu_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("menu_date",sa.Date(),nullable=False),sa.Column("menu_meal_type_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("notes",sa.String(1000)),*audit(),
        sa.ForeignKeyConstraint(["menu_id"],["menus.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["menu_meal_type_id"],["menu_meal_types.id"],ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id",name="pk_menu_days"),
        sa.UniqueConstraint("menu_id","menu_date","menu_meal_type_id",name="uq_menu_days_menu_date_meal_type"))
    op.create_index("ix_menu_days_menu_id","menu_days",["menu_id"]);op.create_index("ix_menu_days_menu_meal_type_id","menu_days",["menu_meal_type_id"])
    op.create_index("ix_menu_days_menu_date","menu_days",["menu_id","menu_date","menu_meal_type_id"])
    op.create_table("menu_dishes",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("menu_day_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("dish_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("diner_count",sa.Integer(),server_default="1",nullable=False),
        sa.Column("notes",sa.String(1000)),sa.Column("sort_order",sa.Integer(),server_default="1",nullable=False),*audit(),
        sa.CheckConstraint("diner_count >= 0",name="ck_menu_dishes_diner_count_nonnegative"),
        sa.CheckConstraint("sort_order >= 1",name="ck_menu_dishes_sort_order_positive"),
        sa.ForeignKeyConstraint(["menu_day_id"],["menu_days.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dish_id"],["dishes.id"],ondelete="RESTRICT"),sa.PrimaryKeyConstraint("id",name="pk_menu_dishes"),
        sa.UniqueConstraint("menu_day_id","dish_id",name="uq_menu_dishes_day_dish"))
    op.create_index("ix_menu_dishes_menu_day_id","menu_dishes",["menu_day_id"]);op.create_index("ix_menu_dishes_dish_id","menu_dishes",["dish_id"])
    op.create_index("ix_menu_dishes_day_sort","menu_dishes",["menu_day_id","sort_order","id"])


def downgrade():
    op.drop_table("menu_dishes");op.drop_table("menu_days");op.drop_table("menu_meal_types");op.drop_table("menus")
