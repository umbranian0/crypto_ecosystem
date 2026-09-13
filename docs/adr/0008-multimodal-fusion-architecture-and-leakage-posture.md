---
status: accepted
---

# Multimodal dataset fusion: joins live inside `validation-service` (no new module, no un-fired trigger pulled forward); per-connector-type leakage posture documented; `CompositeDatasetSource` confirmed single-reference-with-mode-dispatch, not multi-field composition

`docs/product/backlog-multimodal-dataset-fusion.md` (MDF-001) asks for a written decision, before any
join code is written, on (a) where multi-source dataset assembly lives and whether that pulls a
component forward against an un-fired trigger; (b) each existing connector type's documented
publication/confirmation lag, revision risk, and the resulting minimum safe purge-gap/alignment rule;
(c) an explicit confirm-or-correct of whether `CompositeDatasetSource` already supports multi-field
composition. This is a decision-work ticket only — no fusion/join code exists after this ADR, per the
backlog's own instruction and per `docs/sprints/sprint-31.md`'s scope.

## (a) Where the join happens, and whether this pulls a component forward against an un-fired trigger

**The join happens inside `services/validation-service`, as a new dataset-assembly step that runs
before `naive_first_engine` is invoked — not a standalone feature-store/join service.**

Concretely: a new module (working name `src/app/feature_dataset.py`, sibling to the existing
`dataset_source.py`) will own resolving a *list* of `{source, field}` references into one aligned,
multi-column `pandas.DataFrame` — by calling the *existing* `CompositeDatasetSource.load()` once per
reference (reuse, not reimplementation of the four existing dispatch branches:
`InlineOrLocalFileDatasetSource`/`ObjectStorageDatasetSource`/`IngestionServiceDatasetSource`/their
composite) and then applying MDF-002's alignment rule across the resulting series. This sits one layer
above `CompositeDatasetSource`, not inside it — `CompositeDatasetSource.load(reference) -> LoadedSeries`
stays a single-reference-in/single-series-out contract, unmodified. Only the assembly step calling it
N times is new.

**This is not a pull-forward against an un-fired trigger, and no ADR-0003-style disclosure is
required.** `implementation-plan.md` section 6's trigger table entry #3 (`services/validation-service`
— "as soon as `naive_first_engine` needs to be run against a real dataset via an API call instead of a
local script") already fired (Sprint 03; `services/validation-service/README.md`'s own status line
confirms "Trigger #3 has fired"). The backlog's finding #5 is correct that the trigger table has no line
item literally reading "combine N datasets into one aligned input" — but that is because the trigger
table triggers *modules*, not every feature inside an already-triggered module. Assembling a run's input
dataset is already `validation-service`'s bounded context per `implementation-plan.md` section 2
("Runs `naive_first_engine` against a dataset + config") and per its own README ("Does not own: the
validation algorithm itself... dataset storage"; assembling *what gets validated* is explicitly this
service's job, only the storage of the raw data is `ingestion-service`'s). Extending that existing
responsibility from "one `{source, field}` reference" to "one-or-more `{source, field}` references,
aligned into one table" is new *scope* within an already-triggered module, not a new module requiring
its own trigger — the same category distinction ADR-0003 itself draws (its own consequence note warns
against homogenizing pull-forward language across genuinely different situations). No new service is
stood up, no new trigger-table row is needed, and this ADR is not an instance of the ADR-0003 pattern.

**Why not a standalone feature-store service** (per the backlog's own preference and the sprint's
requirement to treat this as a genuinely open question, not a foregone conclusion): a separate service
would (1) require its own schema/trigger-table entry the backlog itself confirms doesn't exist and isn't
justified by any concrete external-caller need today — the only consumer of an aligned multi-source
table is `validation-service`'s own run-execution path, not a second, independent caller; (2) add an
inter-service HTTP hop and a second place enforcing "preprocessing is fit train-fold-only, never
globally" (CLAUDE.md's leakage rule), duplicating rather than reusing the Template Method
(`split → baseline → metrics → DM test`) `validation-service`'s README already commits to running
unshortcut; (3) contradict `implementation-plan.md`'s own operating principle ("don't scaffold a service
before something concrete needs it") — there is no second caller, and YAGNI applies exactly as it does
everywhere else in this repo's build-order discipline. No concrete reason was found in the backlog, the
implementation plan, or the module boundary map to override the backlog's own recommendation.

**`libs/naive_first_engine` is untouched by this ADR.** Per its own README, `Baseline.predict(train:
pd.Series, test: pd.Series) -> pd.Series` and `dm_test`'s error-`Series`-in contract only ever need to
see the *target* series (the naive baselines are computed on the target alone; the DM test compares
per-point errors on the target alone). `splitting.generate_splits` operates on a `DatetimeIndex` only
and is column-count-agnostic by construction — it needs the aligned table's *index*, never its columns.
None of this requires any change to `naive_first_engine`'s public API. Whether a *new*, additional
interface is needed for "a candidate model that consumes a multi-column feature DataFrame" is MDF-004's
question, explicitly deferred to a later sprint (high-scrutiny, extra reviewer pass, per the backlog) —
this ADR takes no position on that beyond confirming today's `Baseline` protocol needs no edit for
anything decided here.

## (b) Per-connector-type publication/confirmation lag, revision risk, and minimum safe purge-gap/alignment rule

Reusing (not inventing) the "documented causal lag" concept `docs/solution-design.md` already assigns to
the sentiment/on-chain connectors, and the causal-lag mechanism `services/ingestion-service/README.md`
already documents as enforced per-connector via `FetchResult.fetched_at` ("recording *when data became
known*, not just when it happened... enforced in this interface... not left to each adapter's
discretion").

| Connector | Known publication/confirmation lag | Revisable after initial publication? | Minimum safe purge-gap/alignment rule |
|---|---|---|---|
| `BinancePriceConnector` (`binance_price_btcusdt_1h`) | Exchange OHLCV candles are closed/published at each hourly boundary; `fetched_at` is recorded at crawl time, not backdated. No known confirmation delay beyond the candle's own close. | No — a closed exchange candle is not revised after the fact (unlike an on-chain estimate or a sentiment score). | No *additional* purge gap beyond whatever `purge_gap_hours` the run already configures for its target series. This connector is also, in every real dataset in this repo today, the *target* series itself (per `IngestionServiceDatasetSource`'s live-UAT finding) — its own row is never itself a "feature leaking into its own target," but if a second-run's model treats price as a *feature* alongside a different target, the same zero-additional-lag rule applies. |
| `BlockchainInfoConnector` (parameterized: `blockchain_info_hash-rate`, `blockchain_info_n-unique-addresses`) | **Unverified, materially real revision risk** — blockchain.info's charts (hash-rate especially) are estimates computed over a trailing window and can be refined as more blocks confirm; this repo's own code has no documented SLA for when a given interval's value becomes final, and `services/ingestion-service/README.md` records no confirmation-lag guarantee for this connector beyond `fetched_at` itself. Sampling cadence observed in this connector's real ingested data (per `ONCHAIN_FACTORIES`) is coarser than the hourly price connector. | **Yes, plausibly** — no confirmation from blockchain.info's own API contract that a value is final at the moment it first appears. Not disproven, so treated as revisable by default (fail-closed, per CLAUDE.md's no-silent-inference rule: absence of a documented "this value never changes" guarantee is not evidence that it never changes). | **Minimum safe rule: treat a row's `fetched_at` timestamp (not its nominal metric timestamp) as the earliest instant the value may be used, and require at least one full sampling interval of this connector (its own between-row spacing, conservatively floored at 24h — this connector's real cadence is daily-or-coarser) as an added purge-gap buffer beyond the target series' own `purge_gap_hours`.** This is disclosed as a conservative default requiring product confirmation before MDF-003 ships it as a hard-coded constant — not asserted as an SLA this repo has independently verified with blockchain.info. |
| `RedditSentimentConnector` (`reddit_vader_sentiment`) | **Highest risk of the three, and the exact risk this backlog names explicitly** ("a sentiment score for day D that was computed or revised using information published after day D's close"). VADER scoring happens at crawl (`fetched_at`) time, which can arbitrarily postdate `created_utc` (a submission's own posting time) depending on the crawler's own schedule — there is no guarantee a submission is scored the same hour it's posted. Submissions can also be edited or deleted on Reddit after posting, changing what a later re-crawl would score for the same nominal timestamp (this connector does not currently re-crawl/update already-scored submissions, per its `connectors/` implementation, but the underlying source data itself is mutable). | **Yes, by construction** — `created_utc` is not the "known-at" instant; `fetched_at` is. | **Minimum safe rule, and the one binding constraint carried into MDF-002: a sentiment row must be aligned using its `fetched_at` timestamp as the "available-as-of" instant, never `created_utc`.** This is not a new invention — it is exactly the causal-lag mechanism `services/ingestion-service/README.md` already states is enforced at the connector-interface level (`FetchResult.fetched_at`, "the exact leakage failure mode one layer up from the validation engine"); MDF-001's contribution is stating explicitly that the multi-source alignment step must actually *use* `fetched_at` for this source, not silently fall back to the more convenient `created_utc` the connector's raw table also exposes. |

**Binding constraint carried forward to MDF-002**: for every connector, the "available-as-of" instant
used for alignment is `fetched_at` (when the platform learned the value), never the value's own nominal
timestamp, whenever the two can plausibly differ (on-chain, sentiment) — this generalizes the sentiment
case above to the on-chain case identically, since both share the same underlying risk shape (a value
whose nominal timestamp does not prove when it became knowable).

## (c) `CompositeDatasetSource` — confirmed: single-reference-with-mode-dispatch only, not multi-field composition

Read directly against `services/validation-service/src/app/dataset_source.py`. **The backlog's reading
(finding #4) is correct, confirmed, not corrected**: `CompositeDatasetSource.load(reference)` dispatches
on which *key* a single `reference` dict contains (`"object_key"` → `ObjectStorageDatasetSource`,
`"source"` → `IngestionServiceDatasetSource`, anything else → `InlineOrLocalFileDatasetSource`) and
returns exactly one `LoadedSeries` per call. There is no code path anywhere in this class, or in any of
the four `DatasetSource` implementations it wraps, that accepts a *list* of references or composes more
than one series into a single return value — "Composite" here names "composed of multiple *possible
source implementations* for one field," not "multiple simultaneous fields." A caller wanting N fields
today would have to call `.load()` N times itself; nothing in `validation-service` currently does that.
This confirms the gap named in (a) above is real: the new multi-source assembly step is genuinely new
code, not a rename or a config flag on existing code.

## Consequence for future readers

- MDF-002 (this sprint) must design the alignment/resampling rule using `fetched_at` as each
  non-price source's "available-as-of" instant (per (b) above) and must confirm the assembled table's
  index is what `generate_splits` receives unchanged, strictly after alignment — see that ADR.
- MDF-003 (deferred, next MDF sprint) is the first ticket authorized to write real fusion/join code
  under `services/validation-service/src/app/feature_dataset.py` (or whatever filename its own ticket
  breakdown settles on) — this ADR authorizes the *location* and *shape*, not the code itself.
- MDF-004 (deferred, high-scrutiny) still owns the open question of whether `naive_first_engine` needs a
  new (additive, non-modifying) interface for a multi-column candidate-model input — nothing in this ADR
  should be read as resolving that question early.
- The on-chain connector's revision-risk finding in (b) is disclosed as conservative-by-design, not
  independently verified against blockchain.info's own API guarantees — flagged here for whoever
  eventually ships MDF-003's hard-coded purge-gap constant to confirm or tighten, not left as a silent
  assumption.
