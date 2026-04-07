# Phase 4: Community & API Keys Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement community cache tool, public API keys for third-party developers, Discord bot support, and tournament tracking.

**Architecture:**
- Community cache submission tool (background agent)
- API key management for partners
- Webhook system for Discord bots
- Tournament/event tracking

**Tech Stack:** Python, FastAPI, SQLite (local cache tool), Discord.py

---

## Task 1: Community Cache Tool

**Files:**
- Create: `tools/cache-submitter/`

**Step 1: Create cache watcher**

```python
# tools/cache-submitter/main.py
import os
import time
import threading
import subprocess
import requests
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


API_URL = "https://yourdomain.com/api/v1"


class DemoHandler(FileSystemEventHandler):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.processed = set()
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith(".dem"):
            self.submit_demo(event.src_path)
    
    def submit_demo(self, demo_path: str):
        # Extract match ID from filename
        match_id = extract_match_id(demo_path)
        salt = extract_salt(demo_path)
        
        if match_id in self.processed:
            return
        
        try:
            resp = requests.post(
                f"{API_URL}/ingest/cache",
                json={"match_id": match_id, "demo_salt": salt},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            self.processed.add(match_id)
            print(f"Submitted {match_id}")
        except Exception as e:
            print(f"Failed: {e}")


def run_watcher(api_key: str):
    httpcache = Path(os.path.expanduser("~/Steam/appcache/httpcache"))
    
    if not httpcache.exists():
        print("httpcache not found")
        return
    
    event_handler = DemoHandler(api_key)
    observer = Observer()
    observer.schedule(event_handler, str(httpcache), recursive=True)
    observer.start()
    
    print("Watching for new demos...")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    import sys
    api_key = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("API_KEY")
    if not api_key:
        print("Usage: python -m cache-submitter <api_key>")
        sys.exit(1)
    
    run_watcher(api_key)
```

**Step 2: Create setup.py**

```python
# setup.py
from setuptools import setup

setup(
    name="deadlock-stats-cache",
    version="0.1.0",
    packages=["cache_submitter"],
    install_requires=["watchdog", "requests"],
    entry_points={
        "console_scripts": [
            "deadlock-stats-cache=cache_submitter.main:main",
        ],
    },
)
```

**Step 3: Commit**

```bash
git add tools/cache-submitter/
git commit -m "feat: add community cache submission tool"
```

---

## Task 2: API Keys for Partners

**Files:**
- Modify: `backend/app/models/account.py`

**Step 1: Add API key model**

```python
class APIKey(Base):
    __tablename__ = "api_keys"
    
    key_id = Column(String(36), primary_key=True)
    account_id = Column(String(36), ForeignKey("accounts.account_id"))
    key_hash = Column(String(255), nullable=False)
    name = Column(String(100))
    rate_limit = Column(Integer, default=1000)  # req/min
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)
```

**Step 2: Migration**

```bash
cd backend && source .venv/bin/activate && alembic revision -m "add api keys" && alembic upgrade head
```

**Step 3: Commit**

```bash
git add backend/app/models/account.py
git commit -m "feat: add API key model"
```

---

## Task 3: API Key Endpoints

**Files:**
- Create: `backend/app/routers/api_keys.py`

**Step 1: Create endpoints**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import secrets

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def get_current_account(...):
    # Dependency to get authenticated account
    pass


@router.post("/")
def create_api_key(name: str, db: Session = Depends(get_db), account = Depends(get_current_account)):
    key = secrets.token_urlsafe(32)
    key_hash = hash_key(key)  # Store hashed
    
    api_key = APIKey(
        key_id=secrets.uuid4(),
        account_id=account.account_id,
        key_hash=key_hash,
        name=name,
    )
    db.add(api_key)
    db.commit()
    
    return {"key": key}  # Only returned once!


@router.get("/")
def list_api_keys(db: Session = Depends(get_db), account = Depends(get_current_account)):
    keys = db.query(APIKey).filter(APIKey.account_id == account.account_id).all()
    return [{"id": k.key_id, "name": k.name, "created": k.created_at} for k in keys]


@router.delete("/{key_id}")
def revoke_api_key(key_id: str, db: Session = Depends(get_db), account = Depends(get_current_account)):
    key = db.query(APIKey).filter(APIKey.key_id == key_id, APIKey.account_id == account.account_id).first()
    if not key:
        raise HTTPException(status_code=404)
    
    key.revoked = True
    db.commit()
    return {"status": "revoked"}
```

**Step 2: Commit**

```bash
git add backend/app/routers/api_keys.py
git commit -m "feat: add API key endpoints"
```

---

## Task 4: Rate Limiting Middleware

**Files:**
- Create: `backend/app/middleware/rate_limit.py`

**Step 1: Create rate limiter**

```python
from fastapi import Request, HTTPException
from app.models.account import APIKey
from redis import Redis
import time

redis = Redis.from_url(settings.redis_url)


async def rate_limit_middleware(request: Request, call_next):
    # Check API key
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    
    if api_key:
        key = f"ratelimit:{api_key}"
        current = redis.get(key)
        
        if current and int(current) > 1000:  # Default limit
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        redis.incr(key)
        redis.expire(key, 60)
    
    return await call_next(request)
```

**Step 2: Commit**

```bash
git add backend/app/middleware/rate_limit.py
git commit -m "feat: add rate limiting"
```

---

## Task 5: Discord Bot Support

**Files:**
- Create: `bots/discord/`

**Step 1: Create bot**

```python
# bots/discord/main.py
import discord
from discord import app_commands
import requests

API_URL = "https://yourdomain.com/api/v1"


class DeadlockStatsBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents)
        self.tree = app_commands.CommandTree(self)
    
    async def setup_hook(self):
        await self.tree.sync()


bot = DeadlockStatsBot()


@bot.tree.command()
async def stats(interaction: discord.Interaction, player: str):
    """Get player stats."""
    await interaction.response.defer()
    
    # Search for player
    search = requests.get(f"{API_URL}/players/search?q={player}")
    if not search.json()["data"]:
        await interaction.followup.send("Player not found")
        return
    
    player_id = search.json()["data"][0]["steam_id"]
    
    # Get stats
    stats = requests.get(f"{API_URL}/players/{player_id}/stats")
    
    await interaction.followup.send(f"**{search.json()['data'][0]['display_name']}**\n"
                               f"Win Rate: {stats.json()['data']['win_rate']}%\n"
                               f"Matches: {stats.json()['data']['matches_played']}")


@bot.tree.command()
async def recent(interaction: discord.Interaction, player: str):
    """Get recent matches."""
    # ... similar approach
    pass


# Run with: python -m discord.main
TOKEN = os.environ["DISCORD_BOT_TOKEN"]
bot.run(TOKEN)
```

**Step 2: Commit**

```bash
git add bots/discord/
git commit -m "feat: add Discord bot"
```

---

## Task 6: Tournament Tracking

**Files:**
- Create: `backend/app/models/tournament.py`

**Step 1: Create models**

```python
class Tournament(Base):
    __tablename__ = "tournaments"
    
    tournament_id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    prize_pool = Column(String(50))
    series_id = Column(String(50))  # ESL, DreamHack, etc.


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"
    
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.tournament_id"))
    match_id = Column(Integer, ForeignKey("matches.match_id"))
    stage = Column(String(50))  # groups, playoffs, finals
    schedule_time = Column(DateTime)
```

**Step 2: Add endpoint**

```python
@router.get("/tournaments")
def list_tournaments(db: Session = Depends(get_db)):
    from app.models.tournament import Tournament
    return db.query(Tournament).all()


@router.get("/tournaments/{tournament_id}/matches")
def get_tournament_matches(tournament_id: int, db: Session = Depends(get_db)):
    from app.models.tournament import TournamentMatch
    return db.query(TournamentMatch).filter(TournamentMatch.tournament_id == tournament_id).all()
```

**Step 3: Commit**

```bash
git add backend/app/models/tournament.py backend/app/routers/tournaments.py
git commit -m "feat: add tournament tracking"
```

---

## Task 7: Webhook System

**Files:**
- Create: `backend/app/webhooks.py`

**Step 1: Create webhook runner**

```python
from celery import task


@task
def send_webhook(url: str, payload: dict):
    """Send webhook to third-party."""
    import requests
    
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log.error(f"Webhook failed: {e}")
        raise


# Use when:
# - Match completed
# - Player milestone reached
# - New tournament announced
```

**Step 2: Commit**

```bash
git add backend/app/webhooks.py
git commit -m "feat: add webhook system"
```

---

## Plan Complete

Phase 4 implementation complete:
- ✅ Community cache tool
- ✅ API key model & endpoints
- ✅ Rate limiting middleware
- ✅ Discord bot
- ✅ Tournament tracking
- ✅ Webhook system

---

**Plan complete and saved to `plans/2026-04-07-phase-4-community.md`.**

**Next:** Plan 5 (Platform Ops: Observability, Backups, CI/CD)

---

**Which approach?**
**1. Subagent-Driven (this session)**
**2. Parallel Session (separate)**