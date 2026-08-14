"""Doc-sync check: README.md's "## Routes" section vs. the live FastAPI route set.

RS-008. Implements implementation-plan.md section 8's "for services, FastAPI's
generated OpenAPI schema is the source of truth -- don't hand-maintain a
duplicate" convention, applied to route *existence* (not full request/response
shape, which `/openapi.json`/`/docs` already cover authoritatively).

What it does: imports `app.main.app` (a real import -- unlike
`naive_first_engine`'s NFE-018 `check_doc_sync.py`, which uses `ast` parsing
to avoid importing a standalone lib, this service is already a running
FastAPI app with fully wired routers, so introspecting the real, live
`app.routes` is both simpler and strictly more accurate than re-parsing
source) and compares its route set (method + path, excluding the
framework-injected `HEAD`/`OPTIONS` methods and FastAPI's own
`/openapi.json`/`/docs`/`/redoc` routes) against the README's "## Routes"
list.

This check intentionally does NOT compare request/response field shapes --
that duplication is exactly what this ticket keeps out of the README in favor
of pointing at `/openapi.json`/`/docs`. It only catches the case where a route
is added/removed/renamed in code but the README's route list goes stale, or
vice versa.

The README's "## Routes" section is parsed with a matching, deliberately
simple line grammar (see `parse_readme_routes`) rather than a Markdown
library, since the format is fully controlled by this script/ticket.

Mirrors validation-service's VS-016 `scripts/check_doc_sync.py` exactly
(ticket RS-008 DRY check note), adapted only to reporting-service's own
route list.

Usage: `python scripts/check_doc_sync.py` (or `pytest` via
tests/test_doc_sync.py). Exit code 0 = in sync, 1 = drift detected (message
printed to stdout, one line per divergence).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
README_PATH = SERVICE_ROOT / "README.md"

# FastAPI/Starlette auto-generated routes that are not part of this service's
# own documented contract -- never expected in the README's "## Routes" list.
_FRAMEWORK_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

# Methods Starlette adds automatically to every route (HEAD alongside GET,
# OPTIONS for CORS preflight) -- not hand-declared by any route handler, so
# not expected to be individually documented in the README.
_IMPLICIT_METHODS = {"HEAD", "OPTIONS"}

_ROUTE_ENTRY_RE = re.compile(
    r"^- `(?P<method>[A-Z]+) (?P<path>/\S*)`\s*$"
)


def _flatten_routes(routes, prefix: str = "") -> list[tuple[str, set[str]]]:
    """Recursively expand included sub-routers into (full_path, methods) pairs.

    Newer FastAPI/Starlette versions wrap an `include_router()`d router in a
    lazy `_IncludedRouter` placeholder on `app.routes` instead of eagerly
    flattening its routes at include time -- such placeholders expose no
    `path`/`methods` of their own, only an `original_router` whose own
    `.routes` holds the real `APIRoute` objects. Detected structurally (via
    `original_router`, not an isinstance/class-name check against a private
    FastAPI class) so this keeps working across FastAPI versions that may
    flatten eagerly instead.

    Unlike validation-service's VS-016 precedent (whose routers declare their
    full path and are mounted via a bare `app.include_router(router)`, so a
    route's own `.path` is already complete), this service's `main.py` mounts
    both routers with `prefix="/reports"` (`report_generation.py`/
    `report_retrieval.py` declare relative paths like `/generate`). On this
    FastAPI version the mount prefix lives only on the `_IncludedRouter`
    placeholder's `include_context.prefix`, not on the leaf `APIRoute.path`
    -- accumulated here across nesting levels so a leaf route's real,
    request-matched path is reconstructed rather than silently truncated to
    its router-relative form.
    """
    flattened: list[tuple[str, set[str]]] = []
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            include_context = getattr(route, "include_context", None)
            sub_prefix = getattr(include_context, "prefix", "") or ""
            flattened.extend(_flatten_routes(original_router.routes, prefix + sub_prefix))
        else:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path is None or methods is None:
                continue
            flattened.append((prefix + path, methods))
    return flattened


def collect_code_routes() -> set[str]:
    """Return {"METHOD /path", ...} for the live app's real route set."""
    # Imported lazily (not at module scope) so `--help`/import errors in the
    # app don't shadow this script's own argument handling, and so pytest's
    # collection of this module (via tests/test_doc_sync.py) doesn't require
    # the app to import successfully just to reach `main()`.
    from app.main import app

    routes: set[str] = set()
    for path, methods in _flatten_routes(app.routes):
        if path in _FRAMEWORK_PATHS:
            continue
        for method in methods:
            if method in _IMPLICIT_METHODS:
                continue
            routes.add(f"{method} {path}")
    return routes


def parse_readme_routes(readme_text: str) -> set[str]:
    """Parse the '- `METHOD /path`' entries under README.md's '## Routes'."""
    lines = readme_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## Routes")
    except StopIteration:
        return set()

    routes: set[str] = set()
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        match = _ROUTE_ENTRY_RE.match(line)
        if match:
            routes.add(f"{match.group('method')} {match.group('path')}")
    return routes


def diff_routes(code_routes: set[str], readme_routes: set[str]) -> list[str]:
    messages: list[str] = []

    if not readme_routes:
        messages.append("README.md has no '## Routes' section (or it is empty)")
        return messages

    for route in sorted(code_routes - readme_routes):
        messages.append(f"`{route}` is a live route (app.routes) but missing from README.md")
    for route in sorted(readme_routes - code_routes):
        messages.append(f"`{route}` is documented in README.md but is not a live route (app.routes)")

    return messages


def check() -> list[str]:
    code_routes = collect_code_routes()
    readme_routes = parse_readme_routes(README_PATH.read_text(encoding="utf-8"))
    return diff_routes(code_routes, readme_routes)


def main() -> int:
    messages = check()
    if messages:
        print("README.md's '## Routes' list is out of sync with the live app.routes:\n")
        for message in messages:
            print(f"  - {message}")
        print(f"\n{len(messages)} divergence(s). Update {README_PATH} or the route(s) above.")
        return 1
    print("README.md's '## Routes' list matches the live FastAPI app.routes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
