from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    text,
)


def test_upgrade_adds_new_fields_and_backfills_existing_pickup_codes(tmp_path: Path) -> None:
    database_path = tmp_path / "existing_sobracero.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("email", String(255), nullable=False),
        Column("password_hash", String(255), nullable=False),
        Column("is_admin", Boolean, nullable=False, default=False),
    )
    Table(
        "shops",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("owner_id", ForeignKey("users.id"), nullable=False),
        Column("name", String(160), nullable=False),
        Column("description", String, nullable=False, default=""),
        Column("latitude", Integer, nullable=False, default=0),
        Column("longitude", Integer, nullable=False, default=0),
    )
    Table(
        "products",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("shop_id", ForeignKey("shops.id"), nullable=False),
        Column("name", String(160), nullable=False),
        Column("description", String, nullable=False, default=""),
    )
    Table(
        "lots",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("shop_id", ForeignKey("shops.id"), nullable=False),
        Column("product_id", ForeignKey("products.id"), nullable=False),
        Column("title", String(160), nullable=False),
        Column("description", String, nullable=False, default=""),
        Column("quantity", Integer, nullable=False),
        Column("original_price_cents", Integer, nullable=False),
        Column("discount_percent", Integer, nullable=False),
        Column("expires_at", DateTime, nullable=False),
    )
    Table(
        "reservations",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("lot_id", ForeignKey("lots.id"), nullable=False),
        Column("user_id", ForeignKey("users.id"), nullable=False),
        Column("quantity", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, is_admin) "
                "VALUES (1, 'existing@example.com', 'hash', 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO shops (id, owner_id, name, description, latitude, longitude) "
                "VALUES (1, 1, 'Existing shop', '', 0, 0)"
            )
        )
        connection.execute(
            text("INSERT INTO products (id, shop_id, name, description) " "VALUES (1, 1, 'Existing product', '')")
        )
        connection.execute(
            text(
                "INSERT INTO lots "
                "(id, shop_id, product_id, title, description, quantity, "
                "original_price_cents, discount_percent, expires_at) "
                "VALUES (1, 1, 1, 'Existing lot', '', 2, 1000, 20, '2030-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO reservations (id, lot_id, user_id, quantity, created_at) "
                "VALUES (1, 1, 1, 1, '2025-01-01 00:00:00')"
            )
        )

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    inspector = inspect(engine)
    version_column = next(
        column for column in inspector.get_columns("alembic_version") if column["name"] == "version_num"
    )
    assert version_column["type"].length >= 64
    assert "role" in {column["name"] for column in inspector.get_columns("users")}
    assert "business_type" in {column["name"] for column in inspector.get_columns("shops")}
    assert "category" in {column["name"] for column in inspector.get_columns("products")}
    assert "pickup_code" in {column["name"] for column in inspector.get_columns("reservations")}
    with engine.connect() as connection:
        pickup_code = connection.scalar(text("SELECT pickup_code FROM reservations WHERE id = 1"))
        assert pickup_code is not None
        assert len(pickup_code) == 8
    engine.dispose()
