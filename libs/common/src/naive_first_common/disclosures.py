"""Shared user-facing disclosure text rendered by more than one service.

Text in this module is a platform-wide honesty disclosure, not per-service copy:
`dashboard-web` shows it in the UI and `reporting-service` prints it into the
audit report, and the two must never drift apart -- a tenant reading the report
and a tenant reading the run detail page have to be told the same thing about
the validation protocol. It lives here, in `libs/*`, per CLAUDE.md's DRY rule
("cross-module duplication gets pulled into a `libs/*` package, never
copy-pasted across service boundaries"); the no-cross-service-import rule
forbids one service importing another's code, which is a different thing and
is exactly what this shared package exists to avoid.

Editing any string here changes what every consuming surface renders. That is
the intent -- one edit, one place.
"""

from __future__ import annotations

METHODOLOGY_INTRO = (
    "Every validation run on this platform follows the same leakage-aware protocol, "
    "regardless of this run's own status or outcome:"
)

METHODOLOGY_FACTS: tuple[str, str, str, str] = (
    "Rolling-origin walk-forward validation: each split trains on data up to a point in "
    "time and tests only on the period immediately after it -- never on rows the model "
    "could not yet have seen.",
    "A configurable purge gap separates every split's training window from its test "
    "window, closing the boundary-leakage channel a plain train/test split allows.",
    "Every run is benchmarked against the mandatory Naive0 and NaiveLast baselines -- a "
    "model's result is never reported in isolation.",
    "Model-vs-baseline comparisons use the Diebold-Mariano test with the Harvey et al. "
    "(1997) long-run variance correction for overlapping horizons, not a raw metric "
    "difference.",
)
