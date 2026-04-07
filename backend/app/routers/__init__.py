from fastapi import APIRouter
from app.routers.auth import router as auth_router
from app.routers.players import router as players_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(players_router)
