from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    account_id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255))
    email_verified = Column(Boolean, default=False)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)

    player = relationship("Player", back_populates="account", foreign_keys=[steam_id])
    follows = relationship("AccountFollow", back_populates="account")


class Player(Base):
    __tablename__ = "players"

    steam_id = Column(Integer, primary_key=True)
    account_id = Column(String(36), ForeignKey("accounts.account_id"), nullable=True)
    display_name = Column(String(100), nullable=False)
    avatar_url = Column(String(500))
    rank = Column(Integer)
    rank_tier = Column(Integer)
    opted_out = Column(Boolean, default=False)
    tracked_since = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow)

    account = relationship(
        "Account", back_populates="player", foreign_keys=[account_id]
    )
    name_history = relationship("PlayerNameHistory", back_populates="player")


class PlayerNameHistory(Base):
    __tablename__ = "player_name_history"

    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    display_name = Column(String(100), primary_key=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)


class AccountFollow(Base):
    __tablename__ = "account_follows"

    account_id = Column(String(36), ForeignKey("accounts.account_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    followed_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="follows")
    player = relationship("Player")
