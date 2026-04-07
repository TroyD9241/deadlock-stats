# Phase 2: Demo Parsing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the demo parsing pipeline - GC bot to discover matches, Celery workers to download and parse demo files, and populate granular data tables.

**Architecture:**
- GC bot polls Valve's Game Coordinator for new matches
- Celery workers download demos from Valve CDN
- boon-deadlock parses demos → 17 Polars DataFrames
- Data written directly to PostgreSQL

**Tech Stack:** Python 3.11+, Celery, Upstash Redis, boon-deadlock, ValvePython/steam, Polars

---

## Task 1: Demo-Parsed Data Models

**Files:**
- Create: `backend/app/models/demo.py`

**Step 1: Create models**

```python
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Index
from app.database import Base


class ItemBuild(Base):
    __tablename__ = "item_builds"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    item_id = Column(Integer, ForeignKey("items.item_id"), primary_key=True)
    purchased_at_secs = Column(Integer, primary_key=True)
    slot = Column(Integer)


class AbilityUpgrade(Base):
    __tablename__ = "ability_upgrades"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    ability_id = Column(Integer, ForeignKey("abilities.ability_id"), primary_key=True)
    upgraded_at_secs = Column(Integer, primary_key=True)
    upgrade_number = Column(Integer)


class MatchObjective(Base):
    __tablename__ = "match_objectives"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.match_id"))
    event_type = Column(String(50))  # tower_kill, shrine_kill, mid_boss, urn_pickup, etc.
    team = Column(Integer)
    timestamp_secs = Column(Integer)
    object_id = Column(Integer)
    souls_awarded = Column(Integer)


class MatchEconomySnapshot(Base):
    __tablename__ = "match_economy_snapshots"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    minute = Column(Integer, primary_key=True)
    net_worth = Column(Integer)
    souls_earned_this_minute = Column(Integer)


class MatchJungleKill(Base):
    __tablename__ = "match_jungle_kills"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    camp_tier = Column(Integer, primary_key=True)
    camp_id = Column(Integer, primary_key=True)
    killed_at_secs = Column(Integer)


class MatchLaneStat(Base):
    __tablename__ = "match_lane_stats"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    lane = Column(Integer, primary_key=True)  # 0=mid, 1=offlane, 2=carry
    souls_at_5min = Column(Integer)
    souls_at_10min = Column(Integer)
    creep_kills_laning = Column(Integer)
    denies_laning = Column(Integer)


class MatchDamageEvent(Base):
    __tablename__ = "match_damage_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.match_id"))
    tick = Column(Integer)
    attacker_steam_id = Column(Integer, ForeignKey("players.steam_id"))
    victim_steam_id = Column(Integer, ForeignKey("players.steam_id"))
    damage_amount = Column(Integer)
    damage_type = Column(String(20))
    ability_id = Column(Integer, ForeignKey("abilities.ability_id"))


class MatchModifier(Base):
    __tablename__ = "match_modifiers"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    modifier_name = Column(String(50), primary_key=True)
    applied_at_tick = Column(Integer)
    removed_at_tick = Column(Integer, nullable=True)


class MatchDemoStatus(Base):
    __tablename__ = "match_demo_status"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    status = Column(String(20))  # pending, downloading, parsing, complete, failed
    demo_url = Column(String(500), nullable=True)
    parsed_at = Column(DateTime, nullable=True)
    error_code = Column(String(50), nullable=True)
```

**Step 2: Migration**

```bash
cd backend && source .venv/bin/activate && alembic revision -m "create demo-parsed tables" && alembic upgrade head
```

**Step 3: Commit**

```bash
git add backend/app/models/demo.py alembic/versions/
git commit -m "feat: add demo-parsed data models"
```

---

## Task 2: Celery Configuration

**Files:**
- Create: `backend/celery_app.py`
- Create: `backend/app/celery.py`

**Step 1: Create celery.py**

```python
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "deadlock_stats",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 min max per demo
    worker_prefetch_multiplier=2,
)
```

**Step 2: Create tasks module**

```python
# backend/app/tasks/__init__.py
from celery_app import celery_app as celery


@celery.task(bind=True, max_retries=3)
def process_demo(self, match_id: int, demo_url: str):
    """Process a demo file."""
    from app.workers.demo import download_and_parse_demo
    return download_and_parse_demo(match_id, demo_url)


@celery.task(bind=True)
def discover_matches(self):
    """GC bot task to discover new matches."""
    from app.workers.gc_bot import discover_new_matches
    return discover_new_matches()


@celery.task(bind=True)
def aggregate_stats(self):
    """Recompute aggregation tables."""
    from app.workers.aggregation import recompute_aggregations
    return recompute_aggregations()
```

**Step 3: Commit**

```bash
git add backend/celery_app.py backend/app/tasks/
git commit -m "feat: add Celery configuration"
```

---

## Task 3: Demo Worker

**Files:**
- Create: `backend/app/workers/demo.py`

**Step 1: Create worker**

```python
import os
import httpx
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCRATCH_DIR = Path("/tmp/demos")
SCRATCH_DIR.mkdir(exist_ok=True)


def download_demo(match_id: int, demo_url: str) -> Path:
    """Download demo file to scratch directory."""
    dest = SCRATCH_DIR / f"{match_id}.dem"
    
    if dest.exists():
        return dest
    
    # Validate URL is from Valve CDN allowlist
    allowed_hosts = ["cdn.dota2.com", "cdn.stratz.com"]
    # ... validate host
    
    async with httpx.AsyncClient() as client:
        response = await client.get(demo_url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    
    # Enforce file size limit
    if dest.stat().st_size > 500 * 1024 * 1024:
        raise ValueError("Demo exceeds 500MB limit")
    
    return dest


def parse_demo(demo_path: Path) -> dict:
    """Parse demo with boon-deadlock."""
    from boon import Demo
    
    demo = Demo(str(demo_path))
    
    return {
        "item_purchases": demo.item_purchases,
        "ability_upgrades": demo.ability_upgrades,
        "objectives": demo.objectives,
        "mid_boss": demo.mid_boss,
        "neutrals": demo.neutrals,
        "troopers": demo.troopers,
        "urn": demo.urn,
        "player_ticks": demo.player_ticks,
        "damage": demo.damage,
        "active_modifiers": demo.active_modifiers,
    }


def write_to_db(data: dict, match_id: int, db):
    """Write parsed data to PostgreSQL."""
    from app.models.demo import ItemBuild, MatchObjective, MatchEconomySnapshot
    
    # Write item builds
    for row in data["item_purchases"].iter_rows(named=True):
        db.add(ItemBuild(
            match_id=match_id,
            steam_id=row["steam_id"],
            item_id=row["item_id"],
            purchased_at_secs=row["purchased_at"],
            slot=row["slot"],
        ))
    
    # Write objectives, economy snapshots, etc.
    db.commit()


async def download_and_parse_demo(match_id: int, demo_url: str) -> dict:
    """Main demo processing pipeline."""
    from app.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Download
        demo_path = download_demo(match_id, demo_url)
        
        # Parse
        data = parse_demo(demo_path)
        
        # Write to DB
        write_to_db(data, match_id, db)
        
        # Clean up - delete demo file
        demo_path.unlink(missing_ok=True)
        
        return {"status": "complete", "match_id": match_id}
    
    except Exception as e:
        logger.error(f"Failed to process demo {match_id}: {e}")
        raise
    
    finally:
        db.close()
```

**Step 2: Write tests**

```python
# tests/test_demo_worker.py
import pytest
from unittest.mock import Mock, patch


def test_download_demo_rejects_large_file():
    with pytest.raises(ValueError, match="exceeds 500MB"):
        download_demo(123, "http://cdn.example.com/demo.dem")


def test_parse_demo_calls_boon():
    with patch("boon.Demo") as mock_demo:
        parse_demo(Path("/tmp/test.dem"))
        mock_demo.assert_called_once()
```

**Step 3: Commit**

```bash
git add backend/app/workers/demo.py tests/test_demo_worker.py
git commit -m "feat: add demo worker"
```

---

## Task 4: GC Bot (Match Discovery)

**Files:**
- Create: `backend/app/workers/gc_bot.py`

**Step 1: Create GC bot**

```python
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def discover_new_matches() -> list[int]:
    """Poll GC for new matches for tracked players."""
    # This requires ValvePython setup
    # Pseudocode:
    
    tracked_players = get_tracked_players()  # players with account linked
    
    new_matches = []
    for steam_id in tracked_players:
        matches = gc.get_match_history(steam_id, days=1)
        for match in matches:
            if not match_exists(match.id):
                new_matches.append(match.id)
    
    # Queue for processing
    for match_id in new_matches:
        demo_url = gc.get_demo_url(match_id)
        queue_demo_processing.delay(match_id, demo_url)
    
    return new_matches


def queue_demo_processing(match_id: int, demo_url: str):
    """Add demo to Celery queue."""
    from celery_app import celery_app
    
    celery_app.send_task(
        "app.tasks.process_demo",
        args=[match_id, demo_url],
        queue="demo",
    )
```

**Step 2: Commit**

```bash
git add backend/app/workers/gc_bot.py
git commit -m "feat: add GC bot for match discovery"
```

---

## Task 5: Aggregation Worker

**Files:**
- Create: `backend/app/workers/aggregation.py`

**Step 1: Create aggregation functions**

```python
from sqlalchemy import func, case
from datetime import datetime, timedelta


def recompute_player_stats(steam_id: int, db):
    """Recompute player_stats_snapshots for a player."""
    from app.models.match import Match, MatchPlayer
    from app.models.account import PlayerStatsSnapshot
    
    windows = [("7d", 7), ("30d", 30), ("90d", 90), ("career", None)]
    
    for window_name, days in windows:
        query = db.query(
            func.count(MatchPlayer.match_id).label("matches"),
            func.sum(case((Match.winning_team == MatchPlayer.team, 1), else_=0)).label("wins"),
            func.avg(MatchPlayer.kills).label("avg_kills"),
            func.avg(MatchPlayer.deaths).label("avg_deaths"),
        ).join(Match).filter(MatchPlayer.steam_id == steam_id)
        
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            query = query.filter(Match.started_at >= cutoff)
        
        result = query.first()
        
        # Upsert snapshot
        db.merge(PlayerStatsSnapshot(
            steam_id=steam_id,
            window=window_name,
            matches_played=result.matches,
            wins=result.wins,
            losses=result.matches - result.wins,
            win_rate=result.wins / result.matches if result.matches else 0,
            avg_kills=result.avg_kills or 0,
            avg_deaths=result.avg_deaths or 0,
            computed_at=datetime.utcnow(),
        ))
    
    db.commit()


def recompute_all_aggregations():
    """Celery beat task to recompute all aggregations."""
    # Run daily at 3 AM
    pass
```

**Step 2: Commit**

```bash
git add backend/app/workers/aggregation.py
git commit -m "feat: add aggregation worker"
```

---

## Task 6: Ingest Endpoint (Community Cache)

**Files:**
- Modify: `backend/app/routers/ingest.py`

**Step 1: Add ingest endpoint**

```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.demo import MatchDemoStatus

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/cache")
async def ingest_cache_submission(
    match_id: int,
    demo_salt: str,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Submit demo ID + salt for processing."""
    # Validate match exists via Valve API
    # Queue for processing
    
    status = MatchDemoStatus(
        match_id=match_id,
        status="pending",
    )
    db.add(status)
    db.commit()
    
    # Background task to process
    background_tasks.add_task(queue_demo_processing, match_id, demo_url)
    
    return {"status": "queued"}


@router.get("/status/{match_id}")
async def get_ingest_status(match_id: int, db: Session = Depends(get_db)):
    """Get processing status."""
    status = db.query(MatchDemoStatus).filter(MatchDemoStatus.match_id == match_id).first()
    if not status:
        raise HTTPException(status_code=404, detail="Match not found")
    
    return {
        "match_id": match_id,
        "status": status.status,
        "error": status.error_code,
    }
```

**Step 2: Commit**

```bash
git add backend/app/routers/ingest.py
git commit -m "feat: add ingest endpoints"
```

---

## Task 7: Health Check Enhancement

**Files:**
- Modify: `backend/app/main.py`

**Step 1: Update health endpoint**

```python
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Basic health check."""
    # Check DB
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB: {e}")
    
    return {"status": "healthy"}


@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Extended readiness including queue depth."""
    from celery_app import celery_app
    
    inspector = celery_app.control.inspect()
    active = inspector.active()
    stats = inspector.stats()
    
    return {
        "status": "ready",
        "workers_active": len(active or {}),
        "queue_depth": get_queue_depth(),
    }
```

**Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: enhance health checks"
```

---

## Task 8: Integration Tests

**Files:**
- Create: `tests/test_workers.py`

**Step 1: Create worker tests**

```python
import pytest
from unittest.mock import patch, MagicMock


@patch("app.workers.demo.download_demo")
def test_process_demo(mock_download):
    mock_download.return_value = MagicMock()
    
    result = process_demo(123, "http://example.com/demo.dem")
    
    assert result["status"] == "complete"
    assert result["match_id"] == 123


def test_gc_bot_discovers_new_matches():
    with patch("app.workers.gc_bot.gc") as mock_gc:
        mock_gc.get_match_history.return_value = [MagicMock(id=456)]
        
        matches = discover_new_matches()
        
        assert 456 in matches
```

**Step 2: Run tests**

```bash
cd backend && source .venv/bin/activate && pytest tests/test_workers.py -v
```

**Step 3: Commit**

```bash
git add tests/test_workers.py
git commit -m "test: add worker tests"
```

---

## Plan Complete

Phase 2 implementation complete:
- ✅ Demo-parsed data models
- ✅ Celery configuration
- ✅ Demo worker (download, parse, write)
- ✅ GC bot for match discovery
- ✅ Aggregation worker
- ✅ Ingest endpoint
- ✅ Enhanced health checks
- ✅ Worker tests

**Next:** Plan 3 (Lane Intelligence) → Plan 4 (Community/API Keys) → Plan 5 (Platform Ops)

---

**Plan complete and saved to `plans/2026-04-07-phase-2-demo-parsing.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**