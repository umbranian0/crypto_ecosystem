# Backlog — Open-Source AI Integration & UX

Source: `docs/da-tese-ao-produto.md` (sections 2.1, 2.2, 2.7 — positioning, non-negotiable),
`docs/solution-design.md` (sections 3.5 reporting-service, 3.6 dashboard-web, section 6 build order),
`docs/implementation-plan.md` (section 2 module boundary map, section 6 trigger table, section 7 design
patterns, section 9 DRY/no-cross-service-import rules), `services/dashboard-web/README.md` (current
routes/contract, "Owns"/"Does not own", positioning convention already enforced in every existing
template — e.g. DASH-004/DASH-005's "never prediction/forecast/signal/recommendation" rule and its own
banned-word tests), `services/reporting-service/README.md` (current status: implemented, Jinja2->HTML
rendering, Postgres-backed `reports` schema, `run.completed` subscriber).

**Requested scope**: brainstorm open-source AI/LLM integration for UI/UX value in the existing
dashboard-web/reporting-service surfaces — narrative generation over already-computed honest results,
retrieval-grounded Q&A over a tenant's own stored run data, and conversational configuration guidance.
Explicitly **not** in scope: anything that would generate new predictive/trading claims, anything
duplicating the already-running MR-008+ real-data model-research track, and any change to
`libs/naive_first_engine`'s leakage-safety machinery.

## Trigger/scope decisions flagged for the requester (read before grooming)

1. **No `libs/ai_assist` or similar new shared lib exists in `implementation-plan.md`'s module map or
   trigger table (section 6).** Every story below is scoped to live inside an *existing* module
   (`reporting-service` for narrative generation, `dashboard-web` for chat/copilot UI) as a bounded
   feature within that module's own "owns" boundary, not a new service/lib — consistent with "don't
   scaffold a service before something concrete needs it." If a second module ends up needing the same
   LLM-calling logic (e.g. both `reporting-service` and `dashboard-web` need a prompt-template renderer),
   that is the DRY trigger (implementation-plan.md section 9: "extract on second duplication") to pull it
   into a new `libs/ai_assist` — not built preemptively here. **Flagging this as a decision the PO is
   making, not deriving from an existing doc**, since no prior doc names an AI/LLM module.
2. **All stories below are additive UI/reporting features on top of already-shipped, already-audited
   modules** (`reporting-service`: implemented; `dashboard-web`: implemented, both ahead of their
   original triggers per each README's own "Explicit trigger override" precedent already established in
   this repo for `gateway-api`/`dashboard-web`/`reporting-service`). No story here requires waiting on an
   unfired trigger elsewhere in the build order — they attach to modules that already exist.
3. **Open-source model choice is deliberately left to the Tech Lead**, not decided here (e.g. a small
   local model via Ollama/llama.cpp vs. a hosted-but-open-weights API) — this is an ML-engineer
   feasibility/serving-pattern decision (inference cost, latency, whether local-first Docker Compose can
   actually host a model with acceptable latency), flagged explicitly in AI-001's acceptance criteria
   rather than assumed.
4. **RAG/retrieval scope for AI-002 (Q&A) is intentionally narrow**: retrieval is over the tenant's own
   already-computed `split_results`/`reports` rows only, fetched through existing `gateway-api`
   endpoints — never a raw DB query, never a general web-connected assistant. This is stated as a hard
   constraint in AI-002 itself, not left implicit.

## What does NOT change (binding on every story below, no exceptions)

- No story generates a new predictive/trading claim, price forecast, or "signal" of any kind. An LLM
  component in this backlog only **explains, summarizes, or helps navigate already-computed, already
  leakage-safe validation results** — it never computes a new statistic, never predicts a future value,
  and never overrides a DM verdict or metric with its own judgment.
- No story authorizes skipping, weakening, or working around the leakage-aware protocol
  (`splitting.generate_splits`'s purge gap, train-fold-only fitting, Naive0/NaiveLast baselines,
  Harvey-corrected DM test) for the sake of AI-feature convenience or speed. None of the stories below
  touch `libs/naive_first_engine` at all.
- Every AI-generated narrative/answer must be **grounded in and traceable to specific persisted
  numbers** (a `split_results` row, a report's own rendered table, a `runs` record) — never a
  free-generation summary invented from the model's own training-data knowledge of Bitcoin/crypto
  markets. Acceptance criteria below require a visible citation/link back to the source number for every
  claim the model states.
- CLAUDE.md's "statistical accuracy != economic value" separation is preserved in every generated
  sentence — no generated copy may imply profitability, "buy/sell," or "this model is good for trading."
  This is testable the same way `dashboard-web`'s existing banned-word tests already work (DASH-004/005'
  precedent): a test asserting the generated output never contains a fixed list of banned terms
  ("signal," "buy," "sell," "profit," "trade," "recommendation" in a directive sense) is a required
  acceptance criterion, not optional.
- No story reaches into another service's database schema. An LLM feature living in `reporting-service`
  or `dashboard-web` gets its input data exactly the way every existing route already does — through
  that service's own repository or through `gateway-api`'s public contract, never a new cross-schema
  read (implementation-plan.md section 2's binding rule).
- Any local/open-source model artifact and any additional container this introduces is disclosed in
  `infra/README.md` and the owning service's `Dockerfile`/`docker-compose.yml` entry — no silent new
  dependency, matching this repo's own "disclosed, not silent" convention for capability gaps.

## Prioritization

MoSCoW, one-line rationale per story tied to (a) the module's own "owns" boundary and current status, and
(b) whether it depends on infrastructure not yet decided (e.g. AI-001's model-hosting decision gates
AI-002/AI-003/AI-004).

## Stories

### AI-001 — Feasibility spike: open-source LLM serving pattern for this platform [Must]
**As a** Tech Lead scoping the rest of this backlog, **I want** a documented spike comparing at least two
open-source/open-weights serving options (e.g. a small local model via Ollama running as a new
`infra/docker-compose.yml` service vs. a hosted-but-open-weights inference API called over HTTPS) against
this platform's actual constraints (local-first Docker Compose per `solution-design.md` section 5,
pilot-scale CPU-only hosts, latency budget for a synchronous dashboard request), **so that** every
downstream story in this backlog has a concrete answer to "what actually runs this model and how fast,"
instead of assuming a specific stack.

Acceptance criteria:
- [ ] Spike document (`docs/adr/000X-ai-assist-model-serving.md`) compares at least: (a) a small
  quantized open-weights model served locally via Ollama/llama.cpp as a new Compose service, and (b) a
  hosted open-weights inference API (e.g. via an OpenAI-compatible endpoint pointed at an open-weights
  model) — for each: approximate p50/p95 latency for a ~500-token summarization prompt, approximate
  memory/CPU footprint if local, and whether it fits the "local-first, cloud-portable" deployment
  constraint (`solution-design.md` section 1) without requiring a GPU.
- [ ] A recommendation is made and justified against AI-003's specific latency need (synchronous report
  narrative generation, triggered at run-completion time — already an async/background-friendly point in
  the pipeline, per `reporting-service`'s existing `run.completed` Redis Streams subscriber) vs. AI-004's
  need (synchronous chat-turn latency, a tighter budget).
- [ ] Explicitly answers: does this need a new `libs/*` package for prompt-building/model-calling shared
  logic now, or does the DRY "extract on second duplication" rule (implementation-plan.md section 9)
  mean it stays inline in `reporting-service` until `dashboard-web` needs the same logic (see scope
  decision #1 above)? Answer becomes the binding design note for AI-002/AI-003/AI-004.
- [ ] No model call happens synchronously in a request path that currently has no latency budget for it
  (e.g. `GET /runs/{id}` must not gain an inline LLM call) — spike explicitly flags which existing routes
  are and are not safe extension points.

Rationale for priority: every other story in this backlog is blocked on knowing what actually serves the
model and at what cost — this is the ML-engineer feasibility gate, done first per standard practice
before committing to a UX design that assumes a latency profile that may not hold.
Depends on: none

### AI-002 — Report narrative generation: plain-language summary of a validation run's results [Should]
**As a** non-quant reader of an audit report (compliance reviewer, fund stakeholder — the "compliance/due
diligence" audience named in `da-tese-ao-produto.md` section 2.2), **I want** `reporting-service`'s
generated report to include an LLM-produced plain-language paragraph summarizing that run's own
MAE/RMSE/DA/DM-verdict numbers, **so that** the existing table-only report becomes readable without
requiring the reader to already understand Diebold-Mariano statistics — this belongs to Subsystem 4
(`da-tese-ao-produto.md` section 2.3.4, "Camada de Reality Check / Auditoria"; `solution-design.md`
section 3.5) as an extension of the existing report generator, not a new subsystem.

Acceptance criteria:
- [ ] A new rendering step in `reporting-service`'s existing `ValidationAuditRenderer` (Factory pattern,
  already in place per `implementation-plan.md` section 7) produces a narrative paragraph fed **only**
  the run's own persisted `split_results`/aggregate metrics (already fetched for the table it renders
  today) — no additional data source, no live model call to any external prediction API.
- [ ] The prompt template is a versioned, reviewable artifact (e.g.
  `services/reporting-service/src/app/narrative/prompt_template.py` or a `.jinja` file) checked into the
  repo, not a hidden runtime string — so a future reviewer can audit exactly what was asked of the model.
- [ ] Every factual claim in the generated paragraph (e.g. "the model's MAE was higher than Naive0's at
  this horizon") is checked by a post-generation validator against the actual persisted numbers before
  the report is finalized — a test proves that if the LLM's paragraph asserts a directionally wrong claim
  (e.g. claims the model beat naive when the DM verdict says otherwise), the report generation either
  regenerates or falls back to a template-only report with a disclosed "narrative unavailable" note,
  never silently ships a false claim.
- [ ] A fixed test asserts the generated paragraph never contains any of the banned terms from this
  backlog's "What does NOT change" section, and never asserts anything about future prices/returns.
- [ ] The existing table/DM-verdict rendering is unchanged and remains the report's authoritative
  content — the narrative is clearly labeled "AI-generated summary of the results above" in the rendered
  HTML, distinguishing it from the audited numbers themselves.
- [ ] Report generation degrades gracefully (renders the existing table-only report, unchanged from
  today) if the model call fails/times out — this is additive, not a new single point of failure for
  report generation.

Rationale for priority: directly serves the B2B audit/certification revenue line
(`da-tese-ao-produto.md` section 2.4) named as this product's most concrete near-term value; "Should" not
"Must" because it depends on AI-001's serving-pattern decision and is an enhancement to an
already-shipped, already-valuable report, not a blocker to anything else.
Depends on: AI-001

### AI-003 — Natural-language Q&A over a tenant's own stored run data [Should]
**As a** dashboard-web user (fund/quant-desk analyst or compliance reviewer reviewing their own tenant's
runs), **I want** a chat-style question box on the dashboard (e.g. "why did my model's DM verdict flip to
worse last month?") that is answered by retrieving the tenant's own `split_results`/`runs` history through
`gateway-api`'s existing endpoints and having an LLM phrase a grounded answer, **so that** a user can
navigate their own historical results without manually cross-referencing the runs list, run detail pages,
and the horizon-summary/trend views (`RAV-009`) by hand.

Acceptance criteria:
- [ ] The feature lives in `dashboard-web` (new router module, e.g. `src/app/routers/assistant.py`,
  following the existing "one fresh module per distinct concern" convention already used for
  `operator.py`/`settings.py`) and calls only `gateway-api`'s existing public endpoints (`GET /runs`,
  `GET /runs/{id}`, `GET /runs/{id}/splits`, `GET /runs/trend` if applicable) to retrieve data — never a
  direct DB read, matching `dashboard-web`'s own "Does not own: any data access" boundary.
  `services/dashboard-web/README.md` is updated per implementation-plan.md section 8's documentation
  convention.
- [ ] Retrieval is scoped to the authenticated tenant's own session (`DownstreamHeadersDep`, the same DI
  seam every other route uses) — a test proves a query cannot surface another tenant's data (mirrors the
  existing cross-tenant-leak guard precedent used elsewhere in this repo, e.g. VS-024's pattern).
  Retrieval is a fixed, small number of endpoint calls per question (not an open-ended agent looping
  arbitrarily over the API) — the query pattern is scoped and reviewable, not autonomous.
- [ ] Every answer includes an explicit citation back to the specific run id(s)/split(s) it drew from
  (e.g. a rendered "based on run #42, split 7" reference or inline link), so a user can verify the claim
  against the existing run-detail page rather than trusting the answer blindly.
- [ ] A fixed test asserts the generated answer never contains any banned term from this backlog's "What
  does NOT change" section and never answers a question that isn't answerable from the tenant's own
  stored data (e.g. "will Bitcoin go up next week" is refused with a fixed, honest "this system does not
  predict prices" response, not answered).
- [ ] Unanswerable/out-of-scope questions (asking about data the tenant doesn't have, or asking for a
  prediction) get a fixed refusal message, not a hallucinated answer — a test proves this for at least
  one out-of-scope example.
- [ ] Positioning copy on the assistant's own UI (its intro/placeholder text) states plainly it explains
  the tenant's own validation history and does not predict markets — same "banned-word" test convention
  applied to this static copy too.

Rationale for priority: the most genuinely useful UX-copilot idea from the brainstorm (grounded Q&A over
real data, not a chatbot inventing numbers) but is architecturally the most involved (retrieval scoping,
citation requirement, refusal behavior) and depends on AI-001's latency-budget finding for a synchronous
chat turn — sequenced after AI-002 (a simpler, batch-time narrative generation) establishes the
prompt-grounding/fact-checking pattern this story reuses.
Depends on: AI-001, AI-002 (establishes the fact-grounding/validation pattern reused here)

### AI-004 — Conversational configuration guidance for submitting a validation run [Could] — done (Sprint 51, tickets AI-004-01/AI-004-02)
**As a** dashboard-web user filling out the "Submit a run" form (`GET/POST /runs/new`, DASH-006), **I
want** an optional conversational helper that asks plain-language questions ("how far ahead do you want
to check predictions?" instead of "horizon") and maps my answers to the existing `RunRequest` form
fields, **so that** a first-time or non-technical user can configure horizon/purge-gap/baselines without
needing to already understand the domain vocabulary — while the actual submitted values still go through
the exact same `RunRequest` validation and `POST /runs` call DASH-006 already uses.

Acceptance criteria:
- [ ] This is a **client-side/form-assist layer only** — it pre-fills the existing `run_new.html` form
  fields based on the conversation, it does not introduce a second submission path or a second
  `RunRequest` construction site (reuses DASH-006's single construction site, per this repo's own DRY
  convention). The user always sees and can edit the final form values before submitting — no silent
  auto-submission from the conversational flow.
- [ ] The helper **never sets or suggests a value that would violate the mandatory protocol**: it cannot
  suggest disabling/omitting the purge gap or the naive baselines (these are not exposed as
  optional/skippable in `RunRequest` today, and this story does not add a path that makes them so, per
  this backlog's own "What does NOT change" section).
- [ ] `run_new.html`'s existing "no pre-filled defaults" rule (DASH-006's own documented constraint: "no
  form field carries a pre-filled value that could look like a recommended default") is preserved — the
  conversational helper's suggestions are visibly distinct from a default (e.g. rendered as "suggested
  value based on your answer, please confirm" rather than silently populating the field as if it were
  standard).
- [ ] A fixed test asserts the helper's own copy never contains a banned term from this backlog's "What
  does NOT change" section and never implies a "correct"/"best" configuration in a way that overstates
  certainty (e.g. it may explain what a purge gap is, it may not claim a specific gap value is
  "optimal").
- [ ] Degrades to the existing plain form (unchanged) if the model call fails — the conversational layer
  is strictly additive UI, DASH-006's existing form submission path is never blocked by it.

Rationale for priority: genuinely useful onboarding UX but the smallest-audience, lowest-frequency-use
story here (used once per new user, not repeatedly like AI-002/AI-003) and the hardest to keep from
implying a "recommended" configuration, which risks drifting toward the exact overstated-certainty
problem CLAUDE.md warns against — kept to "Could," last in sequence, revisit priority once AI-002/AI-003
are in production and real usage data exists.
Depends on: AI-001

### AI-005 — done (all slices: reporting-service Sprint 49, dashboard-web/AI-003 Sprint 50, dashboard-web/AI-004 Sprint 51, see docs/tickets/AI-005-dashboard-web-ai004.md) — Document the AI-assist boundary in `services/dashboard-web/README.md` and
`services/reporting-service/README.md` [Must]
**As a** future reader of either service's README (PM, Tech Lead, or a future session), **I want** each
service's README updated with an explicit "AI-assisted features" section stating what the LLM component
does and does not do, which endpoints/data it can read, and where the banned-term/fact-grounding tests
live, **so that** this repo's own documentation-for-scaling convention (implementation-plan.md section 8:
README stays current on status/ownership/contract as it's built) is honored for this feature set exactly
as it is for every other shipped ticket in either service's README history.

Acceptance criteria:
- [ ] Both READMEs gain a section following the existing per-ticket documentation format already used
  throughout each file (status, what it owns, design notes, positioning statement) — not a separate,
  lower-detail treatment.
- [ ] The section states explicitly, in plain terms, the binding constraint from this backlog's "What
  does NOT change" section (grounded-only, no new predictive claims, degrade-on-failure) so a reader who
  has only the module README (not this backlog file) still sees the guardrail.
- [ ] Any new environment variable, container, or model artifact this backlog's stories introduce (per
  AI-001's spike outcome) is listed in `infra/README.md` and the relevant `Dockerfile`/
  `docker-compose.yml` entry, matching this repo's own "disclosed, not silent" convention.

Rationale for priority: "Must" — this repo's own stated convention (implementation-plan.md section 8,
reinforced by user memory: "every ticket/sprint updates READMEs... as part of the work, not a separate
pass") makes README currency non-optional for any shipped story in this backlog, regardless of the
individual feature's own priority.
Depends on: AI-002, AI-003, AI-004 (documents whichever of these actually ship; can be split per-story at
grooming if the Tech Lead prefers one README update per shipped ticket instead of one combined pass)

## What "success" looks like, stated explicitly

Success for this backlog is an AI-assist layer that makes the platform's own already-honest, already
leakage-safe results *more legible* to a non-quant reader and *faster to navigate* for a returning
analyst — never a layer that adds a new claim, prediction, or recommendation the underlying validation
engine didn't already produce. A story that ships with graceful degradation, visible citations, and a
clean banned-term test suite is a complete success regardless of how "impressive" the generated prose
is — matching this platform's own stated differentiator (`da-tese-ao-produto.md` section 2.5: "nós
sabemos como os modelos parecem bons sem ser").
