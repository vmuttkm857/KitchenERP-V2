import uuid
from sqlalchemy.orm import Session

from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.postpartum.exceptions import InvalidPostpartumDataError, PostpartumCaseNotFoundError, PostpartumPauseNotFoundError
from app.domains.postpartum.models import PostpartumCase, PostpartumRoomHistory, PostpartumServicePause
from app.domains.postpartum.repository import PostpartumRepository
from app.domains.postpartum.schemas import CaseCreate, CaseUpdate, PauseCreate, PauseUpdate, RoomChangeCreate
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

    def list(self, page, page_size, active, status, search):
        return self.repository.list_cases(page, page_size, active, status, search)

    def detail(self, case_id):
        value = self.case(case_id)
        return {"case": value, "room_history": self.repository.room_history(case_id), "pauses": self.repository.pauses(case_id)}

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
