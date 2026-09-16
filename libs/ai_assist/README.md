# naive_first_ai_assist

**Status: implemented (AI-003-REFACTOR, Sprint 50).** Extracted from `services/reporting-service`'s
AI-002 `app.narrative.client` once AI-003 (`services/dashboard-web`) needed the same hosted,
OpenAI-compatible chat-completions HTTPS client -- see the DRY-trigger analysis in
[`docs/tickets/AI-003-refactor-ai-assist.md`](../../docs/tickets/AI-003-refactor-ai-assist.md) and the
serving-pattern rationale in [`docs/adr/0011-ai-assist-model-serving.md`](../../docs/adr/0011-ai-assist-model-serving.md).

Shared library for cross-cutting concerns used by more than one service. See
[../../docs/implementation-plan.md](../../docs/implementation-plan.md) sections 2, 7, 9.

**Owns**: the `AssistClient` Adapter/Strategy contract (`generate(prompt: str) -> str`), its narrow
error type `AssistClientError`, the `HostedApiAssistClient` implementation (an `httpx.Client` posting
to `{base_url}/chat/completions` with an `Authorization: Bearer <key>` header, wrapping every
connect/timeout/4xx-5xx/malformed-body failure into one `AssistClientError`), and the
`get_assist_client()` provider.

**Does not own**: any prompt-building logic (`prompt_template.py`-style, structurally different per
caller -- AI-002's fixed per-run summary vs. AI-003's free-text Q&A) or any positioning/banned-term
fact-check logic (`fact_check.py`-style) -- those stay in each consuming service, deliberately not
extracted here (see the ticket's Analysis section for why, and the "extract on second duplication"
rule this decision follows in the other direction).

**Contract**: plain typed Python, `httpx` only. This depends on nothing internal (no service imports,
one-directional dependency per implementation-plan.md's "no service imports another service's code").

## Public API

### `client.py`
- `AssistClient` (class, `Protocol`) -- `generate(prompt: str) -> str`
- `AssistClientError` (class)
- `HostedApiAssistClient` (class)
- `get_assist_client(url_env='NARRATIVE_API_URL', key_env='NARRATIVE_API_KEY', timeout_env='NARRATIVE_API_TIMEOUT_SECONDS', default_timeout_seconds=10.0)`

## Env vars

`get_assist_client()` defaults to AI-002's existing env var names -- `NARRATIVE_API_URL`,
`NARRATIVE_API_KEY`, `NARRATIVE_API_TIMEOUT_SECONDS` (default `10.0` seconds) -- since every current
caller shares the same hosted endpoint/credential, not a second one. Returns `None` (never raises)
when the URL/key env vars are unset, so an unconfigured deployment degrades cleanly instead of
erroring. The `url_env`/`key_env`/`timeout_env` parameters exist only so a future caller could point
at a differently-named var set without forking the class.

## Consumers

- `services/reporting-service` -- `app.narrative.client` re-exports `AssistClient`/`AssistClientError`/
  `HostedApiAssistClient`/`get_assist_client` under their original AI-002 names
  (`NarrativeClient`/`NarrativeClientError`/`HostedApiNarrativeClient`/`get_narrative_client`) for
  backward compatibility -- no duplicated class body.
- `services/dashboard-web` -- planned, AI-003.

## CI

Run tests locally via `uv run pytest` from this directory (no live network access -- every test uses
`httpx.MockTransport`).
