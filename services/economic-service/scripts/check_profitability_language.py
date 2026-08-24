"""ECON-006: grep-style check that no docstring, log message, or README line
outside `src/app/eligibility.py` implies this service currently generates
real profit.

Precedent, per this ticket's DRY check note: `libs/naive_first_engine`'s
NFE-018, `libs/common`'s LC-005, and `services/validation-service`'s VS-016
all pair a standalone `scripts/check_*.py` (importable, runnable via
`python scripts/check_*.py`) with a thin pytest wrapper
(`tests/test_*.py`). This check reuses that same two-file structure, even
though -- unlike those three, which introspect *structured facts* (a route
set, a public function-signature list) -- this check scans *prose* for a
fixed forbidden-word list. A standalone script is still the right shape: it
keeps the check runnable outside pytest (e.g. a future pre-commit hook) and
keeps the "read the real files on disk, don't trust a comment claiming
they're clean" precedent those three scripts established.

**What "outside eligibility.py" means, exactly**: this ticket's binding scope
(ECON-006.md, backlog-economic-service.md) draws the exception at the
*module*, not a sub-region within it -- `src/app/eligibility.py`'s own module
docstring and `compute_economic_simulation`'s docstring are both
"necessarily descriptive" of the one real profitability computation this
service contains, and the ticket names that whole module as the allowed
exception. So this check simply never opens `eligibility.py` at all.

**Forbidden-pattern list (word-boundaried, case-insensitive) and the
reasoning behind each entry** -- this is the ticket's required "document the
exact pattern list and how you drew the line" judgment call:

- `profitable` -- direct adjective claim ("a profitable model").
- `profit` (bare noun/verb, NOT matching inside `profitability` -- `\bprofit\b`
  requires a word boundary right after the "t", so "profitability" never
  matches, only the standalone word "profit" does). This codebase's existing,
  correct prose talks about the *concept* almost exclusively via
  "profitability" (a "profitability figure/column/output/computation/claim/
  field") -- that noun form is deliberately NOT in this forbidden list, only
  the bare "profit" is, because "profitability" is the word this codebase
  already uses to describe the gate's own purpose (see README.md's own
  framing, `app/eligibility.py`, `app/contracts.py`, `app/models.py`,
  `app/repositories/interfaces.py`).
- `alpha` -- the trading-jargon sense CLAUDE.md itself names ("selling the
  rigor ... not alpha"). Does not currently appear anywhere in scope.
- `beats the market` / `beat the market` -- CLAUDE.md's own phrase.
- `makes money` / `make money` -- plain-language near-synonym for "is
  profitable", named in the ticket.
- `returns money` / `return money` -- plain-language near-synonym, named in
  the ticket. Deliberately NOT the bare word "return(s)" -- that word is
  this codebase's normal, legitimate domain vocabulary for the *thing the
  gate withholds until eligibility* (`cost_adjusted_return`,
  "cost/slippage-adjusted returns", "a numeric return figure") and appears
  correctly dozens of times outside `eligibility.py`; only the specific
  "money" collocation asserts an actual monetary gain.
- `generate real returns` / `generates real returns` -- the exact assertion
  phrasing this ticket's own instructions used ("DOES generate real
  returns") to describe the forbidden claim, as distinct from the allowed
  "will compute cost/slippage-adjusted returns once ... eligibility" framing
  (conditional on a future gate-pass, not an assertion of a current one).

**How concept-discussion is distinguished from a profitability claim**: a
hand-curated `ALLOWED_EXCEPTIONS` list of exact substrings, one entry per
known-legitimate current usage, each with an inline reason. This check
intentionally does NOT use a fuzzy "does the line also contain a negation
word like 'no'/'never'" heuristic -- that would be a second, harder-to-audit
piece of logic prone to both false negatives (a real claim sitting next to
an unrelated negation word elsewhere on a long line) and false positives
(a legitimate new negated sentence the heuristic doesn't happen to phrase
the way the heuristic expects). An explicit, reviewable allowlist matches
this repo's existing "introspect the real thing, document the exact list"
convention (NFE-018/LC-005/VS-016) and fails safe: any new "profit"/
"profitable"/etc. mention that isn't already on the allowlist is flagged for
human review rather than silently passed.

Usage: `python scripts/check_profitability_language.py` (or `pytest` via
`tests/test_profitability_language.py`). Exit code 0 = clean, 1 = forbidden
language found outside the allowed exception (message printed to stdout,
one line per hit).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
README_PATH = SERVICE_ROOT / "README.md"
SRC_APP_DIR = SERVICE_ROOT / "src" / "app"

# The one module this ticket names as the allowed exception -- never opened.
_EXEMPT_MODULE = SRC_APP_DIR / "eligibility.py"

_FORBIDDEN_PATTERNS: dict[str, re.Pattern[str]] = {
    "profitable": re.compile(r"\bprofitable\b", re.IGNORECASE),
    "profit": re.compile(r"\bprofit\b", re.IGNORECASE),
    "alpha": re.compile(r"\balpha\b", re.IGNORECASE),
    "beats the market": re.compile(r"\bbeats?\s+the\s+market\b", re.IGNORECASE),
    "makes money": re.compile(r"\bmakes?\s+money\b", re.IGNORECASE),
    "returns money": re.compile(r"\breturns?\s+money\b", re.IGNORECASE),
    "generate(s) real returns": re.compile(
        r"\bgenerates?\s+real\s+returns\b", re.IGNORECASE
    ),
}

# Exact substrings of known-legitimate current usage, each a documented
# judgment call (see module docstring). A line is only excused if one of
# these substrings is present verbatim -- a new, un-allowlisted mention of
# the same forbidden word still fails, by design.
_ALLOWED_EXCEPTIONS: list[str] = [
    # README.md's own CLAUDE.md-mandated disclaimer sentence: explicitly
    # states the platform must NOT be read as currently having a profitable
    # model -- the concept-discussion use this whole ticket exists to permit.
    "must never be read as evidence the platform currently has a profitable model",
    # contracts.py (x2): a quoted string describing the exact serialization
    # bug this design prevents ("a bug could make a refusal look like a
    # 'no profit' result") -- not a claim that the service has ever produced
    # such a figure.
    '"no profit"',
    # ECON-014: models.py's BacktestResult docstring (ECON-013, landed the
    # same sprint) names the forbidden-substring list
    # test_no_profitability_columns.py itself enforces against column names
    # -- a concept-discussion use of the word "profit" (naming the pattern a
    # column name must NOT match), not a claim this service has computed or
    # stored one. Mirrors the "no profit" contracts.py exception immediately
    # above in kind, not mechanism.
    "still rejecting `pnl`/`profit`/`net_return`/`revenue`/`forecast_*`/`win`/",
]


def _is_allowed(line: str) -> bool:
    return any(exception in line for exception in _ALLOWED_EXCEPTIONS)


def _scan_text(source_label: str, text: str) -> list[str]:
    hits: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _is_allowed(line):
            continue
        for term, pattern in _FORBIDDEN_PATTERNS.items():
            if pattern.search(line):
                hits.append(f"{source_label}:{line_number}: forbidden term {term!r} -- {line.strip()}")
    return hits


def collect_scan_targets() -> list[Path]:
    """README.md plus every `.py` file under `src/app`, excluding the one
    ticket-named exempt module (`eligibility.py`)."""
    targets = [README_PATH]
    for path in sorted(SRC_APP_DIR.rglob("*.py")):
        if path == _EXEMPT_MODULE:
            continue
        targets.append(path)
    return targets


def check() -> list[str]:
    messages: list[str] = []
    for path in collect_scan_targets():
        label = str(path.relative_to(SERVICE_ROOT)).replace("\\", "/")
        messages.extend(_scan_text(label, path.read_text(encoding="utf-8")))
    return messages


def main() -> int:
    messages = check()
    if messages:
        print(
            "Forbidden profitability-claim language found outside "
            "src/app/eligibility.py's allowed exception:\n"
        )
        for message in messages:
            print(f"  - {message}")
        print(
            f"\n{len(messages)} hit(s). Reword the line(s) above, or if this is a "
            "genuinely new legitimate concept-discussion use (mirroring "
            "the existing entries in _ALLOWED_EXCEPTIONS), add it there with "
            "a documented reason."
        )
        return 1
    print(
        "No forbidden profitability-claim language found outside "
        "src/app/eligibility.py."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
