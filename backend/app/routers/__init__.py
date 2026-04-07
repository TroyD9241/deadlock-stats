from fastapi import APIRouter
from app.routers.auth import router as auth_router
from app.routers.players import router as players_router
from app.routers.matches import router as matches_router
from app.routers.heroes import router as heroes_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(players_router)
router.include_router(matches_router)
router.include_router(heroes_router)
