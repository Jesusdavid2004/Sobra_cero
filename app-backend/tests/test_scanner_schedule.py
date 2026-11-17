from datetime import datetime, timedelta, timezone

import pytest

from app import dependencies
from app.application.scanner_dto import RunResult
from app.application.use_cases.scanner import RunDueSources
from app.db import Base, SessionLocal, engine
from app.infrastructure.repositories.rescue_plan_repository import SqlAlchemyUnitOfWork
from app.infrastructure.repositories.scanner_repository import (
    SqlAlchemyScannerRepository,
)
from app.models_external import ExternalSourceRow
from app.worker import celery_app, run_due_scanner_sources_task

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class FakeRunner:
    calls: list[tuple[str, str, int | None]] = []

    def run(self, source_key: str, trigger: str, user_id: int | None) -> RunResult:
        type(self).calls.append((source_key, trigger, user_id))
        return RunResult(1, "succeeded", 0, 0, 0, 0, "", "")


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    FakeRunner.calls = []
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def source(key: str, **overrides) -> ExternalSourceRow:
    fields = {"enabled": True, "terms_reviewed": True, "schedule_minutes": 60, **overrides}
    return ExternalSourceRow(key=key, name=key, kind="jsonld_catalog", base_url="https://x.example/", **fields)


def seed(*rows: ExternalSourceRow) -> None:
    with SessionLocal() as session:
        session.add_all(rows)
        session.commit()


def due(now: datetime = NOW) -> list[str]:
    with SessionLocal() as session:
        return SqlAlchemyScannerRepository(session).due_sources(now)


def test_a_scheduled_source_that_never_ran_is_due():
    seed(source("never-ran"))

    assert due() == ["never-ran"]


def test_a_source_is_due_only_after_its_interval_has_passed():
    seed(
        source("recent", last_run_at=NOW - timedelta(minutes=10)),
        source("overdue", last_run_at=NOW - timedelta(minutes=61)),
    )

    assert due() == ["overdue"]


def test_a_source_that_is_disabled_unreviewed_or_unscheduled_is_never_due():
    seed(
        source("disabled", enabled=False),
        source("unreviewed", terms_reviewed=False),
        source("manual-only", schedule_minutes=None),
    )

    assert due() == []


def test_running_the_due_sources_starts_each_one_as_a_scheduled_run_without_a_user():
    seed(source("a"), source("b", last_run_at=NOW - timedelta(minutes=5)))
    with SessionLocal() as session:
        use_case = RunDueSources(SqlAlchemyScannerRepository(session), SqlAlchemyUnitOfWork(session), FakeRunner())

        results = use_case.execute(NOW)

    assert len(results) == 1
    assert FakeRunner.calls == [("a", "scheduled", None)]


def test_the_scheduler_task_is_registered_and_runs_the_due_sources(monkeypatch):
    monkeypatch.setattr(dependencies, "SubprocessSourceRunner", FakeRunner)
    seed(source("a"), source("b"))

    started = run_due_scanner_sources_task()

    assert started == 2
    assert {call[0] for call in FakeRunner.calls} == {"a", "b"}
    assert celery_app.conf.beat_schedule["run-due-scanner-sources"]["task"] == "app.worker.run_due_scanner_sources_task"
