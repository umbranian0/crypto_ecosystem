import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import text

from alembic import context

# app/ is importable because pyproject.toml's [tool.hatch.build.targets.wheel]
# maps "src/app" to the "app" package (see main.py's own import style).
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Single source of truth for the schema (mirrors validation-service's own
# migrations/env.py binding decision): the migration targets
# Base.metadata rather than a hand-written revision, so
# fee_schedules/slippage_models/simulation_configs are never defined twice.
target_metadata = Base.metadata

# DATABASE_URL overrides alembic.ini's sqlalchemy.url when set, so a real
# deployment (Postgres) doesn't need to edit this file (solution-design.md
# section 5: schema-per-service against a single Postgres instance).
if os.environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

# INF-005 precedent (validation-service's own migrations/env.py docstring):
# both the three economic.* tables and alembic_version itself must land in
# the `economic` schema, never `public`, to avoid the same
# public.alembic_version collision across services sharing one Postgres
# instance. Postgres-only: SET search_path/version_table_schema have no
# SQLite equivalent -- test_models.py's
# test_alembic_upgrade_head_creates_matching_schema runs `alembic upgrade
# head` against a real sqlite:/// DATABASE_URL, so this must stay
# conditional on the dialect, not applied unconditionally.
_SCHEMA = "economic"


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgresql+psycopg://")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_SCHEMA if _is_postgres_url(url) else None,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_postgres = connection.dialect.name == "postgresql"
        if is_postgres:
            # Table creation must land in `economic`, not `public` -- set the
            # connection's search_path before context.configure so every
            # unqualified DDL statement resolves there. Combined with
            # version_table_schema below (for alembic_version itself), this
            # is the same two-part fix validation-service's own env.py
            # applies. Postgres-only: SQLite has no SET search_path
            # equivalent, and test_models.py's own alembic-upgrade test runs
            # this same function against a real sqlite:/// URL.
            connection.execute(text(f"SET search_path TO {_SCHEMA}"))
            # SQLAlchemy 2.0 "commit-as-you-go": the SET above auto-begins a
            # transaction on this connection; without committing it here,
            # context.begin_transaction() below nests inside it via a
            # SAVEPOINT, so its own commit-on-exit never commits the *outer*
            # transaction, and the whole migration silently rolls back when
            # the connection closes. Commit it before alembic starts its own
            # transaction.
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=_SCHEMA if is_postgres else None,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
