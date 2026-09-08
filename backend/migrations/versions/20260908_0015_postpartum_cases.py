"""add postpartum case management

Revision ID: 20260908_0015
Revises: 20260908_0014
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0015"
down_revision = "20260908_0014"
branch_labels = None
depends_on = None

def audit_columns():
    return [sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("created_by",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("updated_by",postgresql.UUID(as_uuid=True),nullable=False),sa.ForeignKeyConstraint(["created_by"],["users.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["updated_by"],["users.id"],ondelete="RESTRICT")]

def upgrade():
    op.create_table("postpartum_cases",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("case_number",sa.String(50),nullable=False),sa.Column("name",sa.String(150),nullable=False),sa.Column("current_room",sa.String(100),nullable=False),sa.Column("delivery_type",sa.String(20),nullable=False),sa.Column("delivery_date",sa.Date(),nullable=False),sa.Column("service_start_date",sa.Date(),nullable=False),sa.Column("service_start_meal",sa.String(20),nullable=False),sa.Column("service_end_date",sa.Date()),sa.Column("service_end_meal",sa.String(20)),sa.Column("status",sa.String(20),nullable=False),sa.Column("preparation_mode",sa.String(40),nullable=False),sa.Column("service_note",sa.Text()),sa.Column("is_active",sa.Boolean(),server_default=sa.true(),nullable=False),*audit_columns(),sa.CheckConstraint("delivery_type IN ('vaginal','cesarean')",name="ck_postpartum_cases_delivery_type"),sa.CheckConstraint("service_start_meal IN ('breakfast','lunch','dinner')",name="ck_postpartum_cases_start_meal"),sa.CheckConstraint("service_end_meal IS NULL OR service_end_meal IN ('breakfast','lunch','dinner')",name="ck_postpartum_cases_end_meal"),sa.CheckConstraint("(service_end_date IS NULL) = (service_end_meal IS NULL)",name="ck_postpartum_cases_end_pair"),sa.CheckConstraint("service_end_date IS NULL OR service_end_date >= service_start_date",name="ck_postpartum_cases_date_range"),sa.CheckConstraint("status IN ('pending','active','paused','ended')",name="ck_postpartum_cases_status"),sa.CheckConstraint("preparation_mode IN ('no_herbal','herbal','rice_wine_sesame','no_rice_wine_sesame')",name="ck_postpartum_cases_preparation_mode"))
    for name in ("case_number","name","current_room","delivery_date","status","is_active"): op.create_index(f"ix_postpartum_cases_{name}","postpartum_cases",[name])
    op.create_table("postpartum_room_histories",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("case_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("room",sa.String(100),nullable=False),sa.Column("effective_date",sa.Date(),nullable=False),sa.Column("effective_meal",sa.String(20),nullable=False),*audit_columns(),sa.ForeignKeyConstraint(["case_id"],["postpartum_cases.id"],ondelete="CASCADE"),sa.CheckConstraint("effective_meal IN ('breakfast','lunch','dinner')",name="ck_postpartum_room_histories_meal"))
    op.create_index("ix_postpartum_room_histories_case_id","postpartum_room_histories",["case_id"]); op.create_index("ix_postpartum_room_histories_case_effective","postpartum_room_histories",["case_id","effective_date","effective_meal","id"])
    op.create_table("postpartum_service_pauses",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("case_id",postgresql.UUID(as_uuid=True),nullable=False),sa.Column("start_date",sa.Date(),nullable=False),sa.Column("start_meal",sa.String(20),nullable=False),sa.Column("end_date",sa.Date(),nullable=False),sa.Column("end_meal",sa.String(20),nullable=False),sa.Column("note",sa.Text()),*audit_columns(),sa.ForeignKeyConstraint(["case_id"],["postpartum_cases.id"],ondelete="CASCADE"),sa.CheckConstraint("start_meal IN ('breakfast','lunch','dinner')",name="ck_postpartum_service_pauses_start_meal"),sa.CheckConstraint("end_meal IN ('breakfast','lunch','dinner')",name="ck_postpartum_service_pauses_end_meal"),sa.CheckConstraint("end_date >= start_date",name="ck_postpartum_service_pauses_date_range"))
    op.create_index("ix_postpartum_service_pauses_case_id","postpartum_service_pauses",["case_id"]); op.create_index("ix_postpartum_service_pauses_case_start","postpartum_service_pauses",["case_id","start_date","start_meal","id"])

def downgrade():
    op.drop_table("postpartum_service_pauses"); op.drop_table("postpartum_room_histories"); op.drop_table("postpartum_cases")
