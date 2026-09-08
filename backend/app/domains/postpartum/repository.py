import uuid

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.domains.postpartum.models import PostpartumCase, PostpartumRoomHistory, PostpartumServicePause


class PostpartumRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, value): self.session.add(value)
    def delete(self, value): self.session.delete(value)
    def case(self, case_id): return self.session.get(PostpartumCase, case_id)
    def case_for_update(self, case_id):
        return self.session.scalar(select(PostpartumCase).where(PostpartumCase.id == case_id).with_for_update())
    def pause(self, pause_id): return self.session.get(PostpartumServicePause, pause_id)

    def list_cases(self, page, page_size, active, status, search):
        filters = []
        if active is not None: filters.append(PostpartumCase.is_active == active)
        if status is not None: filters.append(PostpartumCase.status == status)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(or_(func.lower(PostpartumCase.case_number).like(term),
                               func.lower(PostpartumCase.name).like(term),
                               func.lower(PostpartumCase.current_room).like(term)))
        total = self.session.scalar(select(func.count()).select_from(PostpartumCase).where(*filters)) or 0
        rows = self.session.scalars(select(PostpartumCase).where(*filters).order_by(
            PostpartumCase.is_active.desc(), PostpartumCase.service_start_date.desc(),
            PostpartumCase.created_at.desc(), PostpartumCase.id).offset((page - 1) * page_size).limit(page_size))
        return list(rows), total

    @staticmethod
    def _meal_order(column):
        return case((column == "breakfast", 0), (column == "lunch", 1), else_=2)

    def room_history(self, case_id):
        return list(self.session.scalars(select(PostpartumRoomHistory).where(
            PostpartumRoomHistory.case_id == case_id).order_by(
            PostpartumRoomHistory.effective_date, self._meal_order(PostpartumRoomHistory.effective_meal),
            PostpartumRoomHistory.created_at, PostpartumRoomHistory.id)))

    def pauses(self, case_id):
        return list(self.session.scalars(select(PostpartumServicePause).where(
            PostpartumServicePause.case_id == case_id).order_by(
            PostpartumServicePause.start_date, self._meal_order(PostpartumServicePause.start_meal),
            PostpartumServicePause.id)))
