"""LC-005: README.md's Public API section must stay in sync with the code.

Wraps scripts/check_doc_sync.py's `check()` so drift is caught by the normal
pytest run, not only by someone remembering to run the script by hand.
Mirrors libs/naive_first_engine's NFE-018 test_doc_sync.py in structure.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_doc_sync.py"
_spec = importlib.util.spec_from_file_location("common_check_doc_sync", _SCRIPT_PATH)
common_check_doc_sync = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("common_check_doc_sync", common_check_doc_sync)
_spec.loader.exec_module(common_check_doc_sync)


def test_readme_public_api_matches_code():
    divergences = common_check_doc_sync.check()
    assert divergences == [], "README.md Public API section is out of sync:\n" + "\n".join(divergences)
