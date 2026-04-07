from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Hero(Base):
    __tablename__ = "heroes"

    hero_id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500))
    image_url = Column(String(500))
    updated_at = Column(DateTime, default=datetime.utcnow)

    abilities = relationship("Ability", back_populates="hero")


class Item(Base):
    __tablename__ = "items"

    item_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    cost = Column(Integer)
    category = Column(String(50))
    tier = Column(Integer)
    description = Column(String(500))
    image_url = Column(String(500))
    updated_at = Column(DateTime, default=datetime.utcnow)


class Ability(Base):
    __tablename__ = "abilities"

    ability_id = Column(Integer, primary_key=True)
    hero_id = Column(Integer, ForeignKey("heroes.hero_id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(500))
    image_url = Column(String(500))

    hero = relationship("Hero", back_populates="abilities")
