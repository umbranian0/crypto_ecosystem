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

# Single source of truth for the schema (this ticket's AC5): the migration
# targets models.Base.metadata rather than a hand-written revision, so
# `tenants`/`users`/`api_keys` are never defined twice.
target_metadata = Base.metadata

# DATABASE_URL overrides alembic.ini's sqlalchemy.url when set, so a real
# deployment (Postgres) doesn't need to edit this file (solution-design.md
# section 5: schema-per-service against a single Postgres instance).
if os.environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

# GW-012 (hard requirement, upgraded from "should" after INF-005's
# reproduced collision -- see infra/README.md's "Migrations verified
# against Compose Postgres" section): both services' migrations used to
# write to the same default `public.alembic_version` table, so whichever
# ran second against the same real Postgres database found `alembic_version`
# already stamped and silently no-opped its own upgrade(). Targeting the
# `identity` schema explicitly -- both for the app tables (via `search_path`)
# AND for Alembic's own bookkeeping table (`version_table_schema`) -- is
# what actually fixes that, not just "should" polish.
#
# Guarded to the postgresql dialect only: SQLite (this service's own
# tests/test_models.py runs `alembic upgrade head` against a real sqlite
# file as part of its schema-parity check) has no notion of a Postgres-style
# schema/search_path, and passing `version_table_schema` to a sqlite
# connection fails outright (it has no "identity" database attached).
_TARGET_SCHEMA = "identity"


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql")

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    configure_kwargs = {}
    if _is_postgres_url(url):
        configure_kwargs["version_table_schema"] = _TARGET_SCHEMA
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **configure_kwargs,
    )

    with context.begin_transaction():
        if _is_postgres_url(url):
            # Unqualified table names (models.py sets no per-table schema)
            # must resolve to `identity`, not `public`, for the DDL emitted
            # in offline mode too.
            context.execute(f"SET search_path TO {_TARGET_SCHEMA}, public")
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_postgres = connection.dialect.name == "postgresql"
        configure_kwargs = {}
        if is_postgres:
            # Session-level search_path so unqualified CREATE TABLE (etc.)
            # DDL in this connection's transaction lands in `identity`, not
            # `public` -- table creation half of the hard requirement.
            #
            # The explicit `connection.commit()` below matters: SQLAlchemy
            # 2.0 Core connections "autobegin" a transaction on first
            # execute(), and if this SET were left inside that autobegun,
            # never-explicitly-committed transaction, closing `connection`
            # at the end of this `with` block rolls it back -- silently
            # undoing every DDL statement alembic runs afterward too, even
            # though alembic's own nested transaction reports success.
            # Committing here closes that out cleanly so alembic's
            # subsequent `context.begin_transaction()` starts fresh, still
            # under this connection's normal (non-autocommit) isolation.
            connection.execute(text(f"SET search_path TO {_TARGET_SCHEMA}, public"))
            connection.commit()
            configure_kwargs["version_table_schema"] = _TARGET_SCHEMA
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            **configure_kwargs,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
