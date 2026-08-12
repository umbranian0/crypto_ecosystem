"""Tests for `connectors.reddit_sentiment.RedditSentimentConnector`.

`_client()`/`_sentiment_analyzer()` are replaced directly on the instance
(both are lazily built and memoized on `self._reddit`/`self._analyzer`) so
these tests need neither real Reddit credentials nor the `praw`/
`vaderSentiment` packages' real network/model behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone

from connectors.reddit_sentiment import RedditSentimentConnector


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
