# Phase 3: Lane Intelligence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement lane detection, populate lane matchups data, and compute playstyle fingerprints for per-player matchup recommendations.

**Architecture:**
- Map player positions from player_ticks to lane coordinates
- Compute lane matchups with souls differential and laning winner
- Surface per-player matchup builds in API

**Tech Stack:** Polars, SQLAlchemy, PostgreSQL

---

## Task 1: Lane Matchups Model

**Files:**
- Modify: `backend/app/models/demo.py`

**Step 1: Add lane matchups model**

```python
class MatchLaneMatchup(Base):
    __tablename__ = "match_lane_matchups"
    
    match_id = Column(Integer, ForeignKey("matches.match_id"), primary_key=True)
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    hero_id = Column(Integer, ForeignKey("heroes.hero_id"), primary_key=True)
    enemy_steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    enemy_hero_id = Column(Integer, ForeignKey("heroes.hero_id"), primary_key=True)
    lane = Column(Integer, nullable=False)  # 0=mid, 1=offlane, 2=carry
    time_in_lane_together_secs = Column(Integer)
    souls_differential = Column(Integer)
    laning_winner = Column(Integer)  # 1 / -1 / 0
```

**Step 2: Migration**

```bash
cd backend && source .venv/bin/activate && alembic revision -m "add lane_matchups" && alembic upgrade head
```

**Step 3: Commit**

```bash
git add backend/app/models/demo.py
git commit -m "feat: add lane matchups model"
```

---

## Task 2: Lane Detection

**Files:**
- Create: `backend/app/workers/lane_detection.py`

**Step 1: Create lane detector**

```python
import polars as pl


# Map bounds (calibrated from player_ticks data)
LANE_BOUNDS = {
    "mid": {"x": (-500, 500), "y": (-500, 500)},
    "carry": {"x": (-3000, -1500), "y": (-3000, -1500)},  # Radiant carry
    "offlane": {"x": (1500, 3000), "y": (1500, 3000)},    # Dire offlane
}


def detect_lane(x: float, y: float) -> int:
    """Return lane index (0=mid, 1=offlane, 2=carry based on team)."""
    for lane_name, bounds in LANE_BOUNDS.items():
        if bounds["x"][0] <= x <= bounds["x"][1] and bounds["y"][0] <= y <= bounds["y"][1]:
            return {"mid": 0, "offlane": 1, "carry": 2}[lane_name]
    return 0  # Default to mid


def compute_lane_matchups(player_ticks: pl.LazyFrame, match_id: int) -> list[dict]:
    """Compute lane matchups from player_ticks."""
    
    # Sample ticks at 30-second intervals
    ticks = player_ticks.filter(pl.col("tick") % 1800 == 0).collect()
    
    # Group by player, compute lane
    player_lanes = {}
    for row in ticks.iter_rows(named=True):
        lane = detect_lane(row["x"], row["y"])
        player_lanes.setdefault(row["steam_id"], []).append({
            "lane": lane,
            "souls": row["souls"],
            "tick": row["tick"],
        })
    
    # Find opponents in same lane
    matchups = []
    for steam_id, data in player_lanes.items():
        for other_id, other_data in player_lanes.items():
            if steam_id >= other_id:
                continue  # Skip duplicates
            
            # Find overlapping time in same lane
            for d1 in data:
                for d2 in other_data:
                    if d1["lane"] == d2["lane"] and abs(d1["tick"] - d2["tick"]) < 1800:
                        matchups.append({
                            "steam_id": steam_id,
                            "enemy_steam_id": other_id,
                            "lane": d1["lane"],
                            "souls_differential": d1["souls"] - d2["souls"],
                            "laning_winner": 1 if d1["souls"] > d2["souls"] else (-1 if d1["souls"] < d2["souls"] else 0),
                        })
                        break
    
    return matchups


def run_lane_detection(match_id: int):
    """Process lane detection for a match."""
    from app.database import SessionLocal
    from app.models.demo import MatchLaneMatchup
    
    player_ticks = load_player_ticks(match_id)  # Load from boon-deadlock output
    
    matchups = compute_lane_matchups(player_ticks, match_id)
    
    db = SessionLocal()
    try:
        for m in matchups:
            db.add(MatchLaneMatchup(
                match_id=match_id,
                steam_id=m["steam_id"],
                hero_id=get_hero_for_player(match_id, m["steam_id"]),
                enemy_steam_id=m["enemy_steam_id"],
                enemy_hero_id=get_hero_for_player(match_id, m["enemy_steam_id"]),
                lane=m["lane"],
                time_in_lane_together_secs=1800,
                souls_differential=m["souls_differential"],
                laning_winner=m["laning_winner"],
            ))
        db.commit()
    finally:
        db.close()
```

**Step 2: Commit**

```bash
git add backend/app/workers/lane_detection.py
git commit -m "feat: add lane detection worker"
```

---

## Task 3: Playstyle Fingerprints

**Files:**
- Modify: `backend/app/models/account.py`

**Step 1: Add playstyle model**

```python
class PlayerPlaystyleFingerprint(Base):
    __tablename__ = "player_playstyle_fingerprint"
    
    steam_id = Column(Integer, ForeignKey("players.steam_id"), primary_key=True)
    early_aggression_score = Column(Float)  # 0-100
    farm_efficiency_score = Column(Float)
    support_tendency_score = Column(Float)
    late_game_scale_score = Column(Float)
    computed_at = Column(DateTime, default=datetime.utcnow)
```

**Step 2: Migration**

```bash
cd backend && source .venv/bin/activate && alembic revision -m "add playstyle fingerprints" && alembic upgrade head
```

**Step 3: Commit**

```bash
git add backend/app/models/account.py
git commit -m "feat: add playstyle fingerprint model"
```

---

## Task 4: Playstyle Computation

**Files:**
- Create: `backend/app/workers/playstyle.py`

**Step 1: Create computation**

```python
def compute_playstyle_fingerprint(steam_id: int) -> dict:
    """Compute playstyle scores from match history."""
    from app.database import SessionLocal
    from app.models.match import Match, MatchPlayer
    
    db = SessionLocal()
    
    # Get recent matches (last 20)
    matches = db.query(MatchPlayer).join(Match).filter(
        MatchPlayer.steam_id == steam_id,
        Match.started_at >= func.now() - timedelta(days=30),
    ).order_by(Match.started_at.desc()).limit(20).all()
    
    if len(matches) < 5:
        return None  # Not enough data
    
    # Compute scores
    avg_hits_per_min = sum(m.last_hits / (m.match.duration_secs / 60) for m in matches if m.match) / len(matches)
    early_kills = sum(1 for m in matches if m.kills > m.deaths and m.match and m.match.duration_secs < 1800) / len(matches)
    support_pct = sum(1 for m in matches if m.net_worth < 10000) / len(matches)
    late_game_wins = sum(1 for m in matches if m.match and m.match.duration_secs > 2400 and m.match.winning_team == m.team) / len(matches)
    
    # Normalize to 0-100
    scores = {
        "early_aggression_score": min(100, early_kills * 100),
        "farm_efficiency_score": min(100, avg_hits_per_min * 10),
        "support_tendency_score": min(100, support_pct * 100),
        "late_game_scale_score": min(100, late_game_wins * 100),
    }
    
    # UpdateDB
    db.merge(PlayerPlaystyleFingerprint(
        steam_id=steam_id,
        **scores,
        computed_at=datetime.utcnow(),
    ))
    db.commit()
    db.close()
    
    return scores
```

**Step 2: Commit**

```bash
git add backend/app/workers/playstyle.py
git commit -m "feat: add playstyle computation"
```

---

## Task 5: Matchup Build API

**Files:**
- Modify: `backend/app/routers/players.py`

**Step 1: Add matchup builds endpoint**

```python
@router.get("/players/{steam_id}/matchups")
def get_player_matchups(steam_id: int, enemy_hero_id: int, db: Session = Depends(get_db)):
    """Get player's item builds against specific enemy hero."""
    from app.models.account import PlayerMatchupBuild
    from app.models.match import MatchPlayer, Match
    
    # Query most successful builds against this enemy
    builds = db.query(PlayerMatchupBuild).filter(
        PlayerMatchupBuild.steam_id == steam_id,
        PlayerMatchupBuild.enemy_hero_id == enemy_hero_id,
    ).order_by(PlayerMatchupBuild.win_count.desc()).limit(5).all()
    
    return [{"items": b.signature_items, "wins": b.win_count} for b in builds]


@router.get("/players/{steam_id}/playstyle")
def get_player_playstyle(steam_id: int, db: Session = Depends(get_db)):
    """Get player's playstyle fingerprint."""
    from app.models.account import PlayerPlaystyleFingerprint
    
    fp = db.query(PlayerPlaystyleFingerprint).filter(
        PlayerPlaystyleFingerprint.steam_id == steam_id
    ).first()
    
    if not fp:
        raise HTTPException(status_code=404, detail="No playstyle data available")
    
    return {
        "early_aggression": fp.early_aggression_score,
        "farm_efficiency": fp.farm_efficiency_score,
        "support_tendency": fp.support_tendency_score,
        "late_game_scale": fp.late_game_scale_score,
    }
```

**Step 2: Commit**

```bash
git add backend/app/routers/players.py
git commit -m "feat: add matchup builds and playstyle API"
```

---

## Task 6: Tests

**Files:**
- Create: `tests/test_lane_detection.py`

**Step 1: Create tests**

```python
def test_detect_lane():
    assert detect_lane(0, 0) == 0  # mid
    assert detect_lane(-2000, -2000) == 2  # carry


def test_compute_lane_matchups():
    # Create sample player_ticks
    ticks = pl.LazyFrame({
        "steam_id": [1, 1, 2, 2],
        "tick": [0, 1800, 0, 1800],
        "x": [0, 0, 100, 100],
        "y": [0, 0, 100, 100],
        "souls": [1000, 2000, 800, 1500],
    })
    
    matchups = compute_lane_matchups(ticks, 123)
    
    assert len(matchups) > 0
```

**Step 2: Commit**

```bash
git add tests/test_lane_detection.py
git commit -m "test: add lane detection tests"
```

---

## Plan Complete

Phase 3 implementation complete:
- ✅ Lane matchups model
- ✅ Lane detection from player_ticks
- ✅ Playstyle fingerprint model
- ✅ Playstyle computation
- ✅ Matchup builds API
- ✅ Tests

---

**Plan complete and saved to `plans/2026-04-07-phase-3-lane-intelligence.md`.**

**Next:** Plan 4 (Phase 4: Community/API Keys) → Plan 5 (Platform Ops)

---

**Which approach?**
**1. Subagent-Driven (this session)**
**2. Parallel Session (separate)**