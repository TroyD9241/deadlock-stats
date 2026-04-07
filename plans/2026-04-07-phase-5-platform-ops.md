# Platform Ops Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement observability, backups, CI/CD, and production-ready infrastructure.

**Tech Stack:** Sentry, Prometheus/Grafana, GitHub Actions, Cloudflare, Terraform/OpenTofu

---

## Task 1: Sentry Integration

**Files:**
- Modify: `backend/app/main.py`
- Modify: `frontend/`

**Step 1: Add Sentry to backend**

```python
# backend/app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastAPIntegration
from app.config import get_settings

settings = get_settings()

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    integrations=[FastAPIntegration()],
    traces_sample_rate=0.1,
    environment="production",
)


# Tag deploys in CI
# export SENTRY_RELEASE="deadlock-stats@0.1.0"
# sentry-cli releases deploys "$RELEASE"
```

**Step 2: Add Sentry to frontend**

```javascript
// frontend/sentry.client.config.ts
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
});
```

**Step 3: Commit**

```bash
git add backend/app/main.py frontend/sentry.client.config.ts
git commit -m "feat: add Sentry integration"
```

---

## Task 2: Prometheus Metrics

**Files:**
- Create: `backend/app/metrics.py`

**Step 1: Create metrics**

```python
from prometheus_client import Counter, Histogram, Gauge
import time


REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency")
CACHE_HIT = Counter("cache_hits_total", "Cache hits", ["endpoint"])
WORKER_QUEUE_DEPTH = Gauge("worker_queue_depth", "Celery worker queue depth")
DEMO_PARSE_DURATION = Histogram("demo_parse_duration_seconds", "Demo parse duration")
DB_QUERY_DURATION = Histogram("db_query_duration_seconds", "Database query duration")


# Use in routers:
@router.get("/players/{steam_id}")
async def get_player(steam_id: int, db: Session = Depends(get_db)):
    with REQUEST_LATENCY.time():
        # ... query
        REQUEST_COUNT.labels(method="GET", endpoint="players").inc()
```

**Step 2: Add metrics endpoint**

```python
@router.get("/metrics")
async def metrics():
    from prometheus_client import generate_latest
    return Response(generate_latest(), media_type="text/plain")
```

**Step 3: Commit**

```bash
git add backend/app/metrics.py
git commit -m "feat: add Prometheus metrics"
```

---

## Task 3: Health Checks

**Files:**
- Modify: `backend/app/main.py`

**Step 1: Enhance health endpoints**

```python
from sqlalchemy import text


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB error: {e}")
    return {"status": "healthy"}


@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    from app.celery import celery_app
    from redis import Redis
    
    # Check queue depth
    r = Redis.from_url(settings.redis_url)
    queue_depth = r.llen("celery")
    
    # Check workers
    inspector = celery_app.control.inspect()
    active = inspector.active()
    
    return {
        "status": "ready",
        "workers": len(active or {}),
        "queue_depth": queue_depth,
    }
```

**Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: enhance health checks"
```

---

## Task 4: Backup Configuration

**Files:**
- Create: `scripts/backup.sh`

**Step 1: Create backup script**

```bash
#!/bin/bash
# scripts/backup.sh

set -e

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"

# PostgreSQL backup
pg_dump $DATABASE_URL > "$BACKUP_DIR/postgres_$DATE.sql"

# Upload to S3/R2
aws s3 cp "$BACKUP_DIR/postgres_$DATE.sql" s3://backups/deadlock-stats/

# Keep only 7 days local
find $BACKUP_DIR -mtime +7 -delete

echo "Backup complete: $DATE"
```

**Step 2: Create restore script**

```bash
#!/bin/bash
# scripts/restore.sh

DATE=$1
aws s3 cp s3://backups/deadlock-stats/postgres_$DATE.sql /tmp/restore.sql
psql $DATABASE_URL < /tmp/restore.sql
```

**Step 3: Cron schedule**

```yaml
# .github/workflows/backup.yml
on:
  schedule:
    - cron: '0 3 * * *'  # Daily at 3 AM
jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - run: ./scripts/backup.sh
```

**Step 4: Commit**

```bash
git add scripts/backup.sh scripts/restore.sh .github/workflows/backup.yml
git commit -m "feat: add backup scripts"
```

---

## Task 5: CI/CD Pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Create CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -e ".[dev]"
      
      - name: Run tests
        run: pytest tests/ -v --cov
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff && ruff check backend/

  deploy:
    needs: [test, lint]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy to production
        run: |
          # SSH to server, pull, restart services
```

**Step 2: Create CD workflow**

```yaml
# .github/workflows/cd.yml
name: CD

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          # Deploy via docker-compose or k8s
```

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/cd.yml
git commit -m "feat: add CI/CD pipeline"
```

---

## Task 6: Docker Setup

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Step 1: Create Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Create docker-compose**

```yaml
version: '3.8'

services:
  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  worker:
    build: ./backend
    command: celery -A app.celery worker
    depends_on:
      - redis

volumes:
  postgres_data:
```

**Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Docker configuration"
```

---

## Task 7: Monitoring Dashboards

**Files:**
- Create: `dashboards/grafana/`

**Step 1: Create dashboard JSON**

```json
{
  "dashboard": {
    "title": "Deadlock Stats",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "{{endpoint}}"
          }
        ]
      },
      {
        "title": "Response Latency",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "p95"
          }
        ]
      },
      {
        "title": "Worker Queue Depth",
        "type": "graph",
        "targets": [
          {
            "expr": "worker_queue_depth",
            "legendFormat": "queue"
          }
        ]
      }
    ]
  }
}
```

**Step 2: Commit**

```bash
git add dashboards/grafana/
git commit -m "feat: add Grafana dashboards"
```

---

## Plan Complete

Platform Ops implementation complete:
- ✅ Sentry integration
- ✅ Prometheus metrics
- ✅ Enhanced health checks
- ✅ Backup/restore scripts
- ✅ CI/CD pipeline
- ✅ Docker configuration
- ✅ Monitoring dashboards

---

**All 5 plans complete!**

| Plan | File |
|------|------|
| 1. Core Infrastructure | `plans/2026-04-07-core-infrastructure.md` |
| 2. Demo Parsing | `plans/2026-04-07-phase-2-demo-parsing.md` |
| 3. Lane Intelligence | `plans/2026-04-07-phase-3-lane-intelligence.md` |
| 4. Community | `plans/2026-04-07-phase-4-community.md` |
| 5. Platform Ops | `plans/2026-04-07-phase-5-platform-ops.md` |

---

**Ready to execute. Which approach?**
**1. Subagent-Driven (this session)**
**2. Parallel Session (separate)**