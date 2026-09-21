"""TRUST-003: engine version + config fingerprint computation.

Pure, stateless, no I/O beyond one importlib.metadata lookup (memoized) -- no
network, no DB, no naive_first_engine internals touched. Never used to alter
splitting/baseline/DM-test behavior; purely descriptive metadata persisted
alongside the run row it describes.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib.metadata import version


@lru_cache(maxsize=1)
def get_engine_version() -> str:
    """`naive_first_engine`'s installed distribution version (e.g. "0.1.0"),
    read from package metadata -- not by parsing pyproject.toml at runtime,
    so this stays correct even if a pinned wheel build ever diverges from the
    source tree. Memoized: the installed version cannot change within a
    running process.
    """
    return version("naive_first_engine")


def compute_config_fingerprint(split_config: dict) -> str:
    """SHA-256 of `split_config`'s canonicalized (sorted-key, no-whitespace)
    JSON serialization -- the same logical config always hashes identically
    regardless of incidental key ordering. `split_config` here is exactly the
    dict `_persist_new_run` already builds and persists verbatim as the
    `runs.split_config` JSON column -- no second, independently-shaped
    config object is hashed.
    """
    canonical = json.dumps(split_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
