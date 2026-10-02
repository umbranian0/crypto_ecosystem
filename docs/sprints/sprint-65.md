# Sprint 65 — Epic D: RPT-002 + RPT-004 (`services/reporting-service`, `services/gateway-api`, shared lib extraction)

Sprint goal: by the end of this sprint, a tenant can archive a point-in-time cross-run consistency snapshot as a stored
audit report, and (if the user keeps RPT-004) can ask the API for a field-level diff of two stored validation-audit
reports of comparable runs, without any new capability implying prediction or trading value.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md`, Epic D, `RPT-002` and `RPT-004` (both Could, already
approved/prioritized; the requester asked to proceed with both).
Capacity: not stated by the requester; no capacity claim made.

## Independent verification (code read, not taken from the backlog)

- **Neither story is done.** `reporting-service` `get_report_renderer` knows only `"validation_audit"`;
  `POST /reports/generate` takes only `run_id`; there is no `/diff` route anywhere. The `kind` column exists
  (`reports.report_kind`) but is only ever written as `validation_audit`.
- **Reporting-service today:** `app/generation.py` (fetch run + splits from validation-service with `X-Tenant-Id`,
  render, persist), Factory in `renderers/factory.py`, `GET /reports/{id}` (JSON, `?format=pdf` from RPT-001),
  `reports` table with `run_id` **NOT NULL** and `content` = rendered HTML only (no structured metrics stored).
- **Gateway-api:** `routers/reports.py` proxies `POST /reports/generate` (body is a field-for-field copy of
  `{run_id}` only) and `GET /reports/{id}` (+ pdf pass-through). No list-reports endpoint exists in either service.
- **Dashboard-web:** has **no tenant report viewer**. The only report touchpoint is the operator monitoring page
  trigger (`POST /monitoring/reports/generate`, `run_id` only). The consistency trend itself is live at
  `GET /runs/trend` (RAV-009/010).
- **Where "beat Naive0 in N of M runs" lives:** `dashboard-web/src/app/charting.py` (`_verdict_category`,
  `_run_beats_naive0`, `compute_consistency_indicator`). A service cannot import another service, so
  `reporting-service` cannot reuse it as it stands. The backlog AC forbids a second implementation of that rule.
  **Consequence (disclosed, the real cost of RPT-002):** the pure rule must move into a `libs/` package
  (`naive_first_common` is the existing shared lib) and `dashboard-web` must import it from there, with its behavior
  and tests unchanged. Tech Lead decides the exact module.
- **Reads-through-which-contract:** the backlog says reporting reads "via `gateway-api`'s `GET /runs`". The existing
  reporting-service pattern calls `validation-service` directly (tenant via `X-Tenant-Id`); the gateway endpoint is
  just a proxy of that same `GET /runs` / splits contract. Honoring the AC's intent (no independent aggregation) means
  reusing validation-service's run list + splits contract, not going through the public gateway. Disclosed
  interpretation; Tech Lead confirms.
- **Test-DB safety (found while reading):** `reporting-service/tests/test_postgres_repository.py`,
  `validation-service/tests/test_postgres_repository.py` and most `validation-service`/`ingestion-service` migration
  tests hard-code `.../5432/naive_first` (the live DB). Only `gateway-api` was repointed to `naive_first_test` in
  Sprint 64. `reporting-service` is touched this sprint, so running its suite as-is is the same wipe hazard that
  destroyed `operator_audit_log`. See Binding constraints.

## YAGNI assessment (explicit recommendations)

**RPT-002 — build, narrowed.** It has the cheaper path and a real honest-framing payoff (an archived snapshot of the
"no stable win over Naive0" evidence). Still no pilot has asked, so the slice is the minimum:
- In: new `kind` `"consistency_trend"` (Factory branch + one renderer), optional `kind` (default `validation_audit`,
  backward compatible) on `POST /reports/generate` in reporting-service and the gateway proxy model, scoped by
  `dataset_id` + `horizon` (the same grouping `/runs/trend` uses), HTML only, rule extracted to the shared lib.
- Out (YAGNI): dashboard-web UI for it (no report viewer exists; adding a button that yields an id with nowhere to
  view it is gold-plating; RPT-001 shipped API-only on the same logic), PDF for this kind, scheduling/digests, list
  or search of reports, any chart in the artifact beyond the "N of M" count plus per-run verdict rows.
- Open storage question for the Tech Lead (not a user decision): `reports.run_id` is NOT NULL and a trend report has
  no single run. Choose the least invasive honest option (e.g. a migration making it nullable plus storing the
  `dataset_id`/`horizon` scope, versus a documented scope-key convention in the existing column). A migration, if
  chosen, is additive and must be reviewed for existing rows and RLS.

**RPT-004 — recommend DROP (defer until a real re-audit request).** The backlog itself calls it the heaviest and
lowest-leverage story, its third AC depends on a dashboard report viewer that does not exist and is scoped nowhere,
and no one has reported a re-audit use case. Additional finding: reports store rendered HTML only, so a field-level
diff cannot read stored report content; it must re-fetch each report's two runs from validation-service by
`run_id`, which makes this a run diff dressed as a report diff. Because the requester asked to proceed, the default
is the narrowest honest slice, scheduled last and droppable without affecting RPT-002:
- In: reporting-service `GET /reports/{id}/diff/{other_id}` (Tech Lead may rename), field-level diff of per-split
  `model_*`/`naive0_*`/`dm_*` values for two `validation_audit` reports of the caller's tenant, a stated and tested
  comparability rule (at minimum: both `validation_audit`, same `dataset_id` and `horizon`, same split config so
  per-split alignment is meaningful; otherwise 422 with a plain reason), cross-tenant/unknown id returns the same
  generic 404 as `GET /reports/{id}`, gateway pass-through of the same path.
- Out, **explicitly unmet AC, disclosed:** AC3 (dashboard-web "compare with a previous report" action). It is
  blocked on a report viewer that does not exist; it is not built and the backlog entry must say so plainly.
  Also out: a diff of rendered HTML, a diff UI, diffing consistency-trend reports, summary/"improvement" scoring.
- Positioning rule for the diff output: report neutral field deltas and, if any summary exists, only whether the
  per-split Naive0 comparison verdicts changed. No "improved/better model" language; a smaller error is not an
  economic or predictive claim.

## Stories in scope, in execution order

1. **Test-DB safety chore (prerequisite, not a backlog story).** Repoint `reporting-service` Postgres tests (and
   their alembic subprocess `DATABASE_URL`) at `naive_first_test`, following the gateway-api pattern. Why first:
   nothing else in this sprint may run the reporting suite until this is true.
2. **RPT-002** — a. extract the consistency rule from `dashboard-web/charting.py` into `libs/` (dashboard-web
   imports it; its tests unchanged and green); b. `reporting-service` renderer + Factory branch + optional `kind` and
   scope fields on `POST /reports/generate` + generation function reading validation-service's run list/splits;
   c. gateway proxy model accepts the same optional fields; d. docs. Why before RPT-004: it carries the shared-lib
   extraction and the `generate`/gateway model changes, and RPT-004 touches the same two services' routers.
3. **RPT-004 (recommended drop, narrowest slice if kept)** — reporting-service diff endpoint + comparability rule,
   gateway pass-through, docs. Why last: lowest value, no dependency on RPT-002, safe to cut without rework. If the
   user drops it, the sprint is RPT-002 alone and the sprint goal's second clause is removed.

Order is by dependency/shared-file contention, not priority (both are Could; no reordering of priority occurs).

## Binding constraints carried into tickets

- **No test run may touch the live database.** The Tech Lead must confirm, per touched module (reporting-service,
  gateway-api, dashboard-web, and whichever `libs/` package receives the extraction), that every Postgres-backed
  test targets a test DB (`naive_first_test`) and not `naive_first`, including alembic subprocesses and role/RLS
  fixtures; record the confirmation in the ticket. Untouched modules that still hard-code `naive_first`
  (`validation-service`, `ingestion-service` Postgres/migration tests) must not be run in this sprint's regression
  until repointed; a mechanical repoint is allowed as an additive chore ticket, but is not required. Confirm the
  test DB has the schemas/roles those tests need before relying on it.
- Naive-first, honest framing: the consistency artifact states "beat Naive0 in N of M completed runs" using the
  existing documented rule (undefined splits excluded, `has_data=false` renders "no completed runs", never "0 of 0"),
  carries the platform's audit disclaimer, and never states or implies prediction, signal, or economic value.
  Statistical accuracy is not economic value.
- One implementation of the consistency rule, in a shared lib; no copy in reporting-service.
- Overlapping-horizon significance claims keep the existing Harvey-adjusted DM values; neither story recomputes DM.
- No service imports another service; tenant scope only from authenticated context; the Factory stays the only
  `kind` dispatch (no inferred kind, no new mechanism).
- Backward compatibility: `POST /reports/generate` with only `run_id` behaves byte-identically; existing
  `GET /reports/{id}` and `?format=pdf` unchanged.

## Stories explicitly deferred

- RPT-004 AC3 (dashboard-web compare action): blocked on a nonexistent report viewer; not scoped by any backlog story.
- Dashboard-web surface for archiving the trend snapshot, PDF for `consistency_trend`, report listing/search:
  not in AC, YAGNI.
- Sprint 62 matview-lag copy follow-up, `DBOPT-*` follow-ups, other open Epic A/B/D stories: not pulled in.

## Definition of done

- RPT-002 acceptance criteria checked in `docs/tickets/` ticket(s); RPT-004 (if kept) criteria checked with AC3
  recorded as not built and why; backlog entries updated in place, including the disclosed interpretation of "reads
  through the same contract" and the shared-lib extraction.
- Tests: reporting-service, gateway-api, dashboard-web and the shared-lib suites green, run only against the test
  DB. Covered: Factory returns the new renderer and still rejects unknown kinds; default `kind` unchanged; trend
  report counts equal dashboard-web's `compute_consistency_indicator` on the same fixture (single implementation);
  empty/no-evaluable-run renders the no-data state; tenant isolation; diff comparability rejects (different horizon,
  dataset, split config, non-audit kind) and 404 cross-tenant; positioning grep over all new copy.
- Docs as part of the work: `services/reporting-service/README.md`, `services/gateway-api/README.md`,
  `services/dashboard-web/README.md` (note the import from the shared lib), the shared lib README, `docs/tickets/README.md`
  Sprint 65 section, backlog statuses.
- QA gate (mandatory): Tech Lead raises the `qa` agent (`/qa-validation`) after tickets are done, against the real
  rebuilt `naive-first-*` containers (confirm images are not stale; no host-run scripts, which hit a stale SQLite
  copy): generate a `consistency_trend` report for a QA dataset/horizon via the gateway, retrieve it by id, and check
  its N of M matches `/runs/trend` for the same group; a legacy `{run_id}` generate still works; (if RPT-004 kept)
  diff two QA runs, plus an incomparable pair (422) and a cross-tenant id (404). QA fixtures additive only, named
  "QA65 ...", left in place, never touching or deleting existing data or audit-log rows; use a fresh QA tenant.

## Next (not this sprint)

Dashboard report viewer (prerequisite for any report UI, including RPT-004 AC3), PDF for `consistency_trend`,
Sprint 62 matview-lag copy follow-up.
