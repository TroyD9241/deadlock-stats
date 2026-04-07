from fastapi import HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.account import Player


async def check_opted_out(steam_id: int, db: Session = Depends(get_db)) -> None:
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
    if player and player.opted_out:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
