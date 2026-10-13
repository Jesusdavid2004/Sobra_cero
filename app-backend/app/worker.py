from celery import Celery

from app.config import settings

celery_app = Celery("sobracero", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = {
    "expire-due-lots": {
        "task": "app.worker.expire_due_lots_task",
        "schedule": 60.0,
    }
}


@celery_app.task
def generate_promotions_task(lot_id: int, language: str = "en") -> int:
    from app.db import SessionLocal
    from app.models import Lot
    from app.services import build_promotions

    db = SessionLocal()
    try:
        lot = db.get(Lot, lot_id)
        if not lot:
            return 0
        promotions = build_promotions(db, lot, language)
        return len(promotions)
    finally:
        db.close()


@celery_app.task  # type: ignore[misc]
def expire_due_lots_task() -> int:
    from app.db import SessionLocal
    from app.services import expire_due_lots

    db = SessionLocal()
    try:
        return expire_due_lots(db)
    finally:
        db.close()
