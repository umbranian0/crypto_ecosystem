# AI-003-REFACTOR — extract `libs/ai_assist` (second-duplication trigger check, ADR-0011)

**Sprint**: 50. **Module**: `libs/ai_assist` (new) + `services/reporting-service` (consumer swap only,
no behavior change). **Status**: done. **Priority**: Must (blocks AI-003; sequenced immediately before
it, per ADR-0011's own instruction). **Depends on**: none (AI-002 already shipped, Sprint 49).

## Analysis

ADR-0011 (`docs/adr/0011-ai-assist-model-serving.md`, "`libs/ai_assist` question" section) is explicit
that this is not a decision to re-litigate from scratch: the trigger condition — "a second module needs
the same prompt-building/model-calling logic AI-002 already built" — was already defined, and this
ticket's job is to check whether it is now *true* against AI-002's real shipped code, not to assume an
answer either way (implementation-plan.md section 9: "extract on second duplication").

**Evidence checked** (read directly, not assumed):
`services/reporting-service/src/app/narrative/client.py` ships a `NarrativeClient` Protocol
(`generate(prompt: str) -> str`), a `HostedApiNarrativeClient` implementation (`httpx.Client` posting to
`{base_url}/chat/completions` with an `Authorization: Bearer <key>` header, wrapping every
connect/timeout/4xx-5xx/malformed-body failure into one `NarrativeClientError`), and a
`get_narrative_client()` provider reading `NARRATIVE_API_URL`/`NARRATIVE_API_KEY`/
`NARRATIVE_API_TIMEOUT_SECONDS` env vars, returning `None` (not raising) when unconfigured.

AI-003 (`services/dashboard-web`) needs exactly this: a hosted, OpenAI-compatible chat-completions HTTPS
client with the same one-method `generate(prompt) -> str` contract, the same "narrow error type, never a
raw `httpx` exception escapes" behavior, and the same "unconfigured degrades to `None`, doesn't raise"
provider shape — driven by ADR-0011's own binding recommendation (hosted API required for AI-003's
synchronous latency budget) and the sprint's own binding constraint to reuse `NARRATIVE_API_*`-pattern
env vars rather than invent a second one. This is the exact shape of duplication implementation-plan.md
section 9 and ADR-0011's forward-looking design note (Adapter, `generate(prompt, context) -> text`,
"keeps the hosted-vs-local decision swappable without touching call sites") anticipated.
**Conclusion: the trigger is met. `libs/ai_assist` is created this sprint**, as this dedicated
refactor ticket, immediately before AI-003's own ticket, per ADR-0011's explicit instruction not to fold
extraction into AI-003's ticket silently.

**What is deliberately NOT extracted**: `prompt_template.py` (fed `RunDetailResponse`/`SplitResultResponse`
fields specific to a completed run — AI-003's Q&A shape is structurally different, a free-text question,
not a fixed per-run summary) and `fact_check.py`'s `is_directionally_consistent` (a one-off heuristic
tied to AI-002's specific "did the narrative claim the model beat naive" failure mode) stay where they
are. `fact_check.BANNED_TERMS`/`contains_banned_term` is a six-word tuple and a four-line function; AI-003
needs its own banned-term check with its own module docstring/positioning-copy test target, and
duplicating a four-line list once is cheaper than a premature shared-terms module — not extracted
(revisit only if a third module needs it, same "extract on second duplication" rule applied honestly in
the other direction).

## Design

**Pattern**: Adapter (implementation-plan.md section 7's row for `ingestion-service` connectors is the
existing precedent for "one interface, swappable implementation behind it"; ADR-0011's own design note
names this exact shape for this exact future extraction).

**New package**: `libs/ai_assist/` (mirrors `libs/common`'s layout exactly — `pyproject.toml`,
`src/naive_first_ai_assist/`, `tests/`, `README.md`):
- `src/naive_first_ai_assist/client.py` — `AssistClient` (Protocol, `generate(prompt: str) -> str`),
  `AssistClientError` (Exception), `HostedApiAssistClient` (the `httpx`-based implementation, byte-for-
  byte behavior-identical to today's `HostedApiNarrativeClient`), `get_assist_client(url_env: str =
  "NARRATIVE_API_URL", key_env: str = "NARRATIVE_API_KEY", timeout_env: str =
  "NARRATIVE_API_TIMEOUT_SECONDS", default_timeout_seconds: float = 10.0) -> AssistClient | None` — env
  var names default to the exact `NARRATIVE_API_*` names AI-002 already uses (the sprint's own binding
  constraint: "reuse AI-002's `NARRATIVE_API_*` pattern where sensible... no silent new dependency" — this
  is genuinely the same hosted endpoint/credential, not a second one, so both services share the same
  three env vars by default; the parameter names exist only so a future caller *could* point at a
  differently-named var without forking the class, not because this sprint needs a second var set).
- `pyproject.toml`: `name = "naive_first_ai_assist"`, dependencies `httpx>=0.27`, dev deps `pytest>=7.4`.

**DRY check note (this ticket's own)**: grepped `services/reporting-service/src/app/narrative/client.py`
before writing anything — the new package's `HostedApiAssistClient`/`get_assist_client` bodies are that
file's existing logic moved, not re-derived from scratch or duplicated a third time anywhere.

**Consumer swap — `services/reporting-service/src/app/narrative/client.py`**: becomes a thin
backward-compatible re-export module (`NarrativeClient = AssistClient`, `NarrativeClientError =
AssistClientError`, `HostedApiNarrativeClient = HostedApiAssistClient`, `get_narrative_client =
get_assist_client`) — every existing import site (`app.narrative.generation`,
`app.subscriber`, and every existing test under `tests/narrative/`) keeps working unmodified. No test
file in `services/reporting-service` is edited by this ticket; if any fails, that is a real regression to
fix, not an expected rename ripple.

**File(s) touched**: `libs/ai_assist/` (new, all files), `services/reporting-service/src/app/narrative/
client.py` (rewritten as a re-export), `services/reporting-service/pyproject.toml` (add
`naive_first_ai_assist` dependency + `[tool.uv.sources]` entry, mirroring the existing
`naive_first_common` entry).

## Implementation acceptance criteria

- [x] `libs/ai_assist/src/naive_first_ai_assist/client.py` ships `AssistClient`/`AssistClientError`/
  `HostedApiAssistClient`/`get_assist_client`, behavior-identical to today's
  `NarrativeClient`/`NarrativeClientError`/`HostedApiNarrativeClient`/`get_narrative_client`.
- [x] `services/reporting-service/src/app/narrative/client.py` re-exports from
  `naive_first_ai_assist.client` — no duplicated class body.
- [x] `services/reporting-service/pyproject.toml` depends on `naive_first_ai_assist` via a local editable
  path source, mirroring `naive_first_common`'s existing entry exactly.

## Test acceptance criteria

- [x] `libs/ai_assist/tests/test_client.py`: unit tests for `HostedApiAssistClient`/`get_assist_client`
  (moved/adapted from `reporting-service`'s existing narrative-client tests — same fake-transport
  precedent, no live network access).
- [x] `services/reporting-service`'s full existing suite re-run unmodified and still green — proves the
  re-export is behaviorally transparent to every existing caller/test.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirm `git diff` for `services/reporting-service` touches only `client.py` and `pyproject.toml` (no
  `generation.py`/`fact_check.py`/`prompt_template.py`/`subscriber.py` edits) — the extraction must not
  ripple into files this ticket didn't need to touch.
- Confirm no test file under `services/reporting-service/tests/narrative/` needed editing to keep passing
  — if one did, that's a signal the re-export isn't actually behavior-identical, a blocking finding.
- Confirm `libs/ai_assist` has zero import of anything under `services/*` (one-directional dependency,
  per implementation-plan.md section 2/9 "no service imports another service's code").

## Documentation acceptance criteria

- [x] `libs/ai_assist/README.md` (new): owns/does not own, the `AssistClient` Adapter contract, env var
  names, and a pointer to `docs/adr/0011-ai-assist-model-serving.md` for the serving-pattern rationale.
- [x] `services/reporting-service/README.md`'s existing "AI-assisted features (AI-002)" section gets a
  one-line update noting the client now lives in `libs/ai_assist` (re-exported, not reimplemented) —
  everything else in that section is unchanged, since AI-002's actual behavior did not change.
