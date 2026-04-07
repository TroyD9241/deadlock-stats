from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Match(Base):
    __tablename__ = "matches"

    match_id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    duration_secs = Column(Integer)
    match_mode = Column(String(50))
    winning_team = Column(Integer)  # 0 or 1
    patch_version = Column(String(20))
    average_rank = Column(Integer)
    source = Column(String(20), default="deadlock_api")

    players = relationship("MatchPlayer", back_populates="match")


class MatchPlayer(Base):
    __tablename__ = "match_players"

    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    team = Column(Integer, nullable=False)
    hero_id = Column(Integer, ForeignKey("heroes.hero_id"))
    kills = Column(Integer, default=0)
    deaths = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    net_worth = Column(Integer, default=0)
    last_hits = Column(Integer, default=0)
    denies = Column(Integer, default=0)
    damage_dealt = Column(Integer, default=0)
    damage_taken = Column(Integer, default=0)
    healing_done = Column(Integer, default=0)
    creep_kills = Column(Integer, default=0)
    tower_kills = Column(Integer, default=0)
    mvp = Column(Boolean, default=False)
    ranked_badge_level = Column(Integer)

    match = relationship("Match", back_populates="players")
    player = relationship("Player")
