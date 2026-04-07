from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.match import Match, MatchPlayer

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.match_id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.get("/{match_id}/builds")
def get_match_builds(match_id: int, db: Session = Depends(get_db)):
    return {"items": [], "abilities": []}
