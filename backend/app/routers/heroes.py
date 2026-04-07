from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.reference import Hero, Ability

router = APIRouter(prefix="/heroes", tags=["heroes"])


@router.get("/")
def list_heroes(db: Session = Depends(get_db)):
    return db.query(Hero).all()


@router.get("/{hero_id}")
def get_hero(hero_id: int, db: Session = Depends(get_db)):
    hero = db.query(Hero).filter(Hero.hero_id == hero_id).first()
    if not hero:
        raise HTTPException(status_code=404, detail="Hero not found")
    return hero


@router.get("/{hero_id}/items")
def get_hero_items(hero_id: int, db: Session = Depends(get_db)):
    return []
