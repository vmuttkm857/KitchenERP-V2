"""Optional display colors for dish categories only.

Revision ID: 20261103_0029
Revises: 20261029_0028
"""
from alembic import op
import sqlalchemy as sa

revision = "20261103_0029"
down_revision = "20261029_0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dish_categories", sa.Column("background_color", sa.String(7), nullable=True))
    op.create_check_constraint("ck_dish_categories_background_color", "dish_categories",
        "background_color IS NULL OR background_color ~ '^#[0-9A-Fa-f]{6}$'")


def downgrade():
    # Never silently discard colors configured after the upgrade.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM dish_categories WHERE background_color IS NOT NULL) THEN
            RAISE EXCEPTION 'DISH_CATEGORY_COLORS_PREVENT_DOWNGRADE';
        END IF;
    END $$""")
    op.drop_constraint("ck_dish_categories_background_color", "dish_categories", type_="check")
    op.drop_column("dish_categories", "background_color")
