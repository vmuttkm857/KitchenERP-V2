from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.categories import router as categories_router
from app.api.v1.routes.dishes import router as dishes_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.ingredients import router as ingredients_router
from app.api.v1.routes.recipes import router as recipes_router
from app.api.v1.routes.suppliers import router as suppliers_router


api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(suppliers_router)
api_v1_router.include_router(ingredients_router)
api_v1_router.include_router(dishes_router)
api_v1_router.include_router(recipes_router)
