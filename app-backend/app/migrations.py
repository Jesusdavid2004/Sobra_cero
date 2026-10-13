"""Helpers for applying the application's Alembic schema migrations."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL


def upgrade_database_schema(database_url: URL) -> None:
    backend_root = Path(__file__).resolve().parent.parent
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    command.upgrade(config, "head")
