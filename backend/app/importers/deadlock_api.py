"""
Importer for deadlock-api.com REST API.
Uses the API endpoints to fetch data.
"""

import logging
from datetime import datetime

import httpx
from sqlalchemy import text

from app.database import SessionLocal

logger = logging.getLogger(__name__)

API_BASE = "https://api.deadlock-api.com/v1"


def fetch_heroes():
    """Fetch heroes from API."""
    logger.info("Fetching heroes...")
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{API_BASE}/heroes")
        response.raise_for_status()
        return response.json()


def fetch_items():
    """Fetch items from API."""
    logger.info("Fetching items...")
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{API_BASE}/items")
        response.raise_for_status()
        return response.json()


def import_heroes(heroes: list, db):
    """Import heroes to PostgreSQL."""
    logger.info(f"Importing {len(heroes)} heroes...")

    for hero in heroes:
        db.execute(
            text("""
                INSERT INTO heroes (hero_id, name, description, image_url, updated_at)
                VALUES (:id, :name, :desc, :url, :updated)
                ON CONFLICT (hero_id) DO UPDATE SET 
                    name = EXCLUDED.name,
                    description = COALESCE(EXCLUDED.description, heroes.description),
                    image_url = COALESCE(EXCLUDED.image_url, heroes.image_url),
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": hero.get("id"),
                "name": hero.get("name", ""),
                "desc": hero.get("description", ""),
                "url": hero.get("image_url"),
                "updated": datetime.utcnow(),
            },
        )

    db.commit()
    logger.info(f"Imported heroes")


def import_items(items: list, db):
    """Import items to PostgreSQL."""
    logger.info(f"Importing {len(items)} items...")

    for item in items:
        db.execute(
            text("""
                INSERT INTO items (item_id, name, cost, category, tier, description, image_url, updated_at)
                VALUES (:id, :name, :cost, :category, :tier, :desc, :url, :updated)
                ON CONFLICT (item_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    cost = COALESCE(EXCLUDED.cost, items.cost),
                    category = COALESCE(EXCLUDED.category, items.category),
                    tier = COALESCE(EXCLUDED.tier, items.tier),
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": item.get("id"),
                "name": item.get("name", ""),
                "cost": item.get("cost"),
                "category": item.get("type"),
                "tier": item.get("tier"),
                "desc": item.get("description", ""),
                "url": item.get("image_url"),
                "updated": datetime.utcnow(),
            },
        )

    db.commit()
    logger.info(f"Imported items")


def run_import():
    """Main import function."""
    logger.info("Starting deadlock-api.com import via REST API...")

    db = SessionLocal()
    try:
        # Fetch and import heroes
        heroes = fetch_heroes()
        import_heroes(heroes, db)

        # Fetch and import items
        items = fetch_items()
        import_items(items, db)

        logger.info("Import complete!")

    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_import()
