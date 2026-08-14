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

# Single source of truth for the schema (RS-002 AC): the migration targets
# models.Base.metadata rather than a hand-written revision, so `reports` is
# never defined twice.
target_metadata = Base.metadata

# DATABASE_URL overrides alembic.ini's sqlalchemy.url when set, so a real
# deployment (Postgres) doesn't need to edit this file (solution-design.md
# section 5: schema-per-service against a single Postgres instance).
if os.environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

# RS-002 hard requirement (mirrors VS-013/GW-012, per INF-005's reproduced
# public.alembic_version collision -- see that ticket's Design section):
# both `reports` and `alembic_version` itself must land in the `reporting`
# schema, never `public`, inside the shared Postgres database/
# schema-per-service design INF-001 provisions. Postgres-only: `SET
# search_path`/`version_table_schema` have no SQLite equivalent -- a sqlite
# DATABASE_URL run of `alembic upgrade head` (mirroring
# validation-service's test_models.py precedent) must still work, so this
# stays conditional on the dialect, not applied unconditionally.
_SCHEMA = "reporting"


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgresql+psycopg://")


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
        if is_postgres:
            # Table creation (`reports`) must land in `reporting`, not
            # `public` -- set the connection's search_path before
            # context.configure so every unqualified DDL statement resolves
            # there. Combined with version_table_schema below (for
            # `alembic_version` itself), this is the two-part fix INF-005
            # required (see module-level comment above). Postgres-only:
            # SQLite has no `SET search_path` equivalent.
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
