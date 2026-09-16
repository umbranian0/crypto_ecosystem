# Sprint 48 — AI-assist feasibility spike (gating decision, no feature code)

Sprint goal: the platform has a documented, Tech-Lead-reviewed recommendation for how an open-source/
open-weights LLM would actually be served in this stack (local Compose service vs. hosted open-weights
API), so that AI-002/AI-003/AI-004 can be scoped and built against a real latency/footprint answer
instead of an assumption.

Backlog source: `docs/product/backlog-ai-integration-ux.md` (AI-001 through AI-005)

Stories in scope:
1. **AI-001** (Must) — feasibility spike only. Produces `docs/adr/000X-ai-assist-model-serving.md`
   comparing at least (a) a small quantized open-weights model served locally via Ollama/llama.cpp as
   a new `infra/docker-compose.yml` service, and (b) a hosted open-weights inference API, against this
   platform's real constraints (local-first Docker Compose, CPU-only pilot hosts, synchronous-request
   latency budget). Must also answer the `libs/ai_assist` question explicitly (per the backlog's scope
   decision 1: stays inline until a second module needs the same logic — this spike states whether that
   trigger is already met or not). No feature code, no new service, no new container is built in this
   sprint — the deliverable is the ADR and its recommendation.

Stories explicitly deferred (not in scope this sprint):
- **AI-002, AI-003, AI-004** — all three explicitly depend on AI-001's serving-pattern recommendation
  (backlog's own "Depends on" field for each). Scoping or building any of them before AI-001's ADR
  lands would mean committing to a latency/hosting assumption the spike exists specifically to test —
  deferred to the sprint(s) immediately following, once AI-001 is Tech-Lead-reviewed and reported on.
- **AI-005** — depends on AI-002/AI-003/AI-004 (documents whichever of those ship); nothing to document
  yet. Deferred to close out whichever future sprint(s) ship AI-002/AI-003/AI-004, per the backlog's own
  note that it can be split per shipped story.

Why AI-001 is isolated as its own sprint rather than combined with anything else: it is a hard
dependency gate for four of the backlog's five remaining stories (AI-002, AI-003, AI-004 directly;
AI-005 transitively), and its acceptance criteria are explicitly a recommendation/decision document, not
incremental feature work — bundling it with any AI-002/003/004 scope would risk committing code against
an unreviewed assumption about what the ADR will conclude. This follows the same reasoning this project
already applies to other gating ADR-producing spikes (e.g. MDF-001/MDF-002 before MDF-003 in Sprint 31).

Definition of done for this sprint:
- [x] `docs/adr/0011-ai-assist-model-serving.md` exists, follows this repo's existing ADR format/numbering
  (0011 was the next available ADR number, verified against `docs/adr/` before writing), and has all four
  AI-001 acceptance-criteria boxes checked:
  - [x] local (Ollama/llama.cpp) vs. hosted open-weights comparison with approximate p50/p95 latency for a
    ~500-token summarization prompt and approximate memory/CPU footprint if local, assessed against the
    "local-first, cloud-portable, no GPU required" constraint;
  - [x] an explicit recommendation justified against AI-002's latency need (async-friendly, triggered off
    `reporting-service`'s existing `run.completed` subscriber) vs. AI-003's need (synchronous chat-turn,
    tighter budget) — note: this sprint doc's earlier prose used "AI-003" for the async narrative story and
    "AI-004" for the chat story in a couple of places; the ADR uses the backlog's own story-header
    definitions (AI-002 = async narrative, AI-003 = sync chat) and flags the discrepancy explicitly rather
    than silently picking one;
  - [x] an explicit answer to the `libs/ai_assist` question (build now vs. wait for second-duplication
    trigger), stated as the binding design note for AI-002/AI-003/AI-004's future tickets — answer: stay
    inline in `reporting-service` for AI-002, trigger not yet met, re-evaluate when AI-003 is scoped;
  - [x] an explicit list of which existing routes are and are not safe synchronous extension points for a
    model call (`GET /runs/{id}` and other list/detail reads flagged unsafe; `run.completed` subscriber and
    new dedicated routes flagged safe).
- [x] ADR status is `accepted` per this repo's own ADR lifecycle convention (not left as a draft with no
  stated status).
- [x] Tech Lead reports the recommendation back before any AI-002/003/004 ticket work is scoped — this
  report is the trigger for the requester to commission the next sprint.
- [x] No `infra/docker-compose.yml`, `Dockerfile`, service, or `libs/ai_assist` code changes landed this
  sprint — this is a documentation/decision deliverable only, consistent with "don't scaffold a
  service/lib before its trigger is concretely true."
- [x] `docs/tickets/README.md` updated to reflect AI-001 moving from todo to done, pointing at the ADR.
