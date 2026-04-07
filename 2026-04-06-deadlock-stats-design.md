# Deadlock Stats Platform — Design Spec
**Date:** 2026-04-06
**Status:** Approved

---

## 1. Vision

A public HLTV-equivalent for Valve's Deadlock — a platform where any player can look up their stats, review match history, track item builds, study hero meta, and receive coaching-grade analytics. Differentiates from existing trackers (tracklock.gg, statlocker.gg) through per-player matchup builds, playstyle fingerprinting, laning analysis, and a deep demo-parsed data layer.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Next.js Frontend                     │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────────┐
│                  FastAPI (Public API)                     │
│         /players  /matches  /heroes  /leaderboard        │
└──────────┬──────────────────────────┬───────────────────┘
           │ reads                    │ reads
┌──────────▼──────────┐   ┌──────────▼──────────┐
│     PostgreSQL       │   │    Upstash Redis     │
│  (persistent store)  │   │  (cache + job queue) │
└──────────▲──────────┘   └──────────▲──────────┘
           │ writes                   │ job queue
┌──────────┴──────────────────────────┴──────────────────┐
│               Celery Worker Pool (Python)               │
│  ┌─────────────────┐   ┌──────────────────────────┐    │
│  │  GC Bot Worker  │   │  Demo Processing Worker  │    │
│  │ (ValvePython)   │   │  (boon-deadlock + Polars)│    │
│  └────────┬────────┘   └───────────┬──────────────┘    │
└───────────┼────────────────────────┼───────────────────┘
            │ GC protobuf            │ HTTP download
            ▼                        ▼
      Valve Game                Valve CDN
      Coordinator            (.dem replay files)
```

### Data flow for a new match
1. GC bot polls tracked players → discovers new match ID + salt
2. Match queued in Upstash Redis via Celery
3. Demo worker downloads `.dem` from Valve CDN
4. `boon-deadlock` parses demo → 17 Polars DataFrames
5. Worker writes each DataFrame directly to PostgreSQL via `.write_database()`
6. Lane matchup aggregation computed from `player_ticks` dataset
7. Celery beat tasks recompute aggregation tables on schedule
8. FastAPI serves data; Upstash caches hot responses

---

## 3. Data Sources

### Phase 1 — Bootstrap (Launch)
- **deadlock-api.com daily database dumps** — free, covers millions of matches
- Imported nightly into PostgreSQL
- Provides: match summaries, player stats, hero win rates, item stats, ability paths, leaderboards
- Covers all standard stats immediately on launch with no ingestion pipeline needed

### Phase 2 — Own Pipeline (Post-Launch)
- **Steam Game Coordinator (GC) bot** via `ValvePython/steam`
  - Sends protobuf messages to discover new matches for tracked players
  - Fans out via opponent discovery to grow coverage organically
- **boon-deadlock** Python parser for demo files
  - Covers everything deadlock-api.com does not: granular events, positions, economy ticks, objectives, laning data

### Community Cache Submission (Growth Feature)
- Players install a lightweight background tool that watches `Steam/appcache/httpcache/`
- On new `.dem` file detected, submits match ID + salt to `/ingest/cache`
- More users = better coverage — viral growth mechanic

---

## 4. Demo Parser — boon-deadlock

**`pip install boon-deadlock`** (Python 3.11+, Rust-powered, native Python bindings)

Replaces all C# subprocess approaches. Outputs 17 lazy-loaded Polars DataFrames directly in Python.

### 17 Datasets

| Dataset | Content | Maps To |
|---|---|---|
| `players` | Player info, heroes, teams | `match_players` |
| `player_ticks` | Per-player state every tick (position, health, souls) | `match_economy_snapshots`, `match_lane_matchups` |
| `world_ticks` | World state snapshots | `match_economy_snapshots` |
| `kills` | Kill events with exact timestamps | `match_players` |
| `damage` | Per-event damage log | `match_damage_events` |
| `abilities` | Ability cast events | `ability_upgrades` |
| `item_purchases` | Shop transactions with timestamps | `item_builds` |
| `ability_upgrades` | Skill point allocations | `ability_upgrades` |
| `objectives` | Tower/shrine/walker health + destruction | `match_objectives` |
| `mid_boss` | Mid boss lifecycle — kill credit, timing, souls | `match_objectives` |
| `troopers` | Lane trooper state | `match_lane_stats` |
| `neutrals` | Neutral camp kills per player | `match_jungle_kills` |
| `urn` | Urn pickup, delivery, drop events | `match_objectives` |
| `active_modifiers` | Buff/debuff events (mid boss buff etc.) | `match_modifiers` |
| `stat_modifier_events` | Permanent stat bonuses from objectives | `match_objectives` |
| `chat` | Chat message records | **Not stored** — excluded (PII/legal risk) |
| `flex_slots` | Flex slot unlock timing | `item_builds` |

### Demo Worker Pattern
```python
from boon import Demo
import os

SCRATCH_DIR = "/tmp/demos"  # isolated, sandboxed scratch directory

async def process_demo(match_id: int, demo_path: str):
    # Validate path is within scratch directory before parsing
    resolved = os.path.realpath(demo_path)
    if not resolved.startswith(os.path.realpath(SCRATCH_DIR)):
        raise ValueError(f"Demo path outside scratch directory: {demo_path}")

    # Enforce file size limit before parsing (reject > 500MB)
    if os.path.getsize(resolved) > 500 * 1024 * 1024:
        raise ValueError("Demo file exceeds maximum allowed size")

    demo = Demo(resolved)

    demo.item_purchases.write_database("item_builds", conn, if_table_exists="append")
    demo.ability_upgrades.write_database("ability_upgrades", conn, if_table_exists="append")
    demo.objectives.write_database("match_objectives", conn, if_table_exists="append")
    demo.mid_boss.write_database("match_objectives", conn, if_table_exists="append")
    demo.neutrals.write_database("match_jungle_kills", conn, if_table_exists="append")
    demo.troopers.write_database("match_lane_stats", conn, if_table_exists="append")
    demo.urn.write_database("match_objectives", conn, if_table_exists="append")
    demo.player_ticks.write_database("match_economy_snapshots", conn, if_table_exists="append")
    demo.damage.write_database("match_damage_events", conn, if_table_exists="append")
    demo.active_modifiers.write_database("match_modifiers", conn, if_table_exists="append")
    # demo.chat intentionally excluded — PII/legal risk, no product value

    aggregate_lane_matchups(match_id, demo.player_ticks, conn)
    # Nullify demo_url after successful parse (salt must not persist)
    clear_demo_url(match_id, conn)
    update_demo_status(match_id, "complete", conn)

    # Delete demo file from scratch directory immediately after parsing
    os.remove(resolved)
```

---

## 5. Database Schema

### Reference Data *(deadlock-api.com)*
```
heroes          hero_id, name, description, image_url, updated_at
items           item_id, name, cost, category, tier, description, image_url, updated_at
abilities       ability_id, hero_id, name, description, image_url
```

### Account System

Two account types. Both require the absolute minimum data to function.

```
accounts                    -- email-based viewer accounts
  account_id  (PK, UUID)
  email       (unique)      -- only PII stored; used for login + verification only
  password_hash             -- argon2id
  email_verified  (bool)
  steam_id    (FK → players, nullable) -- set when player links their Steam account
  created_at
  last_login_at             -- retained for security auditing only
  -- NO: username, display name, DOB, location, bio, avatar, phone
```

**What email accounts can do:**
- Follow players and save favourite matches
- Receive match/tournament alerts
- Build custom player watchlists
- Link a Steam account at any time to gain player features

```
players                     -- Steam-authenticated player accounts
  steam_id    (PK, bigint)  -- permanent Steam identity
  account_id  (FK → accounts, nullable) -- set if player also has an email account
  display_name              -- sourced from Steam API, not user-supplied
  avatar_url                -- sourced from Steam API, not user-supplied
  rank
  rank_tier
  opted_out   (bool)        -- GDPR indexing opt-out
  tracked_since
  last_updated
```

**What player accounts additionally unlock:**
- Claim and view own stats
- Priority match processing
- GDPR opt-out of indexing
- Full name history (owner-only)

```
player_name_history
  steam_id (FK), display_name, first_seen_at, last_seen_at
  UNIQUE (steam_id, display_name)
  -- Retention: rolling 90-day window only
  -- Public API exposes: current name + most recent previous name only
  -- Full history: authenticated account owner only (GET /players/{id}/names)
  -- Purged in full on GDPR deletion request

account_follows             -- viewer account saved players/watchlists
  account_id  (FK → accounts)
  steam_id    (FK → players)
  followed_at
  PRIMARY KEY (account_id, steam_id)
```

### Match Data *(deadlock-api.com)*
```
matches
  match_id (PK), started_at, duration_secs, match_mode,
  winning_team, patch_version, average_rank,
  source  -- 'deadlock_api' | 'self_ingested'

match_players
  match_id (FK), steam_id (FK), team, hero_id (FK),
  kills, deaths, assists, net_worth, last_hits, denies,
  damage_dealt, damage_taken, healing_done, creep_kills,
  tower_kills, mvp, ranked_badge_level
  PRIMARY KEY (match_id, steam_id)
```

### Demo-Parsed Data *(boon-deadlock, Phase 2)*
```
item_builds
  match_id (FK), steam_id (FK), item_id (FK),
  purchased_at_secs, slot
  PRIMARY KEY (match_id, steam_id, item_id, purchased_at_secs)

ability_upgrades
  match_id (FK), steam_id (FK), ability_id (FK),
  upgraded_at_secs, upgrade_number
  PRIMARY KEY (match_id, steam_id, ability_id, upgraded_at_secs)

match_objectives
  match_id (FK), event_type, team, timestamp_secs,
  object_id, souls_awarded

match_economy_snapshots
  match_id (FK), steam_id (FK), minute,
  net_worth, souls_earned_this_minute

match_jungle_kills
  match_id (FK), steam_id (FK), camp_tier,
  camp_id, killed_at_secs

match_lane_stats
  match_id (FK), steam_id (FK), lane,
  souls_at_5min, souls_at_10min,
  creep_kills_laning, denies_laning

match_lane_matchups
  match_id (FK), steam_id (FK), hero_id (FK),
  enemy_steam_id (FK), enemy_hero_id (FK), lane,
  time_in_lane_together_secs, souls_differential,
  laning_winner  -- 1 / -1 / 0
  PRIMARY KEY (match_id, steam_id, enemy_hero_id)
  NOTE: populated from player_ticks dataset; empty until lane detection implemented

match_damage_events
  match_id (FK), tick, attacker_steam_id (FK),
  victim_steam_id (FK), damage_amount, damage_type, ability_id

match_modifiers
  match_id (FK), steam_id (FK), modifier_name,
  applied_at_tick, removed_at_tick

match_demo_status
  match_id (PK, FK), status, demo_url, parsed_at, error_code
  -- status: pending | downloading | parsing | complete | failed
  -- demo_url nullified after successful parse (salt must not persist)
  -- error_code is a structured code only — never a raw exception string
```

### Per-Player Aggregations *(Celery-computed)*
```
player_stats_snapshots
  steam_id (FK), window ('career'|'7d'|'30d'|'90d'),
  hero_id (FK, nullable), matches_played, wins, losses,
  win_rate, avg_kills, avg_deaths, avg_assists,
  avg_net_worth, avg_damage_dealt, computed_at
  PRIMARY KEY (steam_id, window, hero_id)

player_item_affinity
  steam_id, hero_id, item_id  (composite PK)
  pick_count, win_count, matches_played, avg_purchase_time_secs

player_matchup_builds
  steam_id, hero_id, enemy_hero_id, item_id  (composite PK)
  pick_count, win_count, matches_played

player_build_fingerprints
  steam_id, hero_id  (composite PK)
  signature_items (JSON), usage_count, win_count,
  avg_completion_time_secs

player_item_timing_benchmarks
  steam_id, hero_id, item_id  (composite PK)
  player_avg_purchase_secs, global_avg_purchase_secs, sample_size

player_playstyle_fingerprint
  steam_id (PK)
  early_aggression_score, farm_efficiency_score,
  support_tendency_score, late_game_scale_score, computed_at

player_performance_trend
  steam_id, window_matches, computed_at  (composite PK)
  avg_kda, win_rate, avg_net_worth_per_min
```

### Meta / Global Analytics
```
hero_synergies
  hero_id_a, hero_id_b, patch_version  (composite PK)
  matches_together, wins_together, win_rate

hero_counters
  hero_id, enemy_hero_id, patch_version  (composite PK)
  matches_played, wins, win_rate

hero_patch_snapshots
  hero_id, patch_version  (composite PK)
  matches_played, win_rate, avg_kills, avg_deaths,
  avg_net_worth, most_common_items (JSON)

global_item_stats
  item_id, patch_version, hero_id, rank_bracket  (composite PK)
  pick_rate, win_rate, avg_purchase_time_secs
```

### Key Indexes
```sql
CREATE INDEX ON match_players (steam_id);
CREATE INDEX ON match_players (hero_id);
CREATE INDEX ON matches (started_at);
CREATE INDEX ON matches (patch_version);
CREATE INDEX ON player_name_history (display_name);
CREATE INDEX ON match_demo_status (status) WHERE status != 'complete';
```

### GDPR Opt-Out Enforcement
All public player endpoints MUST check `players.opted_out` before returning data:
- If `opted_out = true`, return `404 Not Found` for all player-specific endpoints
- Exception: endpoints that return ONLY match-level data (not attributable to player)
- Search results exclude opted-out players via SQL filter in query layer

---

## 6. API Layer

### Base URL
`/api/v1`

### Endpoints
```
PLAYERS
GET  /players/search?q={name}
GET  /players/{steam_id}
GET  /players/{steam_id}/matches
GET  /players/{steam_id}/stats?window=30d
GET  /players/{steam_id}/heroes
GET  /players/{steam_id}/items
GET  /players/{steam_id}/matchups
GET  /players/{steam_id}/trends
GET  /players/{steam_id}/playstyle
GET  /players/{steam_id}/names

MATCHES
GET  /matches/{match_id}
GET  /matches/{match_id}/builds
GET  /matches/{match_id}/objectives
GET  /matches/{match_id}/economy

HEROES
GET  /heroes
GET  /heroes/{hero_id}
GET  /heroes/{hero_id}/items
GET  /heroes/{hero_id}/matchups
GET  /heroes/{hero_id}/builds

LEADERBOARD
GET  /leaderboard?region=&hero_id=

META
GET  /meta/patches
GET  /meta/items
GET  /meta/synergies
GET  /meta/counters

INGEST
POST /ingest/cache
GET  /ingest/status/{match_id}

AUTH
POST /auth/register              -- email + password only, returns verification email
POST /auth/verify-email          -- email verification token
POST /auth/login                 -- email + password
POST /auth/logout
POST /auth/forgot-password       -- sends reset link to email
POST /auth/reset-password        -- token + new password
GET  /auth/steam                 -- Steam OpenID login (player accounts)
GET  /auth/steam/callback        -- Steam OpenID return
GET  /auth/me                    -- current session (either account type)
POST /auth/link-steam            -- authenticated email account links a Steam ID
DELETE /auth/me                  -- delete account + full data cascade
```

### Response Envelope
```json
{
  "data": {},
  "meta": { "cached": true, "cache_age_secs": 42, "patch_version": "1.5" },
  "pagination": { "total": 240, "page": 1, "limit": 20 }
}
```

### Caching (Upstash Redis TTLs)
```
Match data          permanent   (immutable once processed)
Player profile      5 min
Player stats        1 hour
Hero stats          1 hour
Leaderboard         15 min
Meta (items/heroes) 24 hours
Search results      2 min
```

### Rate Limiting
```
Anonymous           60 req/min
Authenticated       300 req/min
API key (partners)  1000 req/min
```

### Authentication

Two paths, one session format.

**Email registration (viewer accounts):**
- Only email + password collected at signup — nothing else
- Email verified before account is active (link expires in 24 hours)
- Password hashed with `argon2id` (not bcrypt — stronger against GPU attacks)
- Reset flow: time-limited single-use token sent to email, expires in 15 minutes
- Rate-limited: 5 registration attempts per IP per hour, 3 reset attempts per email per hour

**Steam OpenID (player accounts):**
- No password stored. Steam handles all credential verification.
- Display name and avatar URL sourced from Steam API — never user-supplied

**Account linking:**
- An email account can link a Steam ID via `POST /auth/link-steam` (authenticated)
- Once linked, the email account gains all player features
- A Steam account can link an email address to enable password-based login fallback

**JWT Session Design:**
- Signing algorithm: RS256 (asymmetric — private key never leaves auth service)
- Access token expiry: 1 hour
- Refresh token: separate `httpOnly` cookie, 30-day expiry, silent refresh
- Revocation: token blocklist in Upstash Redis — invalidated on logout and account deletion
- Cookie attributes: `Secure; HttpOnly; SameSite=Lax`
- CSRF token required on all state-mutating authenticated requests

**Steam OpenID Callback:**
- `GET /auth/steam/callback` never accepts a redirect URL from query parameters
- Post-auth redirect is server-side configured to internal paths only
- `openid.return_to` claim validated against expected server-configured value

**Auth unlocks:** higher rate limits, GDPR opt-out, priority match processing.

### CORS Policy
- Explicit allowlist: production domain only (`https://yourdomain.com`)
- No wildcard `Allow-Origin: *` on any endpoint
- State-mutating endpoints (`POST`, `DELETE`) require matching `Origin` header

### Rate Limiting
```
Anonymous           60 req/min   (keyed on IP)
Authenticated       300 req/min  (keyed on IP + Steam ID — both must pass)
API key (partners)  1000 req/min
```
- Max page size: 100 rows per paginated response (prevents bulk enumeration)
- Sequential `steam_id` scan pattern triggers temporary IP block + alert
- `/players/{id}/playstyle`, `/players/{id}/matchups` require authentication (granular behavioral data)
- Progressive backoff: 429 with `Retry-After` header, temporary IP block after sustained violations

### Ingest Endpoint Security
- `POST /ingest/cache` requires Steam OpenID authentication — submissions attributed to caller's Steam ID
- Rate limited to 10 submissions per authenticated user per hour
- Match ID + salt validated against Valve CDN before queuing (reject invalid pairs immediately)
- Deduplication: if `match_id` already in `match_demo_status` with status `complete`, `pending`, or `downloading`, reject without queuing
- Job queue depth capped with back-pressure to prevent flooding

### Ingest Status Endpoint
- `GET /ingest/status/{match_id}` returns status code and human-readable label only
- Raw `error_code` from `match_demo_status` mapped to sanitized public messages
- Internal error detail never exposed to callers

---

## 7. Frontend

### Stack
- **Framework**: Next.js (App Router)
- **Styling**: Tailwind CSS + shadcn/ui
- **Charts**: Recharts
- **Tables**: TanStack Table
- **Theme**: Dark mode default

### HTTP Security Headers (`next.config.js`)
```js
headers: [
  { key: 'X-Frame-Options',        value: 'SAMEORIGIN' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy',        value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy',     value: 'camera=(), microphone=(), geolocation=()' },
  { key: 'Content-Security-Policy',
    value: "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://avatars.steamstatic.com"
  }
]
```

### Page Structure
```
app/
├── page.tsx                     Home — meta overview, trending
├── players/[steam_id]/
│   ├── page.tsx                 Player profile
│   ├── matches/page.tsx         Match history
│   └── heroes/page.tsx          Per-hero breakdown
├── matches/[match_id]/page.tsx  Match detail
├── heroes/
│   ├── page.tsx                 Hero tier list
│   └── [hero_id]/page.tsx       Hero detail
├── leaderboard/page.tsx
├── search/page.tsx
└── auth/
    ├── steam/page.tsx
    └── callback/page.tsx
```

### Data Fetching Strategy
```
Page              Strategy      Revalidate
────────────────  ──────────    ──────────
Home              ISR           15 min
Player profile    SSR           always fresh
Match detail      ISR           never (immutable)
Hero stats        ISR           1 hour
Leaderboard       ISR           15 min
Search            Client-side   —
Economy/obj charts Client-side  lazy loaded
```

### Key Page Layouts

**Player Profile**
- Avatar, display name, rank badge, "also known as" name history
- Stats bar with career / 90d / 30d / 7d window toggle
- Most played heroes, recent matches, playstyle fingerprint badge

**Match Page**
- Team vs team header with duration and patch
- Per-player scoreboard (K/D/A, net worth, damage, items)
- Objective timeline (visual event bar)
- Economy graph (net worth per player per minute)

**Hero Page**
- Win rate, pick rate, patch indicator
- Best items, best synergies, countered by
- Win rate history by patch (line chart)
- Top players on this hero

---

## 8. Infrastructure & Cost

### Services
```
VPS (app + Celery workers)   Hetzner / DigitalOcean    $6–12/month
PostgreSQL                   Supabase / Neon free tier  $0–5/month
Redis                        Upstash free tier          $0/month at launch
deadlock-api.com data        Free
Demo files                   Download, parse, discard   $0
Domain + SSL                Cloudflare               $12/year
Object storage (backups)    Cloudflare R2 / S3      $0–5/month
────────────────────────────────────────────────────────────────
Total at launch                                         ~$15–30/month
```

### Upstash Redis
- Free tier: 500K commands/month, 256MB
- Pay-as-you-go: $0.20 per 100K commands beyond free tier
- Celery connects via `rediss://` TLS connection string
- Two namespaces: `cache:` and `queue:` — separated to prevent cache eviction from impacting job queue
- Eviction policy: `allkeys-lru` on cache namespace; no eviction on queue namespace
- Alert threshold: 80% memory utilization

### Demo Worker Sandboxing
- Demo files downloaded to isolated scratch directory (`/tmp/demos`) only
- Worker runs as a restricted OS user with no network access and read-only filesystem except scratch dir
- File size validated before parsing (reject > 500MB)
- CDN download via HTTPS only; hostname validated against Valve CDN allowlist before initiating
- Memory and CPU limits enforced via container resource constraints

### GC Bot Credential Management
- Dedicated Steam account used solely for the bot — never shared with any personal account
- Credentials (username, password, TOTP 2FA secret) stored in secrets manager (e.g. HashiCorp Vault or environment secrets injected at runtime)
- Credentials never logged, never committed to source control, never stored in config files
- Credential rotation procedure documented and tested

### Data Import Integrity (Phase 1)
- deadlock-api.com dump files verified via SHA-256 checksum before import
- Every row validated against a strict Pydantic/Pandera schema before insertion
- Import runs under a least-privilege DB user: `INSERT`/`UPDATE` only on target tables, no `DDL`
- Imported to staging schema first, validated, then swapped to production
- Alert on schema drift between expected and received dump structure

### Dependency Pinning
- All Python dependencies pinned to exact versions with hash verification (`pip install --require-hashes`)
- Lock file (`poetry.lock` or `pip-compile` output) committed to source control
- `boon-deadlock` and `ValvePython/steam` changelogs reviewed before any upgrade
- Automated dependency vulnerability scanning in CI

### Database Migrations (Phase 1+)
- Use **Alembic** for Python/FastAPI migrations
- All migrations authored as upgrade/downgrade pairs
- Migration files committed to source control with descriptive names
- Run migrations in CI before deploy: `alembic upgrade head`
- Staging receives migrations before production (detect issues first)
- No DDL in application code — all schema changes via migrations

### Backup & Restore
- **Supabase/Neon automatic daily backups**: retained per provider SLA (typically 7 days)
- **WAL-G or pg_dump** to object storage (S3/R2): daily full dump, hourly WAL archives
- **Point-in-time recovery**: enabled via WAL archiving
- **Restore procedure tested quarterly** — documented runbook
- **Backup verification**: nightly restore to staging, run smoke tests
- RTO target: 4 hours, RPO target: 1 hour

### Observability
- **Error tracking**: Sentry (Python + JS SDK)
  - Release tracking: tag deploys in Sentry
  - Custom error grouping for demo parse failures by error_code
- **Metrics**: Prometheus + Grafana (self-hosted or Grafana Cloud free tier)
  - Request latency, rate limit hits, cache hit/miss ratios
  - Worker queue depth, demo parse duration, import duration
  - DB connection pool usage, query latency p50/p95/p99
- **Health checks**:
  - `/health` — returns DB connection + Redis ping + worker aliveness
  - `/ready` — includes queue depth, import aliveness
- **Alerts**: PagerDuty or Opsgenie (free tier at launch)
  - High error rate, failed health check, worker queue stuck > 1 hour

### Testing Strategy
- **Unit tests**: pytest for all business logic, schema validation, GDPR deletion cascade
- **Integration tests**: FastAPI TestClient against live DB (Testcontainers for PostgreSQL)
- **E2E tests**: Playwright for critical flows (search → player → match → stats)
- **Load testing**: k6 for API rate limits, cache effectiveness
- **CI**: Run unit + integration on PR, e2e + load on main before deploy
- **Coverage**: Target 80% core business logic, 100% API endpoints

---

## 9. Phased Rollout

### Phase 1 — Launch
- Import deadlock-api.com daily dumps into PostgreSQL
- FastAPI serving player profiles, match history, hero stats, leaderboard
- Next.js frontend with all pages
- Steam OpenID login
- All aggregation tables computed from imported data
- **No demo parsing yet** — `match_demo_status` table exists but empty

### Phase 2 — Deep Analytics
- GC bot (ValvePython) discovering matches for tracked players
- Celery workers downloading and parsing demos via boon-deadlock
- Populates: `item_builds`, `ability_upgrades`, `match_objectives`, `match_economy_snapshots`, `match_jungle_kills`, `match_lane_stats`, `match_damage_events`, `match_modifiers`
- Frontend surfaces new data progressively (guarded by `match_demo_status`)

### Phase 3 — Lane Intelligence
- Lane coordinate mapping (one-time calibration from `player_ticks` data)
- `match_lane_matchups` population from `player_ticks` dataset
- Per-player matchup build recommendations surface in UI
- Playstyle fingerprint scores computed from demo data

### Phase 4 — Community & Scale
- Community cache submission tool (users install background agent)
- Tournament/event tracking
- Public API keys for third-party developers and Discord bots
- Migrate to dedicated Redis/Valkey if Upstash costs grow

---

## 10. Security Summary

All findings from the pre-launch security audit have been addressed. Phase gates:

**Phase 1 launch blockers (all resolved):**
- JWT session fully specified (RS256, 1hr expiry, refresh tokens, Redis revocation, `SameSite=Lax`)
- GDPR deletion cascade defined (see Section 11)
- HTTP security headers defined for Next.js
- CORS policy defined
- OpenID callback redirect hardened

**Phase 2 blockers (all resolved):**
- Dump import integrity verification (checksum + schema validation + staging import)
- Demo worker sandboxing (isolated scratch dir, file size limit, CDN allowlist)
- GC bot credential management (secrets manager, dedicated account)
- Demo URL/salt nullified after parse
- Dependency pinning required

**Phase 4 blockers (all resolved):**
- `POST /ingest/cache` requires authentication, rate limited, deduplicated
- Rate limiting hardened against distributed scraping and enumeration

**Privacy decisions (resolved):**
- `match_chat` excluded entirely — not stored, not processed
- `player_name_history` restricted: public shows current + previous name only; full history is authenticated owner only; 90-day rolling retention; purged on deletion
- `player_playstyle_fingerprint` anonymized (scores zeroed) on GDPR deletion, not deleted, to preserve global aggregate integrity
- `computed_at` timestamps omitted from public API responses

---

## 11. GDPR Deletion Cascade

Triggered by `DELETE /auth/me` (authenticated). Completes within 30 days per GDPR Article 17.

**Email account deletion:**

| Table | Action |
|---|---|
| `accounts` | Delete row |
| `account_follows` | Delete all rows for account_id |
| Upstash Redis | Flush all cache keys and JWT tokens for account_id |

If the email account had a linked Steam ID, the player record is NOT automatically deleted — player data belongs to the Steam identity. The Steam account must be deleted separately.

**Player (Steam) account deletion:**

| Table | Action |
|---|---|
| `players` | Delete row |
| `accounts` | Null out `steam_id` FK if linked email account exists |
| `player_name_history` | Delete all rows |
| `match_players` | Anonymize: zero out stats, null out steam_id |
| `player_stats_snapshots` | Delete all rows |
| `player_item_affinity` | Delete all rows |
| `player_matchup_builds` | Delete all rows |
| `player_build_fingerprints` | Delete all rows |
| `player_item_timing_benchmarks` | Delete all rows |
| `player_playstyle_fingerprint` | Zero out all scores (preserve row for global aggregate integrity) |
| `player_performance_trend` | Delete all rows |
| `match_lane_matchups` | Delete rows where steam_id or enemy_steam_id matches |
| `match_damage_events` | Null out attacker/victim steam_id |
| `match_modifiers` | Delete all rows |
| `item_builds` | Delete all rows |
| `ability_upgrades` | Delete all rows |
| `match_economy_snapshots` | Delete all rows |
| `match_jungle_kills` | Delete all rows |
| `match_lane_stats` | Delete all rows |
| `account_follows` | Delete all rows where steam_id matches (others following this player) |
| Upstash Redis | Flush all cache keys containing steam_id |
| JWT blocklist | Add all active tokens for steam_id |

Match-level rows (`matches`, `match_objectives`, `hero_*`, `global_item_stats`) are not personal data and are retained.

---

## 12. Open Questions (Deferred)

- Lane coordinate bounding boxes — one-time calibration from `player_ticks` data against known map geometry (Phase 3)
- `player_ticks` sampling rate — every tick vs every N ticks for economy snapshots (storage vs fidelity tradeoff, decide in Phase 2)
