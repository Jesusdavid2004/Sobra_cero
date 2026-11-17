from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import auth_headers, reset_db

from app import dependencies, main
from app.application.scanner_dto import RunResult
from app.db import SessionLocal
from app.domain.collection import ExecutionStatus, RecordKind, RecordStatus, Trigger
from app.domain.external_data import ExternalBusinessRecord, ExternalProductRecord
from app.domain.places import PlaceCategory
from app.infrastructure.repositories.external_data_repository import (
    SqlAlchemyExternalDataRepository,
)
from app.models import User
from app.models_external import ExternalSourceRow

NOW = datetime.now(timezone.utc)
BASE = "/api/v1/admin/scanner"
SOURCE = {
    "key": "exito-demo",
    "name": "Catalog demo",
    "kind": "jsonld_catalog",
    "base_url": "https://www.exito.com/pan",
}


class FakeRunner:
    calls: list[tuple[str, str, int | None]] = []

    def run(self, source_key: str, trigger: str, user_id: int | None) -> RunResult:
        type(self).calls.append((source_key, trigger, user_id))
        return RunResult(7, "succeeded", 3, 1, 0, 0, "", "")


@pytest.fixture
def api(monkeypatch):
    reset_db()
    main._rate_buckets.clear()
    FakeRunner.calls = []
    monkeypatch.setattr(dependencies, "SubprocessSourceRunner", FakeRunner)
    monkeypatch.setattr(dependencies, "resolve_host", lambda _host: ["93.184.216.34"])
    client = TestClient(main.app)
    admin = auth_headers(client, "admin@example.com", role="customer")
    with SessionLocal() as db:
        db.query(User).filter(User.email == "admin@example.com").update({"is_admin": True})
        db.commit()
    return client, admin


def seed(rows: int = 1) -> None:
    """One source with one business, one promoted product with a price change, and a rejected record."""
    with SessionLocal() as db:
        source = ExternalSourceRow(key="demo", name="Demo", kind="jsonld_catalog", base_url="https://x.example/")
        db.add(source)
        db.flush()
        repository = SqlAlchemyExternalDataRepository(db)
        repository.upsert_business(
            source,
            ExternalBusinessRecord(
                "demo", "b1", "Panadería El Trigo", PlaceCategory.BAKERY, 1.2136, -77.2811, "Calle 18", "Pasto",
                "", "", "", "", NOW,
            ),  # fmt: skip
        )
        product = ExternalProductRecord(
            "demo", "Pan", "Panadería", "https://x.example/pan", 5990, 7990, 25, "InStock", "Tienda", NOW
        )
        repository.upsert_product(source, product)
        later = ExternalProductRecord(
            "demo", "Pan", "Panadería", "https://x.example/pan", 4990, 7990, 38, "InStock", "Tienda", NOW
        )
        repository.upsert_product(source, later)
        execution_id = repository.start_execution(source.id, Trigger.MANUAL, None, NOW)
        repository.add_record(
            execution_id, RecordKind.PRODUCT, RecordStatus.REJECTED, "invalid_price", "https://x.example/x", "{}", NOW
        )
        repository.finish_execution(execution_id, ExecutionStatus.SUCCEEDED, NOW, 2, 1, 1)
        db.commit()


def test_only_an_administrator_can_use_the_scanner(api):
    client, _admin = api
    customer = auth_headers(client, "customer@example.com", role="customer")

    assert client.get(f"{BASE}/summary").status_code == 401
    forbidden = client.get(f"{BASE}/sources", headers=customer)
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "scanner_permission_denied"
    assert client.post(f"{BASE}/sources/x/run", headers=customer).status_code == 403


def test_a_new_source_starts_disabled_and_unreviewed(api):
    client, admin = api

    response = client.post(f"{BASE}/sources", json=SOURCE, headers=admin)

    assert response.status_code == 201
    body = response.json()
    assert (body["enabled"], body["terms_reviewed"], body["last_status"]) == (False, False, "")


def test_unsafe_source_urls_are_rejected_with_a_reason(api):
    client, admin = api

    for url, reason in (
        ("http://www.exito.com/pan", "not_https"),
        ("https://evil.example/pan", "domain_not_allowed"),
        ("https://exito.com@evil.example/", "has_credentials"),
    ):
        response = client.post(f"{BASE}/sources", json={**SOURCE, "base_url": url}, headers=admin)
        assert response.status_code == 422
        assert response.json()["code"] == "scanner_url_rejected"
        assert response.json()["details"] == {"reason": reason}


def test_a_private_address_behind_an_allowed_domain_is_rejected(api, monkeypatch):
    client, admin = api
    monkeypatch.setattr(dependencies, "resolve_host", lambda _host: ["10.0.0.5"])

    response = client.post(f"{BASE}/sources", json=SOURCE, headers=admin)

    assert response.json()["details"] == {"reason": "private_address"}


def test_a_duplicate_key_is_reported(api):
    client, admin = api
    client.post(f"{BASE}/sources", json=SOURCE, headers=admin)

    response = client.post(f"{BASE}/sources", json=SOURCE, headers=admin)

    assert response.status_code == 422
    assert response.json()["details"] == {"reason": "key_taken"}


def test_a_source_cannot_be_enabled_before_its_terms_are_reviewed(api):
    client, admin = api
    client.post(f"{BASE}/sources", json=SOURCE, headers=admin)

    response = client.post(f"{BASE}/sources/exito-demo/enabled", json={"enabled": True}, headers=admin)

    assert response.status_code == 409
    assert response.json()["code"] == "scanner_source_not_runnable"
    assert response.json()["details"] == {"reason": "terms_not_reviewed"}


def test_after_a_recorded_review_the_source_can_be_enabled_and_scheduled(api):
    client, admin = api
    client.post(f"{BASE}/sources", json=SOURCE, headers=admin)

    reviewed = client.post(
        f"{BASE}/sources/exito-demo/terms-review",
        json={
            "note": "Read the terms of use on 2026-11-16; schema.org data is public.",
            "license_note": "Public pages",
        },
        headers=admin,
    )
    enabled = client.post(f"{BASE}/sources/exito-demo/enabled", json={"enabled": True}, headers=admin)
    scheduled = client.put(f"{BASE}/sources/exito-demo/schedule", json={"minutes": 60}, headers=admin)

    assert reviewed.json()["terms_reviewed"] is True
    assert enabled.json()["enabled"] is True
    assert scheduled.json()["schedule_minutes"] == 60


def test_an_unknown_source_uses_the_error_contract(api):
    client, admin = api

    response = client.post(f"{BASE}/sources/missing/enabled", json={"enabled": False}, headers=admin)

    assert response.status_code == 404
    assert response.json() == {"code": "scanner_source_not_found", "message_key": "errors.scanner_source_not_found"}


def test_running_a_source_delegates_to_the_runner_with_the_requesting_admin(api):
    client, admin = api
    client.post(f"{BASE}/sources", json=SOURCE, headers=admin)

    response = client.post(f"{BASE}/sources/exito-demo/run", headers=admin)

    assert response.status_code == 200
    assert response.json()["accepted"] == 3
    assert FakeRunner.calls[0][:2] == ("exito-demo", "manual") and FakeRunner.calls[0][2] is not None


def test_a_run_left_running_by_a_dead_process_is_closed_before_the_next_run(api):
    client, admin = api
    client.post(f"{BASE}/sources", json=SOURCE, headers=admin)
    with SessionLocal() as db:
        source = db.query(ExternalSourceRow).one()
        repository = SqlAlchemyExternalDataRepository(db)
        repository.start_execution(source.id, Trigger.MANUAL, None, NOW - timedelta(hours=2))
        db.commit()

    client.post(f"{BASE}/sources/exito-demo/run", headers=admin)

    executions = client.get(f"{BASE}/executions", headers=admin).json()
    assert [(e["status"], e["stop_reason"]) for e in executions] == [("failed", "crashed")]


def test_the_summary_counts_what_was_collected_and_what_still_needs_a_person(api):
    client, admin = api
    seed()

    summary = client.get(f"{BASE}/summary", headers=admin).json()

    assert summary["total_sources"] == 1 and summary["disabled_sources"] == 1
    assert (summary["products_found"], summary["promotions_detected"]) == (1, 1)
    assert (summary["businesses_discovered"], summary["pending_validation"], summary["rejected_records"]) == (1, 1, 1)
    assert summary["last_runs"][0]["status"] == "succeeded"


def test_collected_products_show_freshness_and_their_price_history(api):
    client, admin = api
    seed()

    products = client.get(f"{BASE}/products", params={"promotions_only": True}, headers=admin).json()
    history = client.get(f"{BASE}/products/{products[0]['id']}/history", headers=admin).json()

    assert (products[0]["freshness"], products[0]["price_cop"]) == ("fresh", 4990)
    assert [point["price_cop"] for point in history] == [5990, 4990]


def test_rejected_records_of_a_run_can_be_inspected(api):
    client, admin = api
    seed()
    execution_id = client.get(f"{BASE}/executions", headers=admin).json()[0]["id"]

    records = client.get(f"{BASE}/executions/{execution_id}/records", headers=admin).json()

    assert [(r["status"], r["reason"]) for r in records] == [("rejected", "invalid_price")]


def test_a_discovered_business_stays_unaffiliated_and_can_be_verified(api):
    client, admin = api
    seed()
    business = client.get(f"{BASE}/businesses", headers=admin).json()[0]

    verified = client.post(
        f"{BASE}/businesses/{business['id']}/verification", json={"status": "verified"}, headers=admin
    )
    after = client.get(f"{BASE}/businesses", params={"verification": "verified"}, headers=admin).json()

    assert business["affiliation"] == "discovered"
    assert verified.status_code == 204
    assert [(b["verification_status"], b["affiliation"]) for b in after] == [("verified", "discovered")]


def test_verifying_an_unknown_business_is_a_404(api):
    client, admin = api

    response = client.post(f"{BASE}/businesses/999/verification", json={"status": "verified"}, headers=admin)

    assert response.status_code == 404
    assert response.json()["code"] == "scanner_business_not_found"
