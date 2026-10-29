"""Explicit snapshot revisions with durable, actor-scoped idempotency.

Revision ID: 20261029_0028
Revises: 20261008_0027
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261029_0028"
down_revision = "20261008_0027"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable additions preserve every historical row without a data backfill.
    op.add_column("requirement_snapshots", sa.Column("revision_intent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("requirement_snapshots", sa.Column("revision_intent_request_hash", sa.String(64), nullable=True))
    op.create_check_constraint("ck_snapshots_revision_intent_pair", "requirement_snapshots",
        "(revision_intent_id IS NULL AND revision_intent_request_hash IS NULL) OR "
        "(snapshot_kind = 'standard' AND revision_intent_id IS NOT NULL AND "
        "revision_intent_request_hash IS NOT NULL AND revision_intent_request_hash ~ '^[0-9a-f]{64}$')")
    op.create_index("uq_snapshots_actor_revision_intent", "requirement_snapshots",
                    ["created_by", "revision_intent_id"], unique=True,
                    postgresql_where=sa.text("revision_intent_id IS NOT NULL"))
    # PostgreSQL transactional DDL keeps this replacement atomic to other writers.
    op.drop_index("uq_requirement_snapshots_standard_content", table_name="requirement_snapshots")
    op.create_index("uq_requirement_snapshots_standard_content", "requirement_snapshots",
                    ["criteria_fingerprint", "content_fingerprint"], unique=True,
                    postgresql_where=sa.text("snapshot_kind = 'standard' AND revision_intent_id IS NULL"))


def downgrade():
    # Refuse to erase successful intent/retry history, even if contents differ.
    # The lock closes the check/drop race with a concurrent explicit creation.
    op.execute("LOCK TABLE requirement_snapshots IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM requirement_snapshots WHERE revision_intent_id IS NOT NULL) THEN
            RAISE EXCEPTION 'SNAPSHOT_REVISION_INTENTS_PREVENT_DOWNGRADE';
        END IF;
    END $$""")
    op.drop_index("uq_requirement_snapshots_standard_content", table_name="requirement_snapshots")
    op.create_index("uq_requirement_snapshots_standard_content", "requirement_snapshots",
                    ["criteria_fingerprint", "content_fingerprint"], unique=True,
                    postgresql_where=sa.text("snapshot_kind = 'standard'"))
    op.drop_index("uq_snapshots_actor_revision_intent", table_name="requirement_snapshots")
    op.drop_constraint("ck_snapshots_revision_intent_pair", "requirement_snapshots", type_="check")
    op.drop_column("requirement_snapshots", "revision_intent_request_hash")
    op.drop_column("requirement_snapshots", "revision_intent_id")
