from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from sboard.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
        return
    raw_path = database_url.removeprefix(prefix)
    Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


settings = get_settings()
_ensure_sqlite_parent(settings.database_url)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    if dbapi_connection.__class__.__module__.split(".")[0] != "sqlite3":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def init_db() -> None:
    from sboard import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        inspector = inspect(engine)
        subscription_columns = {column["name"] for column in inspector.get_columns("subscriptions")}
        rule_columns = {column["name"] for column in inspector.get_columns("rule_sets")}
        group_columns = {column["name"] for column in inspector.get_columns("groups")}
        with engine.begin() as connection:
            group_additions = {
                "strategy": "VARCHAR(20) NOT NULL DEFAULT 'select'",
                "test_url": "VARCHAR(2048) NOT NULL DEFAULT 'https://www.gstatic.com/generate_204'",
                "test_interval": "INTEGER NOT NULL DEFAULT 300",
                "test_tolerance": "INTEGER NOT NULL DEFAULT 50",
            }
            for name, definition in group_additions.items():
                if name not in group_columns:
                    connection.execute(text(f"ALTER TABLE groups ADD COLUMN {name} {definition}"))
            if "template_key" not in rule_columns:
                connection.execute(
                    text("ALTER TABLE rule_sets ADD COLUMN template_key VARCHAR(50)")
                )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_rule_sets_template_key "
                    "ON rule_sets (template_key)"
                )
            )
            if "token" not in subscription_columns:
                connection.execute(text("ALTER TABLE subscriptions ADD COLUMN token VARCHAR(100)"))
            if "group_id" not in rule_columns:
                connection.execute(
                    text(
                        "ALTER TABLE rule_sets ADD COLUMN group_id VARCHAR(36) "
                        "REFERENCES groups(id) ON DELETE SET NULL"
                    )
                )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_rule_sets_group_id ON rule_sets (group_id)")
            )
    from sboard.services.geosite_migration import migrate_geosite_rules

    with Session(engine) as db:
        migrate_geosite_rules(db)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
