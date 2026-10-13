from app.worker import celery_app


def test_expiration_task_runs_from_beat_schedule_every_minute():
    entry = celery_app.conf.beat_schedule["expire-due-lots"]

    assert entry["task"] == "app.worker.expire_due_lots_task"
    assert entry["schedule"] == 60.0
    assert entry["task"] in celery_app.tasks
