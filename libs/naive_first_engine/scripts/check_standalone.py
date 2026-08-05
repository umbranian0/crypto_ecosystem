"""NFE-017: standalone publishability check.

What it does: proves libs/naive_first_engine can be pip-installed and used
in total isolation from the rest of this repo (solution-design.md section
3.4's "extracted and published standalone without a rewrite" promise). It
creates a throwaway venv, installs *only* this package's own pyproject.toml
into it (no `-e`, no workspace-root resolution, no requirements.txt reaching
outside this directory), then from inside that venv imports
naive_first_engine and runs a minimal run_validation_protocol call.

Why .py and not .sh: this repo's dev environment is Windows/PowerShell
(see NFE-001's ticket/README note on the `.venv`/`uv run` sandbox issue) --
a Python script using `sys.executable`/`venv`/`subprocess` runs identically
on Windows and POSIX, whereas a `.sh` script would need a separate `.ps1`
twin to be usable here.

How to re-run: `python scripts/check_standalone.py` from within
libs/naive_first_engine (any Python 3.10+ interpreter on PATH is fine --
this script only needs the stdlib, not the repo's own dev .venv).

When to re-run: whenever a dependency is added to, removed from, or
version-bumped in this package's pyproject.toml, and before any claim that
this package is publishable standalone.

Exit code is non-zero on any failure, so this can be wired into a future
CI step unmodified.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent

SMOKE_SCRIPT = """
import sys

import pandas as pd
import numpy as np

import naive_first_engine
from naive_first_engine.protocol import ValidationConfig, run_validation_protocol

index = pd.date_range("2024-01-01", periods=40, freq="h")
series = pd.Series(np.random.default_rng(0).normal(0.0, 1.0, size=40), index=index, name="y")
config = ValidationConfig(train_window=20, test_window=5, step=5, purge_gap=0, horizon=1)

results = run_validation_protocol(series, config)
assert len(results) > 0, "run_validation_protocol returned no splits"
print(f"OK: run_validation_protocol produced {len(results)} split(s)")
"""


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"+ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def main() -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix="nfe_standalone_check_"))
    venv_dir = tmp_dir / ".venv"
    print(f"[1/5] Creating throwaway venv at {venv_dir}")
    try:
        venv.EnvBuilder(with_pip=True).create(venv_dir)

        if sys.platform == "win32":
            python = venv_dir / "Scripts" / "python.exe"
        else:
            python = venv_dir / "bin" / "python"

        print(f"[2/5] Installing {PACKAGE_DIR} into the throwaway venv (pip install ., no -e)")
        _run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
        _run([str(python), "-m", "pip", "install", "--quiet", str(PACKAGE_DIR)])

        print("[2/5] Installed packages in the throwaway venv (proves isolation):")
        _run([str(python), "-m", "pip", "list"])

        print("[3/5] Running smoke check inside the throwaway venv")
        _run([str(python), "-c", SMOKE_SCRIPT])

        print("[4/5] PASS: naive_first_engine installs and runs standalone in an isolated venv")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"[4/5] FAIL: {exc}")
        return 1
    finally:
        print(f"[5/5] Cleaning up throwaway venv at {tmp_dir}")
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
