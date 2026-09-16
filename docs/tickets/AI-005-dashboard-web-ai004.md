**Status: done** — `services/dashboard-web/README.md` gained the "AI-assisted features (AI-004)" section;
no new env var/config found (confirmed, reuses `NARRATIVE_API_URL`/`NARRATIVE_API_KEY`/
`NARRATIVE_API_TIMEOUT_SECONDS`); `docs/product/backlog-ai-integration-ux.md`'s AI-004/AI-005 entries
marked done; `docs/tickets/README.md` updated with the Sprint 51 table/outcome.

# AI-005 (dashboard-web slice, AI-004 portion): document the AI-004 boundary

Depends on AI-004-01, AI-004-02 (documents what actually shipped).

## Analysis

Closes AI-005 across all three shipped `dashboard-web` AI-assist features (AI-002's reporting-service
slice done Sprint 49, AI-003's dashboard-web slice done Sprint 50, this is the AI-004 slice). Per
implementation-plan.md section 8 and this repo's "docs always updated" convention.

## Design

No code changes. `services/dashboard-web/README.md`'s existing "AI-assisted features" section (already
has an AI-003 subsection from Sprint 50) gains an AI-004 subsection in the same format: status, what it
owns (the `POST /assistant/configure-run` route, `app/assistant/configure_run.py`/
`configure_run_prompt.py`), what it does and does not do (suggests, never auto-fills/auto-submits; no
knowledge of the tenant's actual datasets so never suggests `dataset_id`/`dataset_reference_*`; cannot
suggest disabling the purge gap or naive baselines), where the banned-term/overstated-certainty tests
live, and the same "grounded-only, no new predictive claims, degrade-on-failure" guardrail statement the
AI-002/AI-003 sections already state.

## Documentation acceptance criteria

- [ ] `services/dashboard-web/README.md` gains the AI-004 subsection, matching the AI-002/AI-003 sections'
  format exactly.
- [ ] Confirm (check, do not assume) whether AI-004 introduces any new environment variable/config — per
  Decision 1 of `docs/sprints/sprint-51.md`, expected to be none (reuses `NARRATIVE_API_URL`/
  `NARRATIVE_API_KEY`/`NARRATIVE_API_TIMEOUT_SECONDS` via `get_assist_client()`, already disclosed in
  `infra/README.md`/`docker-compose.yml` since Sprint 50) — if a real gap is found, disclose it there too,
  not silently.
- [ ] `docs/product/backlog-ai-integration-ux.md`'s AI-004 and AI-005 entries marked done, pointing at the
  ticket files.
- [ ] `docs/tickets/README.md`'s AI-assist section gains the Sprint 51 table and Outcome, matching every
  prior sprint's convention.
