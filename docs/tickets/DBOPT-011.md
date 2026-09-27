# DBOPT-011 — Bound `get_splits`/`GET /runs/{run_id}/splits` with `limit`/`offset`; update `run_detail`/`runs_trend` to request a bounded page

**Status: done.** Implemented across `services/validation-service`, `services/gateway-api`,
`services/dashboard-web`, per the Design section below exactly (personally diffed by the Tech Lead
against the ticket's own code samples — byte-for-byte match on the repository/router/proxy changes).
Full test suites, independently re-run by the Tech Lead: `validation-service` 252/252 (the
`created_at`-tie-break flake documented elsewhere in this file's history did not trigger on this
run; it is pre-existing and unrelated to this ticket — `list_runs` is untouched by this diff),
`gateway-api` 249 passed / 1 pre-existing unrelated failure
(`test_get_run_forwards_and_returns_full_detail_shape`, already tracked in `docs/tickets/README.md`
since Sprint 60), `dashboard-web` 455 passed / 8 deselected (Selenium e2e). Both `check_doc_sync.py`
scripts checked (`validation-service` — passes, new route present; `libs/common` — no change, not
touched by this ticket). All Implementation/Test/Review/Documentation acceptance criteria below are
checked, personally verified by the Tech Lead (diff read in full, tail-selection math re-derived,
tests re-run — not taken on the dev agent's self-report alone).

**Modules**: `services/validation-service` (repository/router changes, owns the data),
`services/gateway-api` (pass-through of the new params + new count route),
`services/dashboard-web` (`run_detail`/`runs_trend` call sites updated to request a bounded page).
This ticket spans three modules because it is a thin, additive parameter/route threaded through
the existing pass-through chain (`dashboard-web` → `gateway-api` → `validation-service`) — matching
the shape `RAV-012` (`docs/tickets/RAV-012.md`) already took for the same reason. Splitting it into
three single-module tickets would break one atomic, ordered change into pieces that cannot be
tested independently (a validation-service-only ticket has nothing to bound against; a
dashboard-web-only ticket has nothing new to call) — kept as one ticket, implemented in the
dependency order below.

**Story**: `DBOPT-011`, `docs/product/backlog-db-optimization.md` (Must).
**Depends on**: `DBOPT-012` (the widened index — a performance dependency, not a correctness one:
this ticket's bounded/ordered query works correctly without it, just with an avoidable `Sort` node
at scale). Sequenced **second**. **Blocks** `RAV-016` only by file-overlap (same two
validation-service files, same `run_detail` handler) — not by data dependency; `RAV-016` must not
be dispatched concurrently with this ticket.
**Sprint**: 61 (`docs/sprints/sprint-61.md`).

## Analysis

`PostgresSplitResultRepository.get_splits`/`SQLiteSplitResultRepository.get_splits`
(`services/validation-service/src/app/repositories/{postgres,sqlite}_repository.py`) issue `SELECT
* FROM split_results WHERE run_id = :run_id AND tenant_id = :tenant_id ORDER BY split_index` with
**no `LIMIT`/`OFFSET` anywhere in the call chain** — confirmed by direct read: `routers/splits.py`'s
`GET /runs/{run_id}/splits` handler takes no pagination query params; `gateway-api`'s `get_splits`
proxy (`routers/runs.py:218`) forwards as-is; `dashboard-web`'s `run_detail` handler
(`routers/runs.py:1283-1294`) fetches the **full** response and only then caps what it renders at
`MAX_RENDERED_SPLITS = 500` (`routers/runs.py:1307-1309`) — the truncation is render-time only, the
full unbounded row set is always fetched, deserialized, and held in memory first. `runs_trend`
(`routers/runs.py:1176-1190`) compounds this: for every completed run in a selected
`(dataset_id, horizon)` group it issues its own full, unbounded `GET /runs/{id}/splits` call, with
no cap at all today (not even a render-time one).

**Binding constraint carried from the sprint plan, not optional**: `run_detail`'s existing
behavior renders the **most recent** `MAX_RENDERED_SPLITS` splits (`splits[-MAX_RENDERED_SPLITS:]`,
list-order tail, `routers/runs.py:1309`) and shows an accurate "N of M splits shown" notice when
truncated (`total_splits_count = len(splits)`, `routers/runs.py:1307-1308`,
`templates/run_detail.html`'s existing rendering of `splits_truncated`/`total_splits_count`). This
ticket's bounded fetch **must preserve both** — it must not silently flip to "first N" and must not
make the notice inaccurate or drop it.

## Design

**Design pattern**: Repository (implementation-plan.md section 7) — extends the existing
`SplitResultRepository` interface with one more bounded-read method pair, no new pattern
introduced. No Strategy/Factory/Observer applies here.

**DRY check note**: grepped `services/validation-service/src/app/repositories/interfaces.py` and
`services/dashboard-web/src/app/routers/runs.py` before writing this design. Validation-service
side: `ValidationRunRepository.list_runs`/`.count_runs` (VS-022) is the exact `limit`/`offset` +
companion-count-method precedent this ticket mirrors for `SplitResultRepository` — no new pattern
invented. Dashboard-web side: `run_detail`'s splits-fetch call site (`routers/runs.py:1283-1294`)
and `runs_trend`'s per-run splits-fetch call site (`routers/runs.py:1176-1190`) are two
near-identical blocks (call downstream → check transport failure → check 502/504 → parse JSON or
`[]`) that will become *more* similar once both need count-then-bounded-page logic — this is the
"extract on second duplication" case (implementation-plan.md section 9): a new shared private
helper, `_fetch_bounded_run_splits`, replaces both inline blocks. No existing helper in this file
does count-then-page composition today — this is genuinely new, not a duplicate of
`_fetch_run_splits_summary` (RAV-012's batched-summary call, a different endpoint/purpose entirely,
untouched by this ticket).

**Mechanism chosen (Tech Lead's call, per the sprint plan's explicit deferral on the "how")**: a
new companion `count_splits(tenant_id, run_id) -> int` repository method + `GET
/runs/{run_id}/splits/count` endpoint, mirroring `ValidationRunRepository.list_runs`/`.count_runs`'s
already-established pair **exactly** (same "one query returns the page, a separate cheap `count(*)`
query returns the true total" shape) — not a descending-order-fetch-and-reverse mechanism, and not
an envelope-shape change to `GET /runs/{run_id}/splits` itself. Rationale: (1) it is the mechanism
the sprint plan's own text names as an example ("a `count_splits` companion method mirroring
`ValidationRunRepository`'s already-established `list_runs`/`count_runs` pair"); (2) it keeps `GET
/runs/{run_id}/splits`'s `response_model=list[SplitResultResponse]` **completely unchanged** for
every caller, bounded or not — no conditional response shape, no `Union` response model, the
simplest possible backward-compatibility story; (3) `dashboard-web` computes `offset = max(0, total
- cap)` from the real total, then fetches exactly `cap` rows in existing ascending `split_index`
order starting at that offset — this reproduces `splits[-cap:]`'s exact tail selection without any
new ordering direction, no reversal logic anywhere.

### 1. `services/validation-service/src/app/repositories/interfaces.py`

Add one method to the existing `SplitResultRepository` `Protocol` (do not create a new protocol),
and extend `get_splits`' own signature with optional bounding params:

```python
def get_splits(
    self, tenant_id: str, run_id: str, limit: int | None = None, offset: int = 0
) -> list[SplitResultRecord]:
    """Returns splits ordered by split_index (VS-008 AC3) -- ordering is
    this method's responsibility, not the caller's. DBOPT-011: when
    `limit` is None (default), behavior is byte-identical to before this
    ticket -- the full, unbounded, ordered list. When `limit` is given,
    returns at most `limit` rows starting at `offset`, same ordering.
    """
    ...

def count_splits(self, tenant_id: str, run_id: str) -> int:
    """Total number of splits for this run (unpaginated) -- DBOPT-011,
    mirrors ValidationRunRepository.count_runs' role for GET /runs.
    """
    ...
```

### 2. `services/validation-service/src/app/repositories/{sqlite,postgres}_repository.py`

`SQLiteSplitResultRepository.get_splits`/`PostgresSplitResultRepository.get_splits`: add the same
two keyword parameters, defaulting to today's exact behavior:

```python
def get_splits(
    self, tenant_id: str, run_id: str, limit: int | None = None, offset: int = 0
) -> list[SplitResultRecord]:
    with Session(self._engine) as session:  # or _tenant_scoped_session for Postgres
        query = (
            select(SplitResult)
            .where(SplitResult.run_id == run_id, SplitResult.tenant_id == tenant_id)
            .order_by(SplitResult.split_index)
        )
        if limit is not None:
            query = query.offset(offset).limit(limit)
        rows = session.execute(query).scalars().all()
        return [_split_result_to_record(row) for row in rows]
```

`count_splits`, both implementations, mirroring `count_runs`'s exact shape:

```python
def count_splits(self, tenant_id: str, run_id: str) -> int:
    with Session(self._engine) as session:  # or _tenant_scoped_session for Postgres
        return session.execute(
            select(func.count())
            .select_from(SplitResult)
            .where(SplitResult.run_id == run_id, SplitResult.tenant_id == tenant_id)
        ).scalar_one()
```

No change to `add_splits`, `get_splits_for_runs`, or any other existing method — additive only.

### 3. `services/validation-service/src/app/routers/splits.py`

- `get_splits` handler gains optional query params, forwarded unmodified to the repository:
  ```python
  @router.get("/runs/{run_id}/splits", response_model=list[SplitResultResponse])
  def get_splits(
      run_id: str,
      run_repository: ValidationRunRepositoryDep,
      split_repository: SplitResultRepositoryDep,
      tenant: TenantContext = Depends(get_tenant_context),
      limit: int | None = Query(default=None, ge=1),
      offset: int = Query(default=0, ge=0),
  ) -> list[SplitResultResponse]:
      run = run_repository.get_run(tenant.tenant_id, run_id)
      if run is None:
          raise HTTPException(status_code=404, detail="run not found")
      splits = split_repository.get_splits(tenant.tenant_id, run_id, limit=limit, offset=offset)
      return [_split_result_to_response(split) for split in splits]
  ```
  Reuses the already-extracted `_split_result_to_response` helper (RAV-012) — no second mapping.
  **No response-shape change** — always a bare `list[SplitResultResponse]`, whether or not
  `limit`/`offset` are supplied; omitting them is byte-identical to today's behavior (binding AC).
- New route, same file (natural home — this file already owns every `split_results`-adjacent
  read):
  ```python
  class SplitCountResponse(BaseModel):
      """DBOPT-011: local envelope for GET /runs/{run_id}/splits/count -- a
      single scalar wrapped in an object (not a bare int), matching this
      router's existing "local envelope" convention (SplitPointsResponse,
      RunSplitsSummaryResponse) rather than a bare top-level int body.
      """
      total: int

  @router.get("/runs/{run_id}/splits/count", response_model=SplitCountResponse)
  def get_splits_count(
      run_id: str,
      run_repository: ValidationRunRepositoryDep,
      split_repository: SplitResultRepositoryDep,
      tenant: TenantContext = Depends(get_tenant_context),
  ) -> SplitCountResponse:
      run = run_repository.get_run(tenant.tenant_id, run_id)
      if run is None:
          raise HTTPException(status_code=404, detail="run not found")
      return SplitCountResponse(total=split_repository.count_splits(tenant.tenant_id, run_id))
  ```
  **Route collision check (do this before writing the route, don't assume)**: `/runs/{run_id}/
  splits/count` is 4 path segments (`runs`/`{run_id}`/`splits`/`count`). Distinct from
  `/runs/{run_id}/splits` (3 segments) and `/runs/{run_id}/splits/{split_index}/points` (5
  segments) by segment count alone. `RAV-016` (sequenced after this ticket) will add
  `/runs/{run_id}/splits/points`, also 4 segments — no collision with this route regardless of
  registration order since the literal 4th segment differs (`"count"` vs `"points"`), the same
  reasoning `RAV-012`'s `"summary"` vs `"splits"` collision check already used. State this
  explicitly in a code comment on the new route so `RAV-016`'s own dev agent doesn't have to
  re-derive it.

### 4. `services/gateway-api/src/app/routers/runs.py`

- `get_splits` proxy gains the same two optional params, forwarded unmodified:
  ```python
  @router.get("/runs/{run_id}/splits", response_model=list[SplitResultResponse])
  def get_splits(
      run_id: str,
      client: ValidationServiceClientDep,
      tenant: TenantContext = Depends(get_authenticated_tenant),
      limit: int | None = Query(default=None, ge=1),
      offset: int = Query(default=0, ge=0),
  ) -> list[SplitResultResponse]:
      headers = build_downstream_headers(tenant)
      params = {"offset": offset}
      if limit is not None:
          params["limit"] = limit
      response = _call_downstream(
          client.get, f"/runs/{run_id}/splits", params=params, headers=headers
      )
      _raise_for_error(response)
      return [SplitResultResponse(**item) for item in response.json()]
  ```
- New pass-through route mirroring `get_splits_summary`'s exact shape:
  ```python
  class SplitCountResponse(BaseModel):
      total: int

  @router.get("/runs/{run_id}/splits/count", response_model=SplitCountResponse)
  def get_splits_count(
      run_id: str,
      client: ValidationServiceClientDep,
      tenant: TenantContext = Depends(get_authenticated_tenant),
  ) -> SplitCountResponse:
      headers = build_downstream_headers(tenant)
      response = _call_downstream(client.get, f"/runs/{run_id}/splits/count", headers=headers)
      _raise_for_error(response)
      return SplitCountResponse(**response.json())
  ```
  No business logic reimplemented — pure forward, same as every other route in this file.

### 5. `services/dashboard-web/src/app/routers/runs.py`

New shared private helper (DRY, per the note above), placed near `_fetch_run_splits_summary`:

```python
def _fetch_bounded_run_splits(
    client: httpx.Client, headers: dict[str, str], run_id: str, cap: int
) -> tuple[list[SplitResultResponse], int, int | None]:
    """DBOPT-011: fetches at most `cap` of a run's most-recent-by-split-index
    splits via two bounded downstream calls (a cheap count, then a bounded
    page) instead of the full unbounded list this file used to fetch and
    then truncate client-side. Returns (splits, total_count, error_status):
    error_status is None on success; on a transport failure or 502/504 from
    either call, returns ([], 0, status) for the caller to render via
    `_render_error_for_status` -- this helper does NOT swallow failures the
    way `_fetch_run_splits_summary` (RAV-012) does, since both of this
    helper's call sites already treat a splits-fetch failure as
    page-blocking today; this preserves that existing stance rather than
    introducing a third failure-handling policy in this file.

    Tail-selection semantics (binding, DBOPT-011 AC): `offset = max(0,
    total - cap)` combined with ascending split_index order reproduces
    `splits[-cap:]`'s exact "most recent N" selection -- never "first N".
    When `total <= cap`, `offset` is 0 and every row is returned, matching
    today's unbounded behavior exactly.
    """
    count_response, count_transport_status = _call_downstream(
        client.get, f"/runs/{run_id}/splits/count", headers=headers
    )
    if count_transport_status is not None:
        return [], 0, count_transport_status
    if count_response.status_code in (502, 504):
        return [], 0, count_response.status_code
    total = count_response.json()["total"] if count_response.status_code == 200 else 0

    offset = max(0, total - cap)
    splits_response, splits_transport_status = _call_downstream(
        client.get,
        f"/runs/{run_id}/splits",
        headers=headers,
        params={"limit": cap, "offset": offset},
    )
    if splits_transport_status is not None:
        return [], 0, splits_transport_status
    if splits_response.status_code in (502, 504):
        return [], 0, splits_response.status_code
    splits = (
        [SplitResultResponse(**item) for item in splits_response.json()]
        if splits_response.status_code == 200
        else []
    )
    return splits, total, None
```

`run_detail` (`routers/runs.py:1283-1309`): replace the existing unbounded fetch + client-side
`splits[-MAX_RENDERED_SPLITS:]` truncation with:

```python
rendered_splits, total_splits_count, splits_error_status = _fetch_bounded_run_splits(
    client, headers, run_id, MAX_RENDERED_SPLITS
)
if splits_error_status is not None:
    return _render_error_for_status(request, splits_error_status)
splits_truncated = total_splits_count > MAX_RENDERED_SPLITS
```

Every downstream consumer of `rendered_splits`/`splits_truncated`/`total_splits_count` in the rest
of `run_detail` (the error/DM-verdict charts, the per-split table, `shareable_summary_text`,
`headline_verdict_summary`, the template context) is **unchanged** — this ticket only changes how
`rendered_splits` is obtained, never what it contains for a run under the cap (byte-identical) or
what it contains for a run over the cap (same tail rows as before, now fetched server-side-bounded
instead of over-fetched-then-truncated). **This ticket does not touch the separate per-split
points-fetch loop** (`routers/runs.py:1329-1344`) — that is `RAV-016`'s own call site, sequenced
after this ticket.

`runs_trend` (`routers/runs.py:1176-1190`): replace the per-run unbounded fetch inside the loop
with the same shared helper:

```python
for run in completed_runs:
    splits, _total, splits_error_status = _fetch_bounded_run_splits(
        client, headers, run.id, MAX_RENDERED_SPLITS
    )
    if splits_error_status is not None:
        return _render_error_for_status(request, splits_error_status)
    runs_with_splits.append((run, splits))
```

`runs_trend` has no "N of M" notice today (unlike `run_detail`) — the discarded `_total` reflects
that; bounding it to the same `MAX_RENDERED_SPLITS`-most-recent-splits-per-run cap is the sprint
plan's own explicit instruction (both `run_detail` and `runs_trend` are named as the two callers to
bound), applied for consistency with `run_detail`'s own established cap, not because `runs_trend`
previously had one.

## Implementation acceptance criteria

- [x] `SplitResultRepository.get_splits` gains optional `limit`/`offset` params (interface + both
      SQLite/Postgres implementations); omitting both is byte-identical to pre-ticket behavior.
- [x] `SplitResultRepository.count_splits` added (interface + both implementations), mirroring
      `count_runs`'s shape.
- [x] `GET /runs/{run_id}/splits` (validation-service, gateway-api) gains optional `limit`/`offset`
      query params, defaulting to unbounded — zero contract break for any caller that omits them.
- [x] `GET /runs/{run_id}/splits/count` added to validation-service (`splits.py`) and gateway-api
      (`runs.py`), registered such that no route collision with any existing or `RAV-016`-planned
      route occurs (see Design's collision check).
- [x] `run_detail` and `runs_trend` (dashboard-web) both call the new shared `_fetch_bounded_run_splits`
      helper instead of fetching the full unbounded list; no duplicate count-then-page logic
      written twice.
- [x] `run_detail`'s "most recent `MAX_RENDERED_SPLITS`" tail-selection semantics and its "N of M
      splits shown" notice accuracy are preserved exactly — verified against a fixture run
      exceeding the cap (Test AC below).
- [x] No change to `GET /runs/{run_id}/splits`'s existing response shape (still a bare
      `list[SplitResultResponse]`) for any caller, bounded or not.

## Test acceptance criteria

- [x] `validation-service`: unit test for `get_splits` — omitting `limit`/`offset` returns the full
      unbounded, ordered list (regression check against today's behavior); passing `limit`/`offset`
      returns the correctly bounded/ordered page (a fixture run with e.g. 10 splits, requesting
      `limit=3, offset=6` returns exactly splits 6-8 in ascending `split_index` order).
- [x] `validation-service`: unit test for `count_splits` — returns the correct total for a fixture
      run, `0` for a run with zero splits, and is unaffected by another tenant's splits on the same
      `run_id` value (if such a fixture is feasible) or at minimum is tenant-scoped the same way
      `get_splits` already is.
- [x] `validation-service`: route test for `GET /runs/{run_id}/splits/count` — correct `{"total":
      ...}` for a fixture run; `404` for a nonexistent/cross-tenant run, matching `get_splits`'s
      existing collapsed-404 stance; a regression-style assertion that this route does not get
      swallowed by any existing route pattern.
- [x] `validation-service`: route test for `GET /runs/{run_id}/splits` with `limit`/`offset` —
      correct bounded page; omitting both still returns the full list (regression).
- [x] `gateway-api`: pass-through tests (httpx.MockTransport) for both the new `limit`/`offset`
      forwarding on `get_splits` and the new `get_splits_count` proxy.
- [x] `dashboard-web`: **the sprint's own required test** — a fixture run with more splits than
      `MAX_RENDERED_SPLITS` results in `run_detail` calling the count endpoint once and the bounded
      splits endpoint once (not the old single unbounded call), asserted via a request-counting
      `httpx.MockTransport` handler; `rendered_splits` matches the same tail rows the old
      `splits[-MAX_RENDERED_SPLITS:]` logic would have produced from an equivalent full fixture;
      `splits_truncated`/`total_splits_count` render the same accurate "N of M" values as before
      this ticket for that fixture.
- [x] `dashboard-web`: a fixture run **under** the cap renders identically to pre-ticket behavior
      (no truncation notice, full split set rendered) — regression test.
- [x] `dashboard-web`: `runs_trend` test — a fixture group's completed runs each get their splits
      bounded to `MAX_RENDERED_SPLITS` via the shared helper (reuse, not a second implementation).
- [x] Full suite passes for all three touched services (validation-service, gateway-api,
      dashboard-web) — run and report exact pass counts, including any pre-existing unrelated
      failures already tracked in `docs/tickets/README.md` (e.g. the known
      `test_get_run_forwards_and_returns_full_detail_shape` gateway-api failure).

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read both repository implementations' `get_splits`/`count_splits` — confirm `limit=None`
      truly produces the identical SQL/behavior as before this ticket (no accidental `LIMIT NULL`
      or always-applied `.offset()`).
- [x] Read `_fetch_bounded_run_splits` and confirm it is used by **both** `run_detail` and
      `runs_trend` — no second, near-duplicate count-then-page block anywhere in this diff (grep
      the file for a second `/splits/count` call site).
- [x] Personally verify the tail-selection math (`offset = max(0, total - cap)`) against a
      concrete example (e.g. `total=550, cap=500` → `offset=50` → rows 50-549 in ascending order =
      the most recent 500) and confirm the dashboard-web test actually exercises a case where
      `total > cap`, not only the trivial `total <= cap` case.
- [x] Personally hit `GET /runs/{run_id}/splits/count` against a real (or test-client) app instance
      and confirm it resolves to the new handler, not swallowed by any existing route.
- [x] Run all three services' test suites personally and record exact pass/fail counts, comparing
      against the last known-good counts in `docs/tickets/README.md`'s Sprint 60 entry to confirm
      no new regressions were introduced by this ticket.
- [x] Run both `check_doc_sync.py` scripts (`libs/common` — no change expected here, but confirm;
      `services/validation-service` — must pick up the new `GET /runs/{run_id}/splits/count` route).

## Documentation acceptance criteria

- [x] `services/validation-service/README.md`: add `- \`GET /runs/{run_id}/splits/count\`` to the
      machine-checked "## Routes" list, plus a prose paragraph (same style as the `GET
      /runs/{id}/splits` entry) describing the new `limit`/`offset` params on `GET
      /runs/{run_id}/splits` (unbounded-by-default, backward-compatible) and the new count route's
      contract/tenant-scoping/404 behavior.
- [x] `services/gateway-api/README.md`: document both the new `limit`/`offset` pass-through on `GET
      /runs/{run_id}/splits` and the new `GET /runs/{run_id}/splits/count` pass-through route,
      matching the existing entries' style.
- [x] `services/dashboard-web/README.md`: update the "Run detail page: rendered-split cap for
      oversized runs (DASH-119)" section (and the "Runs list pagination (UAT-009)"/`runs_trend`
      section if it separately documents that handler) to record that `run_detail`/`runs_trend` now
      fetch a server-side-bounded page via `_fetch_bounded_run_splits` (count + bounded page)
      instead of fetching the full unbounded list and truncating client-side, citing `DBOPT-011`.
