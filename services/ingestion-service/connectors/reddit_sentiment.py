"""Sentiment connector: Reddit (via praw) + VADER, replacing the one-off Kaggle
historical dump (data/raw/_platform/sentiment/kaggle_bitcoin_sentiments_21_24/)
as the live, ongoing sentiment source going forward.

Mirrors the reddit_* feature shape already used in the thesis's earlier
feature set (jupyter_notebooks/data/crypto_data_news_reddit_final.csv:
reddit_flair, reddit_tb_polarity, reddit_sid_pos/neg/neu/com) but computes
sentiment with VADER only (vaderSentiment), not TextBlob+VADER — keeping one
well-understood sentiment method rather than reproducing both, since this
library's job is honest validation, not maximizing feature count.

Requires Reddit API credentials as environment variables (never hardcoded):
  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
Create credentials at https://www.reddit.com/prefs/apps (script-type app).

Dependencies (add to services/ingestion-service/requirements.txt):
  praw, vaderSentiment

Tenant-aware credentials (INGEST-004, ADR-0004): when both `tenant_id` and
`credential_repository` are supplied to the constructor, `client_id`/
`client_secret` are resolved via `CredentialRepository.get_credentials`
(decrypted in-process, never logged) instead of `os.environ` -- mirroring
`connectors/base.py`'s `run_incremental` "both supplied -> DB path" convention.
`REDDIT_USER_AGENT` is not a secret and has no `connector_credentials` column,
so it is always read from `os.environ` (with the same default), in both modes.
The plain `os.environ` path for `client_id`/`client_secret` remains the
standalone/no-tenant CLI fallback when either constructor argument is absent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Callable, TYPE_CHECKING

import pandas as pd

from .base import FetchResult, IngestionSource, run_incremental, utcnow

if TYPE_CHECKING:  # pragma: no cover - import-time only, mirrors base.py's
    # own avoidance of a hard runtime dependency on `app`'s src layout.
    from app.repositories.interfaces import CredentialRepository

DEFAULT_SUBREDDITS = ("Bitcoin", "CryptoCurrency")


class RedditSentimentConnector(IngestionSource):
    """Fetches new submissions from the configured subreddits and scores them with VADER."""

    def __init__(
        self,
        subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS,
        limit_per_subreddit: int = 500,
        *,
        tenant_id: str | None = None,
        credential_repository: "CredentialRepository | None" = None,
    ):
        self.subreddits = subreddits
        self.limit_per_subreddit = limit_per_subreddit
        self.name = "reddit_vader_sentiment"
        self._tenant_id = tenant_id
        self._credential_repository = credential_repository
        self._reddit = None
        self._analyzer = None

    def _client(self):
        if self._reddit is None:
            import praw  # local import: keep this an optional dependency of the module

            if self._tenant_id is not None and self._credential_repository is not None:
                credentials = self._credential_repository.get_credentials(self._tenant_id, self.name)
                if credentials is None:
                    raise RuntimeError(
                        f"No credentials stored for tenant {self._tenant_id!r}, source {self.name!r}."
                    )
                client_id = credentials.client_id
                client_secret = credentials.client_secret
            else:
                client_id = os.environ["REDDIT_CLIENT_ID"]
                client_secret = os.environ["REDDIT_CLIENT_SECRET"]
            user_agent = os.environ.get("REDDIT_USER_AGENT", "naive-first-sentiment-connector/0.1")
            self._reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
        return self._reddit

    def _sentiment_analyzer(self):
        if self._analyzer is None:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            self._analyzer = SentimentIntensityAnalyzer()
        return self._analyzer

    def fetch(
        self,
        since: datetime,
        should_cancel: "Callable[[], bool] | None" = None,
        on_progress: "Callable[[int], None] | None" = None,
    ) -> FetchResult:
        """Cancellation checkpoint (INGEST-022): per submission actually
        scored and appended to `rows`, not per subreddit. This is the finer of
        the two loop boundaries this method already has (subreddit, then
        submission within it) -- chosen deliberately so cancellation can take
        effect mid-subreddit rather than only between the two subreddits,
        since a single subreddit's `.new(limit=...)` page can itself be large.
        INGEST-026 (progress reporting) reuses this same per-submission
        boundary; it must not assume a different one. Immediately after each
        submission's row is appended, `on_progress(len(rows))` is called if
        supplied, then `should_cancel()` if supplied; a `True` result stops
        both the inner submission loop and the outer subreddit loop, and the
        returned `FetchResult` is built from whatever is in `rows` so far,
        `cancelled=True`.
        """
        reddit = self._client()
        analyzer = self._sentiment_analyzer()
        since_ts = since.timestamp()

        rows: list[dict] = []
        cancelled = False
        for subreddit_name in self.subreddits:
            subreddit = reddit.subreddit(subreddit_name)
            for submission in subreddit.new(limit=self.limit_per_subreddit):
                if submission.created_utc <= since_ts:
                    continue  # already fetched in a prior run
                text = submission.title if not submission.selftext else f"{submission.title} {submission.selftext}"
                scores = analyzer.polarity_scores(text)
                rows.append(
                    {
                        "created_utc": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                        "subreddit": subreddit_name,
                        "post_id": submission.id,
                        "title": submission.title,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "reddit_sid_pos": scores["pos"],
                        "reddit_sid_neg": scores["neg"],
                        "reddit_sid_neu": scores["neu"],
                        "reddit_sid_com": scores["compound"],
                    }
                )
                if on_progress is not None:
                    on_progress(len(rows))
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
            if cancelled:
                break

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("created_utc").reset_index(drop=True)

        return FetchResult(source=self.name, fetched_at=utcnow(), records=df, cancelled=cancelled)


def default_seed_watermark() -> datetime:
    """No live Reddit crawl has run yet; the Kaggle seed ends 2024-09-12, but Reddit
    was never the source of that seed, so start from the seed's end date as the
    earliest reasonable overlap point rather than re-fetching years of history
    against Reddit's API in one run."""
    return datetime(2024, 9, 12, tzinfo=timezone.utc)


def default_backfill_start() -> datetime:
    """Default backfill depth for a brand-new tenant's first DB crawl
    (INGEST-013) -- distinct from `default_seed_watermark()` above, which is
    only the CSV historical-seed-file cutoff used by this module's own
    `__main__` block, unrelated to a tenant's own per-tenant DB history.

    Unlike `binance_price.default_backfill_start()`/
    `blockchain_onchain.default_backfill_start()`, this is not a verified
    real data boundary -- `praw`'s `.new()` only ever returns the most recent
    ~1000 submissions per subreddit regardless of how far back `since` is
    set, a platform limit, not a calendar date -- so a 5-years-back-from-now
    convention is used instead, per the ticket's own fallback instruction.
    """
    return utcnow() - timedelta(days=5 * 365)


if __name__ == "__main__":
    run_incremental(
        RedditSentimentConnector(),
        incremental_dir="data/raw/_platform/sentiment/reddit_vader/incremental",
        timestamp_column="created_utc",
        seed_watermark=default_seed_watermark(),
    )
