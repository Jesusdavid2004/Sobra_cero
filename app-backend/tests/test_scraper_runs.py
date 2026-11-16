"""End-to-end runs of the Scrapy engine against a local fixture site, in a subprocess like production."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.models_external import (
    ExternalProductRow,
    ExternalSourceRow,
    PriceObservationRow,
    ScrapingExecutionRow,
    ScrapingRecordRow,
)

BACKEND = Path(__file__).resolve().parents[1]
CATALOG_HTML = """<html><head><script type="application/ld+json">
{"@graph": [
 {"@type": "Product", "name": "Pan tajado", "category": "Panadería", "url": "http://fixture/pan",
  "offers": {"price": "5990", "priceCurrency": "COP",
             "priceSpecification": [{"priceType": "https://schema.org/ListPrice", "price": "7990"}]}},
 {"@type": "Product", "name": "Leche entera", "url": "http://fixture/leche",
  "offers": {"price": "4500", "priceCurrency": "COP"}},
 {"@type": "Product", "name": "Producto regalo", "url": "http://fixture/regalo",
  "offers": {"price": "gratis", "priceCurrency": "COP"}}
]}
</script></head><body>catalog</body></html>"""
ROBOTS = "User-agent: *\nDisallow: /privado\n"


class FixtureSite(BaseHTTPRequestHandler):
    requests: list[str] = []

    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(self.path)
        routes = {
            "/robots.txt": (200, "text/plain", ROBOTS),
            "/catalogo": (200, "text/html", CATALOG_HTML),
            "/privado": (200, "text/html", CATALOG_HTML),
            "/denegado": (403, "text/html", "forbidden"),
            "/limitado": (429, "text/html", "slow down"),
        }
        status, content_type, body = routes.get(self.path, (404, "text/plain", "missing"))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture
def site():
    FixtureSite.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureSite)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def register(base_url: str, key: str = "fixture", **overrides) -> None:
    fields = {"enabled": True, "terms_reviewed": True, **overrides}
    with SessionLocal() as session:
        session.add(
            ExternalSourceRow(key=key, name="Fixture store", kind="jsonld_catalog", base_url=base_url, **fields)
        )
        session.commit()


def run(tmp_path: Path, key: str = "fixture") -> dict:
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite:///./test_sobracero.db",
        "APP_ENVIRONMENT": "test",
        "SCRAPER_DISABLE_URL_POLICY": "1",
        "SCRAPER_DOWNLOAD_DELAY": "0",
        "SCRAPER_CACHE_DIR": str(tmp_path),
        "LLM_PROVIDER": "mock",
    }
    result = subprocess.run(
        [sys.executable, "-m", "scraper.run", "--source", key],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.stdout.strip(), result.stderr[-1500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def count(model) -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_a_reviewed_source_is_collected_with_valid_records_stored_and_invalid_ones_rejected(site, tmp_path):
    register(f"{site}/catalogo")

    summary = run(tmp_path)

    assert (summary["status"], summary["accepted"], summary["rejected"]) == ("succeeded", 2, 1)
    with SessionLocal() as session:
        products = {p.name: p for p in session.scalars(select(ExternalProductRow))}
        assert set(products) == {"Pan tajado", "Leche entera"}
        assert (products["Pan tajado"].discount_percent, products["Leche entera"].discount_percent) == (25, 0)
        rejected = session.scalar(select(ScrapingRecordRow))
        assert rejected is not None and rejected.reason == "invalid_price"
        execution = session.scalar(select(ScrapingExecutionRow))
        assert execution is not None and execution.status == "succeeded" and execution.finished_at is not None


def test_running_again_does_not_duplicate_products_or_price_history(site, tmp_path):
    register(f"{site}/catalogo")

    run(tmp_path)
    run(tmp_path)

    assert count(ExternalProductRow) == 2
    assert count(PriceObservationRow) == 2
    assert count(ScrapingExecutionRow) == 2


def test_a_source_whose_terms_were_not_reviewed_is_refused_without_any_request(site, tmp_path):
    register(f"{site}/catalogo", terms_reviewed=False)

    summary = run(tmp_path)

    assert (summary["status"], summary["stop_reason"], summary["error"]) == (
        "stopped",
        "not_allowed",
        "terms_not_reviewed",
    )
    assert FixtureSite.requests == []
    assert count(ExternalProductRow) == 0


def test_a_disabled_source_is_refused_and_the_refusal_is_in_the_history(site, tmp_path):
    register(f"{site}/catalogo", enabled=False)

    summary = run(tmp_path)

    assert summary["error"] == "disabled"
    assert count(ScrapingExecutionRow) == 1
    assert FixtureSite.requests == []


def test_an_access_denied_response_stops_the_run(site, tmp_path):
    register(f"{site}/denegado")

    summary = run(tmp_path)

    assert (summary["status"], summary["stop_reason"]) == ("stopped", "access_denied")
    assert count(ExternalProductRow) == 0


def test_a_rate_limit_response_stops_the_run(site, tmp_path):
    register(f"{site}/limitado")

    assert run(tmp_path)["stop_reason"] == "rate_limited"


def test_a_page_blocked_by_robots_txt_is_never_requested(site, tmp_path):
    register(f"{site}/privado")

    summary = run(tmp_path)

    assert summary["stop_reason"] == "robots_forbidden"
    assert "/privado" not in FixtureSite.requests
    assert count(ExternalProductRow) == 0


def test_an_unknown_source_is_reported_instead_of_crashing(tmp_path):
    assert run(tmp_path, key="nope")["status"] == "refused"
