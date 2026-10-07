import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.shared.schemas import PaginationMeta
from app.domains.menus.schemas import MenuPublic


class MenuImportDishMatch(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class MenuImportLinePreview(BaseModel):
    line_key: str
    date: date
    meal_name: str
    meal_sort_order: int
    column_name: str
    column_sort_order: int
    original_import_name: str
    normalized_name: str
    dish: MenuImportDishMatch | None
    status: Literal["MATCHED", "UNMATCHED", "AMBIGUOUS", "INACTIVE_MATCH"]
    review_required: bool
    source_row: int
    source_column: int
    diner_count: int = 1


class MenuImportSummary(BaseModel):
    date_count: int
    meal_count: int
    column_count: int
    dish_count: int
    matched_count: int
    review_required_count: int
    duplicate_conflict_count: int = 0
    excluded_count: int = 0


class MenuImportLayoutRow(BaseModel):
    meal_name: str
    meal_sort_order: int
    column_name: str
    column_sort_order: int


class OverlappingMenuPublic(BaseModel):
    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_active: bool


class MenuImportPreview(BaseModel):
    source_hash: str
    parser_version: str
    sheet_name: str
    start_date: date
    end_date: date
    summary: MenuImportSummary
    layout: list[MenuImportLayoutRow]
    lines: list[MenuImportLinePreview]
    fatal_errors: list[str]
    warnings: list[str]
    overlapping_menus: list[OverlappingMenuPublic]


MenuImportResolutionStatus = Literal[
    "MATCHED", "UNMATCHED", "AMBIGUOUS", "INACTIVE_MATCH", "MANUALLY_RESOLVED", "EXCLUDED",
]
MenuImportBatchStatus = Literal["REVIEW_REQUIRED", "READY", "FINALIZED"]


class MenuImportLinePublic(BaseModel):
    id: uuid.UUID
    line_key: str
    date: date
    meal_name: str
    meal_sort_order: int
    column_name: str
    column_sort_order: int
    original_import_name: str
    normalized_name: str
    dish: MenuImportDishMatch | None
    resolution_status: MenuImportResolutionStatus
    review_required: bool
    duplicate_conflict: bool
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    excluded_at: datetime | None
    excluded_by: uuid.UUID | None
    source_row: int
    source_column: int
    diner_count: int


class MenuImportBatchSummary(BaseModel):
    id: uuid.UUID
    status: MenuImportBatchStatus
    original_filename: str
    source_hash: str
    parser_version: str
    sheet_name: str
    start_date: date
    end_date: date
    summary: MenuImportSummary
    created_by: uuid.UUID
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class MenuImportFinalizedMenu(BaseModel):
    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_active: bool


class MenuImportBatchDetail(MenuImportBatchSummary):
    layout: list[MenuImportLayoutRow]
    lines: list[MenuImportLinePublic]
    can_finalize: bool
    finalize_warnings: list[str]
    finalized_at: datetime | None
    finalized_by: uuid.UUID | None
    finalized_menu_id: uuid.UUID | None
    finalized_menu: MenuImportFinalizedMenu | None = None


class MenuImportBatchList(BaseModel):
    items: list[MenuImportBatchSummary]
    pagination: PaginationMeta


class MenuImportLineResolve(BaseModel):
    dish_id: uuid.UUID


class MenuImportFinalize(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class MenuImportFinalizeResponse(BaseModel):
    batch_id: uuid.UUID
    status: Literal["FINALIZED"]
    finalized_menu_id: uuid.UUID
    finalized_at: datetime
    already_finalized: bool
    menu: MenuPublic
