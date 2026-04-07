from typing import Optional
from pydantic import BaseModel


class PlayerResponse(BaseModel):
    steam_id: int
    display_name: str
    avatar_url: Optional[str] = None
    rank: Optional[int] = None
    rank_tier: Optional[int] = None


class PlayerMatchResponse(BaseModel):
    match_id: int
    hero_id: int
    team: int
    kills: int
    deaths: int
    assists: int
    win: bool


class PlayerStatsResponse(BaseModel):
    matches_played: int
    wins: int
    losses: int
    win_rate: float
    avg_kills: float
    avg_deaths: float
    avg_assists: float
