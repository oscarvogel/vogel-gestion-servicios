from fastapi import APIRouter

from app.api.v1 import auth, companies

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(companies.router, prefix="/companies", tags=["companies"])
