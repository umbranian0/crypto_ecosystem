"""Doc-sync check: README.md's "Public API" section vs. the four source modules.

LC-005. Implements implementation-plan.md section 8's "for libs, the public
function signatures in the README stay in sync with the code -- CI should
fail if they drift" convention, mirroring `libs/naive_first_engine`'s NFE-018
precedent (`libs/naive_first_engine/scripts/check_doc_sync.py`) in structure,
not literal code -- this lib's module list, README section format, and
public surface are its own.

What it does: for each of tenant_context.py, db.py, contracts.py, testing.py,
it uses the `ast` module (not `inspect`/import) to enumerate top-level `def`/
`class` statements whose name does not start with `_`, and reconstructs each
function's signature text (name + positional/keyword-only params, with
default *expressions* rendered as written in source) directly from the
source tree. Static AST parsing is used instead of `importlib`/`inspect` so
the check does not need the package installed/importable and cannot execute
module-level side effects (relevant here since `tenant_context.py` and
`testing.py` both reference FastAPI/pytest constructs at module scope).

Signature-strictness choice (mirrors NFE-018's own "dev agent's call"): full
parameter list, in order, including default-value expressions, but NOT type
annotations, for the same reason NFE-018 gave -- annotation text is noisy to
hand-maintain in the README and this library's docstrings are the source of
truth for types. Classes are listed as bare `ClassName` (no `__init__`
signature) since `TenantContext` is a Pydantic model (fields, not a
hand-written constructor, are the contract).

The README's "## Public API" section is parsed with the same deliberately
simple line grammar NFE-018 uses (see `parse_readme_public_api`) rather than
a Markdown library, since the format is fully controlled by this
script/ticket.

Usage: `python scripts/check_doc_sync.py` (or `pytest` via
tests/test_doc_sync.py). Exit code 0 = in sync, 1 = drift detected (message
printed to stdout, one line per divergence).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

MODULE_NAMES = [
    "tenant_context.py",
    "db.py",
    "contracts.py",
    "testing.py",
    "logging.py",
]

LIB_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = LIB_ROOT / "src" / "naive_first_common"
README_PATH = LIB_ROOT / "README.md"

_MODULE_HEADING_RE = re.compile(r"^### `(?P<module>\w+\.py)`\s*$")
_ENTRY_RE = re.compile(r"^- `(?P<entry>[^`]+)`(?P<class_suffix> \(class\))?\s*$")


def _format_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render `def name(a, b, c=default): ...` as `name(a, b, c=default)`."""
    args = node.args
    parts: list[str] = []

    positional = [*args.posonlyargs, *args.args]
    num_no_default = len(positional) - len(args.defaults)
    for i, arg in enumerate(positional):
        if i < num_no_default:
            parts.append(arg.arg)
        else:
            default = args.defaults[i - num_no_default]
            parts.append(f"{arg.arg}={ast.unparse(default)}")

    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is None:
            parts.append(arg.arg)
        else:
            parts.append(f"{arg.arg}={ast.unparse(default)}")

    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    return f"{node.name}({', '.join(parts)})"


def extract_public_api(source_path: Path) -> dict[str, tuple[str, bool]]:
    """Return {name: (entry_text, is_class)} for public top-level defs/classes."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    api: dict[str, tuple[str, bool]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            api[node.name] = (_format_function_signature(node), False)
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            api[node.name] = (node.name, True)
    return api


def collect_code_api() -> dict[str, dict[str, tuple[str, bool]]]:
    return {module: extract_public_api(SRC_DIR / module) for module in MODULE_NAMES}


def parse_readme_public_api(readme_text: str) -> dict[str, dict[str, tuple[str, bool]]]:
    """Parse the '### `module.py`' / '- `entry`' blocks under '## Public API'."""
    lines = readme_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## Public API")
    except StopIteration:
        return {}

    api: dict[str, dict[str, tuple[str, bool]]] = {}
    current_module: str | None = None
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        heading_match = _MODULE_HEADING_RE.match(line)
        if heading_match:
            current_module = heading_match.group("module")
            api.setdefault(current_module, {})
            continue
        entry_match = _ENTRY_RE.match(line)
        if entry_match and current_module is not None:
            entry = entry_match.group("entry")
            is_class = entry_match.group("class_suffix") is not None
            name = entry.split("(", 1)[0]
            api[current_module][name] = (entry, is_class)
    return api


def diff_apis(
    code_api: dict[str, dict[str, tuple[str, bool]]],
    readme_api: dict[str, dict[str, tuple[str, bool]]],
) -> list[str]:
    messages: list[str] = []
    for module in MODULE_NAMES:
        code_entries = code_api.get(module, {})
        readme_entries = readme_api.get(module, {})

        for name, (entry, _) in sorted(code_entries.items()):
            if name not in readme_entries:
                messages.append(f"{module}: `{entry}` is in code but not README")
        for name, (entry, _) in sorted(readme_entries.items()):
            if name not in code_entries:
                messages.append(f"{module}: `{entry}` is in README but not code")

        for name in sorted(set(code_entries) & set(readme_entries)):
            code_entry, _ = code_entries[name]
            readme_entry, _ = readme_entries[name]
            if code_entry != readme_entry:
                messages.append(
                    f"{module}: signature mismatch for `{name}` -- "
                    f"code has `{code_entry}`, README has `{readme_entry}`"
                )

    if not readme_api:
        messages.append("README.md has no '## Public API' section")
    else:
        extra_modules = set(readme_api) - set(MODULE_NAMES)
        for module in sorted(extra_modules):
            messages.append(f"README.md documents unknown module `{module}` (not in check's module list)")

    return messages


def check() -> list[str]:
    code_api = collect_code_api()
    readme_api = parse_readme_public_api(README_PATH.read_text(encoding="utf-8"))
    return diff_apis(code_api, readme_api)


def main() -> int:
    messages = check()
    if messages:
        print("README.md public-API list is out of sync with the code:\n")
        for message in messages:
            print(f"  - {message}")
        print(f"\n{len(messages)} divergence(s). Update {README_PATH} or the source module(s) above.")
        return 1
    print("README.md public-API list matches the code across all four modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
