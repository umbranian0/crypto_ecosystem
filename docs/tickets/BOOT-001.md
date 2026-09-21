# BOOT-001 — `infra`: auto-provision `infra/.env` from `infra/.env.example` when missing

**Sprint**: 54. **Module**: `infra`. **Status**: done. **Priority**: Must.
**Depends on**: none. **Blocks**: `BOOT-002` (file-region/renumbering conflict only, not an output
dependency — see `docs/sprints/sprint-54.md`'s "Sequencing decision" section; do not start `BOOT-002`
until this ticket is merged).
**Can run in parallel with**: nothing this sprint — runs first, per the sprint's own sequencing.

## Analysis

Per `docs/product/backlog-installation-ops.md`'s `BOOT-001` story: `infra/README.md` currently states,
ahead of the bootstrap section, "Copy `infra/.env.example` to `infra/.env`... before starting
anything" — a manual, easy-to-forget step with no automation and no existence check. Confirmed directly
(not taken on trust) by reading both `infra/bootstrap.sh` and `infra/bootstrap.ps1` in full: neither
script references `.env`/`.env.example` anywhere in their current 6-step sequence. A fresh clone with
no pre-existing `infra/.env` has every `docker compose` invocation fall back to `docker-compose.yml`'s
own hardcoded defaults for any variable not otherwise set in the shell environment — silently
diverging from the "one documented command, one documented config source" story `infra/README.md`
otherwise tells.

This ticket covers all of `BOOT-001`'s acceptance criteria as stated verbatim in
`docs/product/backlog-installation-ops.md`.

**Constraint from the docs**: this is orchestration/packaging only — `infra`'s trigger (#4,
implementation-plan.md section 6) already fired; this ticket does not touch `libs/*` or any
`services/*` application code (implementation-plan.md section 2, module boundary map). No design
pattern from implementation-plan.md section 7 is force-fit here — see Design below.

## Design

**Pattern**: none newly introduced. Same "pure orchestration script change" stance `SETUP-004`
(`docs/tickets/SETUP-004.md`) already took for this exact pair of files — none of implementation-plan.md
section 7's patterns (Strategy/Repository/Adapter/Factory/Observer/DI/Template Method) apply to a
shell/PowerShell file-existence check and a byte-for-byte copy.

**Files touched** (scoped to `infra/` only, per the module-boundary rule — one module per ticket):
- `infra/bootstrap.sh` — insert a new step 0 (`echo "==> Step 0/7: ..."`) at the very top of the
  numbered sequence, before today's step 1 (`docker compose up -d postgres redis`). Renumber every
  existing `"Step N/6"` line to `"Step (N+1)/7"` (steps 1–6 become 2–7). New step 0 logic: `[ -f
  "$script_dir/.env" ]` (existence check relative to `$script_dir`, matching the existing
  `compose_file` path-resolution convention already in this script — never relative to the caller's
  cwd) — if missing, `cp "$script_dir/.env.example" "$script_dir/.env"` (verbatim byte copy, no
  re-templating) and print a message naming the file created plus the enumerated disclosed-insecure
  dev-only defaults; if present, silent no-op (no message beyond the step header, matching this
  script's existing terseness for already-satisfied steps like `docker compose up -d` on an
  already-running container).
- `infra/bootstrap.ps1` — identical structural change: new step 0 using a `Test-Path`-equivalent
  check, `Copy-Item` for the verbatim copy, same renumbering of every `"Step N/6"` `Write-Host` line to
  `"Step (N+1)/7"`.
- `infra/README.md` — "First-boot bootstrap (INF-015)" section: renumber its own 1–6 narrative list to
  2–7 stating the new step 0, and update the pre-bootstrap-section "Copy `infra/.env.example` to
  `infra/.env`... before starting anything" instruction to state this now happens automatically as
  part of the bootstrap script's first step, with the manual copy kept documented as the fallback for
  anyone running services individually without the bootstrap script (demote, don't delete — the same
  convention this file already applies to its own hand-run sequences and `INF-016`'s migrate script
  relative to the original one-off command).

**DRY check note** (grepped both scripts before writing this ticket): no existing `.env`
existence-check or copy logic exists anywhere in either script today (confirmed via `Grep` for
`.env`/`Test-Path`/`cp `/`Copy-Item` across `infra/*.sh`/`infra/*.ps1` — zero matches before this
ticket). The `fail`/`Fail-Step` failure convention and the `$script_dir`/`$scriptDir`-relative
path-resolution pattern already used for `compose_file` are the two pieces of existing logic this new
step must reuse, not reinvent — the new step 0 must resolve `.env`/`.env.example` paths the same
script-relative way `compose_file` already does, and must route any real failure (e.g. `.env.example`
itself missing, an unwritable directory) through the existing `fail`/`Fail-Step` function rather than a
new ad hoc error path.

## Implementation acceptance criteria

- [x] New step 0 (renumbering existing steps 1–6 to 2–7) in both `infra/bootstrap.sh` and
  `infra/bootstrap.ps1`: if `infra/.env` does not exist, copy `infra/.env.example` to `infra/.env`
  verbatim (byte-for-byte, not regenerated/re-templated) and print a message naming the file just
  created.
- [x] If `infra/.env` already exists, this step is a silent no-op — never overwrites an existing file,
  even if it appears to differ from `.env.example` (drift detection is `BOOT-003`'s territory,
  explicitly deferred, not this ticket's).
- [x] The printed message, when a fresh `.env` was just created, explicitly names the known,
  disclosed-insecure dev-only defaults that should be changed before any non-local deployment:
  `OPERATOR_TOKEN`, `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`,
  `INGESTION_CREDENTIAL_ENCRYPTION_KEY`, `INGESTION_INTERNAL_TOKEN` — this step surfaces
  `.env.example`'s own existing inline disclosures at the moment it matters most (first boot); it does
  not invent new secret-strength policy.
- [x] Both scripts implement this identically in structure (same step, same message shape, same
  file-existence check), maintaining the byte-for-byte structural parity `infra/bootstrap.sh`/`.ps1`
  already have today.
- [x] Any real failure in this new step (e.g. `.env.example` itself missing) fails loudly through the
  existing `fail`/`Fail-Step` convention, naming step 0, not a silent skip or an unhandled exception.
- [x] Running the full script twice in a row (second run against an already-created `.env`) produces no
  change to `infra/.env` and no error — the same idempotency bar `SETUP-004` already set for this
  script. (Verified via the isolated step-0-logic test below — no live Docker daemon was available in
  this environment to run the full end-to-end script.)

## Test acceptance criteria

- [x] This is an `infra`-level ticket with no `pytest` suite of its own (matching `INF-015`/`SETUP-004`'s
  own precedent — no ML/data-pipeline code, no `naive_first_engine` regression check applies here).
  Verification is a real, described dry run, not a source-only review.
- [x] Isolated verification (does not require a live Docker daemon, since this step runs before any
  `docker` invocation in the sequence): run each script's new step-0 logic against a temp directory
  containing a `.env.example` fixture and no `.env`, confirm `.env` is created byte-identical to the
  fixture and the correct message is printed; re-run against the same temp directory (now containing
  `.env`) and confirm no change to `.env`'s contents/mtime-irrelevant-bytes and no error from step 0
  itself. Also confirmed the failure path (fixture directory with no `.env.example`) exits non-zero
  through `fail`/`Fail-Step`, naming step 0, for both the bash and PowerShell logic.
- [ ] Full dry run against a real Docker stack (fresh Postgres volume, no pre-existing `infra/.env`):
  **not performed** — no working Docker daemon in this environment (Docker Desktop requires elevated
  privileges not available here). Only the isolated step-0-logic dry run above was performed; steps 2–7
  of each script are unchanged in behavior from before this ticket and were not re-exercised live as
  part of this ticket's own work.

## Review acceptance criteria (Tech Lead verifies personally)

- Reads the real `git diff` for both `infra/bootstrap.sh` and `infra/bootstrap.ps1` — confirms the new
  step 0 exists in both, confirms every `"Step N/6"` line in both files was actually renumbered to
  `"Step N/7"` (not just the first one — side-by-side check, same discipline the sprint plan's DoD
  requires), confirms no other line in either script changed incidentally.
- Confirms the existence check never overwrites an existing `.env` — reads the actual conditional logic
  in both scripts, not just the dev's self-report.
- Personally runs (or, if Docker isn't reachable, isolates and runs) the new step-0 logic twice against
  a fixture directory and confirms byte-for-byte idempotency directly, not from the dev agent's
  self-report alone.
- Confirms the printed dev-only-defaults message names all five values verbatim
  (`OPERATOR_TOKEN`/`POSTGRES_PASSWORD`/`POSTGRES_APP_PASSWORD`/`INGESTION_CREDENTIAL_ENCRYPTION_KEY`/
  `INGESTION_INTERNAL_TOKEN`), matching `.env.example`'s own existing disclosures — not a paraphrase
  that drops one.

## Documentation acceptance criteria

- [x] `infra/README.md`'s "Copy `infra/.env.example`..." instruction (ahead of the bootstrap section)
  updated to state this now happens automatically as part of `infra/bootstrap.sh`/`.ps1`'s first step,
  manual copy kept as the documented fallback.
- [x] `infra/README.md`'s "First-boot bootstrap (INF-015)" section's numbered list updated for the new
  step 0 and the 2–7 renumbering.
- [x] `docs/product/backlog-installation-ops.md`'s `BOOT-001` entry's acceptance-criteria boxes checked
  and status marked done, pointing to this ticket file.
- [x] `docs/tickets/README.md` gets a new Sprint 54 / `BOOT-*` section listing this ticket and its
  status. (The Sprint 54 section already existed, listing `BOOT-001`/`BOOT-002`; this ticket's status
  updated from `in-progress` to `done`.)
