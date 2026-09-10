import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.postpartum.exceptions import (
    InvalidPostpartumDataError, InvalidPostpartumMenuSourceError, InvalidPostpartumRestrictionAssociationError,
    PostpartumCaseNotFoundError, PostpartumPauseNotFoundError,
    PostpartumRestrictionGroupNameExistsError, PostpartumRestrictionGroupNotFoundError,
    PostpartumMenuSourceNotFoundError,
)
from app.domains.postpartum.meals import MEAL_ORDER, MEAL_VALUES
from app.domains.postpartum.models import (
    PostpartumCase, PostpartumMenuSource, PostpartumRestrictionGroup, PostpartumRoomHistory,
    PostpartumServicePause,
)
from app.domains.postpartum.repository import PostpartumRepository
from app.domains.postpartum.schemas import (
    CaseCreate, CaseRestrictionGroupsReplace, CaseUpdate, PauseCreate, PauseUpdate, RestrictionAssociationsReplace,
    RestrictionGroupCreate, RestrictionGroupUpdate, RoomChangeCreate,
    MenuSourceReplace,
)
from app.domains.postpartum.timeline import valid_interval


class PostpartumService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = PostpartumRepository(session)
        self.audit = AuditLogService(session)

    def case(self, case_id):
        value = self.repository.case(case_id)
        if value is None: raise PostpartumCaseNotFoundError()
        return value

    @staticmethod
    def _menu_source_snapshot(menu_id, mappings):
        return {
            "menu_id": menu_id,
            "mappings": [
                {"postpartum_meal": meal, "menu_meal_type_id": meal_type_id}
                for meal, meal_type_id in sorted(mappings, key=lambda item: MEAL_ORDER[item[0]])
            ],
        }

    def _menu_source_view(self, source, menu):
        rows = self.repository.menu_source_mappings(source.id)
        mappings = sorted(rows, key=lambda row: MEAL_ORDER.get(row[0].postpartum_meal, len(MEAL_ORDER)))
        warnings = []
        if not menu.is_active:
            warnings.append({"code": "MENU_INACTIVE", "message": "目前菜單來源已停用", "postpartum_meal": None})
        for mapping, meal_type in mappings:
            if not meal_type.is_active:
                warnings.append({
                    "code": "MEAL_TYPE_INACTIVE", "message": f"餐別「{meal_type.name}」已停用",
                    "postpartum_meal": mapping.postpartum_meal,
                })
            if meal_type.menu_id != source.menu_id:
                warnings.append({
                    "code": "MEAL_TYPE_MENU_MISMATCH", "message": "餐別不屬於目前菜單來源",
                    "postpartum_meal": mapping.postpartum_meal,
                })
        overlapping = self.repository.overlapping_menu_sources(
            menu.start_date, menu.end_date, exclude_source_id=source.id,
        )
        if overlapping:
            warnings.append({
                "code": "SOURCE_DATE_OVERLAP",
                "message": "此菜單來源日期與其他月子餐菜單來源重疊",
                "postpartum_meal": None,
            })
        mapped = {mapping.postpartum_meal: meal_type for mapping, meal_type in mappings}
        return {
            "id": source.id,
            "configured": True,
            "usable": bool(mappings),
            "menu": {
                "id": menu.id, "name": menu.name, "start_date": menu.start_date,
                "end_date": menu.end_date, "is_active": menu.is_active,
            },
            "mappings": [{
                "postpartum_meal": mapping.postpartum_meal,
                "menu_meal_type": {
                    "id": meal_type.id, "name": meal_type.name,
                    "sort_order": meal_type.sort_order, "is_active": meal_type.is_active,
                },
            } for mapping, meal_type in mappings],
            "meal_statuses": [{
                "postpartum_meal": meal,
                "mapped": meal in mapped,
                "menu_meal_type": None if meal not in mapped else {
                    "id": mapped[meal].id, "name": mapped[meal].name,
                    "sort_order": mapped[meal].sort_order, "is_active": mapped[meal].is_active,
                },
            } for meal in MEAL_VALUES],
            "warnings": warnings,
        }

    def menu_sources(self, from_date=None, to_date=None):
        if from_date is not None and to_date is not None and from_date > to_date:
            raise InvalidPostpartumMenuSourceError("from_date must not be later than to_date")
        rows = self.repository.menu_sources(from_date, to_date)
        return [self._menu_source_view(source, menu) for source, menu in rows]

    def menu_source(self, source_id):
        rows = self.repository.menu_sources()
        for source, menu in rows:
            if source.id == source_id:
                return self._menu_source_view(source, menu)
        raise PostpartumMenuSourceNotFoundError()

    def _validate_menu_source(self, data, exclude_source_id=None):
        mapping_meals = [item.postpartum_meal for item in data.mappings]
        meal_type_ids = [item.menu_meal_type_id for item in data.mappings]
        if not data.mappings:
            raise InvalidPostpartumMenuSourceError("At least one postpartum meal mapping is required")
        if len(set(mapping_meals)) != len(mapping_meals):
            raise InvalidPostpartumMenuSourceError("A postpartum meal may be mapped only once")
        if len(set(meal_type_ids)) != len(meal_type_ids):
            raise InvalidPostpartumMenuSourceError("A MenuMealType may be mapped only once")
        menu = self.repository.menu(data.menu_id)
        if menu is None or not menu.is_active:
            raise InvalidPostpartumMenuSourceError("Selected menu must exist and be active")
        meal_types = self.repository.menu_meal_types(set(meal_type_ids))
        if set(meal_types) != set(meal_type_ids):
            raise InvalidPostpartumMenuSourceError("Every mapped MenuMealType must exist")
        if any(item.menu_id != menu.id for item in meal_types.values()):
            raise InvalidPostpartumMenuSourceError("Every mapped MenuMealType must belong to the selected menu")
        if any(not item.is_active for item in meal_types.values()):
            raise InvalidPostpartumMenuSourceError("Every mapped MenuMealType must be active")
        existing_for_menu = self.repository.menu_source_by_menu(menu.id)
        if existing_for_menu is not None and existing_for_menu.id != exclude_source_id:
            raise InvalidPostpartumMenuSourceError("This menu already has a postpartum source")
        if self.repository.overlapping_menu_sources(menu.start_date, menu.end_date, exclude_source_id):
            raise InvalidPostpartumMenuSourceError("Configured postpartum menu date ranges must not overlap")
        return menu

    def create_menu_source(self, data: MenuSourceReplace, actor_id):
        try:
            menu = self._validate_menu_source(data)
            source = PostpartumMenuSource(
                id=uuid.uuid4(), menu_id=menu.id, created_by=actor_id, updated_by=actor_id,
            )
            self.repository.add(source)
            self.session.flush()
            requested = [(item.postpartum_meal, item.menu_meal_type_id) for item in data.mappings]
            self.repository.replace_menu_source_mappings(source.id, requested)
            after = self._menu_source_snapshot(menu.id, requested)
            self.audit.record(
                actor_id=actor_id, action="postpartum_menu_source_create",
                entity_type="postpartum_menu_source", entity_id=source.id, entity_label=menu.name,
                after_data=after,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.menu_source(source.id)

    def update_menu_source(self, source_id, data: MenuSourceReplace, actor_id):
        try:
            source = self.repository.menu_source_for_update(source_id)
            if source is None:
                raise PostpartumMenuSourceNotFoundError()
            menu = self._validate_menu_source(data, source.id)
            existing = self.repository.menu_source_mappings(source.id)
            before = self._menu_source_snapshot(
                source.menu_id,
                [(mapping.postpartum_meal, mapping.menu_meal_type_id) for mapping, _ in existing],
            )
            requested = [(item.postpartum_meal, item.menu_meal_type_id) for item in data.mappings]
            source.menu_id = menu.id
            source.updated_by = actor_id
            self.repository.replace_menu_source_mappings(source.id, requested)
            self.audit.record(
                actor_id=actor_id, action="postpartum_menu_source_update",
                entity_type="postpartum_menu_source", entity_id=source.id, entity_label=menu.name,
                before_data=before, after_data=self._menu_source_snapshot(menu.id, requested),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.menu_source(source.id)

    def list(self, page, page_size, active, status, search):
        values, total = self.repository.list_cases(page, page_size, active, status, search)
        groups = self.repository.case_restriction_groups([value.id for value in values])
        return [{"case": value, "restriction_groups": groups.get(value.id, [])} for value in values], total

    def detail(self, case_id):
        value = self.case(case_id)
        groups = self.repository.case_restriction_groups([case_id])
        return {"case": value, "room_history": self.repository.room_history(case_id),
                "pauses": self.repository.pauses(case_id), "restriction_groups": groups.get(case_id, [])}

    def replace_case_restriction_groups(self, case_id, data: CaseRestrictionGroupsReplace, actor_id):
        try:
            value = self.repository.case_for_update(case_id)
            if value is None:
                raise PostpartumCaseNotFoundError()
            requested_ids = set(data.restriction_group_ids)
            existing_ids = self.repository.case_restriction_group_ids(case_id)
            group_models = self.repository.restriction_group_models(requested_ids)
            if set(group_models) != requested_ids:
                raise InvalidPostpartumRestrictionAssociationError("Every requested restriction group must exist")
            if any(not group_models[group_id].is_active for group_id in requested_ids - existing_ids):
                raise InvalidPostpartumRestrictionAssociationError("New restriction group assignments must be active")
            self.repository.replace_case_restriction_groups(case_id, existing_ids, requested_ids)
            value.updated_by = actor_id
            self.audit.record(
                actor_id=actor_id, action="postpartum_case_restriction_groups_replace",
                entity_type="postpartum_case", entity_id=value.id, entity_label=value.name,
                before_data={"restriction_group_ids": sorted(existing_ids, key=str)},
                after_data={"restriction_group_ids": sorted(requested_ids, key=str)},
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        groups = self.repository.case_restriction_groups([case_id])
        return {"case_id": case_id, "restriction_groups": groups.get(case_id, [])}

    @staticmethod
    def _validate_service(start_date, start_meal, end_date, end_meal):
        if (end_date is None) != (end_meal is None):
            raise InvalidPostpartumDataError("Service end date and meal must be provided together")
        if end_date is not None and not valid_interval(start_date, start_meal, end_date, end_meal):
            raise InvalidPostpartumDataError("Service end must not precede service start")

    def create(self, data: CaseCreate, actor_id):
        self._validate_service(data.service_start_date, data.service_start_meal, data.service_end_date, data.service_end_meal)
        value = PostpartumCase(id=uuid.uuid4(), **data.model_dump(), created_by=actor_id, updated_by=actor_id)
        room = PostpartumRoomHistory(id=uuid.uuid4(), case_id=value.id, room=data.current_room,
            effective_date=data.service_start_date, effective_meal=data.service_start_meal,
            created_by=actor_id, updated_by=actor_id)
        self.repository.add(value); self.repository.add(room)
        self.audit.record(actor_id=actor_id, action="postpartum_case_create", entity_type="postpartum_case",
            entity_id=value.id, entity_label=value.name, after_data=audit_snapshot(value, "case_number", "name", "current_room", "status"))
        try: self.session.commit()
        except Exception: self.session.rollback(); raise
        return value

    def update(self, case_id, data: CaseUpdate, actor_id):
        value = self.case(case_id)
        before = audit_snapshot(value, "case_number", "name", "delivery_type", "delivery_date", "service_start_date", "service_start_meal", "service_end_date", "service_end_meal", "status", "preparation_mode", "service_note", "is_active")
        changes = data.model_dump(exclude_unset=True)
        start_date = changes.get("service_start_date", value.service_start_date)
        start_meal = changes.get("service_start_meal", value.service_start_meal)
        end_date = changes.get("service_end_date", value.service_end_date)
        end_meal = changes.get("service_end_meal", value.service_end_meal)
        self._validate_service(start_date, start_meal, end_date, end_meal)
        for field, item in changes.items(): setattr(value, field, item)
        value.updated_by = actor_id
        self.audit.record(actor_id=actor_id, action="postpartum_case_update", entity_type="postpartum_case",
            entity_id=value.id, entity_label=value.name, before_data=before,
            after_data=audit_snapshot(value, "case_number", "name", "delivery_type", "delivery_date", "service_start_date", "service_start_meal", "service_end_date", "service_end_meal", "status", "preparation_mode", "service_note", "is_active"))
        self.session.commit(); return value

    def set_active(self, case_id, active, actor_id):
        value = self.case(case_id); before = audit_snapshot(value, "is_active")
        value.is_active = active; value.updated_by = actor_id
        self.audit.record(actor_id=actor_id, action="postpartum_case_reactivate" if active else "postpartum_case_deactivate",
            entity_type="postpartum_case", entity_id=value.id, entity_label=value.name, before_data=before,
            after_data=audit_snapshot(value, "is_active"))
        self.session.commit(); return value

    def change_room(self, case_id, data: RoomChangeCreate, actor_id):
        try:
            value = self.repository.case_for_update(case_id)
            if value is None: raise PostpartumCaseNotFoundError()
            before = value.current_room
            history = PostpartumRoomHistory(id=uuid.uuid4(), case_id=case_id, **data.model_dump(), created_by=actor_id, updated_by=actor_id)
            self.repository.add(history)
            value.current_room = data.room
            value.updated_by = actor_id
            self.audit.record(actor_id=actor_id, action="postpartum_room_change", entity_type="postpartum_case",
                entity_id=value.id, entity_label=value.name, before_data={"current_room": before}, after_data={"current_room": value.current_room})
            self.session.commit()
            return history
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _validate_pause(start_date, start_meal, end_date, end_meal):
        if not valid_interval(start_date, start_meal, end_date, end_meal):
            raise InvalidPostpartumDataError("Pause end must not precede pause start")

    def create_pause(self, case_id, data: PauseCreate, actor_id):
        value = self.case(case_id); self._validate_pause(data.start_date, data.start_meal, data.end_date, data.end_meal)
        pause = PostpartumServicePause(id=uuid.uuid4(), case_id=case_id, **data.model_dump(), created_by=actor_id, updated_by=actor_id)
        self.repository.add(pause)
        self.audit.record(actor_id=actor_id, action="postpartum_pause_create", entity_type="postpartum_service_pause",
            entity_id=pause.id, entity_label=value.name, after_data=audit_snapshot(pause, "case_id", "start_date", "start_meal", "end_date", "end_meal", "note"))
        self.session.commit(); return pause

    def _pause(self, case_id, pause_id):
        self.case(case_id); value = self.repository.pause(pause_id)
        if value is None or value.case_id != case_id: raise PostpartumPauseNotFoundError()
        return value

    def update_pause(self, case_id, pause_id, data: PauseUpdate, actor_id):
        value = self._pause(case_id, pause_id); before = audit_snapshot(value, "start_date", "start_meal", "end_date", "end_meal", "note")
        changes = data.model_dump(exclude_unset=True)
        start_date=changes.get("start_date",value.start_date); start_meal=changes.get("start_meal",value.start_meal)
        end_date=changes.get("end_date",value.end_date); end_meal=changes.get("end_meal",value.end_meal)
        self._validate_pause(start_date,start_meal,end_date,end_meal)
        for field,item in changes.items(): setattr(value,field,item)
        value.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="postpartum_pause_update",entity_type="postpartum_service_pause",
            entity_id=value.id,before_data=before,after_data=audit_snapshot(value,"start_date","start_meal","end_date","end_meal","note"))
        self.session.commit(); return value

    def delete_pause(self, case_id, pause_id, actor_id):
        value=self._pause(case_id,pause_id); before=audit_snapshot(value,"case_id","start_date","start_meal","end_date","end_meal","note")
        self.repository.delete(value)
        self.audit.record(actor_id=actor_id,action="postpartum_pause_delete",entity_type="postpartum_service_pause",
            entity_id=value.id,before_data=before)
        self.session.commit()

    def restriction_group(self, group_id):
        value = self.repository.restriction_group(group_id)
        if value is None:
            raise PostpartumRestrictionGroupNotFoundError()
        return value

    def list_restriction_groups(self, page, page_size, active, search):
        return self.repository.list_restriction_groups(page, page_size, active, search)

    def restriction_group_detail(self, group_id):
        value = self.restriction_group(group_id)
        ingredients = self.repository.restriction_ingredients(group_id)
        dishes = self.repository.restriction_dishes(group_id)
        group = {
            "id": value.id, "name": value.name, "color": value.color, "notes": value.notes,
            "is_active": value.is_active, "ingredient_count": len(ingredients), "dish_count": len(dishes),
            "created_at": value.created_at, "updated_at": value.updated_at,
            "created_by": value.created_by, "updated_by": value.updated_by,
        }
        return {"group": group, "ingredients": ingredients, "dishes": dishes}

    def create_restriction_group(self, data: RestrictionGroupCreate, actor_id):
        name = data.name.strip()
        if self.repository.restriction_group_name_exists(name):
            raise PostpartumRestrictionGroupNameExistsError()
        value = PostpartumRestrictionGroup(
            id=uuid.uuid4(), name=name, color=data.color.upper(), notes=data.notes,
            created_by=actor_id, updated_by=actor_id,
        )
        self.repository.add(value)
        self.audit.record(
            actor_id=actor_id, action="postpartum_restriction_group_create",
            entity_type="postpartum_restriction_group", entity_id=value.id, entity_label=value.name,
            after_data=audit_snapshot(value, "name", "color", "notes", "is_active"),
        )
        self._commit_restriction_group()
        self.session.refresh(value)
        return value

    def update_restriction_group(self, group_id, data: RestrictionGroupUpdate, actor_id):
        value = self.restriction_group(group_id)
        before = audit_snapshot(value, "name", "color", "notes", "is_active")
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes:
            changes["name"] = changes["name"].strip()
            if self.repository.restriction_group_name_exists(changes["name"], group_id):
                raise PostpartumRestrictionGroupNameExistsError()
        if "color" in changes:
            changes["color"] = changes["color"].upper()
        for field, item in changes.items():
            setattr(value, field, item)
        value.updated_by = actor_id
        self.audit.record(
            actor_id=actor_id, action="postpartum_restriction_group_update",
            entity_type="postpartum_restriction_group", entity_id=value.id, entity_label=value.name,
            before_data=before, after_data=audit_snapshot(value, "name", "color", "notes", "is_active"),
        )
        self._commit_restriction_group()
        self.session.refresh(value)
        return value

    def set_restriction_group_active(self, group_id, active, actor_id):
        value = self.restriction_group(group_id)
        before = audit_snapshot(value, "is_active")
        value.is_active = active
        value.updated_by = actor_id
        self.audit.record(
            actor_id=actor_id,
            action="postpartum_restriction_group_reactivate" if active else "postpartum_restriction_group_deactivate",
            entity_type="postpartum_restriction_group", entity_id=value.id, entity_label=value.name,
            before_data=before, after_data=audit_snapshot(value, "is_active"),
        )
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(value)
        return value

    def replace_restriction_associations(self, group_id, data: RestrictionAssociationsReplace, actor_id):
        value = self.restriction_group(group_id)
        requested_ingredients = set(data.ingredient_ids)
        requested_dishes = set(data.dish_ids)
        existing_ingredients = self.repository.restriction_ingredient_ids(group_id)
        existing_dishes = self.repository.restriction_dish_ids(group_id)
        ingredient_models = self.repository.ingredient_models(requested_ingredients)
        dish_models = self.repository.dish_models(requested_dishes)
        if set(ingredient_models) != requested_ingredients:
            raise InvalidPostpartumRestrictionAssociationError("Every requested Ingredient must exist")
        if set(dish_models) != requested_dishes:
            raise InvalidPostpartumRestrictionAssociationError("Every requested Dish must exist")
        if any(not ingredient_models[item].is_active for item in requested_ingredients - existing_ingredients):
            raise InvalidPostpartumRestrictionAssociationError("New Ingredient associations must be active")
        if any(not dish_models[item].is_active for item in requested_dishes - existing_dishes):
            raise InvalidPostpartumRestrictionAssociationError("New Dish associations must be active")
        try:
            self.repository.replace_restriction_ingredients(group_id, existing_ingredients, requested_ingredients)
            self.repository.replace_restriction_dishes(group_id, existing_dishes, requested_dishes)
            value.updated_by = actor_id
            self.audit.record(
                actor_id=actor_id, action="postpartum_restriction_associations_replace",
                entity_type="postpartum_restriction_group", entity_id=value.id, entity_label=value.name,
                before_data={"ingredient_ids": sorted(existing_ingredients, key=str), "dish_ids": sorted(existing_dishes, key=str)},
                after_data={"ingredient_ids": sorted(requested_ingredients, key=str), "dish_ids": sorted(requested_dishes, key=str)},
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.restriction_group_detail(group_id)

    def _commit_restriction_group(self):
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            constraint = getattr(getattr(getattr(exc, "orig", None), "diag", None), "constraint_name", None)
            if constraint == "uq_postpartum_restriction_groups_name_normalized":
                raise PostpartumRestrictionGroupNameExistsError() from exc
            raise
