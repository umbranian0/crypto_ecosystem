# Dependency upgrade policy

Cross-cutting policy for how each of the platform's five modules' dependencies get reviewed for
updates. Root-level `docs/` placement is deliberate — this spans all five modules, not any one of
them (same placement precedent as `docs/implementation-plan.md` itself).

## Cadence: manual, reviewed once per sprint

**Decision (OPS-003, explicit — not automated Dependabot/Renovate this sprint):** dependency
upgrades across all five modules are reviewed manually, once per sprint, not via an automated bot
(`.github/dependabot.yml`/Renovate).

**Rationale:** OPS-001 stood up `.github/workflows/ci.yml`, which is the technical precondition
for an automated route being viable at all (a bot's upgrade PRs need something to gate them before
merge). That precondition is now satisfied. But standing up Dependabot today would generate PRs
against a platform with no live pilot client and no dependency-related incident on record — the
same YAGNI reasoning `docs/product/backlog-operability.md` already applies to OPS-006/OPS-007. An
automated bot would produce ongoing PR noise with nothing real yet to weigh it against. A manual,
once-per-sprint reviewed cadence is cheaper to reverse later (turn Dependabot on once there's a
real client/incident to justify tuning its noise) than to stand up now and have to tune down. This
is a policy decision made explicitly here, not left open for a future contributor to re-derive.

## Where the cadence is tracked

The "reviewed once per sprint" check is not just asserted here with no home — it is tracked as a
recurring line item in each future sprint's own outcome notes in `docs/tickets/README.md` (the
same per-sprint "Sprint NN outcome" paragraphs that already exist for every closed sprint in that
file, e.g. the Sprint 05/06/07/08 outcome paragraphs). Starting with the next sprint after this
ticket lands, that sprint's own outcome note must state whether a dependency review happened and
what, if anything, changed. If a sprint's outcome note is silent on this, the cadence was not
followed for that sprint — that omission is itself visible in `docs/tickets/README.md`, not hidden.

## Current dependency-pinning state, by module

The five modules are not currently consistent in how dependencies are pinned. This policy names
that inconsistency rather than glossing over it:

- **`libs/naive_first_engine`** — `uv`-managed (`pyproject.toml` + `uv.lock`). Locked.
- **`libs/common`** — `uv`-managed (`pyproject.toml` + `uv.lock`). Locked.
- **`services/validation-service`** — `uv`-managed (`pyproject.toml` + `uv.lock`). Locked.
- **`services/gateway-api`** — `uv`-managed (`pyproject.toml` + `uv.lock`). Locked.
- **`services/ingestion-service`** — plain `requirements.txt`, floors only (e.g. `>=` version
  constraints), no lockfile mechanism at all. Not locked.

## `services/ingestion-service`'s unpinned floors: explicit decision

**Decision (this ticket, not left open): stays as-is this sprint.** Moving
`services/ingestion-service/requirements.txt` to a lockfile (`uv`/`pip-tools`) is real, useful
work, but it requires first giving the module a `pyproject.toml`/`uv`-managed structure — a
structural change explicitly out of scope this session. The module's current `requirements.txt` +
hand-built `.venv` setup was itself a deliberate, recent choice made specifically to unblock its
new test suite, not a placeholder that was awaiting an immediate follow-up.

This is flagged as a **named, tracked future gap**, not silently left unaddressed: a candidate
story (migrate `services/ingestion-service` to a `uv`-managed `pyproject.toml` + `uv.lock`,
matching the other four modules) belongs in a future sprint's backlog grooming, sourced from this
policy doc.

## Review checklist (per sprint)

1. For each of the four `uv`-managed modules, run `uv lock --upgrade` (or equivalent) locally to
   check for available upgrades; review the diff, don't merge blind.
2. For `services/ingestion-service`, manually check `requirements.txt`'s floors against the
   installed versions in `.venv` for anything egregiously out of date.
3. Record the outcome (upgraded / reviewed, nothing to do / skipped) in that sprint's outcome note
   in `docs/tickets/README.md`, per "Where the cadence is tracked" above.
