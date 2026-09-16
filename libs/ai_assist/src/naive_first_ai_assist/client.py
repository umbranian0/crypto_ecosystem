"""AI-003-REFACTOR: `AssistClient` Adapter/Strategy seam, extracted from
`services/reporting-service/src/app/narrative/client.py` (AI-002) once
AI-003 (`services/dashboard-web`) needed the same hosted, OpenAI-compatible
chat-completions HTTPS client -- one interface every model-calling
implementation satisfies, so the real hosted-HTTP call is swappable and every
caller's tests use a fake rather than live network access/credentials.

ADR-0011: hosted open-weights inference API over HTTPS only -- no local
Ollama/llama.cpp, no new container, no `infra/docker-compose.yml` service.
`HostedApiAssistClient` is the only implementation here that imports
`httpx`/touches the network.
"""

from __future__ import annotations

import os
from typing import Protocol

import httpx

_NARRATIVE_API_URL_ENV_VAR = "NARRATIVE_API_URL"
_NARRATIVE_API_KEY_ENV_VAR = "NARRATIVE_API_KEY"
_NARRATIVE_API_TIMEOUT_ENV_VAR = "NARRATIVE_API_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT_SECONDS = 10.0


class AssistClientError(Exception):
    """Raised for any failure calling the hosted model (connection, timeout,
    non-2xx response, malformed response body) -- a narrow type so no caller
    has to catch a raw `httpx` exception.
    """


class AssistClient(Protocol):
    """One-method Adapter/Strategy contract -- matches ADR-0011's forward-
    looking `generate(prompt, context) -> text` shape, `context` omitted
    here since every current caller's prompt is fully self-contained.
    """

    def generate(self, prompt: str) -> str:
        ...


class HostedApiAssistClient:
    """Calls a hosted, OpenAI-compatible chat-completions HTTPS endpoint via
    `httpx`. Never lets a raw `httpx` exception escape this class -- every
    failure mode is re-raised as `AssistClientError`.
    """

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def generate(self, prompt: str) -> str:
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AssistClientError("assist model call failed") from exc

        if response.status_code >= 400:
            raise AssistClientError(
                f"assist model responded with status {response.status_code}"
            )

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AssistClientError("assist model response malformed") from exc


def get_assist_client(
    url_env: str = _NARRATIVE_API_URL_ENV_VAR,
    key_env: str = _NARRATIVE_API_KEY_ENV_VAR,
    timeout_env: str = _NARRATIVE_API_TIMEOUT_ENV_VAR,
    default_timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> AssistClient | None:
    """Returns `None` (rather than raising) if the URL/key env vars aren't
    set, so an unconfigured deployment degrades cleanly instead of erroring.
    Defaults to AI-002's existing `NARRATIVE_API_*` env var names -- this is
    genuinely the same hosted endpoint/credential, not a second one; the
    parameter names exist only so a future caller could point at a
    differently-named var without forking the class.
    """
    base_url = os.environ.get(url_env)
    api_key = os.environ.get(key_env)
    if not base_url or not api_key:
        return None

    timeout_seconds = float(os.environ.get(timeout_env, default_timeout_seconds))
    return HostedApiAssistClient(base_url, api_key, timeout_seconds)
