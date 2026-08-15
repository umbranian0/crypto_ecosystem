# ECON-004 — Mocked upstream integration only

**Status: done** — implemented by dev agent, interrupted mid-task (session usage limit) before the ticket file/README documentation steps landed; code and tests were complete and correct. Tech Lead completed the Documentation acceptance criteria (this file, README's new "Upstream integration (ECON-004)" section) and, on independent re-verification, found and fixed two real test-authoring bugs the dev agent never got to self-check (see Outcome).

## Analysis
Story: ECON-004 (Must), `docs/product/backlog-economic-service.md`. Depends on: ECON-001 (done), ECON-003 (needs `UpstreamValidationResult`). Covers backlog ECON-004's acceptance criteria in full. Constraining docs: this is a **hard architectural rule for this backlog, not a temporary stub** (sprint-13.md's own repeated instruction) — no `httpx` call to `validation-service`'s real base URL anywhere in this ticket's code, no `VALIDATION_SERVICE_URL`-style env var read anywhere. If you find yourself importing `httpx` or reading any `*_URL` env var pointed at `validation-service`, stop — that is out of scope for this ticket and this entire sprint.

**Why this matters (read before implementing, not just for the README)**: per the backlog's own override note, `validation-service` has never produced a real "client model beat naive" result — `VS-017` (client-supplied prediction baseline) is deferred, unbuilt. There is nothing real to integrate against yet. Mocking is not a placeholder for "later, once we get around to it" — it is the thing that makes this entire sprint ethically defensible per CLAUDE.md and da-tese-ao-produto.md section 2.7.

**DRY check (performed before writing this ticket)**: no existing upstream-client abstraction exists anywhere in `economic-service` yet (ECON-001/002/003 don't touch this). `naive_first_common`'s existing modules (`tenant_context.py`, `db.py`, `contracts.py`, `testing.py`) were checked — none define an upstream-HTTP-client interface, so there is nothing to reuse from `libs/common` here; this is new to `economic-service` and stays local (it doesn't call any other service for real, so nothing here is a cross-service concern that would justify a `libs/*` promotion).

## Design
**Pattern**: this is the seam the Strategy/DI patterns exist for (implementation-plan.md section 7's DI row) — a `UpstreamValidationResultClient` interface with exactly one implementation wired into DI (`MockValidationResultClient`), matching FastAPI's `Depends()` mechanism already used throughout every other service.

Files touched (`services/economic-service/` only):
- `src/app/upstream_client.py` — `UpstreamValidationResultClient` `typing.Protocol` (one method, e.g. `get_result(tenant_id: str, validation_run_id: str) -> UpstreamValidationResult`, importing `UpstreamValidationResult` from `app.contracts`, not redefining it) and `MockValidationResultClient`, the sole implementation, returning hardcoded fixture data with `source="mock_fixture"` always, never `"live"`.
- `src/app/dependencies/upstream.py` (or added to `dependencies/repositories.py` — implementer's choice, document which) — the DI provider (`get_upstream_client`) wiring `MockValidationResultClient` as the only implementation.
- `tests/test_upstream_client.py`.

The fixture module's docstring and the returned object's own repr must make it unambiguous the data is fabricated — `source: Literal["mock_fixture"]` (never `"live"`) is exactly the field ECON-005's gate checks to refuse it; the docstring should say this explicitly so a future reader understands the field's purpose, not just its type.

## Implementation acceptance criteria
- [x] `MockValidationResultClient` implements the `UpstreamValidationResultClient` interface ECON-005 depends on, returning hardcoded fixture data, never an `httpx` call to `validation-service`'s real base URL. No `VALIDATION_SERVICE_URL`-style env var is read or wired to a real network call anywhere in this ticket's code (grep-confirmed by Tech Lead across the whole `src/app/` tree, not just this ticket's own file: zero real `httpx` import, zero real `*_URL` env var read — the only textual matches are inside docstrings explaining the rule in prose).
- [x] The fixture module's docstring and the returned object's own `source: Literal["mock_fixture"]` field, plus a custom `__repr__` (`"MockValidationResultClient(source='mock_fixture', fabricated=True, ...)"`), make it unambiguous the data is fabricated.
- [x] `README.md` states the fact confirmed in the backlog's override note and the hard rule for future tickets — confirmed current (already present from ECON-001) and a new "Upstream integration (ECON-004)" section added, cross-linking `MockValidationResultClient`/`UpstreamValidationResultClient` by name.

## Test acceptance criteria
- [x] A test asserting `MockValidationResultClient` is the *only* thing implementing `UpstreamValidationResultClient` anywhere in this codebase's DI wiring — AST-based, parses every file under `src/app/`, finds every class with a real (non-stub) `get_result` method, asserts the set has exactly one member, and separately asserts the real `Depends(get_upstream_client)` default returns an instance of exactly that class.
- [x] A test asserting `MockValidationResultClient.get_result(...)`'s returned `UpstreamValidationResult.source` is always `"mock_fixture"`, never `"live"`, across two different call arguments.
- [x] `.venv\Scripts\python.exe -m pytest -q` passes with zero failures, no regression on prior tickets' tests (**39 passed**, confirmed by Tech Lead, after the two test-bug fixes below).

## Review acceptance criteria
- Tech Lead personally grepped `src/app/` for `httpx` and for `_URL`, confirmed zero real matches pointed at `validation-service` — both textual hits are inside docstring prose explaining the rule, not code (`contracts.py` line 43, `upstream_client.py` line 10).
- Tech Lead read `dependencies/upstream.py` directly and confirmed `MockValidationResultClient` is the only class ever returned by `get_upstream_client()` — a plain, unconditional return, no branch, no env-var switch.

## Documentation acceptance criteria
- [x] `README.md`'s existing override-disclosure section (from ECON-001) confirmed current; new "Upstream integration (ECON-004)" section added, cross-linking `MockValidationResultClient`/`UpstreamValidationResultClient` by name and restating the hard mock-only rule.

## Sequencing note
Depends on ECON-001 and ECON-003 (not ECON-002) — sequenced after both prior branches land, per sprint-13.md's own decision, even though it only strictly needs ECON-003.

## Outcome

**Files created**: `src/app/upstream_client.py` (`UpstreamValidationResultClient` Protocol + `MockValidationResultClient`), `src/app/dependencies/upstream.py` (kept as its own module, separate from `dependencies/repositories.py`, since the mock client has no DB/Engine dependency at all — documented choice), `tests/test_upstream_client.py`. **Files modified**: `README.md` (new "Upstream integration (ECON-004)" section, by Tech Lead).

**Two real bugs found and fixed by the Tech Lead on independent re-verification** (the dev agent was interrupted by a session usage limit before running its own final self-check, so these were never caught before this review):
1. `test_mock_client_is_the_only_di_wired_implementation`'s AST walk originally flagged *any* class with a method named `get_result`, which incorrectly counted the `UpstreamValidationResultClient` Protocol's own stub-bodied (`...`) method signature as a second "implementer." Fixed by adding `_is_protocol_stub_body()`, which distinguishes a Protocol's stub declaration (body is just `...`) from a real implementation (a body that actually returns something) — the Protocol interface declares the contract, it does not implement it, and is now correctly excluded from the implementer count.
2. `test_upstream_client_module_has_no_httpx_import_and_no_url_env_var_read`'s raw `"_URL" not in source` check matched against the module's own docstring, which explains the hard rule in prose using the literal text `*_URL`-style — a false positive on documentation, not code. Fixed by stripping triple-quoted docstrings before the substring check (`re.sub(r'"""[\s\S]*?"""', "", source)`); the stronger, already-present `"os" not in imported_roots` check (env var reads are structurally impossible without importing `os`) is unchanged and is the real guarantee here.

Neither bug indicated an actual violation of ECON-004's constraint — both were confirmed, before and after the fix, via a from-scratch grep of the real `src/app/` tree by the Tech Lead directly.

**Test run**: `.venv\Scripts\python.exe -m pytest -q` from `services/economic-service/` — **39 passed**, 0 failed (33 pre-existing ECON-001/002/003 tests + 6 new ECON-004 tests, after the 2 test-bug fixes above; before the fixes, 2 of those 6 failed).
