"""VS-032: standalone, operator/cron-run deletion script -- the primary
retention-enforcement mechanism for the `split_points` table (RAV-006's
"scheduled deletion/archival script" option). Physically bounds the table's
size regardless of whether anything ever reads it, unlike
`SplitPointRepository.get_points`'s query-time cutoff (defense in depth,
sqlite_repository.py/postgres_repository.py), which only hides old rows from
reads between two runs of this script.

Same "standalone script, argparse CLI, env-var-driven DB connection" shape as
`services/gateway-api/scripts/provision_tenant.py`/
`services/ingestion-service/scripts/seed_tenant.py` (DRY check note, ticket
Design section) -- no new orchestration framework, no second hardcoded `90`
(imports `SPLIT_POINT_RETENTION_DAYS` from the repository module instead).

Not routed through `SplitPointRepository` (unlike those two precedent
scripts, which do go through their respective repositories' own
`create_*`/`seed_*` methods): that interface has no delete method (VS-031's
Design section scoped it to `add_points`/`get_points` only, read/write, not
delete), and adding one there would blur "repository = the app's own runtime
data-access seam" with "operator-run bulk maintenance" for a single script's
sake. This script instead reuses `app.dependencies.repositories`'s own
env-var-resolution helpers (`_database_url`/`_db_path`/`_is_postgres_url`/
`_postgres_engine_url`/`_get_engine`) to build the same `Engine` the running
service would, then issues one `DELETE ... WHERE created_at < :cutoff`
directly against `app.models.SplitPoint` -- the same table, same connection
convention, no second URL-resolution copy.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.dependencies.repositories import (
    _database_url,
    _db_path,
    _get_engine,
    _is_postgres_url,
    _postgres_engine_url,
)
from app.models import SplitPoint
from app.repositories.sqlite_repository import SPLIT_POINT_RETENTION_DAYS


def _resolve_engine() -> Engine:
    database_url = _database_url()
    if database_url and _is_postgres_url(database_url):
        engine_url = _postgres_engine_url(database_url)
        return _get_engine(engine_url)
    db_path = _db_path()
    return _get_engine(f"sqlite:///{db_path}")


def prune_split_points(engine: Engine, older_than_days: int) -> int:
    """Deletes `split_points` rows with `created_at` older than
    `older_than_days` and returns the number of rows deleted -- the core
    logic under test (Test acceptance criteria #2), independent of CLI
    argument parsing/stdout.
    """
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    with Session(engine) as session:
        result = session.execute(delete(SplitPoint).where(SplitPoint.created_at < cutoff))
        session.commit()
        return result.rowcount


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Physically delete split_points rows older than the retention "
            "cutoff (operator/cron-run tool, no app process dependency)."
        )
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=SPLIT_POINT_RETENTION_DAYS,
        help=f"Retention window in days (default: {SPLIT_POINT_RETENTION_DAYS}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    engine = _resolve_engine()
    deleted_count = prune_split_points(engine, args.older_than_days)
    print(f"deleted {deleted_count} split_points row(s) older than {args.older_than_days} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
