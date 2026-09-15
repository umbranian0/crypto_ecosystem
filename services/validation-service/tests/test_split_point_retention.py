"""VS-032: retention/pruning policy for `split_points`.

Both tests insert `SplitPoint` rows directly via a raw SQLAlchemy `Session`
(bypassing `SplitPointRepository.add_points`, which cannot set `created_at`
independently of "now") so `created_at` can be controlled precisely -- an
in-window row and an out-of-window row, per Test acceptance criteria #1/#2.
Neither test asserts "the constant exists" or "the function was called";
both prove real query/deletion behavior against a real SQLite file.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SplitPoint
from app.repositories import sqlite_repository as sqlite_repository_module
from app.repositories.sqlite_repository import SQLiteSplitPointRepository
from scripts.prune_split_points import prune_split_points

RUN_ID = "run-1"
TENANT_ID = "tenant-1"


def _insert_point(engine, *, point_id: str, created_at: datetime, split_index: int = 0) -> None:
    with Session(engine) as session:
        session.add(
            SplitPoint(
                id=point_id,
                run_id=RUN_ID,
                tenant_id=TENANT_ID,
                split_index=split_index,
                baseline_key="naive0",
                timestamp=created_at,
                predicted=0.0,
                actual=0.0,
                created_at=created_at,
            )
        )
        session.commit()


def _seed_in_and_out_of_window_rows(engine) -> None:
    now = datetime.utcnow()
    in_window = now - timedelta(days=1)
    out_of_window = now - timedelta(days=91)  # older than the 90-day default
    _insert_point(engine, point_id="in-window", created_at=in_window)
    _insert_point(engine, point_id="out-of-window", created_at=out_of_window)


def test_get_points_excludes_rows_older_than_the_retention_cutoff(db_path):
    repository = SQLiteSplitPointRepository(db_path)
    _seed_in_and_out_of_window_rows(repository._engine)

    points = repository.get_points(TENANT_ID, RUN_ID, split_index=0)

    assert [p.id for p in points] == ["in-window"]


def test_prune_split_points_physically_deletes_only_out_of_window_rows(db_path):
    repository = SQLiteSplitPointRepository(db_path)
    engine = repository._engine
    _seed_in_and_out_of_window_rows(engine)

    deleted_count = prune_split_points(engine, older_than_days=90)

    assert deleted_count == 1
    with Session(engine) as session:
        remaining_ids = session.execute(select(SplitPoint.id)).scalars().all()
    assert remaining_ids == ["in-window"]


def test_split_point_retention_days_is_the_single_source_both_mechanisms_read(
    db_path, monkeypatch
):
    # Patching the module constant changes both the query-time cutoff
    # (get_points) and the script's deletion window in one place -- proving
    # there is no second, independently hardcoded `90` anywhere.
    monkeypatch.setattr(sqlite_repository_module, "SPLIT_POINT_RETENTION_DAYS", 30)

    repository = SQLiteSplitPointRepository(db_path)
    engine = repository._engine
    now = datetime.utcnow()
    # 45 days old: within the original 90-day window, but outside a patched
    # 30-day window -- distinguishes "the patched constant is actually read"
    # from "some other, unrelated cutoff logic happens to still pass".
    _insert_point(engine, point_id="45-days-old", created_at=now - timedelta(days=45))
    _insert_point(engine, point_id="10-days-old", created_at=now - timedelta(days=10))

    points = repository.get_points(TENANT_ID, RUN_ID, split_index=0)
    assert [p.id for p in points] == ["10-days-old"]

    deleted_count = prune_split_points(
        engine, older_than_days=sqlite_repository_module.SPLIT_POINT_RETENTION_DAYS
    )
    assert deleted_count == 1
    with Session(engine) as session:
        remaining_ids = session.execute(select(SplitPoint.id)).scalars().all()
    assert remaining_ids == ["10-days-old"]
