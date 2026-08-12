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
"""
from __future__ import annotations

from datetime import datetime, timezone
import os

import pandas as pd

from .base import FetchResult, IngestionSource, run_incremental, utcnow

DEFAULT_SUBREDDITS = ("Bitcoin", "CryptoCurrency")


class RedditSentimentConnector(IngestionSource):
    """Fetches new submissions from the configured subreddits and scores them with VADER."""

    def __init__(self, subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS, limit_per_subreddit: int = 500):
        self.subreddits = subreddits
        self.limit_per_subreddit = limit_per_subreddit
        self.name = "reddit_vader_sentiment"
        self._reddit = None
        self._analyzer = None

    def _client(self):
        if self._reddit is None:
            import praw  # local import: keep this an optional dependency of the module

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

    def fetch(self, since: datetime) -> FetchResult:
        reddit = self._client()
        analyzer = self._sentiment_analyzer()
        since_ts = since.timestamp()

        rows: list[dict] = []
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

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("created_utc").reset_index(drop=True)

        return FetchResult(source=self.name, fetched_at=utcnow(), records=df)


def default_seed_watermark() -> datetime:
    """No live Reddit crawl has run yet; the Kaggle seed ends 2024-09-12, but Reddit
    was never the source of that seed, so start from the seed's end date as the
    earliest reasonable overlap point rather than re-fetching years of history
    against Reddit's API in one run."""
    return datetime(2024, 9, 12, tzinfo=timezone.utc)


if __name__ == "__main__":
    run_incremental(
        RedditSentimentConnector(),
        incremental_dir="data/raw/_platform/sentiment/reddit_vader/incremental",
        timestamp_column="created_utc",
        seed_watermark=default_seed_watermark(),
    )
