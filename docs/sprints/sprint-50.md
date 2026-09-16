# Sprint 50 — AI-assist (services/dashboard-web)

Sprint goal: A dashboard-web user can ask a natural-language question about their own tenant's stored
validation-run history and get a grounded, cited, honestly-scoped answer, with the AI-assist
documentation trail (AI-005) fully closed for both services it spans.

Backlog source: docs/product/backlog-ai-integration-ux.md

Stories in scope (execution order):
1. **AI-003** (Should) — Natural-language Q&A over a tenant's own stored run data, `services/dashboard-web`.
   Now unblocked: AI-001 (serving-pattern decision, ADR-0011) is done, and AI-002 is done, which
   established the fact-grounding/validation pattern (prompt template + post-generation fact-check +
   banned-term test + graceful degradation) this story reuses. Goes first because AI-005's dashboard-web
   slice documents its actual landed behavior and cannot start before it.
2. **AI-005** (Must, dashboard-web slice) — Document the AI-assist boundary in
   `services/dashboard-web/README.md`. Depends on AI-003 within this sprint (documents what actually
   shipped, same precedent as Sprint 49's reporting-service slice). Closes the full AI-005 story across
   both services once this slice lands (reporting-service slice already done, Sprint 49).

Stories explicitly deferred: AI-004 (Could) — smallest-audience, lowest-frequency story per the backlog's
own priority rationale; not re-evaluated until AI-002/AI-003 have real production usage data. No new
scope added beyond what's in the approved backlog.

Dependency/sequencing notes (binding, not to be silently reordered):
- AI-003 depends on AI-001 (done) and AI-002 (done) per the backlog itself — both prerequisites are
  satisfied, so AI-003 is legitimately unblocked this sprint, not pulled ahead of its stated dependencies.
- ADR-0011 requires the Tech Lead to explicitly re-check the `libs/ai_assist` extraction trigger
  ("second module needing the same LLM-calling logic") against AI-002's actual shipped
  `reporting-service/src/app/narrative/` code once AI-003 is scoped. This is a real decision point for
  AI-003's ticket breakdown — the ADR predicts but does not guarantee the trigger fires. Not for the PM
  to resolve; flagged to the Tech Lead as something to actually check, not skip.
- ADR-0011 binds AI-003's model call to a new, dedicated route (e.g. `POST /assistant/ask`,
  `src/app/routers/assistant.py`) — never retrofitted onto an existing hot-path route (`GET /runs`,
  `GET /runs/{id}`, etc., which ADR-0011 explicitly lists as unsafe extension points).
- AI-003's retrieval is scoped to gateway-api's existing public endpoints only (`GET /runs`,
  `GET /runs/{id}`, `GET /runs/{id}/splits`, `GET /runs/trend` if applicable) — no new gateway-api
  endpoint is in scope this sprint; if the Tech Lead finds a real gap requiring one, that must be flagged
  back to the PM/PO, not assumed or built silently.
- AI-005 (dashboard-web slice) is strictly after AI-003 in this sprint — same file-ordering discipline
  this repo already applies to sequential same-scope pairs (e.g. Sprint 49's AI-002 → AI-005 partial).

Definition of done for this sprint:
- AI-003's acceptance criteria in docs/product/backlog-ai-integration-ux.md are all met, including: the
  cross-tenant-leak guard test (mirrors VS-024's precedent — a test proving a query cannot surface
  another tenant's data), the explicit-citation-per-answer requirement, the banned-term test on both
  generated answers and static assistant UI copy, and the fixed-refusal test for out-of-scope questions
  (e.g. "will Bitcoin go up" refused, not answered).
- `services/dashboard-web/README.md` gains the AI-005 "AI-assisted features" section in the same format
  already used in `services/reporting-service/README.md` (Sprint 49 precedent).
- Any new environment variable/config this story introduces is disclosed in `infra/README.md` and the
  `dashboard-web` `Dockerfile`/`docker-compose.yml` entry — no silent new dependency.
- Tests passing: full `services/dashboard-web` suite re-run with zero regressions; `qa` agent
  (`/qa-validation`) raised by the Tech Lead after both tickets are Tech-Lead-verified done, per this
  project's standing QA-gate requirement.
- `docs/tickets/README.md`'s AI-assist section updated with the Sprint 50 table and outcome, matching
  every prior sprint's documentation convention.
