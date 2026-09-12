import uuid
from datetime import timedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.postpartum.conflicts import evaluate_case_dish_conflicts, evaluate_replacement_candidates
from app.domains.postpartum.change_sheet import build_change_sheet, build_daily_change_sheet
from app.domains.postpartum.exceptions import (
    InvalidPostpartumDataError, InvalidPostpartumMenuSourceError, InvalidPostpartumRestrictionAssociationError,
    PostpartumCaseNotFoundError, PostpartumPauseNotFoundError,
    PostpartumRestrictionGroupNameExistsError, PostpartumRestrictionGroupNotFoundError,
    PostpartumMenuSourceNotFoundError, PostpartumReplacementGroupNotFoundError,
    PostpartumConflictHandlingNotFoundError, InvalidPostpartumReplacementError,
    PostpartumConflictAlreadyHandledError,
)
from app.domains.postpartum.meals import MEAL_ORDER, MEAL_VALUES
from app.domains.postpartum.models import (
    PostpartumCase, PostpartumMenuSource, PostpartumRestrictionGroup, PostpartumRoomHistory,
    PostpartumServicePause, PostpartumReplacementGroup, PostpartumConflictHandling,
)
from app.domains.postpartum.repository import PostpartumRepository
from app.domains.postpartum.schemas import (
    CaseCreate, CaseRestrictionGroupsReplace, CaseUpdate, PauseCreate, PauseUpdate, RestrictionAssociationsReplace,
    RestrictionGroupCreate, RestrictionGroupUpdate, RoomChangeCreate,
    MenuSourceReplace, ReplacementGroupCreate, ReplacementGroupUpdate,
    ConflictAcknowledgementCreate, ReplacementCandidateSearch,
)
from app.domains.postpartum.timeline import service_is_eligible_at, valid_interval


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

    @staticmethod
    def _conflict_source_summary(row):
        return {
            "source_id": row["source_id"], "menu_id": row["menu_id"],
            "menu_name": row["menu_name"], "start_date": row["start_date"],
            "end_date": row["end_date"], "is_active": row["menu_is_active"],
        }

    def _load_conflict_context(self, start_date, end_date):
        source_rows = self.repository.conflict_sources_range(start_date, end_date)
        sources = {}
        for row in source_rows:
            source = sources.setdefault(row["source_id"], {
                **self._conflict_source_summary(row), "mappings": {},
            })
            if row["postpartum_meal"] is not None:
                source["mappings"][row["postpartum_meal"]] = row

        menu_rows = self.repository.conflict_menu_rows_range(
            {item["menu_id"] for item in sources.values()}, start_date, end_date,
        )
        menu_rows_by_slot = {}
        for row in menu_rows:
            menu_rows_by_slot.setdefault((
                row["menu_id"], row["menu_date"], row["menu_meal_type_id"],
            ), []).append(row)

        candidate_cases = self.repository.conflict_case_candidates_range(start_date, end_date)
        candidate_ids = [item.id for item in candidate_cases]
        pauses_by_case = {case_id: [] for case_id in candidate_ids}
        for pause in self.repository.conflict_pauses(candidate_ids):
            pauses_by_case[pause.case_id].append((
                pause.start_date, pause.start_meal, pause.end_date, pause.end_meal,
            ))

        group_rows = self.repository.conflict_case_groups(candidate_ids)
        groups_by_case = {case_id: [] for case_id in candidate_ids}
        groups = {}
        for row in group_rows:
            group_id = row["restriction_group_id"]
            groups_by_case[row["case_id"]].append(group_id)
            groups[group_id] = {
                "id": group_id, "name": row["name"], "color": row["color"],
                "notes": row["notes"], "is_active": row["is_active"],
            }
        group_ids = set(groups)
        dish_targets_by_group = {group_id: {} for group_id in group_ids}
        for row in self.repository.conflict_group_dishes(group_ids):
            dish_targets_by_group[row["restriction_group_id"]][row["id"]] = {
                "id": row["id"], "code": row["code"], "name": row["name"],
                "is_active": row["is_active"],
            }
        ingredient_targets_by_group = {group_id: {} for group_id in group_ids}
        for row in self.repository.conflict_group_ingredients(group_ids):
            ingredient_targets_by_group[row["restriction_group_id"]][row["id"]] = {
                "id": row["id"], "code": row["code"], "name": row["name"],
                "is_active": row["is_active"],
            }
        dish_ids = {row["dish_id"] for row in menu_rows if row["dish_id"] is not None}
        recipe_ingredients_by_dish = {dish_id: {} for dish_id in dish_ids}
        for row in self.repository.conflict_recipe_ingredients(dish_ids):
            recipe_ingredients_by_dish[row["dish_id"]][row["id"]] = {
                "id": row["id"], "code": row["code"], "name": row["name"],
                "is_active": row["is_active"],
            }
        return {
            "sources": list(sources.values()), "menu_rows_by_slot": menu_rows_by_slot,
            "candidate_cases": candidate_cases, "pauses_by_case": pauses_by_case,
            "groups_by_case": groups_by_case, "groups": groups,
            "dish_targets_by_group": dish_targets_by_group,
            "ingredient_targets_by_group": ingredient_targets_by_group,
            "recipe_ingredients_by_dish": recipe_ingredients_by_dish,
        }

    def _menu_conflicts_from_context(self, target_date, postpartum_meal, context):
        source_rows = [item for item in context["sources"] if (
            item["start_date"] <= target_date <= item["end_date"]
        )]
        candidates = [{key: item[key] for key in (
            "source_id", "menu_id", "menu_name", "start_date", "end_date", "is_active",
        )} for item in source_rows]
        base = {
            "target_date": target_date,
            "postpartum_meal": postpartum_meal,
            "evaluation_status": "unavailable",
            "evaluation_performed": False,
            "source_resolution": {
                "status": "not_configured", "source": None, "candidates": candidates,
            },
            "mapping_resolution": {"status": "not_checked", "menu_meal_type": None},
            "menu_day": None,
            "menu_dishes": [],
            "eligible_cases": [],
            "case_dish_results": [],
            "warnings": [],
        }
        if not source_rows:
            base["warnings"] = [{"code": "SOURCE_NOT_CONFIGURED", "message": "此日期沒有月子餐 ERP 菜單來源"}]
            return base
        if len(source_rows) > 1:
            base["source_resolution"]["status"] = "ambiguous"
            base["warnings"] = [{"code": "SOURCE_AMBIGUOUS", "message": "此日期有多份重疊的月子餐菜單來源，已停止檢查"}]
            return base

        source_record = source_rows[0]
        source_summary = candidates[0]
        base["source_resolution"].update({"status": "available", "source": source_summary})
        if not source_record["is_active"]:
            base["source_resolution"]["status"] = "inactive"
            base["warnings"] = [{"code": "MENU_INACTIVE", "message": "此日期的月子餐菜單來源已停用"}]
            return base
        source = source_record["mappings"].get(postpartum_meal)
        if source is None:
            base["mapping_resolution"]["status"] = "not_mapped"
            return base

        meal_type = None
        if source["menu_meal_type_id"] is not None:
            meal_type = {
                "id": source["menu_meal_type_id"], "name": source["menu_meal_type_name"],
                "sort_order": source["menu_meal_type_sort_order"],
                "is_active": source["menu_meal_type_is_active"],
            }
        base["mapping_resolution"] = {"status": "mapped", "menu_meal_type": meal_type}
        if source["mapped_menu_meal_type_id"] is not None and meal_type is None:
            base["mapping_resolution"]["status"] = "inconsistent"
            base["warnings"] = [{"code": "MEAL_TYPE_MISSING", "message": "餐別 mapping 的 ERP 餐別不存在"}]
            return base
        if source["menu_meal_type_menu_id"] != source["menu_id"]:
            base["mapping_resolution"]["status"] = "inconsistent"
            base["warnings"] = [{"code": "MEAL_TYPE_MENU_MISMATCH", "message": "餐別 mapping 不屬於目前菜單來源"}]
            return base
        if not source["menu_meal_type_is_active"]:
            base["mapping_resolution"]["status"] = "inactive"
            base["warnings"] = [{"code": "MEAL_TYPE_INACTIVE", "message": "餐別 mapping 的 ERP 餐別已停用"}]
            return base

        menu_rows = context["menu_rows_by_slot"].get((
            source["menu_id"], target_date, source["menu_meal_type_id"],
        ), [])
        if not menu_rows:
            base["warnings"] = [{"code": "MENU_DAY_NOT_CONFIGURED", "message": "此日期與餐別尚未建立 ERP 菜單內容"}]
            return base
        base["menu_day"] = {"id": menu_rows[0]["menu_day_id"], "menu_date": menu_rows[0]["menu_date"]}
        menu_dishes = [row for row in menu_rows if row["menu_dish_id"] is not None]

        candidate_cases = context["candidate_cases"]
        pauses_by_case = context["pauses_by_case"]
        eligible_cases = [item for item in candidate_cases if service_is_eligible_at(
            target_date, postpartum_meal,
            item.service_start_date, item.service_start_meal,
            item.service_end_date, item.service_end_meal,
            pauses_by_case[item.id],
        )]
        eligible_ids = [item.id for item in eligible_cases]

        groups_by_case = context["groups_by_case"]
        groups = context["groups"]

        dish_views, case_warnings, results = evaluate_case_dish_conflicts(
            case_ids=eligible_ids, menu_dishes=menu_dishes,
            groups_by_case=groups_by_case, groups=groups,
            dish_targets_by_group=context["dish_targets_by_group"],
            ingredient_targets_by_group=context["ingredient_targets_by_group"],
            recipe_ingredients_by_dish=context["recipe_ingredients_by_dish"],
        )
        base["menu_dishes"] = dish_views
        base["eligible_cases"] = [{
            "id": item.id, "case_number": item.case_number, "name": item.name,
            "current_room": item.current_room, "status": item.status,
            "restriction_groups": [groups[group_id] for group_id in groups_by_case[item.id]],
            "warnings": case_warnings[item.id],
        } for item in eligible_cases]
        base["case_dish_results"] = results
        base["evaluation_performed"] = True
        partial_group_codes = {"RESTRICTION_GROUP_NOTE_ONLY", "RESTRICTION_GROUP_NO_TARGETS"}
        partial = not menu_dishes or any(
            item["ingredient_coverage"] == "partial" for item in dish_views
        ) or any(
            warning["code"] in partial_group_codes
            for warnings in case_warnings.values() for warning in warnings
        )
        base["evaluation_status"] = "partial" if partial else "complete"
        if not menu_dishes:
            base["warnings"] = [{"code": "MENU_DISHES_EMPTY", "message": "此日期與餐別沒有 ERP 菜色可供檢查"}]
        return base

    @staticmethod
    def _conflict_summary(result):
        conflicts = [item for item in result["case_dish_results"] if item["outcome"] == "conflict"]
        manual_case_ids = {
            item["case_id"] for item in result["case_dish_results"]
            if item["outcome"] == "unknown" or item["coverage"] == "partial"
        }
        manual_case_ids.update(
            item["id"] for item in result["eligible_cases"] if item["warnings"]
        )
        if not result["evaluation_performed"]:
            status = "unmapped" if result["mapping_resolution"]["status"] == "not_mapped" else "unavailable"
        elif conflicts:
            status = "conflict"
        elif result["evaluation_status"] == "partial":
            status = "partial"
        else:
            status = "complete"
        source = result["source_resolution"]["source"]
        meal_type = result["mapping_resolution"]["menu_meal_type"]
        return {
            "target_date": result["target_date"], "postpartum_meal": result["postpartum_meal"],
            "status": status, "evaluation_status": result["evaluation_status"],
            "evaluation_performed": result["evaluation_performed"],
            "source_status": result["source_resolution"]["status"],
            "mapping_status": result["mapping_resolution"]["status"],
            "menu_name": None if source is None else source["menu_name"],
            "menu_meal_type_name": None if meal_type is None else meal_type["name"],
            "eligible_case_count": len(result["eligible_cases"]),
            "menu_dish_count": len(result["menu_dishes"]),
            "conflict_case_count": len({item["case_id"] for item in conflicts}),
            "conflict_count": len(conflicts),
            "manual_review_case_count": len(manual_case_ids),
            "warnings": result["warnings"],
        }

    def menu_conflicts(self, target_date, postpartum_meal):
        context = self._load_conflict_context(target_date, target_date)
        return self._menu_conflicts_from_context(target_date, postpartum_meal, context)

    def menu_conflicts_daily(self, target_date):
        context = self._load_conflict_context(target_date, target_date)
        meals = [self._menu_conflicts_from_context(target_date, meal, context) for meal in MEAL_VALUES]
        summaries = [self._conflict_summary(item) for item in meals]
        conflict_results = [
            result for meal in meals for result in meal["case_dish_results"]
            if result["outcome"] == "conflict"
        ]
        manual_case_ids = {
            result["case_id"] for meal in meals for result in meal["case_dish_results"]
            if result["outcome"] == "unknown" or result["coverage"] == "partial"
        }
        manual_case_ids.update(
            item["id"] for meal in meals for item in meal["eligible_cases"] if item["warnings"]
        )
        return {
            "target_date": target_date, "meals": meals, "summaries": summaries,
            "conflict_case_count": len({item["case_id"] for item in conflict_results}),
            "conflict_count": len(conflict_results),
            "manual_review_case_count": len(manual_case_ids),
        }

    def menu_conflicts_weekly(self, anchor_date):
        week_start = anchor_date - timedelta(days=anchor_date.weekday())
        week_end = week_start + timedelta(days=6)
        context = self._load_conflict_context(week_start, week_end)
        days = []
        for offset in range(7):
            target_date = week_start + timedelta(days=offset)
            evaluations = [
                self._menu_conflicts_from_context(target_date, meal, context) for meal in MEAL_VALUES
            ]
            days.append({
                "target_date": target_date,
                "meals": [self._conflict_summary(item) for item in evaluations],
            })
        return {"week_start": week_start, "week_end": week_end, "days": days}

    @staticmethod
    def _handling_key(item):
        return item.case_id, item.original_menu_dish_id

    def _validate_conflict_items(self, target_date, postpartum_meal, items, context=None):
        if len({self._handling_key(item) for item in items}) != len(items):
            raise InvalidPostpartumReplacementError("同一衝突項目不可重複")
        context = context or self._load_conflict_context(target_date, target_date)
        evaluation = self._menu_conflicts_from_context(target_date, postpartum_meal, context)
        if not evaluation["evaluation_performed"]:
            raise InvalidPostpartumReplacementError("目前日期與餐次無法執行禁忌檢查")
        menu_dishes = {item["menu_dish_id"]: item for item in evaluation["menu_dishes"]}
        eligible_cases = {item["id"] for item in evaluation["eligible_cases"]}
        conflicts = {
            (item["case_id"], item["menu_dish_id"]): item
            for item in evaluation["case_dish_results"] if item["outcome"] == "conflict"
        }
        for item in items:
            dish = menu_dishes.get(item.original_menu_dish_id)
            if item.case_id not in eligible_cases or dish is None:
                raise InvalidPostpartumReplacementError("衝突項目不屬於目前日期、餐次或供餐個案")
            if dish["dish"]["id"] != item.original_dish_id:
                raise InvalidPostpartumReplacementError("原菜色資料已變更，請重新確認")
            if (item.case_id, item.original_menu_dish_id) not in conflicts:
                raise InvalidPostpartumReplacementError("只能處理目前仍存在的已確認禁忌衝突")
        return context, evaluation

    def _candidate_assessment(self, dish, case_ids, context, recipe_map=None):
        if recipe_map is None:
            recipe_map = {dish["id"]: {}}
            for row in self.repository.conflict_recipe_ingredients({dish["id"]}):
                recipe_map[dish["id"]][row["id"]] = {
                    "id": row["id"], "code": row["code"], "name": row["name"],
                    "is_active": row["is_active"],
                }
        return evaluate_replacement_candidates(
            candidate_dishes=[dish], case_ids=case_ids,
            groups_by_case=context["groups_by_case"], groups=context["groups"],
            dish_targets_by_group=context["dish_targets_by_group"],
            ingredient_targets_by_group=context["ingredient_targets_by_group"],
            recipe_ingredients_by_dish=recipe_map,
        )[0]

    def replacement_candidates(self, data: ReplacementCandidateSearch):
        context, _ = self._validate_conflict_items(
            data.target_date, data.postpartum_meal, data.items,
        )
        dishes, total = self.repository.replacement_candidate_dishes(
            data.page, data.page_size, data.search, data.category_id,
        )
        recipe_map = {dish["id"]: {} for dish in dishes}
        for row in self.repository.conflict_recipe_ingredients(set(recipe_map)):
            recipe_map[row["dish_id"]][row["id"]] = {
                "id": row["id"], "code": row["code"], "name": row["name"],
                "is_active": row["is_active"],
            }
        results = evaluate_replacement_candidates(
            candidate_dishes=dishes, case_ids=sorted({item.case_id for item in data.items}, key=str),
            groups_by_case=context["groups_by_case"], groups=context["groups"],
            dish_targets_by_group=context["dish_targets_by_group"],
            ingredient_targets_by_group=context["ingredient_targets_by_group"],
            recipe_ingredients_by_dish=recipe_map,
        )
        return results, total

    @staticmethod
    def _group_snapshot(group, handlings):
        return {
            "target_date": group.target_date, "postpartum_meal": group.postpartum_meal,
            "replacement_dish_id": group.replacement_dish_id, "note": group.note,
            "items": [{
                "case_id": item.case_id, "original_menu_dish_id": item.original_menu_dish_id,
                "original_dish_id": item.original_dish_id, "note": item.note,
            } for item in sorted(handlings, key=lambda row: (str(row.case_id), str(row.original_menu_dish_id)))],
        }

    def _new_handling(self, target_date, postpartum_meal, item, actor_id, group_id=None, note=None):
        return PostpartumConflictHandling(
            id=uuid.uuid4(), target_date=target_date, postpartum_meal=postpartum_meal,
            case_id=item.case_id, original_menu_dish_id=item.original_menu_dish_id,
            original_dish_id=item.original_dish_id, replacement_group_id=group_id,
            note=note, created_by=actor_id, updated_by=actor_id,
        )

    def create_replacement_group(self, data: ReplacementGroupCreate, actor_id):
        try:
            context, _ = self._validate_conflict_items(data.target_date, data.postpartum_meal, data.items)
            dish_model = self.repository.dish_models({data.replacement_dish_id}).get(data.replacement_dish_id)
            if dish_model is None or not dish_model.is_active:
                raise InvalidPostpartumReplacementError("替代菜必須存在且啟用")
            dish = {"id": dish_model.id, "code": dish_model.code, "name": dish_model.name, "is_active": dish_model.is_active}
            assessment = self._candidate_assessment(dish, sorted({item.case_id for item in data.items}, key=str), context)
            if assessment["status"] == "conflict":
                raise InvalidPostpartumReplacementError("替代菜仍命中所選個案禁忌")
            if self.repository.conflict_handlings_for_items(
                [item.model_dump() for item in data.items], for_update=True,
            ):
                raise PostpartumConflictAlreadyHandledError("衝突項目已被處理")
            group = PostpartumReplacementGroup(
                id=uuid.uuid4(), target_date=data.target_date, postpartum_meal=data.postpartum_meal,
                replacement_dish_id=data.replacement_dish_id, note=data.note,
                created_by=actor_id, updated_by=actor_id,
            )
            self.repository.add(group)
            # No ORM relationship is needed for these write-only aggregates, so
            # flush the parent explicitly before inserting composite-FK items.
            self.session.flush()
            handlings = [self._new_handling(
                data.target_date, data.postpartum_meal, item, actor_id, group.id,
            ) for item in data.items]
            for handling in handlings:
                self.repository.add(handling)
            self.audit.record(
                actor_id=actor_id, action="postpartum_replacement_group_create",
                entity_type="postpartum_replacement_group", entity_id=group.id,
                entity_label=dish_model.name, after_data=self._group_snapshot(group, handlings),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.replacement_group(data.target_date, data.postpartum_meal, group.id)

    def update_replacement_group(self, group_id, data: ReplacementGroupUpdate, actor_id):
        try:
            group = self.repository.replacement_group(group_id, for_update=True)
            if group is None:
                raise PostpartumReplacementGroupNotFoundError()
            context, _ = self._validate_conflict_items(group.target_date, group.postpartum_meal, data.items)
            dish_model = self.repository.dish_models({data.replacement_dish_id}).get(data.replacement_dish_id)
            if dish_model is None or not dish_model.is_active:
                raise InvalidPostpartumReplacementError("替代菜必須存在且啟用")
            assessment = self._candidate_assessment(
                {"id": dish_model.id, "code": dish_model.code, "name": dish_model.name, "is_active": True},
                sorted({item.case_id for item in data.items}, key=str), context,
            )
            if assessment["status"] == "conflict":
                raise InvalidPostpartumReplacementError("替代菜仍命中所選個案禁忌")
            existing = self.repository.conflict_handlings(
                group.target_date, group.postpartum_meal, for_update=True,
            )
            current = [item for item in existing if item.replacement_group_id == group.id]
            before = self._group_snapshot(group, current)
            requested_keys = {self._handling_key(item) for item in data.items}
            blockers = [item for item in existing if (
                (item.case_id, item.original_menu_dish_id) in requested_keys
                and item.replacement_group_id != group.id
            )]
            if blockers and not data.reassign_items:
                raise PostpartumConflictAlreadyHandledError("衝突項目已被其他處理占用")
            source_group_ids = {
                item.replacement_group_id for item in blockers if item.replacement_group_id is not None
            }
            source_before = {}
            for source_group_id in source_group_ids:
                source_group = self.repository.replacement_group(source_group_id, for_update=True)
                source_members = [item for item in existing if item.replacement_group_id == source_group_id]
                if source_group is not None:
                    source_before[source_group_id] = (source_group, self._group_snapshot(source_group, source_members))
            for item in current:
                if (item.case_id, item.original_menu_dish_id) not in requested_keys:
                    self.repository.delete(item)
            if data.reassign_items:
                for item in blockers:
                    self.repository.delete(item)
                self.session.flush()
                remaining = self.repository.conflict_handlings(group.target_date, group.postpartum_meal)
                for source_group_id, (source_group, before_source) in source_before.items():
                    source_members = [item for item in remaining if item.replacement_group_id == source_group_id]
                    if source_members:
                        self.audit.record(
                            actor_id=actor_id, action="postpartum_replacement_group_update",
                            entity_type="postpartum_replacement_group", entity_id=source_group_id,
                            before_data=before_source,
                            after_data=self._group_snapshot(source_group, source_members),
                        )
                    else:
                        self.repository.delete(source_group)
                        self.audit.record(
                            actor_id=actor_id, action="postpartum_replacement_group_cancel",
                            entity_type="postpartum_replacement_group", entity_id=source_group_id,
                            before_data=before_source,
                        )
            current_keys = {(item.case_id, item.original_menu_dish_id) for item in current}
            requested_by_key = {self._handling_key(item): item for item in data.items}
            for handling in current:
                key = handling.case_id, handling.original_menu_dish_id
                requested = requested_by_key.get(key)
                if requested is not None:
                    handling.original_dish_id = requested.original_dish_id
                    handling.updated_by = actor_id
            for item in data.items:
                if self._handling_key(item) not in current_keys:
                    self.repository.add(self._new_handling(
                        group.target_date, group.postpartum_meal, item, actor_id, group.id,
                    ))
            group.replacement_dish_id = data.replacement_dish_id
            group.note = data.note
            group.updated_by = actor_id
            self.session.flush()
            final = [item for item in self.repository.conflict_handlings(
                group.target_date, group.postpartum_meal,
            ) if item.replacement_group_id == group.id]
            self.audit.record(
                actor_id=actor_id, action="postpartum_replacement_group_update",
                entity_type="postpartum_replacement_group", entity_id=group.id,
                entity_label=dish_model.name, before_data=before,
                after_data=self._group_snapshot(group, final),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.replacement_group(group.target_date, group.postpartum_meal, group.id)

    def cancel_replacement_group(self, group_id, actor_id):
        try:
            group = self.repository.replacement_group(group_id, for_update=True)
            if group is None:
                raise PostpartumReplacementGroupNotFoundError()
            handlings = [item for item in self.repository.conflict_handlings(
                group.target_date, group.postpartum_meal,
            ) if item.replacement_group_id == group.id]
            before = self._group_snapshot(group, handlings)
            self.repository.delete(group)
            self.audit.record(
                actor_id=actor_id, action="postpartum_replacement_group_cancel",
                entity_type="postpartum_replacement_group", entity_id=group.id,
                before_data=before,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def acknowledge_conflict(self, data: ConflictAcknowledgementCreate, actor_id):
        try:
            self._validate_conflict_items(data.target_date, data.postpartum_meal, [data.item])
            if self.repository.conflict_handlings_for_items([data.item.model_dump()], for_update=True):
                raise PostpartumConflictAlreadyHandledError("衝突項目已被處理")
            handling = self._new_handling(
                data.target_date, data.postpartum_meal, data.item, actor_id, note=data.note,
            )
            self.repository.add(handling)
            self.audit.record(
                actor_id=actor_id, action="postpartum_conflict_acknowledge",
                entity_type="postpartum_conflict_handling", entity_id=handling.id,
                after_data={
                    "target_date": handling.target_date, "postpartum_meal": handling.postpartum_meal,
                    "case_id": handling.case_id, "original_menu_dish_id": handling.original_menu_dish_id,
                    "original_dish_id": handling.original_dish_id, "note": handling.note,
                },
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        values = self.conflict_handlings(data.target_date, data.postpartum_meal)["manual_acknowledgements"]
        return next(item for item in values if item["id"] == handling.id)

    def cancel_acknowledgement(self, handling_id, actor_id):
        try:
            handling = self.repository.conflict_handling(handling_id, for_update=True)
            if handling is None or handling.replacement_group_id is not None:
                raise PostpartumConflictHandlingNotFoundError()
            before = {
                "target_date": handling.target_date, "postpartum_meal": handling.postpartum_meal,
                "case_id": handling.case_id, "original_menu_dish_id": handling.original_menu_dish_id,
                "original_dish_id": handling.original_dish_id, "note": handling.note,
            }
            self.repository.delete(handling)
            self.audit.record(
                actor_id=actor_id, action="postpartum_conflict_acknowledgement_cancel",
                entity_type="postpartum_conflict_handling", entity_id=handling.id, before_data=before,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _handling_item_view(self, handling, identities, dishes, status, current_conflicts):
        identity = identities.get(handling.original_menu_dish_id)
        stale = identity is None or identity["dish_id"] != handling.original_dish_id or (
            identity is not None and identity["menu_date"] != handling.target_date
        ) or (handling.case_id, handling.original_menu_dish_id) not in current_conflicts
        dish = dishes[handling.original_dish_id]
        warnings = [] if not stale else [{
            "code": "ORIGINAL_MENU_DISH_STALE",
            "message": "原菜單菜色已刪除、變更或移至其他日期，請重新確認",
            "case_id": handling.case_id, "menu_dish_id": handling.original_menu_dish_id,
        }]
        return {
            "id": handling.id, "case_id": handling.case_id,
            "original_menu_dish_id": handling.original_menu_dish_id,
            "original_dish": {"id": dish.id, "code": dish.code, "name": dish.name, "is_active": dish.is_active},
            "status": "requires_reconfirmation" if stale else status,
            "note": handling.note, "warnings": warnings,
        }

    def _load_change_sheet_context(self, target_date, postpartum_meal=None):
        groups = self.repository.replacement_groups(target_date, postpartum_meal)
        handlings = self.repository.conflict_handlings(target_date, postpartum_meal)
        identities = self.repository.menu_dish_identities({item.original_menu_dish_id for item in handlings})
        dish_ids = {item.original_dish_id for item in handlings} | {item.replacement_dish_id for item in groups}
        dishes = self.repository.dish_models(dish_ids)
        replacement_recipe_map = {item.replacement_dish_id: {} for item in groups}
        for row in self.repository.conflict_recipe_ingredients(set(replacement_recipe_map)):
            replacement_recipe_map[row["dish_id"]][row["id"]] = {
                "id": row["id"], "code": row["code"], "name": row["name"],
                "is_active": row["is_active"],
            }
        return {
            "groups": groups, "handlings": handlings, "identities": identities,
            "dishes": dishes, "conflict_context": self._load_conflict_context(target_date, target_date),
            "replacement_recipe_map": replacement_recipe_map,
        }

    def _conflict_handlings_from_context(self, target_date, postpartum_meal, preload):
        groups = [item for item in preload["groups"] if item.postpartum_meal == postpartum_meal]
        handlings = [item for item in preload["handlings"] if item.postpartum_meal == postpartum_meal]
        identities = preload["identities"]
        dishes = preload["dishes"]
        context = preload["conflict_context"]
        evaluation = self._menu_conflicts_from_context(target_date, postpartum_meal, context)
        current_conflicts = set() if not evaluation or not evaluation["evaluation_performed"] else {
            (item["case_id"], item["menu_dish_id"])
            for item in evaluation["case_dish_results"] if item["outcome"] == "conflict"
        }
        replacement_recipe_map = preload["replacement_recipe_map"]
        group_views = []
        for group in groups:
            members = [item for item in handlings if item.replacement_group_id == group.id]
            item_views = [self._handling_item_view(
                item, identities, dishes, "replaced", current_conflicts,
            ) for item in members]
            replacement = dishes[group.replacement_dish_id]
            assessment = self._candidate_assessment(
                {"id": replacement.id, "code": replacement.code, "name": replacement.name,
                 "is_active": replacement.is_active},
                sorted({item.case_id for item in members}, key=str), context,
                replacement_recipe_map,
            )
            reconfirm = not replacement.is_active or assessment["status"] == "conflict" or any(
                item["status"] == "requires_reconfirmation" for item in item_views
            )
            group_views.append({
                "id": group.id, "target_date": group.target_date, "postpartum_meal": group.postpartum_meal,
                "replacement_dish": assessment["dish"], "note": group.note,
                "status": "requires_reconfirmation" if reconfirm else "replaced",
                "candidate_status": assessment["status"], "review_needed": assessment["review_needed"],
                "warnings": assessment["warnings"], "items": item_views,
            })
        acknowledgements = []
        for item in handlings:
            if item.replacement_group_id is None:
                view = self._handling_item_view(
                    item, identities, dishes, "manually_acknowledged", current_conflicts,
                )
                view.update({"target_date": item.target_date, "postpartum_meal": item.postpartum_meal})
                acknowledgements.append(view)
        group_statuses = {item["id"]: item["status"] for item in group_views}
        handling_by_key = {
            (item.case_id, item.original_menu_dish_id): item for item in handlings
        }
        current_dishes = {item["menu_dish_id"]: item["dish"] for item in evaluation["menu_dishes"]}
        conflict_items = []
        for result in evaluation["case_dish_results"]:
            if result["outcome"] != "conflict":
                continue
            key = result["case_id"], result["menu_dish_id"]
            handling = handling_by_key.get(key)
            if handling is None:
                item_status = "pending"
            elif handling.replacement_group_id is None:
                item_status = "manually_acknowledged"
            else:
                item_status = group_statuses.get(handling.replacement_group_id, "requires_reconfirmation")
            conflict_items.append({
                "case_id": result["case_id"], "original_menu_dish_id": result["menu_dish_id"],
                "original_dish": current_dishes[result["menu_dish_id"]], "status": item_status,
                "handling_id": None if handling is None else handling.id,
                "replacement_group_id": None if handling is None else handling.replacement_group_id,
            })
        return {
            "target_date": target_date, "postpartum_meal": postpartum_meal,
            "replacement_groups": group_views, "manual_acknowledgements": acknowledgements,
            "conflict_items": conflict_items,
        }, evaluation

    def _conflict_handlings_with_evaluation(self, target_date, postpartum_meal):
        return self._conflict_handlings_from_context(
            target_date, postpartum_meal,
            self._load_change_sheet_context(target_date, postpartum_meal),
        )

    def conflict_handlings(self, target_date, postpartum_meal):
        return self._conflict_handlings_with_evaluation(target_date, postpartum_meal)[0]

    def change_sheet(self, target_date, postpartum_meal):
        handling_view, evaluation = self._conflict_handlings_with_evaluation(target_date, postpartum_meal)
        case_ids = {
            item["case_id"]
            for group in handling_view["replacement_groups"] for item in group["items"]
        } | {item["case_id"] for item in handling_view["manual_acknowledgements"]}
        cases = self.repository.case_models(case_ids)
        return build_change_sheet(target_date, postpartum_meal, handling_view, cases, evaluation)

    def change_sheet_daily(self, target_date):
        preload = self._load_change_sheet_context(target_date)
        views = [
            self._conflict_handlings_from_context(target_date, meal, preload)
            for meal in MEAL_VALUES
        ]
        case_ids = {
            item["case_id"]
            for handling_view, _ in views
            for group in handling_view["replacement_groups"] for item in group["items"]
        } | {
            item["case_id"]
            for handling_view, _ in views
            for item in handling_view["manual_acknowledgements"]
        }
        cases = self.repository.case_models(case_ids)
        meals = [
            build_change_sheet(target_date, meal, handling_view, cases, evaluation)
            for meal, (handling_view, evaluation) in zip(MEAL_VALUES, views)
        ]
        return build_daily_change_sheet(target_date, meals)

    def replacement_group(self, target_date, postpartum_meal, group_id):
        result = self.conflict_handlings(target_date, postpartum_meal)
        for group in result["replacement_groups"]:
            if group["id"] == group_id:
                return group
        raise PostpartumReplacementGroupNotFoundError()

    def revalidate_replacement_group(self, group_id):
        group = self.repository.replacement_group(group_id)
        if group is None:
            raise PostpartumReplacementGroupNotFoundError()
        return self.replacement_group(group.target_date, group.postpartum_meal, group.id)

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
