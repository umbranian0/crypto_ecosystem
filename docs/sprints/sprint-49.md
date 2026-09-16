# Sprint 49 — AI-002 report narrative generation (reporting-service)

Sprint goal: a completed validation run's `reporting-service` report includes a fact-checked,
clearly-labeled AI-generated plain-language narrative summarizing that run's own metrics/DM verdict,
built entirely on AI-001's binding hosted-API/no-libs-ai_assist recommendation, with the corresponding
`services/reporting-service/README.md` slice documenting the new capability.

Backlog source: `docs/product/backlog-ai-integration-ux.md` (AI-002, AI-005 partial)

Stories in scope:
1. **AI-002** (Should) — report narrative generation. Next unblocked story: depends only on AI-001,
   which is done (`docs/adr/0011-ai-assist-model-serving.md`, `docs/tickets/AI-001.md`). Sequenced
   first and alone as the feature story — it establishes the fact-grounding/post-generation-validation
   pattern the backlog's own text says AI-003 will reuse, so it must land and be verified before any
   later story attempts to reuse that pattern.
2. **AI-005 (partial: reporting-service README only)** — closes out this sprint, documenting exactly
   the AI-002 slice that ships here. Sequenced last because it documents AI-002's actual landed
   behavior, not a planned one. The backlog's own AI-005 "Depends on" note explicitly allows splitting
   this per shipped story — this sprint takes the `reporting-service` half only; the
   `dashboard-web` half stays deferred until AI-003 (or AI-004) actually ships.

Stories explicitly deferred:
- **AI-003** — blocked per the backlog's own dependency chain: depends on AI-001 (done) **and** AI-002
  establishing the fact-grounding/validation pattern this story reuses. AI-002 has not shipped yet at
  sprint-planning time, so AI-003 is not yet unblocked, let alone scoped. Not touched this sprint.
- **AI-004** — depends on AI-001 only per the backlog, but the backlog's own priority rationale keeps
  it last-sequenced ("Could," lowest-frequency-use, revisit once AI-002/AI-003 are in production usage
  data exists) — not scoped this sprint, consistent with that stated sequencing.
- **AI-005 (dashboard-web half)** — deferred until whichever of AI-003/AI-004 ships and gives
  `dashboard-web` something real to document; only the `reporting-service` slice closes this sprint.

Sequencing/dependency note for the Tech Lead: this is a two-ticket, single-module
(`services/reporting-service`) chain — AI-005's README ticket is a hard sequential follow-on to AI-002
(cannot accurately document a capability before its diff lands), not parallelizable with it. No other
module is touched this sprint (no `dashboard-web`, `gateway-api`, `infra`, or `libs/*` changes are in
scope for AI-002/AI-005 per ADR-0011's explicit "no libs/ai_assist yet" and "hosted API only" findings).

Definition of done for this sprint:
- All of AI-002's backlog acceptance criteria checked off against the real diff (not a self-report):
  narrative step lives in `ValidationAuditRenderer`, fed only already-persisted run metrics, no new
  data source, no inline synchronous call on any hot-path read route (per ADR-0011's unsafe-extension-
  point list) — the call sits in the existing `run.completed` Redis Streams subscriber (RS-006);
  versioned prompt template checked into the repo; post-generation fact-check validator with a test
  proving a directionally-wrong claim triggers regeneration or a disclosed "narrative unavailable"
  fallback, never a silently-shipped false claim; banned-term test passing; narrative visibly labeled
  "AI-generated summary of the results above" and never overrides the table/DM verdict; graceful
  degradation to the existing table-only report on model-call failure/timeout, proven by a test.
- Hosted open-weights API only, called over HTTPS — no local Ollama/llama.cpp Compose service, no new
  container, per ADR-0011's binding recommendation.
- No `libs/ai_assist` package created — model-calling/prompt logic stays inline in
  `services/reporting-service/src/app/narrative/` (or equivalent single-module location) per ADR-0011's
  binding answer to the DRY-extraction question.
- `services/reporting-service/README.md` gains an "AI-assisted features" section (AI-005 partial) in
  the existing per-ticket README format (status, what it owns, design notes, positioning statement),
  stating plainly the grounded-only/no-new-predictive-claims/degrade-on-failure constraint so a reader
  of the README alone (without the backlog file) sees the guardrail.
- Any new environment variable (e.g. hosted-API endpoint/key) is disclosed in `infra/README.md` and
  `services/reporting-service`'s `Dockerfile`/`docker-compose.yml` entry — no silent new dependency.
- `docs/tickets/README.md`'s AI-assist section updated with a Sprint 49 table (AI-002, AI-005 status
  moved from todo to reflect real outcome as each ticket completes).
- Full `services/reporting-service` test suite re-run and passing, zero regressions in any other
  module's suite (this sprint's diff is scoped to `reporting-service` only).
