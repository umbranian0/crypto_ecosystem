# Backlog — Trust & Transparency and Admin/Ops Maturity

Source: `CLAUDE.md` (root — non-negotiable positioning: validation/audit infrastructure, never a
trading/prediction product; statistical accuracy != economic value, kept separate); `docs/da-tese-ao-produto.md`
(sections 1.2/1.3 for the DM/Harvey-correction/leakage-protocol facts this backlog's Trust stories must
tie back to, and section 1.3's own published numbers, used verbatim by `TRUST-002`); `docs/solution-design.md`
sections 3.1 (data quality gate), 3.4 (validation engine reproducibility), 3.5 (reporting), 3.6
(dashboard/SDK); `docs/implementation-plan.md` sections 2 (module boundary map), 6 (trigger-based build
order — no story here proposes anything for `libs/sdk` (trigger #9, unfired), `services/economic-service`
(trigger #11, deferred), or a new ingestion connector (trigger #10, unfired)), 7 (Factory/Repository/
Strategy patterns reused rather than reinvented below), 9 (DRY conventions); `docs/adr/0003-disclosed-trigger-override-pattern.md`;
`docs/product/backlog-first-run-setup-and-ops.md` (full text — confirms `SETUP-001`-`004`/`010`-`012`/
`015`/`020`-`022`/`030`/`034`/`035` are done, `SETUP-023` (alerting) and `SETUP-013`/`014` were declined
there, `SETUP-031`/`032`/`033` remain open Must/Could portability stories this backlog does not
duplicate); `docs/product/backlog-operability.md` (`OPS-006`/`007` — structured logging shipped, full
metrics/alerting stack declined); `services/reporting-service/README.md` (read in full — `RS-001`-`009`
done, PDF export and object-storage backing explicitly declined "this sprint", Factory-based report-kind
selection already built, disclosed trigger-#7 override already in place — not re-litigated here);
`services/reporting-service/src/app/templates/validation_audit.html.jinja` (read in full — the actual
rendered report structure `TRUST-001`/`004`/`005`/`RPT-001`/`002`/`004` extend); `services/dashboard-web/README.md`
(read in full, including the DM-verdict-chart/Harvey-caption section, the `verdict-label-*` CSS
convention, `RAV-009`/`010`'s cross-run trend view, `VS-017`'s client-baseline mechanism, and
`DASH-006`'s explicit no-pre-filled-defaults design rule — `ONB-002` is written to respect that rule, not
override it); `services/dashboard-web/src/app/static/style.css` (read directly — confirms `verdict-label-worse`
uses `#e0a06a`, an amber, not a pure red, and the codebase already has a test guarding against a
red/green better/worse pairing); `services/validation-service/README.md` (read in full — confirms
`VS-017`'s `client_prediction_reference`/`client_baseline` mechanism is fully built and exposed via
`POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`); `services/gateway-api/README.md` and
`scripts/revoke_api_key.py`/`scripts/provision_tenant.py` (read/grepped — confirm key issuance/revocation
today is operator-only or CLI-only, with no tenant-facing self-service path); `services/ingestion-service/README.md`
(read/grepped in full — confirms `crawl_runs.status` is a plain, unconstrained string with `"failed"` as
the only failure signal and no persisted rejection-reason/detail field, and that `INGEST-010`'s
`seed_tenant.py`/platform-CSV backfill mechanism already exists as an operator CLI action); `libs/common/src/naive_first_common/logging.py`
(read in full — structured JSON logs + a per-request correlation id exist; there is no persisted,
queryable audit-log table for privileged operator actions); `libs/naive_first_engine/pyproject.toml`
(confirms a real, bumpable `version = "0.1.0"` exists to fingerprint against, `TRUST-003`).

## Scope

Two themes from the brainstorm, prioritized as the strongest fit for this platform's audit-infrastructure
positioning, per the requester's own lean: **Trust & Transparency** (Epic A, `TRUST-*`) and **Admin/Ops
Maturity** (Epic C, `ADMIN-*`). The other two themes are scoped too, sequenced after: **Reporting depth**
(Epic B, `RPT-*`) and **Onboarding** (Epic D, `ONB-*`). Kept in one file, not split, because all four
epics come from the same single brainstorming pass and several stories cross-reference each other
(`RPT-003`/`ONB-003`, `TRUST-003`/`TRUST-004`) — splitting would duplicate the cross-reference text
`docs/product/backlog-first-run-setup-and-ops.md`'s own single-file, multi-epic structure already shows
is the right shape for a themed, same-session backlog like this one.

**Out of scope, stated explicitly, per this backlog's own governing instruction not to propose stories
for a module whose trigger hasn't fired**: nothing here touches `libs/sdk` (trigger #9), a new
ingestion connector/data source (trigger #10), or `services/economic-service` (trigger #11) — none of
those triggers have fired, and no story below is a second-order override of any of them. If, while
grooming this backlog, the Tech Lead or PM finds a genuine trigger firing for any of the three (e.g. a
client asking to submit predictions programmatically, which would be `libs/sdk`'s trigger), that is a
stop-and-flag moment, not something to fold into a story here.

**No story in this backlog authorizes skipping the leakage-aware protocol.** Every story here is UI,
reporting, admin-surface, or metadata/audit-trail work built around `naive_first_engine`'s existing
output — none proposes computing splits/baselines/metrics/DM results differently, fitting preprocessing
globally, or bypassing the mandatory Naive0/NaiveLast baselines.

## Prioritization scheme

MoSCoW, the same convention every other backlog file in `docs/product/` already uses. Each story's
one-line rationale ties back to what it unlocks and the owning module's owns/does-not-own boundary.

---

## Epic A — Trust & Transparency (`TRUST-*`)

Starting point, stated honestly before any story below: this is not greenfield. The DM/Harvey
correction is already disclosed in one place — `_dm_verdict_chart.html`'s caption states plainly that
"better"/"worse" are "under the Harvey et al. (1997)-corrected Diebold-Mariano test already applied
upstream," and the audit report's own section 5 already carries a permanent statistical-vs-economic
disclaimer. And the "model didn't beat naive" UI state is already substantially non-alarming by
design: `verdict-label-worse` renders in `#e0a06a` (amber), not a pure red, specifically because
`style.css`'s own comment and `test_style_css_dm_verdict_colors_never_pair_pure_red_and_pure_green`
already forbid a red/green better/worse pairing. The gaps below are real, but narrower than "build this
from scratch."

### TRUST-001 — Permanent, standalone methodology disclosure panel (not just a chart caption) [Should] — DONE (Sprint 57)

As a tenant or third party reading a run's results or a generated audit report, I want a permanent,
always-visible section stating the leakage-aware protocol's fixed parameters (rolling-origin
walk-forward, configurable purge gap, mandatory Naive0/NaiveLast baselines, Diebold-Mariano with the
Harvey et al. 1997 long-run variance correction for overlapping horizons), so that the methodology claim
is visible regardless of which chart happens to render, not dependent on reading one chart's caption.

Acceptance criteria:
- [x] `dashboard-web`'s `GET /runs/{run_id}` renders a new, always-visible (not gated on `{% if splits %}`,
  unlike today's DM-verdict-chart caption) "Methodology" panel stating the same four facts named above,
  in plain language, reusable across every run regardless of status or split count.
- [x] `reporting-service`'s `validation_audit.html.jinja` gains an equivalent always-visible "Methodology"
  subsection (today's section 2, "Leakage-protocol parameters," states the run's own parameter values but
  never names Diebold-Mariano or the Harvey correction by name) — extends section 2, does not duplicate
  section 5's existing statistical-vs-economic disclaimer.
- [x] The exact wording is one shared constant (mirroring `FHS-004`'s `CAVEAT_SENTENCE` precedent — a
  single source of truth, not two independently drifting copies). As actually shipped, this AC's own
  original text ("authored once... kept identical by a shared test/fixture in each service, not literally
  imported cross-service") describes a mechanism that turned out not to work: each service's same-text
  test only compared its own copy against another literal in its own test file, so nothing cross-checked
  the two services and editing one left the other silently stale. Corrected post-review (commit `a780493`):
  the constant lives once in `libs/common` as `naive_first_common.disclosures.METHODOLOGY_FACTS`, imported
  by both services — a `libs/*` shared package, not one *service* importing another service's code, so
  implementation-plan.md section 2's module-boundary rule is unaffected; CLAUDE.md's DRY rule (cross-module
  duplication belongs in `libs/*`) governs here instead.
- [x] Positioning check: wording never implies "the system predicts prices" — it describes the validation
  methodology, matching every other user-facing string in both services (CLAUDE.md).

Rationale for priority: Should — the underlying fact is already computed and already disclosed once; this
is a visibility/completeness fix (always-on vs. chart-conditional), not a new capability, but it's the
single most concrete "make the rigor visible" ask in the brainstorm, so it doesn't drop to Could.
Depends on: none

See `docs/tickets/TRUST-001-01.md` (dashboard-web) and `docs/tickets/TRUST-001-02.md` (reporting-service)
for the full implementation record, including the libs/common supersession.

### TRUST-002 — Static "leaky vs. purged walk-forward" side-by-side demo using the thesis's own numbers [Should] — DONE (Sprint 57)

As a prospective tenant or evaluator who has never used this platform, I want a static page showing,
side by side, what the thesis's own results looked like with a naive/leaky evaluation methodology versus
the purged, leakage-aware one this platform enforces, so that I understand concretely why the
purge-gap/naive-first protocol matters, using real numbers instead of an abstract claim.

Acceptance criteria:
- [x] A new static page (e.g. `/help/leakage-demo`, sibling to `UAT-014`'s existing `/help/concepts` page
  — same router module, same "no backend call, static content" pattern, not a new mechanism).
- [x] Content is the thesis's own real, already-published numbers from `docs/da-tese-ao-produto.md`
  section 1.3 (e.g. OLS's headline vs. Naive0 at 1h/6h/24h, DM better/worse split counts) — no fabricated
  or illustrative-only numbers standing in for real ones.
- [x] The "leaky" side is described honestly as what the protocol change protects against (e.g. "a naive
  random-split or globally-fit-preprocessing evaluation would have reported the model as competitive; the
  purge-gap/train-only-fit protocol this platform enforces reports the same model honestly losing to
  Naive0 in MAE/RMSE at every horizon") — not a fabricated re-run of the thesis under a leaky protocol (no
  such re-run is available or in scope; the "leaky" column is descriptive/didactic, not itself computed by
  this platform).
- [x] Positioning check: explicitly reinforces, not contradicts, the core finding (CLAUDE.md: no model
  beat naive stably) — this page cannot read as "buy this model," only "this is why validation discipline
  matters."
- [x] Linked from `TRUST-001`'s methodology panel and from `/help/concepts`.

See `docs/tickets/TRUST-002.md` for the full implementation record.

Rationale for priority: Should — real trust-building value, cheap to build (static content, no backend
change, no new data), directly serves the platform's own stated sales argument (da-tese-ao-produto.md
section 2.5's core sales pitch: "we know how models can look good without being good -- because we tested
that ourselves").
Depends on: none

### TRUST-003 — Per-run config/engine fingerprint for later re-verification [Should] — DONE (Sprint 56)

**Status: done.** Implemented in `docs/sprints/sprint-56.md` / `docs/tickets/TRUST-003.md`:
`services/validation-service` gained migration `0012_add_runs_engine_fingerprint_columns.py`
(`runs.engine_version`/`runs.config_fingerprint`, both nullable `String`, deliberately no
`server_default`) and `src/app/fingerprint.py` (`get_engine_version()`/`compute_config_fingerprint()`),
wired into `_persist_new_run` so every run row created from this migration forward gets both fields
populated at `create_run` time regardless of eventual outcome; `libs/common`'s `RunDetailResponse`
gained matching `engine_version`/`config_fingerprint: str | None = None` fields. See that ticket for the
full Analysis/Design/Implementation/Test/Review/Documentation record.

As a future auditor or the tenant themselves, re-examining a run months later, I want each run to persist
a fingerprint of exactly what produced it (the `naive_first_engine` library version, plus a hash of the
run's own already-persisted `split_config`), so that "prove this run used protocol X" is answerable from
the run record itself, not just asserted.

Acceptance criteria:
- [x] `validation-service`'s `runs` table gains two new nullable columns (new migration, following the
  same additive-nullable-column precedent `runs.warnings`/`runs.feature_lineage` already established):
  `engine_version` (the `naive_first_engine` package version string, e.g. read from its installed
  distribution metadata — `libs/naive_first_engine/pyproject.toml` already declares a real, bumpable
  `version = "0.1.0"` to source this from) and `config_fingerprint` (a deterministic hash, e.g. SHA-256, of
  the run's own `split_config` JSON — canonicalized key order so the same config always hashes
  identically).
- [x] Both fields are populated at `POST /runs` time, before `run_validation_protocol` is invoked, and are
  `null` only for runs created before this migration (a disclosed, not silently-backfilled, gap — no
  retroactive fingerprinting of historical runs in this story's scope).
- [x] `RunDetailResponse` (`libs/common`, `naive_first_common.contracts`, ARCH-003) is extended with both
  fields, consumed verbatim (not recomputed) by `dashboard-web`'s run detail page and `reporting-service`'s
  report renderer — one source of truth, no second hash computed downstream.
- [x] A unit test proves the same `split_config` always produces the same `config_fingerprint`, and a
  differing config (even a single differing value) produces a different one.

Rationale for priority: Should — real audit-infrastructure value (solution-design.md's own design
principle 4: "everything the validation engine touches is reproducible and auditable"), bounded scope (two
columns + one pure hash function), and is the direct prerequisite `TRUST-004` needs.
Depends on: none

### TRUST-004 — Auto-generated reproducibility statement per report [Should] — DONE (Sprint 56)

**Status: done.** Implemented in `docs/sprints/sprint-56.md` / `docs/tickets/TRUST-004.md`, sequenced
strictly after `TRUST-003`: `services/reporting-service/src/app/templates/validation_audit.html.jinja`
gained a new "2.5. Reproducibility statement" subsection, positioned between section 2
("Leakage-protocol parameters") and section 3 ("Results table (per split)"), rendering
`engine_version`/`config_fingerprint`/`dataset_id` plus a fixed reproducibility-expectation sentence for
a fingerprinted run, or an explicit "not available for runs created before this platform tracked engine
fingerprints" note for a null-fingerprint (pre-`TRUST-003`) run — never a fabricated value. Template-only
change; `ValidationAuditRenderer`/`generation.py` required zero Python code change. See that ticket for
the full Analysis/Design/Implementation/Test/Review/Documentation record.

As a report reader, I want a short, auto-generated "how to reproduce this exact result" statement on
every audit report, so that reproducibility is a stated, checkable claim, not just an implicit property
of the protocol.

Acceptance criteria:
- [x] `reporting-service`'s `validation_audit.html.jinja` gains a new subsection (after today's section 2,
  "Leakage-protocol parameters") stating: the `naive_first_engine` version (`TRUST-003`'s
  `engine_version`), the `config_fingerprint`, the dataset reference/source used, and a fixed sentence
  stating that re-running this exact configuration against the same dataset and library version is
  expected to reproduce these results, and a different result under the same fingerprint should be
  investigated as a regression.
- [x] Populated programmatically from the already-persisted run record (`TRUST-003`'s two new fields plus
  existing `dataset_id`/`dataset_reference` metadata already on the run) — never hand-typed, same
  "populated programmatically where possible" convention `solution-design.md` section 3.5 already states
  for the leakage checklist.
- [x] A run created before `TRUST-003`'s migration (so `engine_version`/`config_fingerprint` are `null`)
  renders this subsection with an explicit "not available for runs created before this platform tracked
  engine fingerprints" note, never a fabricated fingerprint.

Rationale for priority: Should — small, additive template change once `TRUST-003` exists; directly
strengthens the "auditable, not just accurate" positioning this whole platform is built on.
Depends on: TRUST-003

### TRUST-005 — Reframe "model didn't beat naive" copy as the expected, first-class scientific finding [Should] — DONE (Sprint 57)

As a tenant or reader seeing a "worse" or "no significant difference" verdict, I want the report's own
language to state plainly that this is a common, expected, scientifically valid outcome — consistent with
this platform's own founding result — rather than reading only as a recommendation to fall back to naive,
so that the finding doesn't read as a malfunction or a discouraging surprise.

Discovered-done note, stated honestly: most of this is already right — neutral amber-not-red styling
(`verdict-label-worse`, `style.css`), and the report's per-split language ("the model did not beat naive
on this split -- Naive0 performed significantly better") is already factual, not alarmist. The one
concrete remaining gap: `validation_audit.html.jinja`'s section 6 ("Recommendations") only says to "treat
the naive baseline as the safer default" when a model loses — it never states that losing to naive is
itself the common, expected finding this platform's own published research established, which is the one
sentence needed to make a "worse" verdict read as validating the process, not merely as "your model didn't
win."

Acceptance criteria:
- [x] `validation_audit.html.jinja`'s "Overall" verdict paragraph (today's `{% if better_count == 0 %}`
  branch) gains one additional sentence for the `better_count == 0` case only: a plain statement that under
  rigorous, leakage-free validation, most models — including sophisticated ones — do not beat a strong
  naive baseline in a stable way, so this outcome is common and not evidence of a broken evaluation.
- [x] The added sentence does not soften or hide the actual verdict (the "did not beat naive" language
  stays exactly as-is) — it is additive context, not a replacement for the honest result.
- [x] `dashboard-web`'s run detail page gains the equivalent sentence in the same condition (a run whose
  `better_count == 0` across its splits), reusing the same wording precedent `TRUST-001` establishes for
  shared cross-service copy — in the actually-shipped form, that precedent is the `libs/common` shared
  constant `a780493` established, not per-service copy-paste (disclosed deviation, see
  `docs/tickets/TRUST-005-01.md`/`TRUST-005-02.md`'s own "Superseded in part" notes).
- [x] Positioning check: the added sentence never implies any model should beat naive, only that not
  beating it is expected and valid (CLAUDE.md's core finding, restated honestly, not softened into "your
  model is fine anyway").

See `docs/tickets/TRUST-005-01.md` (dashboard-web) and `docs/tickets/TRUST-005-02.md` (reporting-service)
for the full implementation record.

Rationale for priority: Should — the styling/factual-language half of this is already done, so this is a
small, high-leverage copy-only change (no new field, no new endpoint) that closes the one real remaining
gap.
Depends on: none

---

## Epic B — Reporting depth (`RPT-*`)

Sequenced after Epic A/C per the requester's own lean. One story here (`RPT-003`) is escalated to Must
despite that lean — see its own rationale for why.

### RPT-001 — Certification-style PDF export [Should]

As a tenant or third party who needs an audit artifact outside a browser (e.g. for a compliance file, an
investor packet, an M&A due-diligence bundle), I want a PDF version of a generated report, so that the
report is usable the way `da-tese-ao-produto.md` section 2.3.4's "certification/seal" revenue line
actually requires (a deliverable document, not only an HTML page behind auth).

Discovered-done note: `reporting-service`'s own README already discloses this exact gap plainly -- "PDF
export is also out of scope this sprint (HTML only, backlog decision 3)" -- this story is that
already-named, already-deferred follow-up, not a fresh discovery.

Acceptance criteria:
- [ ] `reporting-service` adds WeasyPrint (the tool `solution-design.md` section 3.5 already named as the
  intended PDF path) as a dependency, and a new code path renders the same `ValidationAuditRenderer` HTML
  output to PDF — one rendering source (the existing Jinja2 template), two output formats, not a second,
  divergent report-content implementation.
- [ ] `GET /reports/{id}` gains an `?format=pdf` option (or an equivalent new route, Tech Lead's call at
  ticket time) returning `application/pdf`; the default (no `format`) stays byte-identical to today's HTML
  response — no breaking change to any existing caller.
- [ ] A status-only report (run not yet `"completed"`) renders a status-only PDF, same content parity the
  HTML path already guarantees — no fabricated metrics table in either format.
- [ ] `reporting-service`'s README's "PDF export is out of scope" line is updated to reflect this shipped,
  per this repo's "docs stay current" convention.

Rationale for priority: Should — real, named B2B revenue-line value (docs section 2.4's paid
audit/certification line), but sequenced after Epic A/C per the requester's stated lean and because no
pilot client has asked for a downloadable artifact yet (same disclosed-override posture the rest of this
platform already uses honestly).
Depends on: none

### RPT-002 — Package the existing cross-run consistency trend as an archivable report artifact [Could]

As a tenant or auditor, I want the "beat Naive0 in N of M completed runs" consistency view
(`RAV-009`/`RAV-010`, already live at `dashboard-web`'s `GET /runs/trend`) available as a versioned,
storable report the same way a single-run audit report already is, so that a point-in-time consistency
snapshot can be archived and compared later, not only viewed live.

Acceptance criteria:
- [ ] `reporting-service`'s existing Factory (`get_report_renderer(kind)`, `RS-003`) gains a second `kind`,
  e.g. `"consistency_trend"`, alongside the existing `"validation_audit"` — the extension point this
  Factory was explicitly built for (docs section 2.6 phase 5: "certification seal / continuous-monitoring
  digest later"), not a new dispatch mechanism.
- [ ] The new renderer consumes the same tenant-scoped run history `dashboard-web`'s `RAV-009`/`010`
  already query via `gateway-api`'s `GET /runs` — reads through that same contract, not a new aggregation
  computed independently (avoiding two implementations of "beat naive in N of M runs").
- [ ] `POST /reports/generate` accepts an optional `kind` field (default `"validation_audit"`, backward
  compatible) rather than inferring it from `run_id` alone, since a consistency-trend report is not scoped
  to one run.
- [ ] HTML output only this story (mirrors `RS-002`'s own "out of scope this sprint" precedent for PDF) —
  `RPT-001`'s PDF path can be extended to this `kind` in a later, separate ticket, not bundled here.

Rationale for priority: Could — real value, but this is explicitly "docs section 2.6 phase 5" work
(certification/continuous-monitoring) which the roadmap itself sequences after the core audit-report line;
no pilot client has asked for an archivable trend snapshot yet.
Depends on: none (reuses `RS-003`'s existing Factory)

### RPT-003 — Expose the already-built "audit my model's predictions" flow in `dashboard-web` [Must] — DONE (Sprint 55)

**Status: done.** Implemented in `docs/sprints/sprint-55.md` / `docs/tickets/RPT-003.md` — `run_new.html`
gained a new, clearly optional "Your model's predictions (optional)" fieldset (local file path / inline
JSON, a disclosed two-mode-not-three-mode scope call — see the ticket's Design section for the full
reasoning), `run_new_submit` wires it into `RunRequest.client_prediction_reference` only when supplied,
`run_detail.html` required zero change (already rendered a client baseline whenever present, VS-017/VS-029/
DASH-125/RAV-005). See that ticket for the full Analysis/Design/Implementation/Test/Review/Documentation
record.

As a tenant with predictions from their own model, I want `dashboard-web`'s "Submit a run" form to let me
supply my own prediction series (alongside the target dataset), the same way `POST /runs` already accepts
it, so that I can actually perform this platform's core "bring your own predictions, get an honest
naive-first verdict" workflow (`da-tese-ao-produto.md` section 2.3.6) through the UI, not only via a raw,
undocumented-to-a-tenant API call.

Discovered-done note, and why this is the one Must in this epic: the backend half of this is already fully
built — `validation-service`'s `VS-017` (`client_prediction_reference`, wired through `POST /runs`/`GET
/runs/{id}`/`GET /runs/{id}/splits`, with its own mandatory audit disclaimer already attached to every
response) and `dashboard-web`'s own rendering half (`DASH-125`'s honest "Model" label, `RAV-005`'s
client-baseline chart overlay) are done and tested. Confirmed directly against
`services/dashboard-web/src/`: `client_prediction_reference` appears nowhere in `runs.py` or
`run_new.html` — `GET /runs/new`'s form has no field for it at all. This means the platform's own headline
capability — the entire reason `da-tese-ao-produto.md` names "bring your own model" as Subsystem 6 — is
reachable today only by a tenant hand-crafting a raw HTTP `POST /runs` call, not through the dashboard a
pilot client is actually expected to use. That gap is why this is Must, not Should, despite the epic's
overall lower sequencing.

Acceptance criteria:
- [x] `GET /runs/new`/`POST /runs/new` (`src/app/routers/runs.py`) gain an optional
  `client_prediction_reference` input, mirroring `dataset_reference`'s existing two-mode pattern (a local
  file path field and an inline-payload JSON textarea) — reusing the same parsing/validation code path
  `dataset_reference` already uses (DRY, implementation-plan.md section 9), not a third, independent
  reference-parsing implementation.
- [x] The field is clearly optional and labeled as such (e.g. "Your model's predictions (optional) --
  leave blank to evaluate Naive0/NaiveLast only") — submitting without it must remain byte-identical to
  today's behavior (no regression to the existing naive-only flow).
- [x] `RunRequest` construction includes `client_prediction_reference` only when supplied (`None`
  otherwise, matching `RunRequest`'s own honest-default convention, same precedent `UAT-008`'s `label`
  field already established).
- [x] `run_detail.html` (already rendering `client_baseline`/`has_client_model` per `DASH-125`/`RAV-005`)
  requires no change — this story only adds the missing submission path, the rendering path is already
  built.
- [x] Positioning check: form copy never implies the platform "improves," "corrects," or "certifies the
  provenance of" the tenant's own model — it states only that the platform will compare the supplied
  series against the mandatory naive baselines under the leakage-aware protocol, mirroring `VS-017`'s own
  `CLIENT_PREDICTION_AUDIT_DISCLAIMER` wording.

Rationale for priority: Must — this is not new product scope, it is closing the single largest gap between
what the backend already honestly supports and what a real pilot client can actually reach through the UI;
every other story in this epic is lower-leverage than making the platform's own named headline capability
(Subsystem 6, "bring your own model") usable at all without a raw API call.
Depends on: none (all backend pieces already shipped)

### RPT-004 — Report diffing across re-runs [Could]

As a tenant who re-audits a model after fixing an issue, I want to see a diff between two reports for the
same (or a related) dataset, so that I can see concretely what changed, not just two independent report
pages I have to compare by eye.

Acceptance criteria:
- [ ] A new `GET /reports/{id}/diff/{other_id}` (or equivalent, Tech Lead's call) computes a field-level
  diff between two already-persisted reports' underlying metrics (per-split `model_*`/`naive0_*`/`dm_*`
  values), not a text/HTML diff of the rendered page.
- [ ] Rejects (with a clear error, not a nonsensical diff) two reports for genuinely incomparable runs
  (e.g. different horizons or different dataset sources) — the Tech Lead defines the exact comparability
  rule at ticket time, but it must be a real, stated rule, not silently comparing apples to oranges.
- [ ] `dashboard-web` surfaces this as a simple "compare with a previous report" action from the report
  viewer (not yet built as of this backlog — depends on a report viewer existing in `dashboard-web` first,
  which is itself not in either service's current scope; note this dependency plainly rather than silently
  assuming a viewer exists).

Rationale for priority: Could — real value, but the heaviest story in this epic (a new comparability rule,
a new endpoint, a UI surface that itself doesn't exist yet) and the lowest-leverage relative to `RPT-003`'s
existing-capability-exposure fix; defer until a real re-audit use case is reported.
Depends on: none, but practically blocked on a `dashboard-web` report viewer existing (not currently
scoped anywhere)

---

## Epic C — Admin/Ops Maturity (`ADMIN-*`)

### ADMIN-001 — Narrow, single-signal notification on health-state transition (re-evaluated from `SETUP-023`'s decline) [Should]

As an operator, I want a single, minimal notification (not a paging/alerting stack) fired when
`gateway-api`'s aggregate `GET /system/health` (`SETUP-020`) flips from all-healthy to any-degraded/
unreachable, so that I don't have to be actively looking at `/monitoring` at the exact moment something
breaks, without standing up the full alerting/on-call system `OPS-007`/`SETUP-023` already, correctly,
declined.

Real re-evaluation, not a habitual re-decline: `SETUP-023`'s own stated revisit trigger was "a real
incident visibility alone didn't prevent, or a real pilot client requiring an SLA." Neither has happened —
there is still no pilot client and no reported incident. That trigger has not fired, and a full
alerting/paging stack (escalation policies, multi-channel routing, on-call rotation) remains unjustified
for a single-operator, no-SLA, local-first deployment — building one now would be exactly the premature
infrastructure this repo's own conventions warn against. But the accumulated surface
(`SETUP-020`/`021`/`022`, all now built) has a real, narrower gap worth naming honestly: today, every one
of those signals is pull-only — an operator must actively load `/monitoring` to see anything. The smallest
correct escalation from "Won't" is a single one-way push on the one binary signal that matters most (is
the aggregate health check still green), not a rebuilt alerting product.

Acceptance criteria:
- [ ] A single, optional `MONITORING_WEBHOOK_URL` env var (unset by default, same disclosed-optional
  convention `NARRATIVE_API_URL` already uses) — when set, `gateway-api` POSTs a small, fixed-shape JSON
  payload (`{"event": "health_transition", "previous_status": ..., "current_status": ..., "at": ...}`) to
  that URL exactly once per transition (healthy to degraded/unreachable, and the reverse recovery
  transition), never on every poll.
- [ ] No retry/backoff/queueing logic beyond a single best-effort POST with a short timeout — a failed
  webhook delivery is logged (`OPS-006`'s structured logging) and dropped, never blocks or crashes the
  health-check path itself.
- [ ] Explicitly out of scope, stated in this story itself (so it cannot silently reopen `OPS-007`'s
  declined scope): no escalation policy, no multiple channels/recipients, no acknowledgement/snooze
  mechanism, no paging-service integration (PagerDuty/Opsgenie/etc.) — one URL, one event shape, fire and
  forget.
- [ ] `infra/README.md`/`gateway-api`'s README document this as a deliberately minimal notification
  primitive, not a monitoring/alerting subsystem, with the same "revisit when a real trigger fires" framing
  `SETUP-023`/`OPS-007` already use for the fuller version.

Rationale for priority: Should — a real, bounded, cheap escalation of the accumulated monitoring surface
now that `SETUP-020`/`021`/`022` all exist, but deliberately kept to the smallest correct scope so it does
not reopen the already-declined full alerting stack.
Depends on: SETUP-020 (already shipped)

### ADMIN-002 — Operator action audit log [Should]

As the platform owner, I want every privileged operator action (tenant creation, API key revocation,
connector-credential status lookups) persisted to a durable, queryable audit trail, so that this
audit/validation platform has the same auditability over its own administration that it sells to tenants
over their models — today it does not.

Real gap, confirmed directly: `libs/common`'s structured logging (`OPS-006`) gives every log line a
correlation id and a JSON shape, but log lines are not a durable, queryable audit trail (no persistence
guarantee, no schema, not scoped to "privileged action" specifically) — and no `audit_log`-shaped table
exists anywhere in `identity`/`gateway-api`'s schema today.

Acceptance criteria:
- [ ] A new `identity.operator_audit_log` table (`gateway-api` owns the `identity` schema per
  implementation-plan.md section 5) with, at minimum: `id`, `action` (e.g. `"tenant.create"`,
  `"api_key.revoke"`), `target_tenant_id` (nullable, the tenant acted upon), `at` (timestamp),
  `correlation_id` (joins back to `OPS-006`'s existing structured logs for full request context) — never
  the operator token itself, hashed or otherwise (there is only one shared token today, `SETUP-010`;
  logging it, even hashed, adds no value and is a needless secret-adjacent surface).
- [ ] Every existing operator-authenticated mutating endpoint (`POST /tenants`, the API-key revoke
  endpoint, both `SETUP-011`) writes one row on success — write-on-success only in this story's scope; a
  rejected/`403` attempt is already captured by `OPS-006`'s existing structured logs and is not duplicated
  into this table (a deliberate, disclosed scope line, not an oversight).
- [ ] A new operator-authenticated `GET /operator-audit-log` (paginated, same `limit`/`offset` convention
  `GET /runs`/`GET /tenants` already use) is added, and surfaced read-only in `dashboard-web`'s Settings
  area (a new, small page, or a section on an existing one — Tech Lead's call), matching `SETUP-012`'s
  existing "operator session required" gate.
- [ ] Positioning/security check: this log is additive audit trail only — it introduces no new way to
  mutate tenant state, and no raw secret (API key, operator token) ever appears in a row.

Rationale for priority: Should — directly closes a real credibility gap for a platform whose entire value
proposition is "we audit rigorously" (`da-tese-ao-produto.md` section 2.2) while having no persisted trail
of its own administrative actions; bounded scope (one table, wired into two already-existing endpoints).
Depends on: SETUP-010, SETUP-011 (both already shipped)

### ADMIN-003 — Surface why a crawl failed, not just that it failed [Should]

As an operator or tenant looking at a failed crawl on the Monitoring/`/datasets` pages, I want to see the
actual failure reason (e.g. "credential rejected by Reddit," "connector timeout," "malformed response from
source"), not only the bare word `"failed"`, so that I can act on it without reading container logs.

Scope correction, stated honestly: `solution-design.md` section 3.1 describes a "data quality gate"
concept (coverage %, gap detection, quarantine-with-report) as part of the original design — that
subsystem, as originally envisioned, is not built; there is no separate quarantine/quality-scoring step
distinct from a crawl simply succeeding or raising an exception. The real, concrete, buildable gap today
(confirmed directly against `services/ingestion-service/README.md`) is narrower and more actionable:
`crawl_runs.status` is a plain, unconstrained string, and `record_crawl_run(..., status="failed")` is
written on any exception during fetch, with no accompanying reason/detail column persisted or surfaced
anywhere. This story closes that specific, real gap — it does not build the broader solution-design.md
quality-gate subsystem, which remains unscoped (and would need its own trigger discussion, since
coverage/gap-detection heuristics are new capability, not a visibility fix).

Acceptance criteria:
- [ ] `ingestion.crawl_runs` gains a nullable `failure_detail` column (new migration, same additive
  precedent `validation-service`'s `runs.failure_reason` already established for exactly this shape of
  problem) — populated with `str(exc)` (or a curated message where the connector already raises a
  descriptive exception) at the same call site that already sets `status="failed"`.
- [ ] `GET /connectors/{source}/status` includes `failure_detail` (nullable, `null` for any non-`"failed"`
  status) in its response.
- [ ] `dashboard-web`'s crawl-status panel (`DASH-109`/`115`) renders `failure_detail` when present, next
  to the existing status badge — no new page, extends the existing panel.
- [ ] No raw credential, connection string, or stack trace is ever placed in `failure_detail` — same
  discipline every other user-facing error message in this platform already follows (`GET /health`'s
  generic `"database unreachable"` convention is the model to follow, adapted to be more specific here
  since this is operator/tenant-facing troubleshooting context, not a public unauthenticated endpoint — the
  Tech Lead should define the exact allowed message shape per connector at ticket time).

Rationale for priority: Should — real, concrete, narrowly-scoped visibility gap with an existing
column-precedent to follow; explicitly does not overreach into the unbuilt, larger "data quality gate"
concept.
Depends on: none

### ADMIN-004 — Tenant-facing usage/quota view [Won't, this backlog]

As a tenant, I want to see how much of my quota/plan I've used.

Rationale: Won't, this backlog. Confirmed by grep: no quota, plan-tier, or usage-limit concept exists
anywhere in this platform — no rate limiting, no metering, no billing/plan model. This is the same YAGNI
reasoning `backlog-infra.md`'s `INF-017` (DB-backed config) and this backlog's own sibling `SETUP-014`
(feature flags) already applied and were correctly declined for: building a "usage" view with nothing
being measured or enforced against would be speculative UI over a mechanism that doesn't exist. What
partial value this idea has is already available: a tenant can already see their own run count via the
existing paginated `GET /runs` (`total` field, `UAT-009`'s pagination). Revisit the day a real
pricing/plan-tier decision is made, or a real pilot client asks "how much have I used" — not before.
Depends on: none

### ADMIN-005 — Self-serve API key rotation for tenants [Should]

As a tenant, I want to mint a new API key for myself and revoke an old one from my own logged-in session,
so that routine credential hygiene (e.g. after a suspected leak, or periodic rotation) does not require
contacting an operator or having host/container access to a CLI script.

Discovered-done note: confirmed by reading both scripts and `SETUP-011`/`012` directly — every existing
key-lifecycle path is either operator-gated (`dashboard-web`'s Settings -> Tenants page, `SETUP-012`,
itself requiring the separate `OPERATOR_TOKEN`) or CLI-only, host-access-gated
(`provision_tenant.py`/`revoke_api_key.py`, explicitly documented as "operator/test-fixture tool, not a
tenant-self-service mechanism"). There is no path today for a tenant, authenticated as themselves, to
manage their own key.

Acceptance criteria:
- [ ] A new tenant-authenticated (not operator-authenticated — the caller's own existing API key/session is
  the credential, same `get_authenticated_tenant` dependency every other tenant-facing endpoint already
  uses) `POST /me/api-keys` on `gateway-api`, minting a new key for the caller's own tenant, reusing the
  same key-generation/hashing code `provision()` already uses (DRY, one key-minting implementation, three
  callers: CLI, operator UI, now self-service).
- [ ] A new `POST /me/api-keys/{key_id}/revoke`, tenant-authenticated, scoped to the caller's own tenant
  only (never another tenant's key, enforced the same way every other tenant-scoped query in this platform
  already is) — reuses `ApiKeyRepository.revoke_key`, not a second revocation code path.
- [ ] Lockout guard, stated explicitly as the highest-risk part of this story: since a tenant authenticates
  with an API key, revoking the key currently in use would immediately lock the caller out mid-session. The
  endpoint/UI flow must enforce "mint the new key first, confirm it's usable, only then offer to revoke the
  old one" as the only path — never a single-step "replace my key" action that could revoke-before-confirm.
  `dashboard-web`'s UI additionally shows an explicit warning before revoking the key the tenant is
  currently using to view that very page.
- [ ] `dashboard-web` gains a new, tenant-session-gated (the existing `session_id` cookie, `DASH-002`/`003`
  — not the operator session) "My API Keys" page, listing the tenant's own keys (metadata only, same
  never-show-a-raw-key-after-creation rule `SETUP-012`'s one-time-reveal template already enforces, reused
  verbatim here — not a second reveal template) with "create new" / "revoke" actions.
- [ ] A test proves a tenant's self-service call cannot list, create, or revoke a key belonging to any
  other tenant (the cross-tenant-isolation case every other tenant-scoped endpoint in this platform is
  already tested against).

Rationale for priority: Should — real security-hygiene and operator-toil-reduction value, bounded scope
(reuses existing key-minting/revocation functions and the existing one-time-reveal template), but the
lockout-guard design needs real care, so it doesn't rank above the epic's other, lower-risk stories.
Depends on: none (all backend building blocks -- `provision()`, `ApiKeyRepository.revoke_key`,
`get_authenticated_tenant`, the one-time-reveal template -- already exist)

---

## Epic D — Onboarding (`ONB-*`)

### ONB-001 — Guided first-run wizard: next-step orientation beyond key reveal [Should]

As a fresh operator who just completed `SETUP-003`'s wizard, I want the key-reveal confirmation page to
point me to a concrete next step (seed sample data, submit a first run), so that "guided" covers getting
to a first real result, not only getting a tenant and a key.

Scope check against `SETUP-003`, stated honestly: `SETUP-003` (done) covers exactly tenant-name-in,
API-key-shown-once-out, then a link to `/login` — a real, working, but minimal slice. This story is the
literal next-step gap: after `/login`, a fresh tenant with zero data and zero runs has no in-product
guidance toward "seed some data" or "submit a run," despite both being possible today.

Acceptance criteria:
- [ ] `SETUP-003`'s existing key-reveal confirmation page gains a short "what's next" section with two
  links: one to `/runs/new` (submit a run — already exists) and one explaining, in plain operator-facing
  language, that sample data can be seeded via `seed_tenant.py` (`INGEST-010`, already exists,
  CLI/operator-only — this story documents/links to it, it does not rebuild it; see `ONB-002` for making
  this reachable without a CLI).
- [ ] No change to `SETUP-002`/`SETUP-003`'s actual tenant/key-creation logic — this is copy/navigation
  only, added to the existing confirmation page.
- [ ] Positioning check: "next step" language describes submitting a validation run / seeding ingested data
  only — never "get your first prediction" or similar (CLAUDE.md).

Rationale for priority: Should — small, additive, closes a real "then what?" gap in an otherwise-working
wizard.
Depends on: SETUP-003 (already shipped)

### ONB-002 — A reachable "try a demo run" action, distinct from the real submission form's no-defaults rule [Should]

As a fresh operator or evaluator with no data of their own yet, I want a clearly-labeled "try a demo
validation run" action that seeds a small sample dataset and submits one pre-configured run against it, so
that I can see a real result immediately, without needing CLI/container access or already knowing valid
`train_window`/`test_window`/`purge_gap_hours` values.

Design constraint, carried over deliberately from `DASH-006`, not overridden: `run_new.html`'s existing
submission form has an explicit, already-documented design rule — "no form field... carries a pre-filled
value that could look like a recommended default." This story must not violate that rule by adding default
values to the real submission form. Instead, "try a demo run" is a separate, explicitly-labeled action (a
distinct button/page, e.g. "Try a demo run with sample data" on the onboarding/next-step screen `ONB-001`
adds), never a change to `run_new.html`'s own defaults.

Acceptance criteria:
- [ ] A new, clearly-labeled demo action (e.g. `POST /demo-run`, `dashboard-web`) that (a) triggers
  `INGEST-010`'s existing `seed_tenant_platform_history` seeding for the caller's own tenant if it has no
  ingested data yet (reusing that existing mechanism, not a new seeding implementation), then (b) submits
  one run against the seeded dataset using a fixed, disclosed, illustrative configuration.
- [ ] The resulting run detail page and any copy referencing this action states explicitly "demo
  configuration -- not a recommended default for your own data," so it cannot be mistaken for
  `run_new.html`'s own (deliberately default-free) real submission path.
- [ ] This action is idempotent-safe: calling it again for a tenant that already has seeded data does not
  duplicate rows (relies on `INGEST-010`'s own already-established upsert/idempotency guarantee) and simply
  submits another demo run.
- [ ] Positioning check: the demo run's results are presented with the same honest "did not beat naive"
  framing (`TRUST-005`) as any real run — never a curated "impressive" example.

Rationale for priority: Should — directly serves the stated onboarding ask (sample dataset + pre-canned
run) while explicitly respecting an existing, deliberate design guardrail rather than quietly working
around it.
Depends on: ONB-001 (natural place to surface the action), INGEST-010 (already shipped)

### ONB-003 — CSV upload path for predictions [Won't, this backlog -- duplicate of RPT-003]

As a tenant, I want to upload a CSV of my model's predictions.

Rationale: Won't, this backlog, as a separate story. This is the same capability `RPT-003` already scopes
(the "Stored dataset"/local-file/inline-JSON `client_prediction_reference` input on the submit-run form) —
`dataset_reference`'s existing two modes already include a local file path, and `RPT-003` extends that
exact mechanism to predictions. Scoping a second, independent "CSV upload" story here would either
duplicate `RPT-003` outright or silently diverge from it into a second upload code path, which this
platform's own DRY convention (implementation-plan.md section 9) rules out. Any future dedicated
multipart-file-upload affordance (as opposed to a path/inline-JSON reference) is a real, separate idea, but
is not asked for here distinctly from "the CSV path for predictions," so it is not invented as a second
story.
Depends on: RPT-003

---

## Summary

| Priority | Count | IDs |
|---|---|---|
| Must | 1 | RPT-003 |
| Should | 12 | TRUST-001, 002, 003, 004, 005, RPT-001, ADMIN-001, 002, 003, 005, ONB-001, 002 |
| Could | 2 | RPT-002, 004 |
| Won't | 2 | ADMIN-004, ONB-003 |

Explicit calls made in this session, flagged for the requester/PM/Tech Lead to confirm:

1. `SETUP-023`'s alerting decline was re-evaluated, not re-deferred by habit (`ADMIN-001`): concluded the
   full alerting/paging stack still has no fired trigger (no incident, no pilot-client SLA ask), but the
   accumulated monitoring surface (`SETUP-020`/`021`/`022`) now justifies one narrow, bounded escalation —
   a single optional webhook fired on health-state transition, explicitly not a paging system. If this
   reasoning is wrong (e.g. the requester wants the full stack now, or wants it deferred further), that's a
   real product call to make explicitly, not something this backlog should assume.
2. `ADMIN-004` (tenant usage/quota view) was declined (Won't), not scoped, because no quota/plan/rate-limit
   mechanism exists anywhere in the platform to display usage against — confirm this reasoning holds rather
   than silently treating "no story" as an oversight.
3. `RPT-003` was escalated to Must despite the epic's overall lower sequencing lean, because investigation
   found the platform's own named headline capability (Subsystem 6, "bring your own model") is fully built
   on the backend but unreachable through `dashboard-web`'s UI — flagged explicitly in case the requester
   disagrees with prioritizing it above the rest of its own epic.
4. No trigger for `libs/sdk` (#9), a new ingestion connector (#10), or `services/economic-service` (#11)
   was found to have fired during this investigation — nothing in this backlog proposes work against any of
   the three.

Sequencing note for the PM/Tech Lead: `TRUST-003` unlocks `TRUST-004`; `ONB-001` is the natural place to
surface `ONB-002`'s new action; everything else in this backlog is independently schedulable.
