"""Load demonstration businesses for Pasto so the map can be shown without any external source.

Usage: python scripts/seed_pasto_demo.py
Reads DATABASE_URL like the backend. Safe to run again: records are matched by their demo id.

Everything it writes belongs to a source of kind `demo`, is flagged `is_demo`, is never shown
unless a visitor opts in, and is never an affiliated shop. It writes no products or prices, so
nothing here can look like a real promotion.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app-backend"))

from app.db import SessionLocal  # noqa: E402
from app.domain.collection import SourceKind  # noqa: E402
from app.domain.external_data import ExternalBusinessRecord  # noqa: E402
from app.domain.places import PlaceCategory  # noqa: E402
from app.infrastructure.repositories.external_data_repository import (  # noqa: E402
    SqlAlchemyExternalDataRepository,
)
from app.models_external import ExternalSourceRow  # noqa: E402

SOURCE_KEY = "demo-pasto"
CITY = "Pasto"
DEMO_BUSINESSES = (
    ("Demo Panadería Centro", PlaceCategory.BAKERY, 1.2140, -77.2810, "Calle 18 con Carrera 25"),
    ("Demo Supermercado Plaza", PlaceCategory.SUPERMARKET, 1.2152, -77.2796, "Carrera 26"),
    ("Demo Restaurante La Esquina", PlaceCategory.RESTAURANT, 1.2128, -77.2825, "Calle 17"),
    ("Demo Cafetería Universidad", PlaceCategory.CAFE, 1.2297, -77.2885, "Cerca de la Universidad de Nariño"),
    ("Demo Tienda de Barrio Obrero", PlaceCategory.STORE, 1.2210, -77.2700, "Barrio Obrero"),
    ("Demo Plaza de Mercado", PlaceCategory.MARKET, 1.2100, -77.2790, "Sector El Potrerillo"),
    ("Demo Panadería Terminal", PlaceCategory.BAKERY, 1.2010, -77.2740, "Cerca del Terminal"),
    ("Demo Restaurante Unicentro", PlaceCategory.RESTAURANT, 1.2038, -77.2646, "Centro comercial"),
    ("Demo Supermercado Sur", PlaceCategory.SUPERMARKET, 1.1960, -77.2830, "Sur de la ciudad"),
    ("Demo Cafetería Parque", PlaceCategory.CAFE, 1.2175, -77.2745, "Frente al parque"),
)


def main() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        repository = SqlAlchemyExternalDataRepository(session)
        source = repository.get_source(SOURCE_KEY)
        if source is None:
            source = ExternalSourceRow(
                key=SOURCE_KEY,
                name="Demonstration data (Pasto)",
                kind=SourceKind.DEMO.value,
                license_note="Invented for demonstrations. Not real businesses.",
            )
            session.add(source)
            session.flush()
        for index, (name, category, latitude, longitude, address) in enumerate(DEMO_BUSINESSES, start=1):
            repository.upsert_business(
                source,
                ExternalBusinessRecord(
                    source_key=SOURCE_KEY,
                    external_id=f"demo/{index}",
                    name=name,
                    category=category,
                    latitude=latitude,
                    longitude=longitude,
                    address=address,
                    city=CITY,
                    website="",
                    phone="",
                    opening_hours="",
                    source_url="",
                    observed_at=now,
                ),
            )
        session.commit()
    sys.stdout.write(f"Loaded {len(DEMO_BUSINESSES)} demonstration businesses for {CITY}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
