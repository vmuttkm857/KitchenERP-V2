import os
import uuid
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from PIL import Image,UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.audit.service import AuditLogService,audit_snapshot
from app.domains.production.exceptions import ProductionConflict,ProductionImageError,ProductionIngredientNotFound,ProductionMenuNotFound,ProductionProfileNotFound,ProductionStepNotFound,ProductionValidationError,ProductionVersionNotFound
from app.domains.production.models import DishProductionProfile,ProductionBatchIngredient,ProductionBatchVersion,ProductionProcessStep
from app.domains.production.planner import split_production_batches
from app.domains.production.repository import ProductionRepository
from app.domains.production.schemas import IngredientUpdate,ProfileCreate,ProfileUpdate,StepCreate,StepUpdate,VersionCopy,VersionCreate,VersionUpdate

MAX_IMAGE_BYTES=5*1024*1024

class ProductionService:
    def __init__(self,session:Session):self.session=session;self.repository=ProductionRepository(session);self.audit=AuditLogService(session)
    def _profile(self,dish_id):
        value=self.repository.profile(dish_id)
        if value is None:raise ProductionProfileNotFound()
        return value
    def _version(self,dish_id,version_id):
        profile=self._profile(dish_id);value=self.repository.version(version_id)
        if value is None or value.profile_id!=profile.id:raise ProductionVersionNotFound()
        return profile,value
    def _commit(self):
        try:self.session.commit()
        except IntegrityError as exc:self.session.rollback();raise ProductionConflict() from exc
    def _flush(self):
        try:self.session.flush()
        except IntegrityError as exc:self.session.rollback();raise ProductionConflict() from exc
    def create_profile(self,dish_id,data:ProfileCreate,actor_id):
        dish=self.repository.dish(dish_id)
        if dish is None:raise ProductionProfileNotFound()
        if self.repository.profile(dish_id):raise ProductionConflict()
        value=DishProductionProfile(dish_id=dish_id,max_batch_size=data.max_batch_size,notes=data.notes,created_by=actor_id,updated_by=actor_id);self.repository.add(value);self._flush()
        self.audit.record(actor_id=actor_id,action="production_profile_create",entity_type="dish_production_profile",entity_id=value.id,entity_label=dish.name,after_data=audit_snapshot(value,"dish_id","max_batch_size","notes"));self._commit();return self.get_profile(dish_id)
    def update_profile(self,dish_id,data:ProfileUpdate,actor_id):
        value=self._profile(dish_id);before=audit_snapshot(value,"max_batch_size","notes");changes=data.model_dump(exclude_unset=True)
        maximum=changes.get("max_batch_size",value.max_batch_size)
        if any(item.serving_count>maximum for item in self.repository.versions(value.id)):raise ProductionValidationError("Batch version exceeds maximum batch size")
        for key,item in changes.items():setattr(value,key,item)
        value.updated_by=actor_id;self.audit.record(actor_id=actor_id,action="production_profile_update",entity_type="dish_production_profile",entity_id=value.id,before_data=before,after_data=audit_snapshot(value,"max_batch_size","notes"));self._commit();return self.get_profile(dish_id)
    def delete_profile(self,dish_id,actor_id):
        value=self._profile(dish_id);filename=value.image_filename;self.repository.delete(value);self.audit.record(actor_id=actor_id,action="production_profile_delete",entity_type="dish_production_profile",entity_id=value.id,before_data=audit_snapshot(value,"dish_id","max_batch_size","notes","image_filename"));self._commit()
        if filename:self._image_path(filename).unlink(missing_ok=True)
    def create_version(self,dish_id,data:VersionCreate,actor_id):
        profile=self._profile(dish_id)
        if data.serving_count>profile.max_batch_size:raise ProductionValidationError("Batch version exceeds maximum batch size")
        value=ProductionBatchVersion(profile_id=profile.id,serving_count=data.serving_count,name=data.name,is_official=data.is_official,notes=data.notes,created_by=actor_id,updated_by=actor_id);self.repository.add(value);self._flush()
        for recipe,ingredient in self.repository.recipe_rows(dish_id):self.repository.add(ProductionBatchIngredient(version_id=value.id,dish_ingredient_id=recipe.id,ingredient_id=ingredient.id,quantity=recipe.quantity*data.serving_count,unit=recipe.unit,sort_order=recipe.sort_order,usage_category="main_ingredient",quantity_note=None,notes=recipe.notes,created_by=actor_id,updated_by=actor_id))
        self.audit.record(actor_id=actor_id,action="production_version_create",entity_type="production_batch_version",entity_id=value.id,after_data=audit_snapshot(value,"profile_id","serving_count","name","is_official","notes"));self._commit();return self.get_profile(dish_id)
    def copy_version(self,dish_id,source_id,data:VersionCopy,actor_id):
        profile,source=self._version(dish_id,source_id)
        if data.serving_count>profile.max_batch_size:raise ProductionValidationError("Batch version exceeds maximum batch size")
        value=ProductionBatchVersion(profile_id=profile.id,serving_count=data.serving_count,name=data.name,is_official=data.is_official,notes=source.notes,created_by=actor_id,updated_by=actor_id);self.repository.add(value);self._flush();ratio=Decimal(data.serving_count)/Decimal(source.serving_count)
        ingredients=self.repository.ingredients({source.id});steps=self.repository.steps({source.id})
        for item,_,_ in ingredients:self.repository.add(ProductionBatchIngredient(version_id=value.id,dish_ingredient_id=item.dish_ingredient_id,ingredient_id=item.ingredient_id,quantity=item.quantity*ratio,unit=item.unit,usage_category=item.usage_category,sort_order=item.sort_order,quantity_note=item.quantity_note,notes=item.notes,created_by=actor_id,updated_by=actor_id))
        for step in steps:self.repository.add(ProductionProcessStep(version_id=value.id,step_order=step.step_order,step_type=step.step_type,title=step.title,instruction=step.instruction,equipment=step.equipment,duration_seconds=step.duration_seconds,temperature_celsius=step.temperature_celsius,batch_size=step.batch_size,servings_per_tray=step.servings_per_tray,trays_per_batch=step.trays_per_batch,quantity_note=step.quantity_note,notes=step.notes,created_by=actor_id,updated_by=actor_id))
        self.audit.record(actor_id=actor_id,action="production_version_copy",entity_type="production_batch_version",entity_id=value.id,metadata={"source_version_id":source.id,"serving_count":data.serving_count});self._commit();return self.get_profile(dish_id)
    def update_version(self,dish_id,version_id,data:VersionUpdate,actor_id):
        profile,value=self._version(dish_id,version_id);before=audit_snapshot(value,"serving_count","name","is_official","notes");changes=data.model_dump(exclude_unset=True)
        next_count=changes.get("serving_count",value.serving_count)
        if next_count>profile.max_batch_size:raise ProductionValidationError("Batch version exceeds maximum batch size")
        if next_count!=value.serving_count:
            ratio=Decimal(next_count)/Decimal(value.serving_count)
            for item,_,_ in self.repository.ingredients({value.id}):item.quantity*=ratio;item.updated_by=actor_id
        for key,item in changes.items():setattr(value,key,item)
        value.updated_by=actor_id;self.audit.record(actor_id=actor_id,action="production_version_update",entity_type="production_batch_version",entity_id=value.id,before_data=before,after_data=audit_snapshot(value,"serving_count","name","is_official","notes"));self._commit();return self.get_profile(dish_id)
    def delete_version(self,dish_id,version_id,actor_id):
        _,value=self._version(dish_id,version_id);self.repository.delete(value);self.audit.record(actor_id=actor_id,action="production_version_delete",entity_type="production_batch_version",entity_id=value.id,before_data=audit_snapshot(value,"serving_count","name","is_official","notes"));self._commit();return self.get_profile(dish_id)
    def update_ingredient(self,dish_id,version_id,item_id,data:IngredientUpdate,actor_id):
        _,version=self._version(dish_id,version_id);value=self.repository.ingredient(item_id)
        if value is None or value.version_id!=version.id:raise ProductionIngredientNotFound()
        before=audit_snapshot(value,"quantity","unit","usage_category","quantity_note","notes")
        for key,item in data.model_dump(exclude_unset=True).items():setattr(value,key,item)
        value.updated_by=actor_id;self.audit.record(actor_id=actor_id,action="production_ingredient_update",entity_type="production_batch_ingredient",entity_id=value.id,before_data=before,after_data=audit_snapshot(value,"quantity","unit","usage_category","quantity_note","notes"));self._commit();return self.get_profile(dish_id)
    def create_step(self,dish_id,version_id,data:StepCreate,actor_id):
        _,version=self._version(dish_id,version_id);value=ProductionProcessStep(version_id=version.id,created_by=actor_id,updated_by=actor_id,**data.model_dump());self.repository.add(value);self._flush();self.audit.record(actor_id=actor_id,action="production_step_create",entity_type="production_process_step",entity_id=value.id,after_data=data);self._commit();return self.get_profile(dish_id)
    def update_step(self,dish_id,version_id,step_id,data:StepUpdate,actor_id):
        _,version=self._version(dish_id,version_id);value=self.repository.step(step_id)
        if value is None or value.version_id!=version.id:raise ProductionStepNotFound()
        before=audit_snapshot(value,"step_order","step_type","title","instruction","equipment","duration_seconds","temperature_celsius","batch_size","servings_per_tray","trays_per_batch","quantity_note","notes")
        for key,item in data.model_dump(exclude_unset=True).items():setattr(value,key,item)
        value.updated_by=actor_id;self.audit.record(actor_id=actor_id,action="production_step_update",entity_type="production_process_step",entity_id=value.id,before_data=before,after_data=data);self._commit();return self.get_profile(dish_id)
    def delete_step(self,dish_id,version_id,step_id,actor_id):
        _,version=self._version(dish_id,version_id);value=self.repository.step(step_id)
        if value is None or value.version_id!=version.id:raise ProductionStepNotFound()
        self.repository.delete(value);self._flush()
        for order,step in enumerate(self.repository.steps({version.id}),1):step.step_order=order;step.updated_by=actor_id
        self.audit.record(actor_id=actor_id,action="production_step_delete",entity_type="production_process_step",entity_id=value.id);self._commit();return self.get_profile(dish_id)
    def reorder_steps(self,dish_id,version_id,ordered_ids,actor_id):
        _,version=self._version(dish_id,version_id);steps=self.repository.steps({version.id})
        if set(ordered_ids)!={item.id for item in steps}:raise ProductionValidationError("Every step must appear exactly once")
        by_id={item.id:item for item in steps}
        temporary_base=len(steps)
        for order,item_id in enumerate(ordered_ids,1):by_id[item_id].step_order=temporary_base+order;by_id[item_id].updated_by=actor_id
        self._flush()
        for order,item_id in enumerate(ordered_ids,1):by_id[item_id].step_order=order
        self.audit.record(actor_id=actor_id,action="production_steps_reorder",entity_type="production_batch_version",entity_id=version.id,metadata={"ordered_ids":ordered_ids});self._commit();return self.get_profile(dish_id)
    def _assemble(self,profile,dish,versions,ingredients,steps):
        ingredient_map=defaultdict(list);step_map=defaultdict(list)
        for item,code,name in ingredients:ingredient_map[item.version_id].append({"id":item.id,"dish_ingredient_id":item.dish_ingredient_id,"ingredient_id":item.ingredient_id,"ingredient_code":code,"ingredient_name":name,"quantity":item.quantity,"unit":item.unit,"usage_category":item.usage_category,"sort_order":item.sort_order,"quantity_note":item.quantity_note,"notes":item.notes})
        for item in steps:step_map[item.version_id].append({key:getattr(item,key) for key in ("id","step_order","step_type","title","instruction","equipment","duration_seconds","temperature_celsius","batch_size","servings_per_tray","trays_per_batch","quantity_note","notes")})
        return {"id":profile.id,"dish_id":dish.id,"dish_code":dish.code,"dish_name":dish.name,"max_batch_size":profile.max_batch_size,"notes":profile.notes,"has_image":self._has_image(profile.image_filename),"image_mime_type":profile.image_mime_type,"image_size_bytes":profile.image_size_bytes,"created_at":profile.created_at,"updated_at":profile.updated_at,"versions":[{"id":item.id,"serving_count":item.serving_count,"name":item.name,"is_official":item.is_official,"notes":item.notes,"created_at":item.created_at,"updated_at":item.updated_at,"ingredients":ingredient_map[item.id],"steps":step_map[item.id]} for item in versions]}
    def get_profile(self,dish_id):
        dish=self.repository.dish(dish_id);profile=self._profile(dish_id);versions=self.repository.versions(profile.id);ids={item.id for item in versions};return self._assemble(profile,dish,versions,self.repository.ingredients(ids),self.repository.steps(ids))
    def _profile_bundle(self,dish_ids):
        profiles=self.repository.profiles(dish_ids);versions=self.repository.versions_for_profiles({item.id for item in profiles});ids={item.id for item in versions};ingredients=self.repository.ingredients(ids);steps=self.repository.steps(ids);dish_map={dish_id:self.repository.dish(dish_id) for dish_id in dish_ids};version_map=defaultdict(list)
        for version in versions:version_map[version.profile_id].append(version)
        return {profile.dish_id:self._assemble(profile,dish_map[profile.dish_id],version_map[profile.id],ingredients,steps) for profile in profiles}
    def dish_plan(self,dish_id,diner_count,sort_order=1,notes=None,bundle=None):
        profile=(bundle or self._profile_bundle({dish_id})).get(dish_id);dish=self.repository.dish(dish_id)
        if profile is None:return {"dish_id":dish_id,"dish_code":dish.code,"dish_name":dish.name,"diner_count":diner_count,"sort_order":sort_order,"notes":notes,"profile_notes":None,"profile_missing":True,"max_batch_size":None,"has_image":False,"batch_count":0,"batches":[]}
        official=[(item["serving_count"],str(item["id"])) for item in profile["versions"] if item["is_official"]]
        choices=split_production_batches(diner_count,profile["max_batch_size"],official);versions={str(item["id"]):item for item in profile["versions"]};batches=[]
        for index,choice in enumerate(choices,1):
            source=versions.get(choice.version_id or "");ratio=Decimal(choice.serving_count)/Decimal(choice.source_serving_count) if source and choice.source_serving_count else Decimal(1)
            if source:ingredients=[{**item,"quantity":item["quantity"]*ratio} for item in source["ingredients"]];steps=source["steps"]
            else:
                ingredients=[{"ingredient_id":ingredient.id,"ingredient_code":ingredient.code,"ingredient_name":ingredient.name,"quantity":recipe.quantity*choice.serving_count,"unit":recipe.unit,"usage_category":"main_ingredient","quantity_note":None,"notes":recipe.notes} for recipe,ingredient in self.repository.recipe_rows(dish_id)];steps=[]
            batches.append({"batch_number":index,"serving_count":choice.serving_count,"official":choice.official,"version_id":uuid.UUID(choice.version_id) if choice.version_id else None,"version_name":source["name"] if source else None,"version_notes":source["notes"] if source else None,"source_serving_count":choice.source_serving_count,"ingredients":ingredients,"steps":steps})
        return {"dish_id":dish_id,"dish_code":dish.code,"dish_name":dish.name,"diner_count":diner_count,"sort_order":sort_order,"notes":notes,"profile_notes":profile["notes"],"profile_missing":False,"max_batch_size":profile["max_batch_size"],"has_image":profile["has_image"],"batch_count":len(batches),"batches":batches}
    def menu_plan(self,menu_id,menu_date=None,meal_id=None):
        menu=self.repository.menu(menu_id)
        if menu is None:raise ProductionMenuNotFound()
        if menu_date is not None and not(menu.start_date<=menu_date<=menu.end_date):raise ProductionValidationError("Date is outside menu range")
        if meal_id is not None:
            meal=self.repository.meal(meal_id)
            if meal is None or meal.menu_id!=menu_id:raise ProductionValidationError("Meal type does not belong to menu")
        rows=self.repository.menu_rows(menu_id,menu_date,meal_id);bundle=self._profile_bundle({row["dish_id"] for row in rows});days=[]
        for row in rows:
            if not days or days[-1]["menu_date"]!=row["menu_date"]:days.append({"menu_date":row["menu_date"],"meals":[]})
            meals=days[-1]["meals"]
            if not meals or meals[-1]["meal_type_id"]!=row["meal_id"]:meals.append({"meal_type_id":row["meal_id"],"meal_type_name":row["meal_name"],"meal_order":row["meal_order"],"dishes":[]})
            meals[-1]["dishes"].append(self.dish_plan(row["dish_id"],row["diner_count"],row["sort_order"],row["notes"],bundle))
        return {"menu_id":menu.id,"menu_name":menu.name,"days":days}
    def _media_dir(self):path=Path(settings.media_root).resolve()/"dish-images";path.mkdir(parents=True,exist_ok=True);return path
    def _image_path(self,filename):
        path=(Path(settings.media_root).resolve()/"dish-images"/filename).resolve();root=(Path(settings.media_root).resolve()/"dish-images")
        if path.parent!=root:raise ProductionImageError()
        return path
    def _has_image(self,filename):
        if not filename:return False
        try:return self._image_path(filename).is_file()
        except (OSError,ProductionImageError):return False
    def save_image(self,dish_id,payload,content_type,actor_id):
        profile=self._profile(dish_id)
        if len(payload)>MAX_IMAGE_BYTES:raise ProductionImageError("Image exceeds 5 MB")
        allowed={"JPEG":("image/jpeg","jpg"),"PNG":("image/png","png"),"WEBP":("image/webp","webp")}
        try:
            image=Image.open(BytesIO(payload));image.verify();image=Image.open(BytesIO(payload));image.load()
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:raise ProductionImageError("Invalid image") from exc
        if image.format not in allowed or content_type!=allowed[image.format][0]:raise ProductionImageError("Only JPEG, PNG and WEBP are supported")
        mime,extension=allowed[image.format];filename=f"{uuid.uuid4()}.{extension}";directory=self._media_dir();temporary=directory/f".{filename}.tmp";target=directory/filename
        image.save(temporary,format=image.format);os.replace(temporary,target);old=profile.image_filename;profile.image_filename=filename;profile.image_mime_type=mime;profile.image_size_bytes=target.stat().st_size;profile.updated_by=actor_id
        try:self.audit.record(actor_id=actor_id,action="production_image_replace" if old else "production_image_upload",entity_type="dish_production_profile",entity_id=profile.id,after_data={"image_mime_type":mime,"image_size_bytes":profile.image_size_bytes});self._commit()
        except Exception:target.unlink(missing_ok=True);raise
        if old:self._image_path(old).unlink(missing_ok=True)
        return self.get_profile(dish_id)
    def delete_image(self,dish_id,actor_id):
        profile=self._profile(dish_id)
        if not profile.image_filename:return self.get_profile(dish_id)
        filename=profile.image_filename;profile.image_filename=None;profile.image_mime_type=None;profile.image_size_bytes=None;profile.updated_by=actor_id;self.audit.record(actor_id=actor_id,action="production_image_delete",entity_type="dish_production_profile",entity_id=profile.id);self._commit();self._image_path(filename).unlink(missing_ok=True);return self.get_profile(dish_id)
    def image(self,dish_id):
        profile=self._profile(dish_id)
        if not profile.image_filename:raise ProductionImageError("Image not found")
        path=self._image_path(profile.image_filename)
        if not path.is_file():raise ProductionImageError("Image not found")
        return path,profile.image_mime_type
