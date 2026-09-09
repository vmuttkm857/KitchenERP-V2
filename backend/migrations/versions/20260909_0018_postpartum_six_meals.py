"""expand postpartum meals to six

Revision ID: 20260909_0018
Revises: 20260909_0017
"""

from alembic import op


revision = "20260909_0018"
down_revision = "20260909_0017"
branch_labels = None
depends_on = None

THREE_MEALS = "'breakfast','lunch','dinner'"
SIX_MEALS = "'breakfast','morning_snack','lunch','afternoon_snack','dinner','evening_snack'"


def _replace_constraint(table: str, name: str, expression: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    _replace_constraint(
        "postpartum_cases", "ck_postpartum_cases_start_meal",
        f"service_start_meal IN ({SIX_MEALS})",
    )
    _replace_constraint(
        "postpartum_cases", "ck_postpartum_cases_end_meal",
        f"service_end_meal IS NULL OR service_end_meal IN ({SIX_MEALS})",
    )
    _replace_constraint(
        "postpartum_room_histories", "ck_postpartum_room_histories_meal",
        f"effective_meal IN ({SIX_MEALS})",
    )
    _replace_constraint(
        "postpartum_service_pauses", "ck_postpartum_service_pauses_start_meal",
        f"start_meal IN ({SIX_MEALS})",
    )
    _replace_constraint(
        "postpartum_service_pauses", "ck_postpartum_service_pauses_end_meal",
        f"end_meal IN ({SIX_MEALS})",
    )


def downgrade() -> None:
    _replace_constraint(
        "postpartum_service_pauses", "ck_postpartum_service_pauses_end_meal",
        f"end_meal IN ({THREE_MEALS})",
    )
    _replace_constraint(
        "postpartum_service_pauses", "ck_postpartum_service_pauses_start_meal",
        f"start_meal IN ({THREE_MEALS})",
    )
    _replace_constraint(
        "postpartum_room_histories", "ck_postpartum_room_histories_meal",
        f"effective_meal IN ({THREE_MEALS})",
    )
    _replace_constraint(
        "postpartum_cases", "ck_postpartum_cases_end_meal",
        f"service_end_meal IS NULL OR service_end_meal IN ({THREE_MEALS})",
    )
    _replace_constraint(
        "postpartum_cases", "ck_postpartum_cases_start_meal",
        f"service_start_meal IN ({THREE_MEALS})",
    )
