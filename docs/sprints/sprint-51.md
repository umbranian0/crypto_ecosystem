# Sprint 51 — AI-assist (services/dashboard-web): AI-004

Sprint goal: A first-time dashboard-web user filling out the "Submit a run" form can get optional,
plain-language conversational guidance that maps their answers into the existing `RunRequest` fields as
visibly-marked suggestions they must confirm — with the AI-assist documentation trail (AI-005) fully closed
for this story too, and without adding any second run-submission path or weakening the mandatory purge-gap/
naive-baseline protocol.

Backlog source: docs/product/backlog-ai-integration-ux.md

Stories in scope (execution order):
1. **AI-004** (Could) — Conversational configuration guidance for submitting a validation run,
   `services/dashboard-web`. Now taken up: its sole dependency, AI-001 (serving-pattern decision,
   ADR-0011), is done, and AI-002/AI-003 have both since shipped (Sprints 49-50), giving this story two
   real precedents to follow (fact-grounding/degradation pattern, dedicated-route pattern, and the
   already-extracted `libs/ai_assist` client) rather than needing to invent any of that from scratch. Per
   the backlog's own rationale this was deliberately left last/lowest-priority in the AI-integration set —
   this sprint is that deferred pickup, not a re-prioritization.
2. **AI-005** (Must, dashboard-web slice) — Document the AI-assist boundary in
   `services/dashboard-web/README.md` for AI-004's landed behavior specifically. Depends on AI-004 within
   this sprint (documents what actually shipped, same precedent as Sprint 49's reporting-service slice and
   Sprint 50's AI-003 slice). This closes out AI-005 as a fully-documented story across all three AI-assist
   features now shipped in dashboard-web.

Stories explicitly deferred: none remaining in `docs/product/backlog-ai-integration-ux.md` — AI-001 through
AI-005 are all in scope across Sprints 48-51 once this sprint completes. No new scope added beyond what's
in the approved backlog.

## Decision 1 — `libs/ai_assist` extraction: already done, not this sprint's work

ADR-0011 named the extraction trigger ("a second *module* needing the same LLM-calling logic") as a
decision point to re-check at AI-003's scoping time, not a preemptive build. Reading the actual shipped
code confirms this already happened: `libs/ai_assist/src/naive_first_ai_assist/client.py` exists
(`AssistClient`, `AssistClientError`, `get_assist_client()`), and AI-003's shipped
`services/dashboard-web/src/app/assistant/generation.py` and `routers/assistant.py` both import from
`naive_first_ai_assist.client` rather than a service-local client — per that module's own docstring, this
was done as "AI-003-REFACTOR," evidently as part of or immediately after AI-003's ticket. The extraction
is therefore **already complete** — this sprint has no `libs/ai_assist` scaffolding work to do. AI-004's
ticket should call `get_assist_client()` the same way AI-003 does, not build or copy a second client.

One thing this sprint's ticket *does* still need to check (not assumed done): whether AI-004's guardrail
copy (banned-term list, refusal/degradation text) should be a fresh service-local module or literally reuse
`app.assistant.fact_check.contains_banned_term` — AI-003's own `fact_check.py` docstring already states the
precedent for this exact question ("module-local, deliberate copy, not a shared contract, because each
service/feature is free to diverge without touching another") when it explains why AI-003's banned-term
list wasn't pulled from AI-002's. That reasoning applies here too: a small, feature-owned guardrail list is
not itself the DRY-extraction trigger the ADR was about (the trigger was the *model-calling client*, which
is already shared) — flagged to the Tech Lead as a "check, don't silently copy without reading the
precedent" note, not resolved definitively here.

## Decision 2 — new route and reused construction site

AI-004's acceptance criteria are explicit that this is additive UI only: it must reuse DASH-006's single
`RunRequest` construction site (`services/dashboard-web/src/app/routers/runs.py`'s `run_new_submit`, the
only place a `RunRequest` is built in this service) and must not add a second submission path. ADR-0011
independently reinforces this from the serving-latency side: the model call driving the conversational
helper "must sit on its own request, never fused into the actual run-submission call," following the same
"new, dedicated" pattern AI-003 established (`POST /assistant/ask`, not a retrofit of an existing route).

Recommended shape for the Tech Lead to scope from (not binding on implementation detail, per this role's
boundary — the exact module layout is the Tech Lead's call):
- A new route, e.g. `POST /assistant/configure-run`, that accepts the conversation so far (the user's
  plain-language answers) and returns *suggested* field values for `run_new.html`'s existing form fields
  (`dataset_id`, `horizon`, `purge_gap_hours`, `train_window`, `test_window`, `step`, `label`) — never a
  `RunRequest` itself, never a call to `POST /runs`.
- `run_new.html` (already read: the form DASH-006/DASH-108/DASH-120 built) gains an optional
  conversational widget that, on response, populates the *same* form fields the user already sees and can
  edit — not a parallel form, not a hidden field the visible form doesn't expose.
- Whether this route lives in a new module (matching "one fresh module per distinct concern," since
  form-assist is a materially different concern from AI-003's Q&A) or as an addition to
  `app/routers/assistant.py` (since both are "the AI-assist surface") is a real design choice the Tech Lead
  should make and document in that module's own docstring, following this repo's existing per-file
  docstring convention — the PM is not deciding module boundaries here.

## Decision 3 — guardrails binding on this sprint's ticket(s), non-negotiable

Carried directly from AI-004's own acceptance criteria and this backlog's "What does NOT change" section —
restated here as the sprint-level definition of what "done" must include, not new invention:

- **Banned-term test**: the helper's own generated copy (questions it asks, suggestions it produces) is
  checked against the same banned-term convention (`signal`, `buy`, `sell`, `profit`, `trade`,
  `recommendation`) AI-002/AI-003 already test for, plus AI-004's own additional constraint — it must never
  claim a specific configuration value is "optimal"/"correct"/"best," only explain what a field means.
- **No pre-filled defaults, ever**: `run_new.html`'s existing DASH-006 rule ("no form field carries a
  pre-filled value that could look like a recommended default") is preserved unchanged. A value the
  conversational helper proposes must be rendered as a visibly distinct "suggested value based on your
  answer — please confirm," never silently populated as if it were a standard default the way a pre-filled
  field would read.
- **Never touches the protocol floor**: the helper cannot suggest, imply, or expose a path to
  disabling/shortening the purge gap or omitting the mandatory naive baselines. `RunRequest` does not
  expose these as optional today and this story must not add a path that makes them so — this is the
  single highest-stakes constraint carried over verbatim from DASH-006's own original docstring note.
- **Graceful degradation**: if the model call fails/times out, `run_new.html`'s existing plain form
  (unchanged, exactly as it renders today) remains fully usable — the conversational layer is strictly
  additive UI, never a blocker to the existing submission path, mirroring AI-002/AI-003's own
  fail-to-fallback shape.
- **One submission path only**: the conversational flow never auto-submits. The user always reaches the
  same `POST /runs/new` → `RunRequest` construction → `POST /runs` path DASH-006 already uses, with the
  same visible-before-submit review step every other path through this form already has.

## Dependency/sequencing notes (binding, not to be silently reordered)

- AI-004 depends on AI-001 only, per the backlog — already done (ADR-0011). It does not depend on AI-002 or
  AI-003 functionally, but this sprint sequences it after both because they are already shipped and this
  sprint's Decision 1 above relies on reading their actual landed code (not a hypothetical) to answer the
  `libs/ai_assist` question correctly.
- AI-005 (dashboard-web slice, AI-004 portion) is strictly after AI-004 in this sprint's execution order —
  same file-ordering discipline this repo already applies to sequential same-scope pairs (Sprint 49's
  AI-002 → AI-005 partial; Sprint 50's AI-003 → AI-005 partial).
- No new `libs/*` or `infra/*` scaffolding is anticipated this sprint (Decision 1 above) — if the Tech
  Lead's ticket breakdown finds a real need for one anyway (e.g. a genuinely new env var/config for this
  route), that is disclosed in `infra/README.md` and the `dashboard-web` Dockerfile/compose entry per this
  repo's "disclosed, not silent" convention, not silently added.

Definition of done for this sprint:
- AI-004's acceptance criteria in docs/product/backlog-ai-integration-ux.md are all met, including: the
  client-side/form-assist-only constraint (single `RunRequest` construction site, no second submission
  path), the "suggested value, please confirm" visual distinction from a default, the banned-term test
  covering both generated suggestions and the helper's own static copy, the "no optimal/correct claim"
  test, and the graceful-degradation-to-plain-form test.
- `services/dashboard-web/README.md` gains the AI-004 slice of the "AI-assisted features" section, in the
  same format already used for the AI-002 (reporting-service) and AI-003 (dashboard-web) slices —
  completing AI-005 across all three shipped AI-assist features.
- Any new environment variable/config this story introduces is disclosed in `infra/README.md` and the
  `dashboard-web` Dockerfile/`docker-compose.yml` entry — no silent new dependency (expected to be none,
  per Decision 1, but not assumed without checking).
- Tests passing: full `services/dashboard-web` suite re-run with zero regressions; `qa` agent
  (`/qa-validation`) raised by the Tech Lead after the ticket(s) are Tech-Lead-verified done, per this
  project's standing QA-gate requirement.
- `docs/tickets/README.md`'s AI-assist section updated with the Sprint 51 table and outcome, matching every
  prior sprint's documentation convention.
