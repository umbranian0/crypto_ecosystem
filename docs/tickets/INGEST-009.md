# INGEST-009 (revised) — `GET /datasets`, `GET /datasets/{source}/series`: tenant-scoped dataset API

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: done. **Priority**: Must.
**Depends on**: `INGEST-002`, `INGEST-003`, `INGEST-007`. **Blocks**: `GW-020`, `VS-023`.
**Can run in parallel with**: `INGEST-008` (separate router file).

## Analysis
Story: backlog `INGEST-009`, **superseded** by `docs/solution-design.md` section 8.1/8.3 and
`docs/adr/0005-dataset-is-a-continuous-tenant-source-table.md`: a dataset is `{tenant_id, source}`, a
continuous table, not a static per-id snapshot. `GET /datasets/{id}` (static lookup) is replaced by
`GET /datasets/{source}/series?start=&end=&field=`. This ticket implements the endpoint from the ADR,
not the backlog's original sketch.

## Design
Pattern: Repository (query methods on `INGEST-003`'s repository or a sibling read-repository), no new
pattern. File: new `services/ingestion-service/src/app/routers/datasets.py`. **DRY check**: reuses
`INGEST-002`'s existing PK index (`tenant_id, source, event_time`) — no new secondary index invented.

## Implementation acceptance criteria
- [x] `GET /datasets` (tenant-authenticated): one entry per distinct `(source, tenant_id)` present in
  the ingestion tables — `source`, `earliest_timestamp`, `latest_timestamp`, `row_count`. Empty-history
  tenant → `200 {"items": []}`, never `404`.
- [x] `GET /datasets/{source}/series?start=&end=&field=` (tenant-authenticated): `start`/`end` ISO-8601,
  both optional (omitted `start` = earliest row, omitted `end` = latest row — same code path, not a
  special case). Returns `{"timestamps": [...], "values": [...]}`.
- [x] `field` query param selects the value column for multi-column sources. Documented defaults:
  `close` for `price_ohlcv`, `value` for `onchain_metric`, `reddit_sid_com` for `sentiment_score` —
  **flagged for product confirmation** per solution-design.md 8.11 open question #2, implemented as the
  working default in the meantime.
- [x] Cross-tenant / nonexistent `source` both return `404` (collapsed, same convention as
  `validation-service`'s `GET /runs/{id}`).
- [x] `GET /connectors/{source}/status` (tenant-authenticated): last `crawl_runs` row for that source —
  feeds the (currently blocked) `DASH-109` panel; built here since it's the same read-repository, cheap
  to include, and unblocks `DASH-109` the moment its own sibling-backlog dependency lands.

## Test acceptance criteria
- [x] Empty-tenant listing, multi-field selection, cross-tenant `404` collapsing.
- [x] `start`/`end` omitted-both, omitted-one, both-present cases.

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms the `{id}` static-lookup shape from the original backlog sketch does NOT exist anywhere in
  this diff — only the `{source}/series` range endpoint.
- Confirms `field` defaults are documented in the README, not silently chosen with no trace.

## Documentation acceptance criteria
- [x] `services/ingestion-service/README.md` documents all new routes and the `field` default table,
  linking ADR-0005 for the dataset-semantics rationale.
