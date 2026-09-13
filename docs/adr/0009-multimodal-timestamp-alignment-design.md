---
status: accepted
---

# Multimodal timestamp alignment: target-series index is authoritative, sources aligned via lag-aware forward-fill using `fetched_at` never a nominal timestamp, missing-timestamp policy is a required per-run config choice, alignment happens strictly before `generate_splits`

`docs/product/backlog-multimodal-dataset-fusion.md` (MDF-002) asks for a documented alignment strategy
combining series sampled at different frequencies into one row-aligned table, because
`naive_first_engine`'s splitter assumes one coherent `DatetimeIndex` and every existing connector
samples on its own schedule. Depends on MDF-001 (`docs/adr/0008-multimodal-fusion-architecture-and-
leakage-posture.md`), which placed the join inside `validation-service` and documented each connector's
lag/revision posture. This is a decision-work ticket only — no join code is written by this ADR, per
`docs/sprints/sprint-31.md`'s scope.

## Per-source-pair resampling/alignment rule

**Rule: for every non-target feature source, forward-fill the last value whose `fetched_at` (never its
own nominal metric timestamp) is `<= row_timestamp - source_lag`, where `source_lag` is that connector's
documented minimum safe purge-gap/alignment buffer from ADR-0008 (b).** Never interpolate using a
future-dated value, and never use a value's nominal timestamp as a stand-in for when it became knowable
— this generalizes ADR-0008's sentiment-specific finding ("a sentiment row must be aligned using
`fetched_at`, never `created_utc`") to every source, since the on-chain connector shares the identical
risk shape (a nominal timestamp that does not prove availability).

Concretely, per source-pair (target = the price/return series being validated, always the row-timestamp
driver — see "authoritative clock" below):

- **Price feature onto price target** (same connector, e.g. combining `binance_price_btcusdt_1h` as
  both target and, hypothetically, a differently-lagged price field as a feature): zero additional lag
  beyond the run's own `purge_gap_hours`, per ADR-0008 — same-index alignment, no resampling needed.
- **On-chain feature (`blockchain_info_hash-rate`/`blockchain_info_n-unique-addresses`) onto a
  higher-frequency target**: forward-fill the most recent on-chain row whose `fetched_at <=
  row_timestamp - 24h` (ADR-0008's conservative floor) onto every target-index row. A target row earlier
  than the first eligible on-chain `fetched_at` has no valid feature value yet (see missing-timestamp
  policy below).
- **Sentiment feature (`reddit_vader_sentiment`) onto a higher-frequency target**: forward-fill the most
  recent sentiment row whose `fetched_at <= row_timestamp` (sentiment's own alignment buffer is baked
  into using `fetched_at` directly rather than `created_utc` — no separate additive buffer beyond that
  substitution, since `fetched_at` already is the "known-at" instant, unlike the on-chain case where even
  `fetched_at` is not guaranteed final).

## Missing-timestamp policy: required per-run config, no silent default

**A run assembling a multi-source feature set must supply an explicit `missing_timestamp_policy` field
— `"drop_row"`, `"forward_fill_exhausted_as_null_then_drop"`, or `"exclude_source"` — as part of its
request; there is no default, and a request with feature references but no policy is rejected (`422`),
matching this repo's existing "no silent inference" convention** (`DatasetSourceError`'s hard-fail
posture in `dataset_source.py`; DH-003's "no auto-resolution of any kind... which of two contradictory
readings is correct is a judgment call this platform declines to make silently" reasoning applies
identically to "which policy resolves a missing alignment row"). This is required so two runs' results
are comparable when they use different policies — a `"drop_row"` run and an `"exclude_source"` run over
the same nominal date range can have different effective sample counts, and that must be visible on the
run record, not silently absorbed.

- `"drop_row"`: a target-index row with no eligible value for a requested feature source (before that
  source's first eligible `fetched_at`, or after gaps) is dropped from the assembled table entirely.
- `"forward_fill_exhausted_as_null_then_drop"`: forward-fill as far as data allows; rows still null after
  fill are dropped (equivalent to `"drop_row"` restricted to the genuinely-unfillable leading window —
  named separately so the run record can distinguish "no data existed yet" from "a later gap was
  bridged by forward-fill").
- `"exclude_source"`: the offending source's column is dropped for the *entire* run rather than dropping
  individual rows — used when a tenant would rather validate on fewer feature columns than lose rows
  from the target's own history.

This value must be persisted on the run record (dataset lineage, per the backlog's framing decision
requiring every multi-source run to be visibly labeled with its composition) so a later reader can see
which policy produced a given row count — not inferred after the fact from row counts alone.

## Authoritative clock for the final aligned index

**The target series' own `DatetimeIndex` is authoritative.** The assembled table's index is exactly the
target series' index (the same series `validation-service` already loads today via a single
`dataset_reference` — this does not change), and every feature column is aligned *onto* that index per
the forward-fill rule above — never the reverse (features do not add new rows to the index; a feature
source sampled at a different cadence never introduces a timestamp the target series doesn't already
have). This is a direct consequence of ADR-0008 (a): `naive_first_engine`'s splitter and DM test only
ever reason about the target series' own index, so preserving that index unchanged is what keeps
`generate_splits`'s purge-gap protocol operating on the real, already-understood risk window instead of
a new one invented by feature alignment.

**Confirmed: this index is what `generate_splits` receives unchanged, strictly before splitting.** The
assembly/alignment step (ADR-0008's new `feature_dataset.py`-shaped module) must run to completion —
producing one aligned `DataFrame` whose index is the target series' index — *before* `POST /runs`'s
handler calls `generate_splits`/`run_validation_protocol`, exactly the same ordering `validation-service`
already uses for its existing single-series `DatasetSource.load()` call (load, then split — never the
reverse). This is the single point in this sprint most directly tied to CLAUDE.md's leakage-avoidance
rule (per `docs/sprints/sprint-31.md`'s own framing): if alignment ever ran *after* a split boundary was
already chosen, a forward-fill could reach across that boundary using post-split information, and the
purge gap would no longer protect the real train/test risk window. Splitting happens strictly after
alignment, never before — no exception.

**`splitting.py` requires no change.** `generate_splits(index, train_window, test_window, step,
purge_gap)` (per `libs/naive_first_engine/README.md`'s own public API) takes a `DatetimeIndex` and is
column-count-agnostic by construction — feeding it the aligned table's index (still exactly the target
series' own index, per the authoritative-clock decision above) is byte-identical to today's single-series
call. This ADR does not authorize any change to `libs/naive_first_engine`.

## Worked example (real data from two of the three existing connectors)

Using `binance_price_btcusdt_1h` (target, hourly) and `blockchain_info_hash-rate` (feature, real
observed cadence: daily-or-coarser per ADR-0008's table) over a four-hour illustrative window, with
`missing_timestamp_policy = "drop_row"`:

| target `row_timestamp` (price, hourly) | eligible hash-rate row used (`fetched_at <= row_timestamp - 24h`) | aligned feature value | outcome |
|---|---|---|---|
| `2024-01-02T00:00:00Z` | none (no hash-rate row has `fetched_at <= 2024-01-01T00:00:00Z` in this illustrative slice — the earliest ingested hash-rate row's `fetched_at` is `2024-01-01T06:00:00Z`) | — | **row dropped** (`"drop_row"` policy; would be null-then-kept-for-fill-window under `"forward_fill_exhausted_as_null_then_drop"` instead, same outcome here since there is nothing yet to fill from) |
| `2024-01-02T01:00:00Z` | hash-rate row `fetched_at = 2024-01-01T06:00:00Z` (first row whose lagged eligibility window, `2024-01-01T01:00:00Z`, is now satisfied) | that row's `value` | **kept**, forward-filled |
| `2024-01-02T02:00:00Z` | same hash-rate row (no newer eligible hash-rate row yet — this connector's cadence is coarser than hourly) | same value, unchanged | **kept**, forward-filled (value repeats — expected under forward-fill onto a higher-frequency target, disclosed here rather than presented as new information) |
| `2024-01-02T03:00:00Z` | same hash-rate row | same value, unchanged | **kept**, forward-filled |

This example is illustrative (a four-row slice, not a full run) but uses this repo's real connector
identities, real sampling-cadence relationship (hourly target vs. daily-or-coarser on-chain feature), and
the real `fetched_at`-based eligibility rule from ADR-0008 — not a synthetic naming convention. The
dropped first row is called out explicitly rather than silently absorbed, matching this ADR's own
missing-timestamp-policy requirement.

## Consequence for future readers

- MDF-003 (deferred, next MDF sprint) implements this alignment rule for real inside the
  `feature_dataset.py`-shaped module ADR-0008 named, and must expose `missing_timestamp_policy` as a
  required (not defaulted) field on whatever request shape it adds.
- MDF-004 (deferred, high-scrutiny) must confirm `generate_splits`'s purge-gap logic applies identically
  regardless of whether the assembled input is univariate or multivariate — this ADR states the
  *index* handed to `generate_splits` is unchanged by fusion, which is the fact MDF-004's own acceptance
  criteria depend on, but MDF-004 must verify it against real MDF-003 code, not merely cite this ADR.
- The on-chain 24h lag floor and the worked example's specific numbers are illustrative/conservative
  defaults carried from ADR-0008, not independently reverified against a live blockchain.info SLA —
  flagged here again (not just in ADR-0008) since MDF-002's worked example is the first place a reader
  might mistake the illustrative numbers for a verified guarantee.
