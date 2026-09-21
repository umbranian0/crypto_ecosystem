# Sprint 55 — `dashboard-web`: expose the "bring your own model" submission path (RPT-003)

Sprint goal: a tenant with their own model's predictions can submit them through `dashboard-web`'s
"Submit a run" form (`GET /runs/new` / `POST /runs/new`) and get a real, honest client-baseline-vs-naive
verdict — closing the gap where this platform's own named headline capability (Subsystem 6, "bring your
own model") is fully built end-to-end on the backend but reachable today only via a raw, undocumented
`POST /runs` HTTP call, not through the UI a pilot client is actually expected to use.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md` — `RPT-003` (the one Must in that backlog,
escalated above its own epic's overall lower sequencing lean; see that story's own rationale).

## Verification of the PO's cited findings (done independently, not taken on trust)

- `services/dashboard-web/src/app/routers/runs.py` (read in full): confirmed `client_prediction_reference`
  appears nowhere in this file. `run_new_form`, `run_new_submit`, and the `RunRequest(...)` construction
  site inside `run_new_submit` build only `dataset_id`/`dataset_reference`/`horizon`/`purge_gap_hours`/
  `train_window`/`test_window`/`step`/`label` — no client-prediction field is read from the submitted
  form, parsed, or forwarded.
- `services/dashboard-web/src/app/templates/run_new.html` (read in full): confirmed `GET /runs/new`'s
  rendered form has no field, fieldset, label, or hidden input referencing a client prediction/model
  series anywhere — only the "Dataset reference" fieldset (local file path / inline JSON) and the
  "Stored dataset" fieldset (source dropdown + optional start/end/field) exist as input surfaces besides
  the run-config fields (horizon/purge gap/windows/step/label).
- `libs/common/src/naive_first_common/contracts.py` (grepped): confirmed `RunRequest` already declares
  `client_prediction_reference: dict | None = None` (VS-017's shared contract field), with its own
  comment stating `None` (the default) is byte-identical to pre-VS-017 behavior and that the mandatory
  naive baselines are never conditional on it. This is the exact field `dashboard-web`'s form needs to
  populate — no backend/contract change is needed, only a UI path that sets it.
- `services/validation-service/README.md` (read in full, VS-017/VS-029 sections): confirmed the backend
  mechanism is fully built and wired through `POST /runs` (loads `client_prediction_reference` via the
  same `DatasetSourceDep` seam as `dataset_reference`, wraps it in `ClientPredictionBaseline`, adds it as
  a third, strictly additive `extra_baselines` entry), `GET /runs/{id}` and `GET /runs/{id}/splits`
  (`client_baseline`/`has_client_model` fields, `CLIENT_PREDICTION_AUDIT_DISCLAIMER` present verbatim on
  every non-null `client_baseline`). Confirmed the disclaimer's own stance: the platform audits the
  *comparison* between the client-supplied series and the naive baselines, and explicitly does **not**
  certify the *provenance* of the client's own predictions — this is the wording precedent the new form
  copy must mirror, not invent independently.
- `run_detail.html`'s rendering half (`DASH-125`'s honest "Model" label, `RAV-005`'s client-baseline chart
  overlay) already consumes `client_baseline`/`has_client_model` — confirmed via `RunDetailResponse`
  usage in `runs.py`'s `run_detail` handler (`model_column_label(run)` already passed to the template).
  This story does not need to touch `run_detail.html` or `runs_list.html`.
- Net: the backlog's own "discovered-done" claim holds exactly as written. This is a pure `dashboard-web`
  UI-submission-path gap, not a backend gap, not a contract gap, and not a rendering gap.

## Why this is a one-story sprint

`RPT-003` has no dependency on anything else in `backlog-trust-and-admin-ops.md` and nothing else in
that backlog depends on it. It is, on its own, a real, non-trivial change to the highest-traffic form in
`dashboard-web` (`run_new.html`/`runs.py`'s `run_new_submit`), reusing `dataset_reference`'s existing
two-mode (local file path / inline JSON) parsing pattern for a second, structurally similar but distinct
field, with its own DRY obligation (reuse the parsing code path, not a third independent implementation),
an explicit no-regression bar on the existing naive-only flow, and a positioning check on the new field's
copy against `CLIENT_PREDICTION_AUDIT_DISCLAIMER`'s own wording. That is comparable in shape/size to
`sprint-51`'s single-story `AI-004` sprint and smaller than `sprint-54`'s two-tightly-coupled-Musts
sprint — right-sized on its own, not artificially padded. Pairing it with an unrelated Should from Epic A
(Trust & Transparency) this same sprint would mix this Must's tight, single-file-region focus with a
different epic's own sequencing question (which of `TRUST-001`/`002`/`003`/`005` starts the epic) — a
call better made explicitly, as its own sprint, once this one ships. See "Next" below for that plan.

## Story in scope

1. **RPT-003** — Expose the already-built "audit my model's predictions" flow in `dashboard-web`.
   - Files touched: `services/dashboard-web/src/app/routers/runs.py` (`run_new_submit`'s `RunRequest`
     construction site gains an optional `client_prediction_reference`, built the same
     `path`/`inline`-mode way `dataset_reference` already is — reusing that exact parsing code path per
     the ticket's own DRY note, not a third independent reference-parsing implementation),
     `services/dashboard-web/src/app/templates/run_new.html` (new optional fieldset, clearly labeled
     "Your model's predictions (optional)," mirroring `dataset_reference`'s local-file-path/inline-JSON
     fieldset structure).
   - AC highlights (verbatim from the backlog, restated here for the Tech Lead's convenience, not
     reworded): submitting without this field must remain byte-identical to today's naive-only behavior;
     `RunRequest` includes `client_prediction_reference` only when supplied (`None` otherwise, matching
     `RunRequest`'s own honest-default convention, same precedent `UAT-008`'s `label` field already
     established); `run_detail.html` requires no change (its rendering path is already built and already
     tested); form copy must never imply the platform "improves," "corrects," or "certifies the
     provenance of" the tenant's own model — it states only that the platform compares the supplied
     series against the mandatory naive baselines under the leakage-aware protocol, mirroring
     `CLIENT_PREDICTION_AUDIT_DISCLAIMER`'s own wording (confirmed above, in `validation-service/README.md`).
   - Design note the Tech Lead should weigh, not a directive: `dataset_reference` itself has *three*
     modes today (path / inline / stored-dataset, `DASH-108`). The backlog's own AC text describes
     `client_prediction_reference` mirroring the field's "existing two-mode pattern" (path + inline) —
     confirm at ticket-breakdown time whether a third "stored dataset" mode for the client prediction
     series is in scope or a disclosed follow-on; the backlog text as written scopes two modes only, and
     this sprint plan does not expand that.

## Stories explicitly deferred

- Everything else in `backlog-trust-and-admin-ops.md` (`TRUST-001..005`, `RPT-001/002/004`,
  `ADMIN-001/002/003/005`, `ONB-001/002`) — not because it's low-value, but because `RPT-003` is the one
  Must and stands alone cleanly; deferred to subsequent sprints per the roadmap in "Next" below, not
  dropped.

## File-overlap / concurrent-work risk

- No other in-flight or immediately-next-sprint story touches `services/dashboard-web/src/app/routers/runs.py`
  or `services/dashboard-web/src/app/templates/run_new.html`. `TRUST-001`/`TRUST-005` (next epic, next
  sprint) touch `run_detail.html`, a different template in the same service — worth flagging to the Tech
  Lead as a same-service-different-file heads-up, not a same-file conflict.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

- This story lives entirely inside `services/dashboard-web` (trigger #8, already fired — the module is
  built and live) and calls only `gateway-api`'s already-existing `POST /runs` (implementation-plan.md
  section 2: `dashboard-web` calls `gateway-api` only, no direct DB access, no other service's code
  imported). No new endpoint, no new contract field, no migration — `client_prediction_reference` already
  exists on the shared `RunRequest` (`libs/common`) and is already threaded through `gateway-api` and
  `validation-service` (VS-017/VS-029, both already shipped).
- No leakage-aware protocol code (`naive_first_engine`, DM-test computation, mandatory Naive0/NaiveLast
  baselines) is touched or made conditional by this story — `validation-service/README.md`'s own
  confirmation (quoted above) that the two mandatory baselines are never conditional on
  `client_prediction_reference` stays true; this sprint adds a submission path to an already-additive
  field, nothing more.
- No trigger not yet fired (`libs/sdk` #9, a new ingestion connector #10, `services/economic-service` #11)
  is touched, consistent with the backlog file's own explicit out-of-scope statement.

## Definition of done for this sprint

- `RPT-003`'s acceptance criteria (as stated verbatim in `docs/product/backlog-trust-and-admin-ops.md`)
  are checked off in its ticket.
- Submitting the existing form with no client-prediction field filled in remains byte-identical to
  today's behavior — a regression test proves this, not just a manual check.
- A submission with a valid `client_prediction_reference` (both path and inline modes) reaches `POST
  /runs` with the field populated, and the resulting run detail page renders the client baseline via the
  already-existing, already-tested `DASH-125`/`RAV-005` rendering path with no template change required.
- The new field's copy passes the same banned-positioning-words check every other user-facing string in
  this service is tested against (CLAUDE.md) plus the specific "never implies improves/corrects/certifies
  provenance" check this story's own AC calls for.
- `services/dashboard-web/README.md` updated to record this submission path as shipped (README-current
  convention, per this repo's standing rule).
- `docs/product/backlog-trust-and-admin-ops.md`'s `RPT-003` entry marked done with acceptance-criteria
  boxes checked, pointing to its ticket file.
- `docs/tickets/README.md` gets a new Sprint 55 section (Tech Lead updates this when the ticket is
  created/closed, per this repo's standing convention — not done by this sprint plan itself).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after the ticket is Tech-Lead-verified done, before sign-off. QA scope should specifically,
  independently verify: the no-regression claim for the existing naive-only submission path; that a
  submitted client prediction actually reaches `validation-service` and produces a non-null
  `client_baseline` on the resulting run; and the positioning-copy check (no "improves"/"corrects"/
  "certifies provenance" language anywhere in the new field's labels, tooltips, or help text).

## Next (explicitly not this sprint, roadmap note for continuing this backlog)

Per `backlog-trust-and-admin-ops.md`'s own priority table (1 Must, 12 Should, 2 Could, 2 Won't) and its
sequencing note ("`TRUST-003` unlocks `TRUST-004`; `ONB-001` is the natural place to surface `ONB-002`'s
new action; everything else is independently schedulable"), the intended sequencing for subsequent
sprints, right-sized the same way this one is (roughly 1–3 stories per sprint, grouped for either a real
dependency or a tight file-overlap reason — not just priority-list order):

- **Sprint 56 (tentative)** — Epic A, Trust & Transparency, first slice: `TRUST-003` (per-run
  engine/config fingerprint — two new nullable `validation-service` columns + one pure hash function) and
  `TRUST-004` (auto-generated reproducibility statement — a `reporting-service` template addition that
  consumes `TRUST-003`'s new fields) sequenced together, `TRUST-003` first, since `TRUST-004` is its
  direct, stated dependent and is a small additive template change once `TRUST-003`'s fields exist.
- **Sprint 57 (tentative)** — Epic A, remainder: `TRUST-001` (permanent methodology panel, touches both
  `dashboard-web`'s `run_detail.html` and `reporting-service`'s `validation_audit.html.jinja`),
  `TRUST-005` (reframe "didn't beat naive" copy, touches the same two files/templates) — grouped together
  because both are copy/template additions to the same two files in the same two services, and `TRUST-002`
  (static leaky-vs-purged demo page, a new static route with no file overlap with the other two) as a
  third, independent story if sizing allows, or its own small sprint otherwise.
- **Sprint 58 (tentative)** — Epic C, Admin/Ops Maturity, first slice: `ADMIN-002` (operator action audit
  log — new `identity.operator_audit_log` table + two wired endpoints + a `dashboard-web` Settings page)
  on its own, given its own real scope (new table, new paginated endpoint, new UI page).
- **Sprint 59 (tentative)** — Epic C, remainder: `ADMIN-001` (health-transition webhook, `gateway-api`
  only) and `ADMIN-003` (crawl failure-detail surfacing, `ingestion-service` + `dashboard-web`) grouped
  together as two independent, narrowly-scoped, no-cross-dependency stories touching different services;
  `ADMIN-005` (self-serve API key rotation — the epic's highest-risk story, per its own lockout-guard
  note) sequenced as its own sprint instead, given the extra design care its acceptance criteria call for.
- **Sprint 60 (tentative)** — Epic D, Onboarding: `ONB-001` then `ONB-002` together (stated dependency;
  `ONB-001`'s confirmation-page next-step section is the natural place `ONB-002`'s new demo action
  surfaces from).
- **Sprint 61+ (tentative)** — Epic B remainder (`RPT-001` PDF export, `RPT-002` consistency-trend report
  kind, `RPT-004` report diffing — all Could/Should, independent of the other epics), sequenced last per
  the backlog's own scope note, `RPT-001` first (named B2B revenue-line value, cleanly additive to
  `reporting-service`'s existing Factory) before the two Coulds.

This roadmap is a sequencing sketch for continuity, not a committed plan — each future sprint still needs
its own PM pass (re-verify the backlog's citations against then-current code, confirm team
size/velocity, and write its own sprint file) before being handed to the Tech Lead.
