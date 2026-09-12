import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.schemas import PaginationMeta
from app.domains.postpartum.meals import Meal


DeliveryType = Literal["vaginal", "cesarean"]
CaseStatus = Literal["pending", "active", "paused", "ended"]
PreparationMode = Literal["no_herbal", "herbal", "rice_wine_sesame", "no_rice_wine_sesame"]


def _required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class CaseCreate(BaseModel):
    case_number: str = Field(max_length=50)
    name: str = Field(max_length=150)
    current_room: str = Field(max_length=100)
    delivery_type: DeliveryType
    delivery_date: date
    service_start_date: date
    service_start_meal: Meal
    service_end_date: date | None = None
    service_end_meal: Meal | None = None
    status: CaseStatus = "pending"
    preparation_mode: PreparationMode
    service_note: str | None = Field(default=None, max_length=5000)

    _strip_required = field_validator("case_number", "name", "current_room")(_required)

    @model_validator(mode="after")
    def valid_service_range(self):
        if (self.service_end_date is None) != (self.service_end_meal is None):
            raise ValueError("service end date and meal must be provided together")
        return self


class CaseUpdate(BaseModel):
    case_number: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=150)
    delivery_type: DeliveryType | None = None
    delivery_date: date | None = None
    service_start_date: date | None = None
    service_start_meal: Meal | None = None
    service_end_date: date | None = None
    service_end_meal: Meal | None = None
    status: CaseStatus | None = None
    preparation_mode: PreparationMode | None = None
    service_note: str | None = Field(default=None, max_length=5000)

    _strip_required = field_validator("case_number", "name")(_required)


class CasePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_number: str
    name: str
    current_room: str
    delivery_type: DeliveryType
    delivery_date: date
    service_start_date: date
    service_start_meal: Meal
    service_end_date: date | None
    service_end_meal: Meal | None
    status: CaseStatus
    preparation_mode: PreparationMode
    service_note: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class CaseRestrictionGroupSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str
    is_active: bool


class CaseListItem(CasePublic):
    restriction_groups: list[CaseRestrictionGroupSummary] = Field(default_factory=list)


class CaseList(BaseModel):
    items: list[CaseListItem]
    pagination: PaginationMeta


class RoomChangeCreate(BaseModel):
    room: str = Field(max_length=100)
    effective_date: date
    effective_meal: Meal

    _strip_room = field_validator("room")(_required)


class RoomHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    room: str
    effective_date: date
    effective_meal: Meal
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class PauseCreate(BaseModel):
    start_date: date
    start_meal: Meal
    end_date: date
    end_meal: Meal
    note: str | None = Field(default=None, max_length=5000)


class PauseUpdate(BaseModel):
    start_date: date | None = None
    start_meal: Meal | None = None
    end_date: date | None = None
    end_meal: Meal | None = None
    note: str | None = Field(default=None, max_length=5000)


class PausePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    start_date: date
    start_meal: Meal
    end_date: date
    end_meal: Meal
    note: str | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class CaseDetail(BaseModel):
    case: CasePublic
    room_history: list[RoomHistoryPublic]
    pauses: list[PausePublic]
    restriction_groups: list[CaseRestrictionGroupSummary] = Field(default_factory=list)


class CaseRestrictionGroupsReplace(BaseModel):
    restriction_group_ids: list[uuid.UUID] = Field(default_factory=list)


class CaseRestrictionGroupsPublic(BaseModel):
    case_id: uuid.UUID
    restriction_groups: list[CaseRestrictionGroupSummary] = Field(default_factory=list)


class RestrictionGroupCreate(BaseModel):
    name: str = Field(max_length=150)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: str | None = Field(default=None, max_length=5000)

    _strip_name = field_validator("name")(_required)


class RestrictionGroupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "color" in self.model_fields_set and self.color is None:
            raise ValueError("color must not be null")
        return self


class RestrictionGroupPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str
    notes: str | None
    is_active: bool
    ingredient_count: int = 0
    dish_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID
    updated_by: uuid.UUID


class RestrictionGroupList(BaseModel):
    items: list[RestrictionGroupPublic]
    pagination: PaginationMeta


class RestrictionTargetPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class RestrictionGroupDetail(BaseModel):
    group: RestrictionGroupPublic
    ingredients: list[RestrictionTargetPublic]
    dishes: list[RestrictionTargetPublic]


class RestrictionAssociationsReplace(BaseModel):
    ingredient_ids: list[uuid.UUID] = Field(default_factory=list)
    dish_ids: list[uuid.UUID] = Field(default_factory=list)


class MenuSourceMappingInput(BaseModel):
    postpartum_meal: Meal
    menu_meal_type_id: uuid.UUID


class MenuSourceReplace(BaseModel):
    menu_id: uuid.UUID
    mappings: list[MenuSourceMappingInput] = Field(min_length=1, max_length=6)


class MenuSourceMenuSummary(BaseModel):
    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_active: bool


class MenuSourceMealTypeSummary(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool


class MenuSourceMappingPublic(BaseModel):
    postpartum_meal: Meal
    menu_meal_type: MenuSourceMealTypeSummary


class MenuSourceWarning(BaseModel):
    code: str
    message: str
    postpartum_meal: Meal | None = None


class MenuSourceMealStatus(BaseModel):
    postpartum_meal: Meal
    mapped: bool
    menu_meal_type: MenuSourceMealTypeSummary | None = None


class MenuSourcePublic(BaseModel):
    id: uuid.UUID
    configured: bool
    usable: bool
    menu: MenuSourceMenuSummary
    mappings: list[MenuSourceMappingPublic] = Field(default_factory=list)
    meal_statuses: list[MenuSourceMealStatus] = Field(default_factory=list)
    warnings: list[MenuSourceWarning] = Field(default_factory=list)


class MenuSourceList(BaseModel):
    items: list[MenuSourcePublic] = Field(default_factory=list)


ConflictCoverage = Literal["complete", "partial", "unavailable"]
ConflictOutcome = Literal["conflict", "no_conflict", "unknown"]


class MenuConflictWarning(BaseModel):
    code: str
    message: str
    case_id: uuid.UUID | None = None
    menu_dish_id: uuid.UUID | None = None
    restriction_group_id: uuid.UUID | None = None
    ingredient_id: uuid.UUID | None = None
    target_id: uuid.UUID | None = None


class MenuConflictSourceSummary(BaseModel):
    source_id: uuid.UUID
    menu_id: uuid.UUID
    menu_name: str
    start_date: date
    end_date: date
    is_active: bool


class MenuConflictSourceResolution(BaseModel):
    status: Literal["available", "not_configured", "ambiguous", "inactive"]
    source: MenuConflictSourceSummary | None = None
    candidates: list[MenuConflictSourceSummary] = Field(default_factory=list)


class MenuConflictMealTypeSummary(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool


class MenuConflictMappingResolution(BaseModel):
    status: Literal["mapped", "not_mapped", "inactive", "inconsistent", "not_checked"]
    menu_meal_type: MenuConflictMealTypeSummary | None = None


class MenuConflictDaySummary(BaseModel):
    id: uuid.UUID
    menu_date: date


class MenuConflictTargetSummary(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class MenuConflictDishPublic(BaseModel):
    menu_dish_id: uuid.UUID
    sort_order: int
    dish: MenuConflictTargetSummary
    ingredient_coverage: Literal["complete", "partial"]
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class MenuConflictRestrictionGroupSummary(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    notes: str | None
    is_active: bool


class MenuConflictCasePublic(BaseModel):
    id: uuid.UUID
    case_number: str
    name: str
    current_room: str
    status: CaseStatus
    restriction_groups: list[MenuConflictRestrictionGroupSummary] = Field(default_factory=list)
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class MenuConflictReason(BaseModel):
    type: Literal["direct_dish", "ingredient"]
    restriction_group: MenuConflictRestrictionGroupSummary
    matched_target: MenuConflictTargetSummary


class MenuConflictCaseDishResult(BaseModel):
    case_id: uuid.UUID
    menu_dish_id: uuid.UUID
    outcome: ConflictOutcome
    coverage: Literal["complete", "partial"]
    reasons: list[MenuConflictReason] = Field(default_factory=list)
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class MenuConflictResponse(BaseModel):
    target_date: date
    postpartum_meal: Meal
    evaluation_status: ConflictCoverage
    evaluation_performed: bool
    source_resolution: MenuConflictSourceResolution
    mapping_resolution: MenuConflictMappingResolution
    menu_day: MenuConflictDaySummary | None = None
    menu_dishes: list[MenuConflictDishPublic] = Field(default_factory=list)
    eligible_cases: list[MenuConflictCasePublic] = Field(default_factory=list)
    case_dish_results: list[MenuConflictCaseDishResult] = Field(default_factory=list)
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class MenuConflictMealSummary(BaseModel):
    target_date: date
    postpartum_meal: Meal
    status: Literal["conflict", "partial", "complete", "unmapped", "unavailable"]
    evaluation_status: ConflictCoverage
    evaluation_performed: bool
    source_status: Literal["available", "not_configured", "ambiguous", "inactive"]
    mapping_status: Literal["mapped", "not_mapped", "inactive", "inconsistent", "not_checked"]
    menu_name: str | None = None
    menu_meal_type_name: str | None = None
    eligible_case_count: int
    menu_dish_count: int
    conflict_case_count: int
    conflict_count: int
    manual_review_case_count: int
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class MenuConflictDailyResponse(BaseModel):
    target_date: date
    meals: list[MenuConflictResponse]
    summaries: list[MenuConflictMealSummary]
    conflict_case_count: int
    conflict_count: int
    manual_review_case_count: int


class MenuConflictWeeklyDay(BaseModel):
    target_date: date
    meals: list[MenuConflictMealSummary]


class MenuConflictWeeklyResponse(BaseModel):
    week_start: date
    week_end: date
    days: list[MenuConflictWeeklyDay]


ReplacementCandidateStatus = Literal["no_known_conflict", "conflict", "insufficient_recipe_data"]
ConflictHandlingStatus = Literal["pending", "replaced", "manually_acknowledged", "requires_reconfirmation"]


class ConflictItemInput(BaseModel):
    case_id: uuid.UUID
    original_menu_dish_id: uuid.UUID
    original_dish_id: uuid.UUID


class ReplacementGroupCreate(BaseModel):
    target_date: date
    postpartum_meal: Meal
    replacement_dish_id: uuid.UUID
    items: list[ConflictItemInput] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=5000)


class ReplacementGroupUpdate(BaseModel):
    replacement_dish_id: uuid.UUID
    items: list[ConflictItemInput] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=5000)
    reassign_items: bool = False


class ConflictAcknowledgementCreate(BaseModel):
    target_date: date
    postpartum_meal: Meal
    item: ConflictItemInput
    note: str | None = Field(default=None, max_length=5000)


class ReplacementCandidateSearch(BaseModel):
    target_date: date
    postpartum_meal: Meal
    items: list[ConflictItemInput] = Field(min_length=1)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = None
    category_id: uuid.UUID | None = None


class ReplacementCandidatePublic(BaseModel):
    dish: MenuConflictTargetSummary
    status: ReplacementCandidateStatus
    coverage: Literal["complete", "partial"]
    review_needed: bool
    case_results: list[MenuConflictCaseDishResult] = Field(default_factory=list)
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class ReplacementCandidateList(BaseModel):
    items: list[ReplacementCandidatePublic]
    pagination: PaginationMeta


class ConflictHandlingItemPublic(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    original_menu_dish_id: uuid.UUID
    original_dish: MenuConflictTargetSummary
    status: ConflictHandlingStatus
    note: str | None = None
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class ReplacementGroupPublic(BaseModel):
    id: uuid.UUID
    target_date: date
    postpartum_meal: Meal
    replacement_dish: MenuConflictTargetSummary
    note: str | None = None
    status: ConflictHandlingStatus
    candidate_status: ReplacementCandidateStatus
    review_needed: bool
    warnings: list[MenuConflictWarning] = Field(default_factory=list)
    items: list[ConflictHandlingItemPublic]


class ConflictAcknowledgementPublic(ConflictHandlingItemPublic):
    target_date: date
    postpartum_meal: Meal


class ConflictItemStatusPublic(BaseModel):
    case_id: uuid.UUID
    original_menu_dish_id: uuid.UUID
    original_dish: MenuConflictTargetSummary
    status: ConflictHandlingStatus
    handling_id: uuid.UUID | None = None
    replacement_group_id: uuid.UUID | None = None


class ConflictHandlingList(BaseModel):
    target_date: date
    postpartum_meal: Meal
    replacement_groups: list[ReplacementGroupPublic]
    manual_acknowledgements: list[ConflictAcknowledgementPublic]
    conflict_items: list[ConflictItemStatusPublic]


class ChangeSheetSummary(BaseModel):
    replacement_group_count: int
    replacement_item_count: int
    manual_acknowledgement_count: int
    requires_reconfirmation_count: int


class ChangeSheetCaseSummary(BaseModel):
    case_id: uuid.UUID
    case_number: str
    name: str
    current_room: str


class ChangeSheetRestrictionGroup(BaseModel):
    id: uuid.UUID
    name: str
    color: str


class ChangeSheetReplacementItem(BaseModel):
    handling_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    case_name: str
    current_room: str
    original_menu_dish_id: uuid.UUID
    original_dish: MenuConflictTargetSummary
    replacement_dish: MenuConflictTargetSummary
    restriction_groups: list[ChangeSheetRestrictionGroup] = Field(default_factory=list)
    status: ConflictHandlingStatus
    review_needed: bool
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class ChangeSheetReplacementGroup(BaseModel):
    group_id: uuid.UUID
    replacement_dish: MenuConflictTargetSummary
    quantity: int
    case_rooms: list[str]
    cases: list[ChangeSheetCaseSummary]
    items: list[ChangeSheetReplacementItem]
    note: str | None = None
    status: ConflictHandlingStatus
    review_needed: bool
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class ChangeSheetAcknowledgement(BaseModel):
    handling_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    case_name: str
    current_room: str
    original_menu_dish_id: uuid.UUID
    original_dish: MenuConflictTargetSummary
    restriction_groups: list[ChangeSheetRestrictionGroup] = Field(default_factory=list)
    note: str | None = None
    status: ConflictHandlingStatus
    review_needed: bool
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class ChangeSheetReconfirmationItem(ChangeSheetAcknowledgement):
    handling_type: Literal["replacement", "manual_acknowledgement"]
    group_id: uuid.UUID | None = None
    replacement_dish: MenuConflictTargetSummary | None = None


class ChangeSheetResponse(BaseModel):
    target_date: date
    postpartum_meal: Meal
    meal_label: str
    summary: ChangeSheetSummary
    replacement_groups: list[ChangeSheetReplacementGroup]
    manual_acknowledgements: list[ChangeSheetAcknowledgement]
    requires_reconfirmation: list[ChangeSheetReconfirmationItem]
    warnings: list[MenuConflictWarning] = Field(default_factory=list)


class ChangeSheetMealResponse(ChangeSheetResponse):
    has_changes: bool


class ChangeSheetDailyResponse(BaseModel):
    target_date: date
    summary: ChangeSheetSummary
    meals: list[ChangeSheetMealResponse]
    warnings: list[MenuConflictWarning] = Field(default_factory=list)
