from celery import Celery

from app.config import settings

celery_app = Celery("sobracero", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task
def generate_promotions_task(lot_id: int, language: str = "en") -> int:
    from app.db import SessionLocal
    from app.models import Lot
    from app.services import build_promotions

    db = SessionLocal()
    try:
        lot = db.get(Lot, lot_id)
        return len(build_promotions(db, lot, language)) if lot else 0
    finally:
        db.close()
