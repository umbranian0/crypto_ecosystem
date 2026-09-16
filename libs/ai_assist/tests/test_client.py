"""AI-003-REFACTOR tests: `naive_first_ai_assist.client`.

`HostedApiAssistClient` is exercised against `httpx.MockTransport` (no live
network call, same fake-transport precedent as reporting-service's original
narrative-client tests) by reaching into its private `_client` and swapping
its transport -- there is no injectable-transport constructor parameter since
the real constructor only takes `base_url`/`api_key`/`timeout_seconds`.
"""

from __future__ import annotations

import httpx
import pytest

from naive_first_ai_assist.client import (
    HostedApiAssistClient,
    AssistClientError,
    get_assist_client,
)


def _client_with_transport(handler) -> HostedApiAssistClient:
    client = HostedApiAssistClient(
        base_url="https://assist.example.com", api_key="fake-key", timeout_seconds=5.0
    )
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://assist.example.com",
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


def test_generate_raises_assist_client_error_on_non_2xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client_with_transport(handler)
    with pytest.raises(AssistClientError):
        client.generate("some prompt")


def test_generate_raises_assist_client_error_on_connect_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _client_with_transport(handler)
    with pytest.raises(AssistClientError):
        client.generate("some prompt")


def test_generate_raises_assist_client_error_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = _client_with_transport(handler)
    with pytest.raises(AssistClientError):
        client.generate("some prompt")


def test_generate_raises_assist_client_error_on_malformed_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = _client_with_transport(handler)
    with pytest.raises(AssistClientError):
        client.generate("some prompt")


def test_get_assist_client_returns_none_when_env_vars_unset(monkeypatch):
    monkeypatch.delenv("NARRATIVE_API_URL", raising=False)
    monkeypatch.delenv("NARRATIVE_API_KEY", raising=False)

    assert get_assist_client() is None


def test_get_assist_client_returns_hosted_client_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("NARRATIVE_API_URL", "https://assist.example.com")
    monkeypatch.setenv("NARRATIVE_API_KEY", "fake-key")

    client = get_assist_client()

    assert isinstance(client, HostedApiAssistClient)


def test_get_assist_client_respects_custom_env_var_names(monkeypatch):
    monkeypatch.delenv("NARRATIVE_API_URL", raising=False)
    monkeypatch.delenv("NARRATIVE_API_KEY", raising=False)
    monkeypatch.setenv("CUSTOM_API_URL", "https://custom.example.com")
    monkeypatch.setenv("CUSTOM_API_KEY", "fake-key")

    client = get_assist_client(url_env="CUSTOM_API_URL", key_env="CUSTOM_API_KEY")

    assert isinstance(client, HostedApiAssistClient)
