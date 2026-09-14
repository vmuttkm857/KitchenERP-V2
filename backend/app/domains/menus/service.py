import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.service import AuthService
from app.domains.audit.service import AuditLogService, audit_snapshot
from app.domains.menus.exceptions import (
    DuplicateMenuDishError, InvalidMenuCategoryError, InvalidMenuCopyError,
    InvalidMenuDateRangeError, InvalidMenuStructureError, MealTypeInUseError,
    MealTypeColumnNameExistsError, MealTypeColumnNotFoundError,
    MealTypeNameExistsError, MealTypeNotFoundError, MenuInUseError, MenuNotFoundError,
)
from app.domains.menus.models import Menu, MenuDay, MenuDish, MenuMealType, MenuMealTypeColumn
from app.domains.menus.placement import menu_dish_visual_rows
from app.domains.menus.repository import MenuRepository
from app.domains.menus.schemas import (
    CopyDayCommand, CopyWeekCommand, MealTypeColumnCreate, MealTypeColumnReorder,
    MealTypeColumnUpdate, MealTypeCreate, MealTypeReorder, MealTypeUpdate, MenuCreate,
    MenuDishMove, MenuEditorSave, MenuUpdate,
)


class MenuService:
    def __init__(self, session: Session):
        self.session=session; self.repository=MenuRepository(session); self.audit=AuditLogService(session)

    def model(self, menu_id):
        value=self.repository.menu_model(menu_id)
        if value is None: raise MenuNotFoundError()
        return value

    def get(self, menu_id):
        row=self.repository.menu_view(menu_id)
        if row is None: raise MenuNotFoundError()
        return dict(row)

    def list(self, page, page_size, active, search, category_id, start_date=None, end_date=None):
        if start_date is not None and end_date is not None and start_date > end_date:
            raise InvalidMenuDateRangeError("Start date cannot be later than end date")
        return self.repository.list(page,page_size,active,search,category_id,start_date,end_date)

    def _category(self, category_id):
        if category_id is None: return
        category=self.repository.category(category_id)
        if category is None or not category.is_active: raise InvalidMenuCategoryError()

    def create(self, data: MenuCreate, actor_id):
        self._category(data.category_id)
        menu=Menu(id=uuid.uuid4(),name=data.name.strip(),start_date=data.start_date,end_date=data.end_date,
                  category_id=data.category_id,notes=data.notes,created_by=actor_id,updated_by=actor_id)
        self.repository.add(menu)
        self.audit.record(actor_id=actor_id,action="menu_create",entity_type="menu",entity_id=menu.id,
            entity_label=menu.name,after_data=audit_snapshot(menu,"name","start_date","end_date","category_id","notes","is_active"))
        self.session.commit(); return self.get(menu.id)

    def update(self, menu_id, data: MenuUpdate, actor_id):
        menu=self.model(menu_id); before=audit_snapshot(menu,"name","start_date","end_date","category_id","notes","is_active"); changes=data.model_dump(exclude_unset=True)
        start=changes.get("start_date",menu.start_date); end=changes.get("end_date",menu.end_date)
        if end < start: raise InvalidMenuDateRangeError()
        if "category_id" in changes: self._category(changes["category_id"])
        if any(day.menu_date < start or day.menu_date > end for day in self.repository.days(menu_id)):
            raise InvalidMenuDateRangeError("Existing meal slots fall outside the new date range")
        if "name" in changes: changes["name"]=changes["name"].strip()
        for field,value in changes.items(): setattr(menu,field,value)
        menu.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="menu_update",entity_type="menu",entity_id=menu.id,
            entity_label=menu.name,before_data=before,after_data=audit_snapshot(menu,"name","start_date","end_date","category_id","notes","is_active"))
        self.session.commit(); return self.get(menu_id)

    def set_active(self, menu_id, active, actor_id):
        menu=self.model(menu_id); before=audit_snapshot(menu,"name","is_active"); menu.is_active=active; menu.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="menu_reactivate" if active else "menu_deactivate",entity_type="menu",
            entity_id=menu.id,entity_label=menu.name,before_data=before,after_data=audit_snapshot(menu,"name","is_active"))
        self.session.commit(); return self.get(menu_id)

    def hard_delete(self, menu_id, actor_id, password):
        AuthService(self.session).verify_current_password(actor_id,password)
        menu=self.model(menu_id)
        before=audit_snapshot(menu,"name","start_date","end_date","category_id","notes","is_active")
        if self.repository.has_children(menu_id): raise MenuInUseError()
        self.repository.delete(menu)
        self.audit.record(actor_id=actor_id,action="menu_hard_delete",entity_type="menu",entity_id=menu.id,
            entity_label=menu.name,before_data=before)
        self.session.commit()

    def meal_types(self, menu_id): self.model(menu_id); return self.repository.meal_types(menu_id)

    def create_meal_type(self, menu_id, data: MealTypeCreate, actor_id):
        self.model(menu_id); name=data.name.strip()
        if self.repository.meal_name_exists(menu_id,name): raise MealTypeNameExistsError()
        value=MenuMealType(id=uuid.uuid4(),menu_id=menu_id,name=name,sort_order=data.sort_order,created_by=actor_id,updated_by=actor_id)
        self.repository.add(value)
        self.audit.record(actor_id=actor_id,action="meal_type_create",entity_type="menu_meal_type",entity_id=value.id,
            entity_label=value.name,after_data=audit_snapshot(value,"menu_id","name","sort_order","is_active"))
        self._commit_meal(); return value

    def _meal(self, menu_id, meal_type_id):
        value=self.repository.meal_type(meal_type_id)
        if value is None or value.menu_id != menu_id: raise MealTypeNotFoundError()
        return value

    def update_meal_type(self, menu_id, meal_type_id, data: MealTypeUpdate, actor_id):
        value=self._meal(menu_id,meal_type_id); before=audit_snapshot(value,"menu_id","name","sort_order","is_active")
        if data.name is not None:
            name=data.name.strip()
            if self.repository.meal_name_exists(menu_id,name,meal_type_id): raise MealTypeNameExistsError()
            value.name=name
        if data.sort_order is not None: value.sort_order=data.sort_order
        value.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="meal_type_update",entity_type="menu_meal_type",entity_id=value.id,
            entity_label=value.name,before_data=before,after_data=audit_snapshot(value,"menu_id","name","sort_order","is_active"))
        self._commit_meal(); return value

    def set_meal_active(self, menu_id, meal_type_id, active, actor_id):
        value=self._meal(menu_id,meal_type_id); before=audit_snapshot(value,"menu_id","name","sort_order","is_active"); value.is_active=active; value.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="meal_type_reactivate" if active else "meal_type_deactivate",
            entity_type="menu_meal_type",entity_id=value.id,entity_label=value.name,before_data=before,
            after_data=audit_snapshot(value,"menu_id","name","sort_order","is_active"))
        self.session.commit(); return value

    def reorder_meal_types(self, menu_id, data: MealTypeReorder, actor_id):
        values=self.repository.meal_types(menu_id)
        by_id={item.id:item for item in values}
        if len(set(data.ordered_ids)) != len(data.ordered_ids) or set(data.ordered_ids) != set(by_id):
            raise InvalidMenuStructureError("Reorder must contain every meal type exactly once")
        before=[audit_snapshot(item,"id","name","sort_order") for item in values]
        for order,meal_id in enumerate(data.ordered_ids,1):
            by_id[meal_id].sort_order=order; by_id[meal_id].updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="meal_type_reorder",entity_type="menu",entity_id=menu_id,
            entity_label=self.model(menu_id).name,before_data={"meal_types":before},
            after_data={"ordered_ids":data.ordered_ids})
        self.session.commit(); return self.repository.meal_types(menu_id)

    def hard_delete_meal(self, menu_id, meal_type_id, actor_id, password):
        AuthService(self.session).verify_current_password(actor_id,password)
        value=self._meal(menu_id,meal_type_id)
        before=audit_snapshot(value,"menu_id","name","sort_order","is_active")
        if self.repository.meal_type_has_days(meal_type_id): raise MealTypeInUseError()
        self.repository.delete(value)
        self.audit.record(actor_id=actor_id,action="meal_type_hard_delete",entity_type="menu_meal_type",
            entity_id=value.id,entity_label=value.name,before_data=before)
        self.session.commit()

    def _commit_meal(self):
        try: self.session.commit()
        except IntegrityError as exc: self.session.rollback(); raise MealTypeNameExistsError() from exc

    def meal_type_columns(self, menu_id, meal_type_id):
        self._meal(menu_id,meal_type_id)
        return self.repository.meal_type_columns(meal_type_id)

    def _column(self, menu_id, meal_type_id, column_id):
        self._meal(menu_id,meal_type_id)
        value=self.repository.meal_type_column(column_id)
        if value is None or value.menu_meal_type_id!=meal_type_id: raise MealTypeColumnNotFoundError()
        return value

    def create_meal_type_column(self, menu_id, meal_type_id, data: MealTypeColumnCreate, actor_id):
        self._meal(menu_id,meal_type_id); name=data.name.strip()
        if self.repository.column_name_exists(meal_type_id,name): raise MealTypeColumnNameExistsError()
        value=MenuMealTypeColumn(id=uuid.uuid4(),menu_meal_type_id=meal_type_id,name=name,sort_order=data.sort_order,
            created_by=actor_id,updated_by=actor_id)
        self.repository.add(value)
        self.audit.record(actor_id=actor_id,action="meal_type_column_create",entity_type="menu_meal_type_column",
            entity_id=value.id,entity_label=value.name,after_data=audit_snapshot(value,"menu_meal_type_id","name","sort_order"))
        self._commit_column(); return value

    def update_meal_type_column(self, menu_id, meal_type_id, column_id, data: MealTypeColumnUpdate, actor_id):
        value=self._column(menu_id,meal_type_id,column_id); name=data.name.strip()
        if self.repository.column_name_exists(meal_type_id,name,column_id): raise MealTypeColumnNameExistsError()
        before=audit_snapshot(value,"menu_meal_type_id","name","sort_order")
        value.name=name; value.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="meal_type_column_update",entity_type="menu_meal_type_column",
            entity_id=value.id,entity_label=value.name,before_data=before,
            after_data=audit_snapshot(value,"menu_meal_type_id","name","sort_order"))
        self._commit_column(); return value

    def reorder_meal_type_columns(self, menu_id, meal_type_id, data: MealTypeColumnReorder, actor_id):
        self._meal(menu_id,meal_type_id); values=self.repository.meal_type_columns(meal_type_id)
        by_id={item.id:item for item in values}
        if len(set(data.ordered_ids))!=len(data.ordered_ids) or set(data.ordered_ids)!=set(by_id):
            raise InvalidMenuStructureError("Reorder must contain every column exactly once")
        for order,column_id in enumerate(data.ordered_ids,1):
            by_id[column_id].sort_order=order; by_id[column_id].updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="meal_type_column_reorder",entity_type="menu_meal_type",
            entity_id=meal_type_id,entity_label=self._meal(menu_id,meal_type_id).name,
            after_data={"ordered_ids":data.ordered_ids})
        self.session.commit(); return self.repository.meal_type_columns(meal_type_id)

    def delete_meal_type_column(self, menu_id, meal_type_id, column_id, actor_id):
        value=self._column(menu_id,meal_type_id,column_id)
        before=audit_snapshot(value,"menu_meal_type_id","name","sort_order")
        self.repository.delete(value)
        self.audit.record(actor_id=actor_id,action="meal_type_column_delete",entity_type="menu_meal_type_column",
            entity_id=value.id,entity_label=value.name,before_data=before)
        self.session.commit()

    def _commit_column(self):
        try:self.session.commit()
        except IntegrityError as exc:self.session.rollback();raise MealTypeColumnNameExistsError() from exc

    def aggregate(self, menu_id):
        menu=self.get(menu_id); meal_types=self.repository.meal_types(menu_id)
        grouped={}
        for row in self.repository.aggregate_rows(menu_id):
            key=row["menu_day_id"]
            slot=grouped.setdefault(key,{"menu_day_id":key,"menu_date":row["menu_date"],
                "menu_meal_type_id":row["menu_meal_type_id"],"notes":row["slot_notes"],"dishes":[]})
            if row["menu_dish_id"] is not None:
                slot["dishes"].append({"id":row["menu_dish_id"],"dish_id":row["dish_id"],
                    "menu_meal_type_column_id":row["menu_meal_type_column_id"],
                    "dish_code":row["dish_code"],"dish_name":row["dish_name"],
                    "dish_category_name":row["dish_category_name"],"diner_count":row["diner_count"],
                    "notes":row["notes"],"sort_order":row["sort_order"],
                    "created_by":row["created_by"],"updated_by":row["updated_by"]})
        dates=[]; current=menu["start_date"]
        while current <= menu["end_date"]: dates.append(current); current += timedelta(days=1)
        return {"menu":menu,"dates":dates,"meal_types":meal_types,
            "meal_type_columns":self.repository.menu_columns(menu_id),"slots":list(grouped.values())}

    def save_editor(self, menu_id, data: MenuEditorSave, actor_id):
        menu=self.model(menu_id)
        before=self.aggregate(menu_id)
        meal_types={item.id:item for item in self.repository.meal_types(menu_id)}
        existing_days={item.id:item for item in self.repository.days(menu_id)}
        existing_details={item.id:item for item in self.repository.details(set(existing_days))}
        retained_days=set(); retained_details=set(); seen_slots=set()
        all_dish_ids={detail.dish_id for slot in data.slots for detail in slot.dishes}
        all_column_ids={detail.menu_meal_type_column_id for slot in data.slots for detail in slot.dishes if detail.menu_meal_type_column_id is not None}
        dishes=self.repository.dish_models(all_dish_ids)
        columns=self.repository.meal_type_column_models(all_column_ids)
        if len(dishes) != len(all_dish_ids): raise InvalidMenuStructureError("Dish not found")
        if len(columns) != len(all_column_ids): raise InvalidMenuStructureError("Menu column not found")
        try:
            for slot in data.slots:
                key=(slot.menu_date,slot.menu_meal_type_id)
                if key in seen_slots: raise InvalidMenuStructureError("Duplicate date and meal type slot")
                seen_slots.add(key)
                meal=meal_types.get(slot.menu_meal_type_id)
                if meal is None: raise InvalidMenuStructureError("Meal type does not belong to this menu")
                if not (menu.start_date <= slot.menu_date <= menu.end_date): raise InvalidMenuStructureError("Slot date is outside menu range")
                if slot.menu_day_id is None and not slot.dishes and not slot.notes:
                    continue
                if slot.menu_day_id is None:
                    if not meal.is_active: raise InvalidMenuStructureError("Inactive meal type cannot receive a new assignment")
                    day=MenuDay(menu_id=menu_id,menu_date=slot.menu_date,menu_meal_type_id=meal.id,
                                created_by=actor_id,updated_by=actor_id)
                    self.repository.add(day); self.session.flush()
                else:
                    day=existing_days.get(slot.menu_day_id)
                    if day is None or day.menu_date != slot.menu_date or day.menu_meal_type_id != meal.id:
                        raise InvalidMenuStructureError("Menu day identity mismatch")
                    retained_days.add(day.id)
                day.notes=slot.notes; day.updated_by=actor_id
                seen_dishes=set();seen_columns=set()
                for order,payload in enumerate(sorted(slot.dishes,key=lambda value:value.sort_order),1):
                    if payload.dish_id in seen_dishes: raise DuplicateMenuDishError()
                    seen_dishes.add(payload.dish_id); dish=dishes[payload.dish_id]
                    if payload.menu_meal_type_column_id is not None:
                        column=columns[payload.menu_meal_type_column_id]
                        if column.menu_meal_type_id != meal.id: raise InvalidMenuStructureError("Menu column does not belong to this meal type")
                        if column.id in seen_columns: raise InvalidMenuStructureError("Menu column may be used only once in a meal slot")
                        seen_columns.add(column.id)
                    if payload.id is None:
                        if not meal.is_active: raise InvalidMenuStructureError("Inactive meal type cannot receive a new dish assignment")
                        if not dish.is_active: raise InvalidMenuStructureError("Inactive dish cannot be newly assigned")
                        detail=MenuDish(menu_day_id=day.id,dish_id=dish.id,created_by=actor_id,updated_by=actor_id)
                        self.repository.add(detail)
                    else:
                        detail=existing_details.get(payload.id)
                        if detail is None or detail.menu_day_id != day.id or detail.dish_id != dish.id:
                            raise InvalidMenuStructureError("Menu dish identity mismatch")
                        retained_details.add(detail.id)
                    detail.menu_meal_type_column_id=payload.menu_meal_type_column_id
                    detail.diner_count=payload.diner_count; detail.notes=payload.notes
                    detail.sort_order=order; detail.updated_by=actor_id
            submitted_existing_day_ids={slot.menu_day_id for slot in data.slots if slot.menu_day_id}
            for detail_id,detail in existing_details.items():
                if detail_id not in retained_details: self.repository.delete(detail)
            for day_id,day in existing_days.items():
                if day_id not in submitted_existing_day_ids: self.repository.delete(day)
            after=self.aggregate(menu_id)
            self.audit.record(actor_id=actor_id,action="menu_editor_save",entity_type="menu",entity_id=menu.id,
                entity_label=menu.name,before_data=before,after_data=after)
            self.session.commit()
        except Exception:
            self.session.rollback(); raise
        return self.aggregate(menu_id)

    def move_menu_dish(self,menu_id,data:MenuDishMove,actor_id):
        menu=self.repository.menu_model(menu_id,for_update=True)
        if menu is None:raise MenuNotFoundError()
        before=self.aggregate(menu_id)
        try:
            source_row=self.repository.menu_dish_position(data.source_menu_dish_id,for_update=True)
            if source_row is None or source_row[1].menu_id!=menu_id:
                raise InvalidMenuStructureError("Source menu dish does not belong to this menu")
            source,source_day=source_row
            if not (menu.start_date<=data.target_date<=menu.end_date):
                raise InvalidMenuStructureError("Target date is outside menu range")
            target_meal=self._meal(menu_id,data.target_meal_type_id)
            if not target_meal.is_active:
                raise InvalidMenuStructureError("Inactive meal type cannot receive a moved dish")
            target_day=self.repository.day_for_slot(menu_id,data.target_date,target_meal.id,for_update=True)
            day_ids={source_day.id}
            if target_day is not None:day_ids.add(target_day.id)
            locked_dishes=self.repository.details(day_ids,for_update=True)
            source_dishes=[dish for dish in locked_dishes if dish.menu_day_id==source_day.id]
            target_dishes=source_dishes if target_day is not None and target_day.id==source_day.id else [
                dish for dish in locked_dishes if target_day is not None and dish.menu_day_id==target_day.id]
            source_columns=self.repository.meal_type_columns(source_day.menu_meal_type_id)
            target_columns=self.repository.meal_type_columns(target_meal.id)
            source_rows=menu_dish_visual_rows(source_columns,source_dishes)
            target_rows=source_rows if target_dishes is source_dishes else menu_dish_visual_rows(target_columns,target_dishes)
            if data.insert_index>len(target_rows):
                raise InvalidMenuStructureError("Target menu row changed; reload and try again")
            before_id=target_rows[data.insert_index-1].dish.id if data.insert_index and target_rows[data.insert_index-1].dish else None
            after_id=target_rows[data.insert_index].dish.id if data.insert_index<len(target_rows) and target_rows[data.insert_index].dish else None
            if before_id!=data.before_menu_dish_id or after_id!=data.after_menu_dish_id:
                raise InvalidMenuStructureError("Target insertion position changed; reload and try again")
            same_day=target_day is not None and target_day.id==source_day.id
            if not same_day and any(dish.dish_id==source.dish_id for dish in target_dishes):
                raise DuplicateMenuDishError()
            source_index=next((index for index,row in enumerate(source_rows) if row.dish and row.dish.id==source.id),None)
            if source_index is None:raise InvalidMenuStructureError("Source menu dish position is unavailable")
            target_values=[row.dish for row in target_rows]
            insert_index=data.insert_index
            if same_day:
                if insert_index in (source_index,source_index+1):return self.aggregate(menu_id)
                target_values.pop(source_index)
                if source_index<insert_index:insert_index-=1
                while len(target_values)<max(len(target_columns),1):target_values.append(None)
            else:
                source_values=[row.dish for row in source_rows]
                source_values.pop(source_index)
                while len(source_values)<max(len(source_columns),1):source_values.append(None)
            if insert_index<len(target_values) and target_values[insert_index] is None:
                target_values[insert_index]=source
            elif insert_index>0 and target_values[insert_index-1] is None:
                target_values[insert_index-1]=source
            else:
                target_values.insert(insert_index,source)
            required=max(len(target_columns),sum(item is not None for item in target_values),1)
            while len(target_values)>required and target_values[-1] is None:target_values.pop()
            while len(target_values)<required:target_values.append(None)
            if target_day is None:
                target_day=MenuDay(menu_id=menu_id,menu_date=data.target_date,
                    menu_meal_type_id=target_meal.id,created_by=actor_id,updated_by=actor_id)
                self.repository.add(target_day);self.session.flush()
            placements={}
            order=0
            for index,dish in enumerate(target_values):
                if dish is None:continue
                order+=1
                column_id=target_columns[index].id if index<len(target_columns) else None
                placements[dish.id]=(target_day.id,column_id,order)
            if not same_day:
                order=0
                for dish in source_values:
                    if dish is None:continue
                    order+=1
                    placements[dish.id]=(source_day.id,dish.menu_meal_type_column_id,order)
            changed=list({dish.id:dish for dish in (*source_dishes,*target_dishes)}.values())
            self.repository.replace_menu_dish_positions(changed,placements,actor_id)
            after=self.aggregate(menu_id)
            self.audit.record(actor_id=actor_id,action="menu_dish_move",entity_type="menu",
                entity_id=menu.id,entity_label=menu.name,before_data=before,after_data=after,
                metadata={"operation":"insert","source_menu_dish_id":data.source_menu_dish_id,
                    "target_date":data.target_date,
                    "target_meal_type_id":data.target_meal_type_id,
                    "insert_index":data.insert_index,"before_menu_dish_id":data.before_menu_dish_id,
                    "after_menu_dish_id":data.after_menu_dish_id})
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback();raise InvalidMenuStructureError("Menu dish move conflicts with the current menu state") from exc
        except Exception:
            self.session.rollback();raise
        return self.aggregate(menu_id)

    def copy_day(self, destination_menu_id, command: CopyDayCommand, actor_id):
        destination=self.model(destination_menu_id); before=self.aggregate(destination_menu_id)
        try:
            self._copy_day(destination_menu_id,command.source_menu_id,command.source_date,command.destination_date,command.mode,actor_id)
            after=self.aggregate(destination_menu_id)
            self.audit.record(actor_id=actor_id,action="copy_day",entity_type="menu",entity_id=destination.id,
                entity_label=destination.name,before_data=before,after_data=after,
                metadata={"source_menu_id":command.source_menu_id,"source_date":command.source_date,
                          "destination_date":command.destination_date,"mode":command.mode})
            self.session.commit()
        except Exception: self.session.rollback(); raise
        return self.aggregate(destination_menu_id)

    def _prepare_destination_meal_mapping(self,destination_menu_id,source_meals,actor_id):
        destination_meals=self.repository.meal_types(destination_menu_id)
        destination_by_name={meal.name.lower():meal for meal in destination_meals}
        source_by_name={meal.name.lower():meal for meal in source_meals}
        for name,source_meal in source_by_name.items():
            if name in destination_by_name: continue
            meal=MenuMealType(menu_id=destination_menu_id,name=source_meal.name,
                sort_order=source_meal.sort_order,is_active=source_meal.is_active,
                created_by=actor_id,updated_by=actor_id)
            self.repository.add(meal); destination_by_name[name]=meal
        self.session.flush()
        return destination_by_name

    def _copy_day(self,destination_menu_id,source_menu_id,source_date,destination_date,mode,actor_id,
                  destination_meals_by_name=None):
        source=self.model(source_menu_id); destination=self.model(destination_menu_id)
        if not (source.start_date<=source_date<=source.end_date and destination.start_date<=destination_date<=destination.end_date):
            raise InvalidMenuCopyError("Copy dates must fall within their menu ranges")
        source_rows=self.repository.source_rows(source_menu_id,source_date)
        source_meals={row[1].name.lower():row[1] for row in source_rows}
        source_columns={column.id:column for column in self.repository.menu_columns(source_menu_id)}
        destination_columns={(column.menu_meal_type_id,column.name):column for column in self.repository.menu_columns(destination_menu_id)}
        destination_meals=destination_meals_by_name
        if destination_meals is None:
            destination_meals=self._prepare_destination_meal_mapping(
                destination_menu_id,source_meals.values(),actor_id)
        for _,_,detail,dish in source_rows:
            if detail is not None and (dish is None or not dish.is_active): raise InvalidMenuCopyError("Inactive dish cannot be copied as a new assignment")
        destination_days=[day for day in self.repository.days(destination_menu_id) if day.menu_date==destination_date]
        if mode=="replace":
            for detail in self.repository.details({day.id for day in destination_days}): self.repository.delete(detail)
            self.session.flush()
            for day in destination_days: self.repository.delete(day)
            self.session.flush(); destination_days=[]
        day_by_meal={day.menu_meal_type_id:day for day in destination_days}
        details_by_day={}
        columns_by_day={}
        for detail in self.repository.details({day.id for day in destination_days}):
            details_by_day.setdefault(detail.menu_day_id,set()).add(detail.dish_id)
            if detail.menu_meal_type_column_id is not None:columns_by_day.setdefault(detail.menu_day_id,set()).add(detail.menu_meal_type_column_id)
        next_orders={day.id:len(details_by_day.get(day.id,set())) for day in destination_days}
        source_days={}
        for source_day,source_meal,detail,dish in source_rows:
            dest_meal=destination_meals.get(source_meal.name.lower())
            if dest_meal is None:
                raise InvalidMenuCopyError(f"Source meal type has no destination mapping: {source_meal.name}")
            dest_day=day_by_meal.get(dest_meal.id)
            if dest_day is None:
                dest_day=MenuDay(menu_id=destination_menu_id,menu_date=destination_date,menu_meal_type_id=dest_meal.id,
                    notes=source_day.notes,created_by=actor_id,updated_by=actor_id)
                self.repository.add(dest_day); self.session.flush(); day_by_meal[dest_meal.id]=dest_day
                next_orders[dest_day.id]=0
            source_days[source_day.id]=dest_day
            if detail is not None and detail.dish_id not in details_by_day.setdefault(dest_day.id,set()):
                next_orders[dest_day.id]=next_orders.get(dest_day.id,0)+1
                column_id=None
                if detail.menu_meal_type_column_id is not None:
                    if source_menu_id==destination_menu_id and source_meal.id==dest_meal.id:
                        column_id=detail.menu_meal_type_column_id
                    else:
                        source_column=source_columns.get(detail.menu_meal_type_column_id)
                        destination_column=destination_columns.get((dest_meal.id,source_column.name)) if source_column else None
                        column_id=destination_column.id if destination_column else None
                    if column_id in columns_by_day.setdefault(dest_day.id,set()):column_id=None
                self.repository.add(MenuDish(menu_day_id=dest_day.id,dish_id=detail.dish_id,diner_count=detail.diner_count,
                    menu_meal_type_column_id=column_id,notes=detail.notes,sort_order=next_orders[dest_day.id],created_by=actor_id,updated_by=actor_id))
                details_by_day[dest_day.id].add(detail.dish_id)
                if column_id is not None:columns_by_day[dest_day.id].add(column_id)

    def copy_week(self,destination_menu_id,command: CopyWeekCommand,actor_id):
        source=self.model(command.source_menu_id); destination=self.model(destination_menu_id)
        before=self.aggregate(destination_menu_id)
        if (source.end_date-source.start_date).days != 6 or (destination.end_date-destination.start_date).days != 6:
            raise InvalidMenuCopyError("Whole-week copy requires two exact seven-day menus")
        try:
            destination_by_name=self._prepare_destination_meal_mapping(
                destination.id,self.repository.meal_types(source.id),actor_id)
            for offset in range(7): self._copy_day(destination_menu_id,source.id,source.start_date+timedelta(days=offset),destination.start_date+timedelta(days=offset),command.mode,actor_id,destination_by_name)
            after=self.aggregate(destination_menu_id)
            self.audit.record(actor_id=actor_id,action="copy_week",entity_type="menu",entity_id=destination.id,
                entity_label=destination.name,before_data=before,after_data=after,
                metadata={"source_menu_id":source.id,"mode":command.mode})
            self.session.commit()
        except Exception: self.session.rollback(); raise
        return self.aggregate(destination_menu_id)
