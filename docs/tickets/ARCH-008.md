# ARCH-008 — Document the Security()/APIKeyHeader auth pattern as the required shape

**Status: done**

## Analysis
Story: ARCH-008 (Should, `docs/product/backlog-technical-upgrades.md`), no dependency. Deferred
since Sprint 06 (added 2026-08-09), re-confirmed unchanged in Sprints 07/08/09. Constraining
evidence (backlog, cited directly, and independently re-confirmed by the Tech Lead reading
`services/gateway-api/src/app/dependencies/auth.py` directly this sprint): `get_authenticated_tenant`
was rewritten 2026-08-09 from bare `Header()` params to `Security(_authorization_scheme)` /
`Security(_x_api_key_scheme)` (`fastapi.security.APIKeyHeader` instances), purely so FastAPI
registers `securitySchemes` in the OpenAPI doc and Swagger UI shows one top-level "Authorize" dialog
instead of per-endpoint header re-entry. This rewrite already has an accurate, detailed docstring in
`auth.py` itself (lines 13-20 of that file) explaining the *why* -- but per the backlog's own
evidence, "this change has no ticket and ... had no backlog record at all until now," and critically,
`services/gateway-api/README.md`'s own Authentication (GW-006) section (read directly this sprint)
still describes only the resulting header contract (`Authorization: Bearer <key>` /
`X-Api-Key: <key>`) without stating the `Security()`/`APIKeyHeader` mechanism as a *required pattern*
for any future authenticated route -- that's the actual gap this ticket closes: not the code's own
docstring (already fine), but the README's silence on making this the standard for future routers.

## Design
No new design pattern -- this documents an already-implemented pattern as the required shape for
future work. File touched: `services/gateway-api/README.md`'s existing "Authentication (GW-006)"
section (extend, don't duplicate elsewhere in the file). No code changes -- `auth.py`'s own
docstring already documents the mechanism accurately (confirmed by reading it directly); this ticket
is about making the README state it as a forward-looking *requirement* for any future authenticated
router, not merely describing what GW-006 happens to do.

DRY check: grep `services/gateway-api/README.md` for existing `Security()`/`APIKeyHeader` mentions --
none exist yet in the README (only in `auth.py`'s own docstring, a different file). This is new
README content, not a rewrite of existing README text describing the same thing twice.

## Implementation acceptance criteria
- [x] `services/gateway-api/README.md`'s Authentication section is extended with an explicit note:
  any future header-based auth dependency in this service must use `Security()` +
  a `fastapi.security` class (e.g. `APIKeyHeader`), not bare `Header()`, so it participates in the
  same global Swagger "Authorize" UX GW-006 already established -- citing the existing
  `_authorization_scheme`/`_x_api_key_scheme` (`APIKeyHeader`) instances in `auth.py` as the
  reference implementation.
- [x] The note explicitly states `_extract_raw_key`'s parsing/validation logic stays the single
  place format-checking happens regardless of which FastAPI mechanism supplies the raw header
  string -- i.e. `Security()`/`APIKeyHeader` is only responsible for *sourcing* the header value for
  OpenAPI registration purposes, not for validating its shape.
- [x] Zero files under `services/gateway-api/src/` are modified by this ticket -- confirmed via
  `git status` scoped to that path after the ticket is done (the existing `Security()`/`APIKeyHeader`
  code and `auth.py`'s own docstring are cited as evidence, not changed).

## Test acceptance criteria
- [x] The dev agent re-runs `services/gateway-api`'s existing `tests/test_auth.py` (11 cases, per
  the backlog's own evidence) and confirms it still passes unmodified, as a sanity check that this
  ticket touched no auth behavior -- this is not new test-writing, it is confirming no regression
  was introduced by a documentation-only change.

## Review acceptance criteria
- Tech Lead personally confirms: (a) the README note is genuinely forward-looking ("any future
  authenticated router must...") and not merely a restatement of what GW-006 already does; (b) `git
  status` scoped to `services/gateway-api/src/` shows zero changes; (c) `tests/test_auth.py`'s 11
  cases still pass, re-run directly by the Tech Lead, not merely trusted from the dev agent's report.

## Documentation acceptance criteria
- [x] `services/gateway-api/README.md`'s Authentication section carries the new required-pattern
  note.
- [x] `docs/tickets/README.md`'s `services/gateway-api (GW-*)` section (or the shared ARCH-* Sprint
  10 entry alongside ARCH-007) gains an `ARCH-008` row, status `done` once verified.


## Outcome
Implemented by dev agent, 2026-08-12.

- **README change**: `services/gateway-api/README.md`'s Authentication (GW-006) section gained a
  new bullet, "Required pattern for any future header-based auth dependency (ARCH-008)", immediately
  after the existing 401-conditions bullet. It states, forward-looking: any future header-based auth
  dependency in this service must use `Security()` + a `fastapi.security` class (e.g.
  `APIKeyHeader`), never bare `Header()`, citing `auth.py`'s `_authorization_scheme`/
  `_x_api_key_scheme` as the reference implementation; and that `_extract_raw_key` remains the
  single place format-checking happens regardless of which FastAPI mechanism supplies the raw header
  string -- `Security()`/`APIKeyHeader` only sources the value for OpenAPI registration, it does
  not validate shape.
- **No other files touched.** `docs/tickets/README.md` was deliberately left untouched per this
  ticket's own instruction (Tech Lead handles that index update after ARCH-007 and ARCH-008 both land).
- **git status scoped to `services/gateway-api/src/`**: identical before and after this ticket's
  edits -- 4 pre-existing modified files (`auth.py`, `dependencies/repositories.py`, `main.py`,
  `repositories/postgres_repository.py`) from a prior session, untouched and unreverted by this
  ticket. Zero new changes added under that path.
- **Test result**: `services/gateway-api`, `.venv\\Scripts\\python.exe -m pytest tests/test_auth.py -q`
  -> `11 passed, 1 warning in 0.17s` (the warning is an unrelated pre-existing
  `StarletteDeprecationWarning` about `httpx`/`starlette.testclient`, not introduced by this
  ticket).

All Implementation, Test, and Documentation acceptance criteria above are checked off. Review
acceptance criteria are left for the Tech Lead per this ticket's own process (Status intentionally
set to `in-review`, not `done`).


## Tech Lead review (verified independently, not trusted from the dev agent's report)

(a) README note confirmed genuinely forward-looking: it reads "any future header-based auth
dependency added to this service must source its header value(s) via Security() + a
fastapi.security class... never bare Header()" -- not a restatement of what GW-006 currently does,
a requirement for future work, citing _authorization_scheme/_x_api_key_scheme as the reference
implementation and confirming _extract_raw_key stays the single format-checking place regardless of
sourcing mechanism.

(b) git status --porcelain -- services/gateway-api/src/ re-run directly by the Tech Lead: identical
4 pre-existing modified files (auth.py, dependencies/repositories.py, main.py,
postgres_repository.py) from before this sprint began -- zero new changes from this ticket.

(c) tests/test_auth.py re-run directly by the Tech Lead: 11 passed, 1 warning (pre-existing,
unrelated StarletteDeprecationWarning) in 0.13s.

Ticket-index row added together with ARCH-007's row in one pass (see docs/tickets/README.md).