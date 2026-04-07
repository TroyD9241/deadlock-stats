import logging
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal

logger = logging.getLogger(__name__)

DUMP_URL = "https://deadlock-api.com/dumps"


def download_latest_dump() -> bytes:
    """Download latest dump file from deadlock-api.com."""
    with httpx.Client() as client:
        response = client.get(f"{DUMP_URL}/latest")
        response.raise_for_status()
        return response.content


def import_dump(dump_data: bytes, db: Session):
    """Import dump data into PostgreSQL."""
    import gzip
    import json

    try:
        dump_data = gzip.decompress(dump_data)
    except Exception:
        pass

    data = json.loads(dump_data)

    for hero in data.get("heroes", []):
        db.execute(
            "INSERT INTO heroes (hero_id, name, description, image_url, updated_at) "
            "VALUES (:id, :name, :desc, :url, :updated) "
            "ON CONFLICT (hero_id) DO UPDATE SET name = EXCLUDED.name",
            {
                "id": hero["id"],
                "name": hero["name"],
                "desc": hero.get("description"),
                "url": hero.get("image_url"),
                "updated": datetime.utcnow(),
            },
        )

    db.commit()
    logger.info(f"Imported {len(data.get('heroes', []))} heroes")


def run_import():
    """Main import task - scheduled daily."""
    db = SessionLocal()
    try:
        dump = download_latest_dump()
        import_dump(dump, db)
    finally:
        db.close()
