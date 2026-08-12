"""VS-016: pytest entry point for `scripts/check_doc_sync.py`.

Mirrors NFE-018's own `tests/test_doc_sync.py` precedent (a thin pytest
wrapper around the standalone script's `check()` function, so both
`python scripts/check_doc_sync.py` and `pytest` catch the same drift).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_doc_sync import check, diff_routes, parse_readme_routes  # noqa: E402


def test_readme_routes_match_live_app_routes():
    messages = check()
    assert messages == [], "README.md '## Routes' section is out of sync:\n" + "\n".join(messages)


def test_parse_readme_routes_reads_method_and_path():
    readme_text = "\n".join(
        [
            "# validation-service",
            "",
            "## Routes",
            "",
            "- `POST /runs`",
            "- `GET /runs/{run_id}`",
            "",
            "## Something else",
            "- `GET /ignored`",
        ]
    )

    assert parse_readme_routes(readme_text) == {"POST /runs", "GET /runs/{run_id}"}


def test_diff_routes_reports_missing_and_extra_entries():
    code_routes = {"POST /runs", "GET /runs/{run_id}"}
    readme_routes = {"POST /runs", "GET /runs/{run_id}/wrong"}

    messages = diff_routes(code_routes, readme_routes)

    assert any("GET /runs/{run_id}" in m and "missing from README" in m for m in messages)
    assert any("GET /runs/{run_id}/wrong" in m and "not a live route" in m for m in messages)


def test_diff_routes_flags_empty_readme_section():
    messages = diff_routes({"POST /runs"}, set())

    assert messages == ["README.md has no '## Routes' section (or it is empty)"]