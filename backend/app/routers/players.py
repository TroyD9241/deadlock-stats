from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.database import get_db
from app.models.match import Match, MatchPlayer
from app.models.account import Player
from app.schemas.player import PlayerResponse, PlayerMatchResponse, PlayerStatsResponse
from app.middleware.gdpr import check_opted_out

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/search")
def search_players(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return (
        db.query(Player)
        .filter(
            Player.display_name.ilike(f"%{q}%"),
            Player.opted_out == False,  # noqa: E712
        )
        .limit(20)
        .all()
    )


@router.get("/{steam_id}", response_model=PlayerResponse)
def get_player(steam_id: int, db: Session = Depends(get_db)):
    check_opted_out(steam_id, db)
    player = db.query(Player).filter(Player.steam_id == steam_id).first()
    if not player or player.opted_out:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@router.get("/{steam_id}/matches")
def get_player_matches(steam_id: int, limit: int = 20, db: Session = Depends(get_db)):
    match_players = (
        db.query(MatchPlayer)
        .filter(MatchPlayer.steam_id == steam_id)
        .join(Match)
        .order_by(Match.started_at.desc())
        .limit(limit)
        .all()
    )
    results = []
    for mp in match_players:
        match = mp.match
        win = match.winning_team == mp.team
        results.append(
            PlayerMatchResponse(
                match_id=mp.match_id,
                hero_id=mp.hero_id,
                team=mp.team,
                kills=mp.kills,
                deaths=mp.deaths,
                assists=mp.assists,
                win=win,
            )
        )
    return results


@router.get("/{steam_id}/stats")
def get_player_stats(steam_id: int, window: str = "30d", db: Session = Depends(get_db)):
    if window == "30d":
        cutoff = datetime.utcnow() - timedelta(days=30)
    elif window == "7d":
        cutoff = datetime.utcnow() - timedelta(days=7)
    elif window == "1d":
        cutoff = datetime.utcnow() - timedelta(days=1)
    else:
        cutoff = None

    query = db.query(MatchPlayer).filter(MatchPlayer.steam_id == steam_id).join(Match)

    if cutoff:
        query = query.filter(Match.started_at >= cutoff)

    match_players = query.all()

    if not match_players:
        return PlayerStatsResponse(
            matches_played=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            avg_kills=0.0,
            avg_deaths=0.0,
            avg_assists=0.0,
        )

    matches_played = len(match_players)
    wins = sum(1 for mp in match_players if mp.match.winning_team == mp.team)
    losses = matches_played - wins
    win_rate = wins / matches_played if matches_played > 0 else 0.0
    avg_kills = sum(mp.kills for mp in match_players) / matches_played
    avg_deaths = sum(mp.deaths for mp in match_players) / matches_played
    avg_assists = sum(mp.assists for mp in match_players) / matches_played

    return PlayerStatsResponse(
        matches_played=matches_played,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_kills=avg_kills,
        avg_deaths=avg_deaths,
        avg_assists=avg_assists,
    )
