from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.audit.service import AuditLogService
from app.domains.dishes.models import Dish
from app.domains.menu_imports.exceptions import (
    MenuImportAlreadyFinalizedError,
    MenuImportDishUnavailableError,
    MenuImportDuplicateError,
    MenuImportFatalError,
    MenuImportHashMismatchError,
    MenuImportLineNotFoundError,
    MenuImportNotFoundError,
    MenuImportNotReadyError,
    MenuImportValidationError,
)
from app.domains.menu_imports.models import MenuImportBatch, MenuImportLine
from app.domains.menu_imports.parser import normalize_text, parse_menu_xlsx, safe_filename
from app.domains.menu_imports.repository import MenuImportRepository
from app.domains.menus.models import Menu
from app.domains.menus.exceptions import DuplicateMenuDishError, InvalidMenuCategoryError, InvalidMenuStructureError
from app.domains.menus.service import MenuService


class MenuImportService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = MenuImportRepository(session)
        self.audit = AuditLogService(session)

    @staticmethod
    def _match_name(original_name: str, dishes) -> tuple[str, Dish | dict | None]:
        normalized = normalize_text(original_name)
        candidates = [dish for dish in dishes if normalize_text(dish.name if isinstance(dish, Dish) else dish["name"]) == normalized]
        active = [
            dish for dish in candidates
            if (dish.is_active if isinstance(dish, Dish) else dish["is_active"])
        ]
        if len(active) > 1:
            return "AMBIGUOUS", None
        if active:
            return "MATCHED", active[0]
        if candidates:
            return "INACTIVE_MATCH", candidates[0]
        return "UNMATCHED", None

    def _recalculate_batch(self, batch: MenuImportBatch) -> list[MenuImportLine]:
        self.session.flush()
        lines = self.repository.lines(batch.id)
        groups: dict[tuple, list[MenuImportLine]] = {}
        for line in lines:
            line.duplicate_conflict = False
            if line.resolution_status in {"MATCHED", "MANUALLY_RESOLVED"} and line.dish_id is not None:
                groups.setdefault((line.menu_date, line.meal_sort_order, line.dish_id), []).append(line)
        for values in groups.values():
            if len(values) > 1:
                for line in values:
                    line.duplicate_conflict = True
        batch.review_required_count = sum(1 for line in lines if line.review_required)
        batch.duplicate_conflict_count = sum(1 for line in lines if line.duplicate_conflict)
        batch.excluded_count = sum(1 for line in lines if line.resolution_status == "EXCLUDED")
        all_effective_resolved = all(
            line.dish_id is not None
            for line in lines
            if line.resolution_status != "EXCLUDED"
        )
        batch.status = (
            "READY" if batch.review_required_count == 0
            and batch.duplicate_conflict_count == 0
            and all_effective_resolved else "REVIEW_REQUIRED"
        )
        self.session.flush()
        return lines

    @staticmethod
    def _finalize_state(lines: list[MenuImportLine], dishes: dict[uuid.UUID, Dish]) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        if any(line.review_required for line in lines):
            warnings.append("仍有菜色需要確認")
        if any(line.duplicate_conflict for line in lines):
            warnings.append("仍有同日同餐重複菜色")
        effective = [line for line in lines if line.resolution_status != "EXCLUDED"]
        if any(line.dish_id is None for line in effective):
            warnings.append("仍有有效匯入列尚未指定菜色")
        if any(line.dish_id is not None and line.dish_id not in dishes for line in effective):
            warnings.append("已有對應菜色不存在")
        if any(line.dish_id in dishes and not dishes[line.dish_id].is_active for line in effective):
            warnings.append("已有對應菜色已停用")
        return not warnings, warnings

    def can_finalize(self, batch_id: uuid.UUID) -> bool:
        batch = self.repository.batch(batch_id)
        if batch is None:
            raise MenuImportNotFoundError()
        lines = self.repository.lines(batch_id)
        dishes = self.repository.dishes({line.dish_id for line in lines if line.dish_id is not None})
        return self._finalize_state(lines, dishes)[0]

    @staticmethod
    def _require_mutable(batch: MenuImportBatch) -> None:
        if batch.status == "FINALIZED":
            raise MenuImportAlreadyFinalizedError(batch.finalized_menu_id)

    def preview(self, payload: bytes, filename: str, sheet_name: str | None = None) -> dict:
        parsed = parse_menu_xlsx(payload, filename, sheet_name)
        dishes = list(self.session.execute(
            select(Dish.id, Dish.code, Dish.name, Dish.is_active).order_by(Dish.id)
        ).mappings())
        lines = []
        matched_count = 0
        review_count = 0
        for line in parsed.lines:
            status, dish = self._match_name(line.original_import_name, dishes)
            if status == "MATCHED": matched_count += 1
            else: review_count += 1
            lines.append({
                "line_key": line.line_key, "date": line.menu_date, "meal_name": line.meal_name,
                "meal_sort_order": line.meal_sort_order, "column_name": line.column_name,
                "column_sort_order": line.column_sort_order,
                "original_import_name": line.original_import_name,
                "normalized_name": line.normalized_name, "dish": dish, "status": status,
                "review_required": status != "MATCHED", "source_row": line.source_row,
                "source_column": line.source_column, "diner_count": 1,
            })
        overlaps = [dict(row) for row in self.session.execute(select(
            Menu.id, Menu.name, Menu.start_date, Menu.end_date, Menu.is_active,
        ).where(
            Menu.start_date <= parsed.end_date, Menu.end_date >= parsed.start_date,
        ).order_by(Menu.start_date, func.lower(Menu.name), Menu.id)).mappings()]
        warnings = list(parsed.warnings)
        if review_count:
            warnings.append(f"{review_count} 道菜需要人工確認")
        if overlaps:
            warnings.append(f"日期範圍與 {len(overlaps)} 份既有菜單重疊；preview 不會修改它們")
        return {
            "source_hash": parsed.source_hash, "parser_version": parsed.parser_version,
            "sheet_name": parsed.sheet_name, "start_date": parsed.start_date,
            "end_date": parsed.end_date,
            "summary": {
                "date_count": len(parsed.dates), "meal_count": len(parsed.meal_names),
                "column_count": parsed.column_count, "dish_count": len(lines),
                "matched_count": matched_count, "review_required_count": review_count,
            },
            "layout": [{
                "meal_name": row.meal_name,
                "meal_sort_order": row.meal_sort_order,
                "column_name": row.column_name,
                "column_sort_order": row.column_sort_order,
            } for row in parsed.layout],
            "lines": lines, "fatal_errors": list(parsed.fatal_errors),
            "warnings": warnings, "overlapping_menus": overlaps,
        }

    @staticmethod
    def _summary(batch: MenuImportBatch) -> dict:
        return {
            "date_count": batch.date_count,
            "meal_count": batch.meal_count,
            "column_count": batch.column_count,
            "dish_count": batch.dish_count,
            "matched_count": batch.matched_count,
            "review_required_count": batch.review_required_count,
            "duplicate_conflict_count": batch.duplicate_conflict_count,
            "excluded_count": batch.excluded_count,
        }

    def _batch_public(self, batch: MenuImportBatch, *, created_by_name: str | None = None) -> dict:
        return {
            "id": batch.id,
            "status": batch.status,
            "original_filename": batch.original_filename,
            "source_hash": batch.source_hash,
            "parser_version": batch.parser_version,
            "sheet_name": batch.sheet_name,
            "start_date": batch.start_date,
            "end_date": batch.end_date,
            "summary": self._summary(batch),
            "created_by": batch.created_by,
            "created_by_name": created_by_name,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
        }

    def detail(self, batch_id: uuid.UUID) -> dict:
        batch = self.repository.batch(batch_id)
        if batch is None:
            raise MenuImportNotFoundError()
        lines = self.repository.lines(batch_id)
        dishes = self.repository.dishes({line.dish_id for line in lines if line.dish_id is not None})
        result = self._batch_public(batch, created_by_name=self.repository.user_display_name(batch.created_by))
        result["layout"] = batch.layout
        can_finalize, finalize_warnings = self._finalize_state(lines, dishes)
        result["can_finalize"] = can_finalize and batch.status != "FINALIZED"
        result["finalize_warnings"] = [] if batch.status == "FINALIZED" else finalize_warnings
        result["finalized_at"] = batch.finalized_at
        result["finalized_by"] = batch.finalized_by
        result["finalized_menu_id"] = batch.finalized_menu_id
        finalized_menu = self.repository.finalized_menu(batch.finalized_menu_id) if batch.finalized_menu_id else None
        result["finalized_menu"] = ({
            "id": finalized_menu.id, "name": finalized_menu.name,
            "start_date": finalized_menu.start_date, "end_date": finalized_menu.end_date,
            "is_active": finalized_menu.is_active,
        } if finalized_menu is not None else None)
        result["lines"] = [{
            "id": line.id,
            "line_key": line.line_key,
            "date": line.menu_date,
            "meal_name": line.meal_name,
            "meal_sort_order": line.meal_sort_order,
            "column_name": line.column_name,
            "column_sort_order": line.column_sort_order,
            "original_import_name": line.original_import_name,
            "normalized_name": line.normalized_import_name,
            "dish": ({
                "id": dishes[line.dish_id].id,
                "code": dishes[line.dish_id].code,
                "name": dishes[line.dish_id].name,
                "is_active": dishes[line.dish_id].is_active,
            } if line.dish_id in dishes else None),
            "resolution_status": line.resolution_status,
            "review_required": line.review_required,
            "duplicate_conflict": line.duplicate_conflict,
            "resolved_at": line.resolved_at,
            "resolved_by": line.resolved_by,
            "excluded_at": line.excluded_at,
            "excluded_by": line.excluded_by,
            "source_row": line.source_row,
            "source_column": line.source_column,
            "diner_count": line.diner_count,
        } for line in lines]
        return result

    def create_draft(
        self,
        payload: bytes,
        filename: str,
        sheet_name: str | None,
        expected_source_hash: str,
        actor_id: uuid.UUID,
    ) -> dict:
        preview = self.preview(payload, filename, sheet_name)
        if not hmac.compare_digest(preview["source_hash"], expected_source_hash.strip().lower()):
            raise MenuImportHashMismatchError()
        if preview["fatal_errors"]:
            raise MenuImportFatalError(preview["fatal_errors"])
        duplicate = self.repository.active_duplicate(
            preview["source_hash"], preview["sheet_name"], actor_id,
        )
        if duplicate is not None:
            raise MenuImportDuplicateError(duplicate.id)
        summary = preview["summary"]
        batch = MenuImportBatch(
            id=uuid.uuid4(),
            status="REVIEW_REQUIRED" if summary["review_required_count"] else "READY",
            original_filename=safe_filename(filename),
            source_hash=preview["source_hash"],
            parser_version=preview["parser_version"],
            sheet_name=preview["sheet_name"],
            start_date=preview["start_date"],
            end_date=preview["end_date"],
            date_count=summary["date_count"],
            meal_count=summary["meal_count"],
            column_count=summary["column_count"],
            dish_count=summary["dish_count"],
            matched_count=summary["matched_count"],
            review_required_count=summary["review_required_count"],
            duplicate_conflict_count=0,
            excluded_count=0,
            layout=preview["layout"],
            created_by=actor_id,
            updated_by=actor_id,
        )
        try:
            self.repository.add(batch)
            for item in preview["lines"]:
                matched = item["status"] == "MATCHED"
                self.repository.add(MenuImportLine(
                    id=uuid.uuid4(),
                    batch_id=batch.id,
                    line_key=item["line_key"],
                    source_row=item["source_row"],
                    source_column=item["source_column"],
                    menu_date=item["date"],
                    meal_name=item["meal_name"],
                    meal_sort_order=item["meal_sort_order"],
                    column_name=item["column_name"],
                    column_sort_order=item["column_sort_order"],
                    original_import_name=item["original_import_name"],
                    normalized_import_name=item["normalized_name"],
                    dish_id=item["dish"]["id"] if matched else None,
                    diner_count=item["diner_count"],
                    review_required=item["review_required"],
                    resolution_status=item["status"],
                ))
            self._recalculate_batch(batch)
            self.audit.record(
                actor_id=actor_id,
                action="menu_import_draft_create",
                entity_type="menu_import_batch",
                entity_id=batch.id,
                entity_label=batch.original_filename,
                after_data={
                    "source_hash": batch.source_hash,
                    "sheet_name": batch.sheet_name,
                    "status": batch.status,
                    "line_count": batch.dish_count,
                    "review_required_count": batch.review_required_count,
                },
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            duplicate = self.repository.active_duplicate(
                preview["source_hash"], preview["sheet_name"], actor_id,
            )
            if duplicate is not None:
                raise MenuImportDuplicateError(duplicate.id) from exc
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.detail(batch.id)

    def resolve_line(
        self, batch_id: uuid.UUID, line_id: uuid.UUID, dish_id: uuid.UUID, actor_id: uuid.UUID,
    ) -> dict:
        try:
            batch = self.repository.batch(batch_id, for_update=True)
            if batch is None:
                raise MenuImportNotFoundError()
            self._require_mutable(batch)
            line = self.repository.line(batch_id, line_id, for_update=True)
            if line is None:
                raise MenuImportLineNotFoundError()
            if line.resolution_status == "EXCLUDED":
                raise MenuImportValidationError("請先恢復已排除的菜色，再變更對應")
            dish = self.repository.active_dish(dish_id)
            if dish is None:
                raise MenuImportDishUnavailableError()
            before = {
                "line_id": line.id,
                "original_import_name": line.original_import_name,
                "dish_id": line.dish_id,
                "resolution_status": line.resolution_status,
                "review_required": line.review_required,
            }
            line.dish_id = dish.id
            line.resolution_status = "MANUALLY_RESOLVED"
            line.review_required = False
            line.resolved_at = datetime.now(UTC)
            line.resolved_by = actor_id
            line.excluded_at = None
            line.excluded_by = None
            batch.updated_by = actor_id
            self._recalculate_batch(batch)
            self.audit.record(
                actor_id=actor_id,
                action="menu_import_line_resolve",
                entity_type="menu_import_line",
                entity_id=line.id,
                entity_label=line.original_import_name,
                before_data=before,
                after_data={
                    "batch_id": batch.id,
                    "line_id": line.id,
                    "original_import_name": line.original_import_name,
                    "selected_dish_id": dish.id,
                    "resolution_status": line.resolution_status,
                    "review_required": False,
                    "batch_review_required_count": batch.review_required_count,
                    "batch_status": batch.status,
                },
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.detail(batch_id)

    def exclude_line(self, batch_id: uuid.UUID, line_id: uuid.UUID, actor_id: uuid.UUID) -> dict:
        try:
            batch = self.repository.batch(batch_id, for_update=True)
            if batch is None:
                raise MenuImportNotFoundError()
            self._require_mutable(batch)
            line = self.repository.line(batch_id, line_id, for_update=True)
            if line is None:
                raise MenuImportLineNotFoundError()
            before = {
                "batch_id": batch.id, "line_id": line.id,
                "original_import_name": line.original_import_name,
                "dish_id": line.dish_id, "resolution_status": line.resolution_status,
            }
            line.dish_id = None
            line.resolution_status = "EXCLUDED"
            line.review_required = False
            line.resolved_at = None
            line.resolved_by = None
            line.excluded_at = datetime.now(UTC)
            line.excluded_by = actor_id
            batch.updated_by = actor_id
            self._recalculate_batch(batch)
            self.audit.record(
                actor_id=actor_id, action="menu_import_line_exclude",
                entity_type="menu_import_line", entity_id=line.id,
                entity_label=line.original_import_name, before_data=before,
                after_data={
                    "batch_id": batch.id, "line_id": line.id,
                    "original_import_name": line.original_import_name,
                    "dish_id": None, "resolution_status": "EXCLUDED",
                },
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.detail(batch_id)

    def restore_line(self, batch_id: uuid.UUID, line_id: uuid.UUID, actor_id: uuid.UUID) -> dict:
        try:
            batch = self.repository.batch(batch_id, for_update=True)
            if batch is None:
                raise MenuImportNotFoundError()
            self._require_mutable(batch)
            line = self.repository.line(batch_id, line_id, for_update=True)
            if line is None:
                raise MenuImportLineNotFoundError()
            if line.resolution_status != "EXCLUDED":
                raise MenuImportValidationError("只有已排除的菜色可以恢復")
            before = {
                "batch_id": batch.id, "line_id": line.id,
                "original_import_name": line.original_import_name,
                "resolution_status": line.resolution_status,
            }
            status, dish = self._match_name(line.original_import_name, self.repository.all_dishes())
            line.dish_id = dish.id if isinstance(dish, Dish) and status == "MATCHED" else None
            line.resolution_status = status
            line.review_required = status != "MATCHED"
            line.resolved_at = None
            line.resolved_by = None
            line.excluded_at = None
            line.excluded_by = None
            batch.updated_by = actor_id
            self._recalculate_batch(batch)
            self.audit.record(
                actor_id=actor_id, action="menu_import_line_restore",
                entity_type="menu_import_line", entity_id=line.id,
                entity_label=line.original_import_name, before_data=before,
                after_data={
                    "batch_id": batch.id, "line_id": line.id,
                    "original_import_name": line.original_import_name,
                    "dish_id": line.dish_id, "resolution_status": line.resolution_status,
                    "review_required": line.review_required,
                },
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.detail(batch_id)

    def delete_draft(self, batch_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        try:
            batch = self.repository.batch(batch_id, for_update=True)
            if batch is None:
                raise MenuImportNotFoundError()
            self._require_mutable(batch)
            before = {
                "source_hash": batch.source_hash,
                "sheet_name": batch.sheet_name,
                "status": batch.status,
                "line_count": batch.dish_count,
                "review_required_count": batch.review_required_count,
            }
            self.audit.record(
                actor_id=actor_id,
                action="menu_import_draft_delete",
                entity_type="menu_import_batch",
                entity_id=batch.id,
                entity_label=batch.original_filename,
                before_data=before,
                after_data={"deleted": True},
            )
            self.repository.delete_batch(batch.id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def finalize(self, batch_id: uuid.UUID, name: str, category_id: uuid.UUID | None,
                 notes: str | None, actor_id: uuid.UUID) -> dict:
        try:
            batch = self.repository.batch(batch_id, for_update=True)
            if batch is None:
                raise MenuImportNotFoundError()
            if batch.status == "FINALIZED":
                if batch.finalized_menu_id is None or batch.finalized_at is None:
                    raise MenuImportValidationError("正式菜單已不存在，請聯絡系統管理員")
                menu = MenuService(self.session).get(batch.finalized_menu_id)
                self.session.commit()
                return {
                    "batch_id": batch.id, "status": "FINALIZED",
                    "finalized_menu_id": batch.finalized_menu_id,
                    "finalized_at": batch.finalized_at, "already_finalized": True,
                    "menu": menu,
                }
            lines = self._recalculate_batch(batch)
            dishes = self.repository.dishes({line.dish_id for line in lines if line.dish_id is not None})
            eligible, warnings = self._finalize_state(lines, dishes)
            if not eligible or batch.status != "READY":
                raise MenuImportNotReadyError(warnings or ["匯入草稿尚未完成審核"])
            if not isinstance(batch.layout,list) or not batch.layout:
                raise MenuImportValidationError("匯入草稿缺少菜單版面資料")
            if (batch.end_date-batch.start_date).days+1 != batch.date_count:
                raise MenuImportValidationError("匯入草稿日期資料不一致")
            assignments=[{
                "menu_date":line.menu_date,"meal_name":line.meal_name,
                "meal_sort_order":line.meal_sort_order,"column_name":line.column_name,
                "column_sort_order":line.column_sort_order,"dish_id":line.dish_id,
                "diner_count":line.diner_count,"source_row":line.source_row,
                "source_column":line.source_column,
            } for line in lines if line.resolution_status!="EXCLUDED"]
            menu_service=MenuService(self.session)
            menu=menu_service.stage_imported_menu(
                name=name,start_date=batch.start_date,end_date=batch.end_date,
                category_id=category_id,notes=notes,layout=batch.layout,
                assignments=assignments,actor_id=actor_id,
            )
            now=datetime.now(UTC)
            batch.status="FINALIZED";batch.finalized_at=now;batch.finalized_by=actor_id
            batch.finalized_menu_id=menu.id;batch.updated_by=actor_id
            self.audit.record(actor_id=actor_id,action="menu_create",entity_type="menu",
                entity_id=menu.id,entity_label=menu.name,after_data={
                    "name":menu.name,"start_date":menu.start_date,"end_date":menu.end_date,
                    "category_id":menu.category_id,"notes":menu.notes,"is_active":menu.is_active,
                },metadata={"source":"menu_import","batch_id":batch.id})
            self.audit.record(actor_id=actor_id,action="menu_import_finalize",
                entity_type="menu_import_batch",entity_id=batch.id,entity_label=batch.original_filename,
                before_data={"status":"READY"},after_data={
                    "status":"FINALIZED","batch_id":batch.id,"menu_id":menu.id,
                    "source_hash":batch.source_hash,"start_date":batch.start_date,
                    "end_date":batch.end_date,"effective_line_count":len(assignments),
                    "excluded_count":batch.excluded_count,"finalized_by":actor_id,
                })
            self.session.commit()
        except (InvalidMenuCategoryError, InvalidMenuStructureError, DuplicateMenuDishError) as exc:
            self.session.rollback()
            raise MenuImportValidationError(str(exc) or "正式菜單資料不符合既有規則") from exc
        except Exception:
            self.session.rollback()
            raise
        return {
            "batch_id":batch.id,"status":"FINALIZED","finalized_menu_id":menu.id,
            "finalized_at":now,"already_finalized":False,"menu":MenuService(self.session).get(menu.id),
        }

    def list(self, page: int, page_size: int):
        rows, total = self.repository.listing(page, page_size)
        return [self._batch_public(batch, created_by_name=name) for batch, name in rows], total
