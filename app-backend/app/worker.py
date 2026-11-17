from celery import Celery

from app.config import settings

SCANNER_CHECK_SECONDS = 900.0

celery_app = Celery("sobracero", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = {
    "expire-due-lots": {
        "task": "app.worker.expire_due_lots_task",
        "schedule": 60.0,
    },
    "run-due-scanner-sources": {
        "task": "app.worker.run_due_scanner_sources_task",
        "schedule": SCANNER_CHECK_SECONDS,
    },
}


@celery_app.task
def generate_promotions_task(lot_id: int, user_id: int, language: str = "en") -> int:
    from app.db import SessionLocal
    from app.models import Lot
    from app.services import build_promotions

    db = SessionLocal()
    try:
        lot = db.get(Lot, lot_id)
        if not lot:
            return 0
        promotions = build_promotions(db, lot, language, user_id=user_id)
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


@celery_app.task  # type: ignore[misc]
def run_due_scanner_sources_task() -> int:
    """Run the sources whose schedule says they are due. A source still needs its terms reviewed."""
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.dependencies import build_run_due_sources_use_case

    db = SessionLocal()
    try:
        return len(build_run_due_sources_use_case(db).execute(datetime.now(timezone.utc)))
    finally:
        db.close()
