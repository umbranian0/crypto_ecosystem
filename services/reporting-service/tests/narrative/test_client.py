"""AI-002 tests: `app.narrative.client`.

`HostedApiNarrativeClient` is exercised against `httpx.MockTransport` (no
live network call, same precedent `test_generate_endpoint.py` already uses)
by reaching into its private `_client` and swapping its transport -- there is
no injectable-transport constructor parameter since the ticket's real
constructor only takes `base_url`/`api_key`/`timeout_seconds` (env-var
driven, matching `app.dependencies.http_client`'s own shape).
"""

from __future__ import annotations

import httpx
import pytest

from app.narrative.client import (
    HostedApiNarrativeClient,
    NarrativeClientError,
    get_narrative_client,
)


def _client_with_transport(handler) -> HostedApiNarrativeClient:
    client = HostedApiNarrativeClient(
        base_url="https://narrative.example.com", api_key="fake-key", timeout_seconds=5.0
    )
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://narrative.example.com",
        headers={"Authorization": "Bearer fake-key"},
    )
    return client


def test_generate_returns_message_content_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer fake-key"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "a narrative paragraph"}}]}
        )

    client = _client_with_transport(handler)
    assert client.generate("some prompt") == "a narrative paragraph"


def test_generate_raises_narrative_client_error_on_non_2xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client_with_transport(handler)
    with pytest.raises(NarrativeClientError):
        client.generate("some prompt")


def test_generate_raises_narrative_client_error_on_connect_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _client_with_transport(handler)
    with pytest.raises(NarrativeClientError):
        client.generate("some prompt")


def test_generate_raises_narrative_client_error_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = _client_with_transport(handler)
    with pytest.raises(NarrativeClientError):
        client.generate("some prompt")


def test_generate_raises_narrative_client_error_on_malformed_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = _client_with_transport(handler)
    with pytest.raises(NarrativeClientError):
        client.generate("some prompt")


def test_get_narrative_client_returns_none_when_env_vars_unset(monkeypatch):
    monkeypatch.delenv("NARRATIVE_API_URL", raising=False)
    monkeypatch.delenv("NARRATIVE_API_KEY", raising=False)

    assert get_narrative_client() is None


def test_get_narrative_client_returns_hosted_client_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("NARRATIVE_API_URL", "https://narrative.example.com")
    monkeypatch.setenv("NARRATIVE_API_KEY", "fake-key")

    client = get_narrative_client()

    assert isinstance(client, HostedApiNarrativeClient)
