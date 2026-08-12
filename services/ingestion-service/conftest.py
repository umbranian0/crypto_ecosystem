"""Ensures `connectors` (this service's only package, no pyproject.toml/src
layout yet) is importable from `tests/` regardless of pytest's import-mode
defaults.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
