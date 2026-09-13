# Backlog — UAT findings (10-persona dashboard-web review + gateway-api API surface)

Source: `services/dashboard-web/README.md`, `services/gateway-api/README.md` (both read in full for
current shipped state before writing any story below), plus direct reads of
`services/dashboard-web/src/app/routers/operator.py`, `monitoring.html`, and a grep confirming
`validation-service`'s `runs.py`/`splits.py` are where the `model_*` field placeholder mapping lives.
Cross-referenced against `docs/product/backlog-guided-input.md` (GI-001, run-id dropdown — no overlap)
and `docs/product/backlog-first-run-setup-and-ops.md` Epic B (SETUP-034/035/036, operator-login
reachability — no overlap; distinct from this backlog's model-label and run-detail items).

Scope: real, corroborated, scoped fixes only, per this session's explicit "keep it simple, don't
over-engineer" instruction. No sweeping redesign, no new services, no speculative infrastructure.
Declined items (shared `OPERATOR_TOKEN`, no-threat-model security headers) are noted below, not
backlogged as new stories.

MoSCoW prioritization, matching this repo's convention — one-line rationale per story tied to
corroboration strength / module ownership / build-order position.

## Epic 1 — Model label & disclosure honesty (highest severity: 3 independent personas)

### UAT-001 — Label the placeholder "Model" column honestly when no client model was submitted [Must]

**As** the validation-service response consumer (`dashboard-web`'s run-detail page, and any future SDK
consumer of the same field), **I want** the `model_*` metric fields to be visibly labeled as a
NaiveLast-derived placeholder whenever no real `client_baseline` was submitted with the run, **so
that** a reader never mistakes an artifact of the placeholder mapping for a genuine model beating
Naive0.

Acceptance criteria:
- [ ] `validation-service`'s run-creation path already knows (from the presence/absence of the
      `client_baseline`/VS-017 mechanism) whether a real candidate model was submitted; this fact is
      surfaced on `RunDetailResponse`/`SplitResultResponse` (a new boolean field, e.g.
      `has_client_model: bool`, or equivalent — exact field name is the Tech Lead's implementation
      call) rather than requiring the caller to infer it.
- [ ] `run_detail.html`'s "Model" column header/legend renders as "Model (NaiveLast placeholder — no
      client model submitted)" (or equivalent wording matching this platform's existing honesty-caveat
      style, e.g. the DH-001 warnings convention) whenever that field is `false`; renders as plain
      "Model" only when a real `client_baseline` was submitted.
- [ ] RAV-002/003's chart legends and FHS-003's summary panel inherit the same labeling — no chart or
      panel independently re-derives or contradicts this label.
- [ ] `FHS-004`'s "copy summary" plain-text export includes the same placeholder disclosure verbatim
      when applicable — a shared/exported artifact must not silently drop the caveat the live page
      shows.
- [ ] A unit test asserts the placeholder label renders for a fixture run with no `client_baseline`,
      and does not render for a fixture run with one.
- [ ] No computation changes — this is a labeling/response-field fix only; `run_validation_protocol`
      (`libs/naive_first_engine`) is untouched.

Rationale for priority: three independent personas (quant researcher, compliance auditor, academic
reviewer) hit this same misleading-result issue independently — the strongest corroboration signal in
this review, and it goes directly to the product's non-negotiable "never imply we beat naive without
real evidence" positioning (CLAUDE.md). Must-fix before any further UAT round.
Depends on: none

### UAT-002 — Surface the raw-levels-vs-returns warning on every submission path, not just one field's tooltip [Must]

**As** a tenant submitting a run via any path (stored dataset, local file path, or inline JSON), **I
want** the existing "Naive0 is nonsensically wrong by construction on raw price levels" warning to be
visible regardless of which `dataset_reference` mode I use, **so that** I don't get a misleadingly
favorable verdict without ever seeing the caveat that explains it.

Acceptance criteria:
- [ ] The warning text already present on `run_new.html`'s `dataset_reference_field` tooltip (verbatim
      or lightly adapted) is also rendered as a static, always-visible notice on `run_new.html`
      (e.g. above the form, or beside the `dataset_reference_inline`/`dataset_reference_path` fields),
      not gated behind hover-only tooltip discovery on one field.
- [ ] The same warning text is included in `run_detail.html`'s existing per-run disclaimer block (the
      "Benchmark comparison... validation/audit metrics only" paragraph RAV-002/003 already share) so
      it survives to the result-viewing side too, not just the submission side.
- [ ] A unit test scans `run_new.html`/`run_detail.html` and asserts the raw-levels warning text is
      present unconditionally (not only inside a `data-tooltip` attribute).
- [ ] No new computation, no new field — presentation only.

Rationale for priority: same three-persona corroboration as UAT-001; this is the second half of the
same disclosure gap (the warning already exists but is invisible on the paths all three personas
actually used). Grouped as a Must alongside UAT-001 since both are needed to close the full gap.
Depends on: none (independent of UAT-001, can ship together or separately)

## Epic 2 — Run-detail synthesis (busy executive + corroborating personas)

### UAT-003 — Add a headline verdict summary to the run-detail page [Should]

**As** a reader of a validation run (busy executive, or anyone sharing this page externally), **I
want** a one-line, above-the-fold summary of the run's outcome, **so that** I don't have to open a
17-column table and manually count per-split verdicts to understand whether the model beat Naive0.

Acceptance criteria:
- [ ] `run_detail.html` renders a new, single-line summary (e.g. "Beat Naive0 on 4/7 splits, not
      statistically significant" or "Did not beat naive on any split — treat with caution") directly
      below the existing status table, above the existing per-split table/charts.
- [ ] The summary is computed from the same already-fetched `GET /runs/{id}/splits` `dm_verdict`
      field per split (no recomputation of DM statistics) — a small, pure function in `app/charting.py`
      (reusing RAV-003's existing `build_dm_verdict_chart` categorization logic, not a second
      "how many splits are better/worse" tally) so the headline number and the existing DM-verdict
      chart can never disagree.
- [ ] If `has_client_model` (UAT-001) is `false`, the headline text itself states the placeholder
      caveat inline (e.g. "Beat NaiveLast placeholder on 4/7 splits — no client model submitted") —
      this story must not create a second surface that repeats UAT-001's misleading-result problem.
- [ ] The existing detailed tables, charts, and disclaimer paragraph are unchanged — this is additive
      only, proven by a test asserting all pre-existing elements still render byte-identical to before.
- [ ] Zero-split runs show no headline (same "no per-split results yet" branch already in place).

Rationale for priority: corroborated by the busy-executive persona and named as a real usability gap
by others; Should not Must because the underlying data is already fully visible (just harder to read),
so no reader is misled, only inconvenienced — unlike Epic 1's Must items.
Depends on: UAT-001 (for the placeholder-caveat wording inside the headline)

### UAT-004 — Round displayed metric values to a fixed precision [Should]

**As** a reader of a run-detail page or a shared "copy summary" export, **I want** metric values
displayed with a fixed, sane number of decimal places (e.g. 4), **so that** the page/export doesn't
show noise like "0.6460000000000008".

Acceptance criteria:
- [ ] `run_detail.html`'s per-split table, RAV-002/003's chart tooltips/labels (if they render raw
      numbers), and FHS-003's summary panel all render metric values through one shared Jinja2
      filter/macro (e.g. `{{ value | round(4) }}` or a small named filter), not per-template ad hoc
      formatting — extract-on-second-duplication per implementation-plan.md section 9.
- [ ] FHS-004's "copy summary" plain-text export uses the same rounding, not the raw float.
- [ ] The underlying `SplitResultResponse`/`RunDetailResponse` values themselves are unchanged (full
      precision preserved in the API response) — this is a display-only rounding, not a data-truncation
      change to the contract.
- [ ] A unit test renders a fixture with a value like `0.6460000000000008` and asserts the rendered
      HTML contains `0.6460`, not the raw float string.

Rationale for priority: corroborated by 3 personas (compliance auditor, academic reviewer, busy
executive) as unpolished for a "shareable" artifact — real but cosmetic, so Should not Must.
Depends on: none

## Epic 3 — API/backend correctness (gateway-api)

### UAT-005 — Fix `openapi.json`'s incorrect `X-Operator-Token` security scheme on `/runs` [Must]

**As** an external integrator following `gateway-api`'s published OpenAPI schema, **I want** the
documented auth header for `/runs` to match what actually works, **so that** my first authenticated
call doesn't fail against a spec the service itself publishes incorrectly.

Acceptance criteria:
- [ ] `GET /runs`/`POST /runs`/etc. (the `get_authenticated_tenant`/GW-006-gated routes) document
      `Authorization: Bearer <key>` and `X-Api-Key: <key>` as their security schemes in the generated
      OpenAPI schema (via `ARCH-008`'s existing `Security()` + `APIKeyHeader` convention, `auth.py`'s
      `_authorization_scheme`/`_x_api_key_scheme` — confirm these are actually wired to the routes'
      `Security()` dependencies, not just defined but unused).
- [ ] `X-Operator-Token` appears in the schema's `securitySchemes` only on the routes actually gated by
      `get_authenticated_operator` (`operator_auth.py`) — `/runs` and other tenant routes must not list
      it at all.
- [ ] A test fetches `GET /openapi.json` from the running app and asserts `/runs`'s path item's
      `security` list references only the tenant auth schemes, and that `X-Operator-Token`'s
      `securityScheme` object exists but is referenced only by operator-gated paths.

Rationale for priority: a real, confirmed bug in the published contract that blocks any spec-following
integration at the very first call — Must, since this platform's stated audience (external pilot
clients, SDK users) depends on this contract being accurate, even with no real pilot client live yet.
Depends on: none

### UAT-006 — Make `failure_reason` a real, useful message instead of the literal string `"0"` [Should]

**As** a tenant whose run failed, **I want** `failure_reason` to describe why the run failed, **so
that** I can act on it instead of seeing an unhelpful `"0"`.

Acceptance criteria:
- [ ] Trace where `"0"` is being written (likely a stringified exit code or falsy-default bug in
      `validation-service`'s failure-handling path, not `gateway-api`, which only forwards this field
      unmodified per its own README) and fix the actual source to write a real message (e.g. the
      caught exception's string, or a fixed category label like "validation protocol raised an
      unhandled exception" if the raw exception text is judged unsafe to expose).
- [ ] A test creates a run that deterministically fails (e.g. RSS-004's zero-split guardrail, or an
      unparseable dataset) and asserts `failure_reason` is a non-numeric, human-readable string.
- [ ] No change to `gateway-api`'s own forwarding behavior — this is `validation-service`'s field to
      fix, forwarded as-is per the existing architecture.

Rationale for priority: real bug, but scoped to error-path UX rather than blocking correct-path usage
— Should, not Must.
Depends on: none (routes to `validation-service`, not `gateway-api`'s own code, once traced — flag this
during grooming if the Tech Lead confirms the actual source module differs from this story's
assumption)

### UAT-007 — Type and document `RunRequest.dataset_reference`'s shape in the OpenAPI schema [Should]

**As** an external integrator, **I want** `dataset_reference`'s two accepted shapes (`{"path": ...}` /
`{"inline": ...}`) documented with a real schema and example instead of bare `additionalProperties:
true`, **so that** I don't have to guess its shape from source code.

Acceptance criteria:
- [ ] `RunRequest.dataset_reference` gains a typed Pydantic model or `Union` (matching
      `InlineOrLocalFileDatasetSource.load`'s two accepted shapes, the same source `dashboard-web`'s
      `run_new.html` already copies verbatim per its own README) with at least one `example` in the
      OpenAPI schema for each shape.
- [ ] `GET /openapi.json`'s `RunRequest` schema no longer shows bare `additionalProperties: true` for
      this field.
- [ ] Existing `dashboard-web`/`validation-service` callers are unaffected — this is a schema-typing
      change only, not a runtime validation behavior change (unless the Tech Lead judges adding real
      validation here is in scope too, in which case note it as a separate, explicitly-scoped addition,
      not silently bundled).

Rationale for priority: real integration friction for a future SDK/pilot client, but no current caller
is blocked (dashboard-web already knows the shape from source) — Should, not Must, given no real pilot
client exists yet (gateway-api's own README: "Do not read anything ... as 'a pilot client exists'").
Depends on: none

## Epic 4 — Power-user run management

### UAT-008 — Let a tenant name/label a run at submission time [Should]

**As** a tenant with more than a handful of runs, **I want** to attach an optional, freeform label to
a run when I submit it, **so that** I can identify it later by something more useful than a bare
32-char hex id.

Acceptance criteria:
- [ ] `RunRequest` (shared `naive_first_common.contracts`) gains an optional `label: str | None` field
      (reasonable max length, e.g. 200 chars, enforced by the Pydantic model) — version-sync note per
      `gateway-api`'s own README: `gateway-api`'s local copy of `RunRequest` and `validation-service`'s
      real model must be updated together, not independently.
  - Note: it is the Tech Lead's call whether `RunRequest` truly needs a new field here vs. this
    landing as a `PATCH`-style rename-after-creation endpoint instead — flag this design choice for
    Tech Lead review rather than presupposing it in this story.
- [ ] `run_new.html` gains an optional "Label (optional)" text input, submitted as `label`.
- [ ] `runs_list.html` and `run_detail.html` render the label (when present) alongside/instead of the
      bare id — the raw id remains visible too (e.g. as a subtitle), never fully hidden, since it's
      still the canonical identifier for API calls.
- [ ] A run with no label continues to render exactly as today (bare id) — no forced-default label is
      fabricated.
- [ ] This does not gate or alter `POST /runs`'s existing leakage-aware validation/split logic in any
      way — purely a display/identification field.

Rationale for priority: named as the single biggest gap by the power-user persona, real usability
value for any tenant with more than a few runs — Should, since no one is currently blocked, only
inconvenienced, and it's additive schema work across two services (proportionate scope, not urgent).
Depends on: none

### UAT-009 — Add pagination controls to the runs list page [Should]

**As** a tenant with more runs than fit on one page, **I want** next/previous controls on `/runs`, **so
that** I can browse beyond the first page without hand-editing the URL's `limit`/`offset`.

Acceptance criteria:
- [ ] `runs_list.html` renders "Previous"/"Next" links (or page-number links) computed from the
      already-returned `RunListResponse` envelope's `limit`/`offset`/`total` fields (already available
      per `gateway-api`'s `GW-016` README section — this story adds UI only, no backend change).
  - Note: confirm at implementation time whether DASH-122 (referenced in the finding as already
    shipped server-side pagination support) is the correct ticket id/state before starting — this
    story assumes that groundwork is done and adds only the missing UI controls.
- [ ] "Previous" is absent/disabled on the first page; "Next" is absent/disabled when
      `offset + limit >= total`.
- [ ] No client-side re-sort or re-filter is introduced — this story is pagination controls only,
      matching `runs_list.html`'s existing README-documented "no client-side pagination/sorting"
      constraint being narrowly lifted for pagination only, not filtering/sorting (out of scope here).

Rationale for priority: real gap, but a tenant can currently still reach any run via a direct URL or
the run-detail page's own links — inconvenient, not blocking. Should, not Must.
Depends on: none (verify DASH-122's actual shipped state before starting, per the finding's own note)

### UAT-010 — Add hour-based buckets to `/runs/horizon-summary` alongside the existing day-based ones [Should]

**As** a tenant whose runs use hour-based horizons (1/6/24, the actual real-data convention per
`ADR-0007`), **I want** `/runs/horizon-summary`'s bucket selector to include hour-based options, **so
that** I don't see "No completed runs matched" for runs that genuinely exist and match my intended
horizon.

Acceptance criteria:
- [ ] `/runs/horizon-summary`'s selector adds three additional bucket options matching the real
      hour-based horizons the finding names (1h/6h/24h), alongside the existing 7/15/30-day options —
      additive, not a replacement (the day-based buckets stay, since `ADR-0007` is still the platform's
      recorded decision for that unit).
- [ ] Selecting an hour-based bucket filters the tenant's completed runs by that literal `horizon`
      value (no day-to-hour conversion needed for these three, since they're already the dataset's
      native unit per `ADR-0007` finding (a)) — reuses the existing filtering code path, just with a
      different bucket-to-value mapping table, not a second filtering implementation.
- [ ] A test submits a fixture run with `horizon=1` and asserts it's returned when the 1h bucket is
      selected, matching the existing day-bucket tests' pattern.
- [ ] This does not reopen or contradict `ADR-0007`'s finding — it's recorded there as an accepted,
      known follow-up gap, not superseded.

Rationale for priority: three independent personas (power user, academic reviewer, positioning
stress-test) independently hit real confusion from a real data-model mismatch — strong corroboration,
but the page still functions and a workaround exists (view via the runs list instead) — Should, not
Must, given the scope is genuinely additive/small per this session's "don't over-engineer" instruction.
Depends on: none

## Epic 5 — Accessibility

### UAT-011 — Make `data-tooltip` help text accessible to screen readers [Must]

**As** a screen-reader user, **I want** the load-bearing semantic caveats currently shown only via
CSS-hover `data-tooltip` (e.g. the raw-levels-vs-returns warning, the horizon-unit hint) to be
announced, **so that** I don't silently miss safety-relevant disclosures a sighted user sees on hover.

Acceptance criteria:
- [ ] Every existing `data-tooltip` element gains an `aria-label` (or equivalent — `aria-describedby`
      pointing at a visually-hidden element with the same text) carrying the same tooltip text, so a
      screen reader announces it without requiring a mouse hover.
- [ ] A test scans the rendered templates and asserts every `data-tooltip` attribute has a
      corresponding `aria-label`/`aria-describedby` on the same element.
- [ ] No visual change for sighted users — this is additive markup only.

Rationale for priority: this is not merely a polish item — several of these tooltips carry
CLAUDE.md-mandated honesty disclosures (the raw-levels warning UAT-002 also addresses); an
inaccessible disclosure is a disclosure that silently fails for a whole user population. Must, given
the overlap with Epic 1's disclosure-integrity concern.
Depends on: none (complements, does not duplicate, UAT-002 — UAT-002 makes the warning visible to
everyone by default; this story ensures the remaining hover-only tooltips are still announced for
screen readers even where hover-only is otherwise acceptable)

### UAT-012 — Add a skip-to-content link [Could]

**As** a keyboard/screen-reader user, **I want** a skip-to-content link at the top of every page, **so
that** I don't have to tab through the full navigation on every page load.

Acceptance criteria:
- [ ] `base.html` gains a visually-hidden-until-focused "Skip to main content" link as the first
      focusable element, targeting the page's main content landmark.
- [ ] A test asserts the link is present in rendered HTML for at least one representative page.

Rationale for priority: standard accessibility hygiene, real but lower severity than UAT-011 (no
disclosed information is lost without it, only navigation efficiency) — Could.
Depends on: none

### UAT-013 — Use real heading elements for chart section titles [Could]

**As** a screen-reader user navigating by heading, **I want** chart titles (currently `<p
class="chart-title">`) to be real `<h2>`/`<h3>` elements, **so that** heading-based navigation actually
finds them.

Acceptance criteria:
- [ ] `_error_chart.html`/`_dm_verdict_chart.html`/`_forecast_horizon_summary_panel.html`'s title
      elements become real heading tags at a level consistent with the surrounding page structure
      (`run_detail.html`'s existing heading hierarchy) — styled via the existing `chart-title` CSS
      class unchanged, so no visual regression.
- [ ] A test asserts these titles render as `<h2>`/`<h3>` (matching whichever level the Tech Lead
      judges correct for the existing hierarchy), not `<p>`.

Rationale for priority: real but narrow fix, three named templates, no functional/disclosure impact —
Could.
Depends on: none

## Epic 6 — First-time operator onboarding

### UAT-014 — Add a plain-language explanation of purge gap / walk-forward windows reachable in-app [Could]

**As** a non-technical founder or first-time operator, **I want** a short, plain-language explanation
of core concepts (purge gap, walk-forward windows) reachable from inside the app, **so that** I don't
have to read the 600+-line `infra/README.md` or rely on hover tooltips that assume prior knowledge.

Acceptance criteria:
- [ ] A new, short static page (e.g. `/help/concepts` or similar) explains purge gap and walk-forward
      windows in plain language, linked from `run_new.html`'s form (near the relevant fields) and from
      `base.html`'s nav — a single new template, not a rewrite of existing tooltips.
- [ ] Content is reviewed against CLAUDE.md's positioning constraint (no "prediction"/"signal"
      language) the same way every other template in this service already is.
- [ ] This does not replace or duplicate the existing inline `data-tooltip` hints (RSS-001/002,
      DH-008) — those stay as the in-context quick reference; this is the deeper, standalone
      explanation for someone starting from zero.

Rationale for priority: real onboarding friction named by one persona, genuinely valuable but scoped
work with no functional blocker behind it (the tooltips already exist as a partial mitigation) —
Could, consistent with "don't over-engineer" for a persona representing a not-yet-existing pilot
client.
Depends on: none

## Confirmed small bug (recommend as an immediate Tech Lead fix, not a backlog item)

**`/monitoring`'s "Log in to generate a report" message shows even while authenticated** — traced and
confirmed real: `services/dashboard-web/src/app/templates/monitoring.html` line 106 gates the report
form on `{% if crawl_statuses is none %}`, but `crawl_statuses` (`operator.py`'s
`_fetch_crawl_statuses`) is `None` both when the visitor has no tenant session *and* when a genuinely
authenticated tenant's `GET /ingestion/datasets` call transiently fails downstream — the template
cannot distinguish the two, so an authenticated tenant hitting a transient downstream hiccup sees "log
in" instead of a real error. Recommended fix (small, same file/session as the bug, not a new backlog
epic): gate the report form's login-prompt branch on `headers is none` (the actual session-presence
signal `monitoring()` already has and passes as `OptionalDownstreamHeadersDep`), not on
`crawl_statuses is none`, and show `error.html`'s existing generic downstream-failure message for the
authenticated-but-fetch-failed case instead. This is a one-template, one-conditional fix — small enough
that the PO recommends the Tech Lead pick it up directly rather than route it through backlog
grooming, per this task's own framing.

## Explicitly declined / not new scope (confirmed correct, no story written)

- **Baseline security headers (CSP/HSTS/X-Frame-Options)**: noted as a backlog awareness item only, no
  story written — this platform's own locked-in local-first design (CLAUDE.md) has no public internet
  exposure today; building this now would be over-engineering for a threat model that doesn't yet
  apply. Revisit when `gateway-api`'s trigger #5 (first real pilot client) actually fires, since that's
  the point this service becomes internet-facing for a real party.
- **Single shared `OPERATOR_TOKEN` with no per-admin identity**: confirmed already correctly declined —
  this is `SETUP-010`'s own disclosed, deliberate stopgap (`gateway-api`'s README, "Operator
  authentication (GW-021...)" section) with a named revisit trigger (a second real human operator). No
  new story written; the security-CTO persona's finding restates an already-tracked, already-justified
  decision.
- **Positioning stress-test**: clean pass, no findings — noted here as confirmation the platform's
  honesty/positioning discipline held under adversarial review, not a backlog item.

## Summary counts

| Priority | Count | IDs |
|---|---|---|
| Must | 4 | UAT-001, UAT-002, UAT-005, UAT-011 |
| Should | 7 | UAT-003, UAT-004, UAT-006, UAT-007, UAT-008, UAT-009, UAT-010 |
| Could | 3 | UAT-012, UAT-013, UAT-014 |
| Won't | 0 | (declined items above were already correctly declined elsewhere, not re-decided here) |

Plus one confirmed small bug (monitoring.html's login-prompt/fetch-failure conflation) recommended for
immediate Tech Lead pickup rather than backlog sequencing.
