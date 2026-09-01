"""Tests for `connectors.reddit_sentiment.RedditSentimentConnector`.

`_client()`/`_sentiment_analyzer()` are replaced directly on the instance
(both are lazily built and memoized on `self._reddit`/`self._analyzer`) so
these tests need neither real Reddit credentials nor the `praw`/
`vaderSentiment` packages' real network/model behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import credential_crypto as cc
from connectors.base import run_incremental
from connectors.reddit_sentiment import RedditSentimentConnector
from fake_repository import FakeConnectorRecordRepository, FakeCredentialRepository


class _FakeSubmission:
    def __init__(self, created_utc: float, title: str, selftext: str = "", post_id: str = "abc") -> None:
        self.created_utc = created_utc
        self.title = title
        self.selftext = selftext
        self.id = post_id
        self.score = 10
        self.num_comments = 2


class _FakeSubreddit:
    def __init__(self, submissions: list[_FakeSubmission]) -> None:
        self._submissions = submissions

    def new(self, limit: int):
        return iter(self._submissions)


class _FakeReddit:
    def __init__(self, submissions_by_subreddit: dict[str, list[_FakeSubmission]]) -> None:
        self._by_subreddit = submissions_by_subreddit

    def subreddit(self, name: str) -> _FakeSubreddit:
        return _FakeSubreddit(self._by_subreddit.get(name, []))


class _FakeAnalyzer:
    def polarity_scores(self, text: str) -> dict:
        return {"pos": 0.1, "neg": 0.2, "neu": 0.7, "compound": -0.1}


def _connector_with_fakes(submissions_by_subreddit: dict[str, list[_FakeSubmission]]) -> RedditSentimentConnector:
    connector = RedditSentimentConnector(subreddits=("Bitcoin",))
    connector._reddit = _FakeReddit(submissions_by_subreddit)
    connector._analyzer = _FakeAnalyzer()
    return connector


def test_fetch_skips_submissions_at_or_before_since() -> None:
    since = datetime(2026, 1, 2, tzinfo=timezone.utc)
    old = _FakeSubmission(created_utc=datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp(), title="old")
    new = _FakeSubmission(created_utc=datetime(2026, 1, 3, tzinfo=timezone.utc).timestamp(), title="new")
    connector = _connector_with_fakes({"Bitcoin": [old, new]})

    result = connector.fetch(since=since)

    assert len(result.records) == 1
    assert result.records.iloc[0]["title"] == "new"


def test_fetch_includes_selftext_when_present() -> None:
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    submission = _FakeSubmission(
        created_utc=datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp(),
        title="title only",
        selftext="body text",
    )
    connector = _connector_with_fakes({"Bitcoin": [submission]})

    result = connector.fetch(since=since)

    # Both fields are recorded even though the combined text (title+selftext)
    # is only used internally for scoring, not stored as its own column.
    assert result.records.iloc[0]["title"] == "title only"


def test_fetch_returns_empty_dataframe_when_nothing_new() -> None:
    since = datetime(2026, 1, 5, tzinfo=timezone.utc)
    old = _FakeSubmission(created_utc=datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp(), title="old")
    connector = _connector_with_fakes({"Bitcoin": [old]})

    result = connector.fetch(since=since)

    assert result.is_empty()


def test_fetch_attaches_vader_sentiment_scores() -> None:
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    submission = _FakeSubmission(created_utc=datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp(), title="x")
    connector = _connector_with_fakes({"Bitcoin": [submission]})

    result = connector.fetch(since=since)

    row = result.records.iloc[0]
    assert row["reddit_sid_com"] == -0.1
    assert row["reddit_sid_pos"] == 0.1


def test_run_incremental_writes_sentiment_records_via_repository(tmp_path) -> None:
    """INGEST-003 DB-write path: writes via `repository.add_sentiment_records`,
    not a CSV.
    """
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    submission = _FakeSubmission(created_utc=datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp(), title="x")
    connector = _connector_with_fakes({"Bitcoin": [submission]})
    repository = FakeConnectorRecordRepository()

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="created_utc",
        seed_watermark=since,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="sentiment",
    )

    assert len(repository.sentiment) == 1
    tenant_id, source, records = repository.sentiment[0]
    assert tenant_id == "tenant-a"
    assert source == connector.name
    assert records.iloc[0]["post_id"] == "abc"
    assert "fetched_at" in records.columns
    assert list(tmp_path.glob("*.csv")) == []


def test_client_resolves_credentials_from_repository_when_tenant_aware(monkeypatch) -> None:
    """INGEST-004: when both `tenant_id` and `credential_repository` are
    supplied, `_client()` must resolve `client_id`/`client_secret` from the
    repository, not `os.environ` -- proven here by deliberately leaving both
    Reddit env vars unset (`os.environ` would raise `KeyError` if the
    connector fell back to it).
    """
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", cc.generate_key().decode("utf-8"))

    connector = RedditSentimentConnector(
        subreddits=("Bitcoin",), tenant_id="tenant-a", credential_repository=FakeCredentialRepository()
    )
    connector._credential_repository.set_credentials(
        "tenant-a", connector.name, client_id="repo-client-id", client_secret="repo-client-secret"
    )

    captured: dict[str, str] = {}

    class _CapturingPraw:
        @staticmethod
        def Reddit(client_id: str, client_secret: str, user_agent: str):
            captured["client_id"] = client_id
            captured["client_secret"] = client_secret
            return _FakeReddit({})

    monkeypatch.setitem(__import__("sys").modules, "praw", _CapturingPraw())

    connector._client()

    assert captured["client_id"] == "repo-client-id"
    assert captured["client_secret"] == "repo-client-secret"


def test_client_falls_back_to_env_when_not_tenant_aware(monkeypatch) -> None:
    """The standalone/no-tenant CLI fallback (existing `os.environ` path) is
    kept intact -- proven by exercising it with neither `tenant_id` nor
    `credential_repository` supplied.
    """
    monkeypatch.setenv("REDDIT_CLIENT_ID", "env-client-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "env-client-secret")

    connector = RedditSentimentConnector(subreddits=("Bitcoin",))

    captured: dict[str, str] = {}

    class _CapturingPraw:
        @staticmethod
        def Reddit(client_id: str, client_secret: str, user_agent: str):
            captured["client_id"] = client_id
            captured["client_secret"] = client_secret
            return _FakeReddit({})

    monkeypatch.setitem(__import__("sys").modules, "praw", _CapturingPraw())

    connector._client()

    assert captured["client_id"] == "env-client-id"
    assert captured["client_secret"] == "env-client-secret"
