import logging
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.exceptions import InvalidCredentialsError
from app.domains.menus.exceptions import (
    DuplicateMenuDishError, InvalidMenuCategoryError, InvalidMenuCopyError,
    InvalidMenuDateRangeError, InvalidMenuStructureError, MealTypeInUseError,
    MealTypeNameExistsError, MealTypeNotFoundError, MenuInUseError, MenuNotFoundError,
)
from app.domains.menus.schemas import (
    CopyDayCommand, CopyWeekCommand, MealTypeCreate, MealTypePublic, MealTypeReorder, MealTypeUpdate,
    MenuCreate, MenuEditorAggregate, MenuEditorSave, MenuList, MenuPublic, MenuUpdate,
)
from app.domains.menus.service import MenuService
from app.domains.users.models import User
from app.shared.schemas import PaginationMeta, PasswordConfirmation

router=APIRouter(prefix="/menus",tags=["menus"],dependencies=[Depends(get_current_user)])
logger=logging.getLogger("kitchenerp.menus")


def error(exc):
    if isinstance(exc,MenuNotFoundError): return HTTPException(404,"Menu not found")
    if isinstance(exc,MealTypeNotFoundError): return HTTPException(404,"Meal type not found")
    if isinstance(exc,InvalidMenuCategoryError): return HTTPException(422,"Menu category must exist and be active")
    if isinstance(exc,InvalidMenuDateRangeError): return HTTPException(422,str(exc) or "Invalid menu date range")
    if isinstance(exc,MealTypeNameExistsError): return HTTPException(409,"Meal type name already exists in this menu")
    if isinstance(exc,(MenuInUseError,MealTypeInUseError)): return HTTPException(409,"Resource is referenced and cannot be permanently deleted")
    if isinstance(exc,DuplicateMenuDishError): return HTTPException(409,"A dish may appear only once in a meal slot")
    if isinstance(exc,(InvalidMenuStructureError,InvalidMenuCopyError)): return HTTPException(422,str(exc))
    if isinstance(exc,InvalidCredentialsError): return HTTPException(401,"Password verification failed")
    logger.exception("Unhandled menu operation error")
    return HTTPException(400,"Menu operation failed")


@router.get("",response_model=MenuList)
def menu_list(session:Annotated[Session,Depends(get_db_session)],page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),active:bool|None=None,search:str|None=None,category_id:uuid.UUID|None=None,start_date:date|None=None,end_date:date|None=None):
    try:
        items,total=MenuService(session).list(page,page_size,active,search,category_id,start_date,end_date)
        return MenuList(items=[MenuPublic.model_validate(item) for item in items],pagination=PaginationMeta(page=page,page_size=page_size,total=total))
    except Exception as exc:raise error(exc) from exc


@router.post("",response_model=MenuPublic,status_code=201)
def create(data:MenuCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuPublic.model_validate(MenuService(session).create(data,user.id))
    except Exception as exc:raise error(exc) from exc


@router.get("/{menu_id}",response_model=MenuPublic)
def detail(menu_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuPublic.model_validate(MenuService(session).get(menu_id))
    except Exception as exc:raise error(exc) from exc


@router.patch("/{menu_id}",response_model=MenuPublic)
def update(menu_id:uuid.UUID,data:MenuUpdate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuPublic.model_validate(MenuService(session).update(menu_id,data,user.id))
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/deactivate",response_model=MenuPublic)
def deactivate(menu_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuPublic.model_validate(MenuService(session).set_active(menu_id,False,user.id))
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/reactivate",response_model=MenuPublic)
def reactivate(menu_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuPublic.model_validate(MenuService(session).set_active(menu_id,True,user.id))
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/hard-delete",status_code=204)
def hard_delete(menu_id:uuid.UUID,data:PasswordConfirmation,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:MenuService(session).hard_delete(menu_id,user.id,data.password)
    except Exception as exc:raise error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{menu_id}/meal-types",response_model=list[MealTypePublic])
def meal_types(menu_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:return [MealTypePublic.model_validate(item,from_attributes=True) for item in MenuService(session).meal_types(menu_id)]
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/meal-types",response_model=MealTypePublic,status_code=201)
def create_meal(menu_id:uuid.UUID,data:MealTypeCreate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MealTypePublic.model_validate(MenuService(session).create_meal_type(menu_id,data,user.id),from_attributes=True)
    except Exception as exc:raise error(exc) from exc


@router.patch("/{menu_id}/meal-types/{meal_type_id}",response_model=MealTypePublic)
def update_meal(menu_id:uuid.UUID,meal_type_id:uuid.UUID,data:MealTypeUpdate,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MealTypePublic.model_validate(MenuService(session).update_meal_type(menu_id,meal_type_id,data,user.id),from_attributes=True)
    except Exception as exc:raise error(exc) from exc


@router.put("/{menu_id}/meal-types/reorder",response_model=list[MealTypePublic])
def reorder_meals(menu_id:uuid.UUID,data:MealTypeReorder,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return [MealTypePublic.model_validate(item,from_attributes=True) for item in MenuService(session).reorder_meal_types(menu_id,data,user.id)]
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/meal-types/{meal_type_id}/deactivate",response_model=MealTypePublic)
def deactivate_meal(menu_id:uuid.UUID,meal_type_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MealTypePublic.model_validate(MenuService(session).set_meal_active(menu_id,meal_type_id,False,user.id),from_attributes=True)
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/meal-types/{meal_type_id}/reactivate",response_model=MealTypePublic)
def reactivate_meal(menu_id:uuid.UUID,meal_type_id:uuid.UUID,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MealTypePublic.model_validate(MenuService(session).set_meal_active(menu_id,meal_type_id,True,user.id),from_attributes=True)
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/meal-types/{meal_type_id}/hard-delete",status_code=204)
def delete_meal(menu_id:uuid.UUID,meal_type_id:uuid.UUID,data:PasswordConfirmation,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:MenuService(session).hard_delete_meal(menu_id,meal_type_id,user.id,data.password)
    except Exception as exc:raise error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{menu_id}/editor",response_model=MenuEditorAggregate)
def editor(menu_id:uuid.UUID,session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuEditorAggregate.model_validate(MenuService(session).aggregate(menu_id))
    except Exception as exc:raise error(exc) from exc


@router.put("/{menu_id}/editor",response_model=MenuEditorAggregate)
def save_editor(menu_id:uuid.UUID,data:MenuEditorSave,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuEditorAggregate.model_validate(MenuService(session).save_editor(menu_id,data,user.id))
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/copy-day",response_model=MenuEditorAggregate)
def copy_day(menu_id:uuid.UUID,data:CopyDayCommand,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuEditorAggregate.model_validate(MenuService(session).copy_day(menu_id,data,user.id))
    except Exception as exc:raise error(exc) from exc


@router.post("/{menu_id}/copy-week",response_model=MenuEditorAggregate)
def copy_week(menu_id:uuid.UUID,data:CopyWeekCommand,user:Annotated[User,Depends(get_current_user)],session:Annotated[Session,Depends(get_db_session)]):
    try:return MenuEditorAggregate.model_validate(MenuService(session).copy_week(menu_id,data,user.id))
    except Exception as exc:raise error(exc) from exc
