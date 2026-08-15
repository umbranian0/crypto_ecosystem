"""ECON-004 tests.

Structural-introspection test mirrors validation-service's VS-016
`check_doc_sync.py` precedent ("prove a structural fact by introspecting the
real running app/DI wiring, not by trusting a comment"): rather than trusting
this module's own docstrings, `test_mock_client_is_the_only_di_wired_implementation`
walks every `.py` file actually shipped under `src/app/` with `ast`, finds
every class definition that structurally implements
`UpstreamValidationResultClient` (declares a `get_result` method), and
asserts the set has exactly one member -- `MockValidationResultClient` --
*and* separately proves that `app.dependencies.upstream.get_upstream_client`
(the real `Depends()` default every route would actually receive) returns an
instance of exactly that class, not merely "some object with the right
shape".
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.contracts import UpstreamValidationResult
from app.dependencies.upstream import (
    UpstreamValidationResultClientDep,
    get_upstream_client,
)
from app.upstream_client import MockValidationResultClient, UpstreamValidationResultClient

APP_SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "app"


def _is_protocol_stub_body(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if `func`'s body is just a `...` stub (optionally preceded by a
    docstring) -- i.e. it's an interface method declaration, not a real
    implementation. Distinguishes `UpstreamValidationResultClient.get_result`
    (a `typing.Protocol` method signature, body `...`) from
    `MockValidationResultClient.get_result` (a real body that returns a
    value) without relying on base-class name resolution, which `ast` alone
    can't reliably do across import aliases.
    """
    body = func.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]  # skip a leading docstring
    return len(body) == 1 and isinstance(body[0], ast.Expr) and body[0].value.__class__ is ast.Constant and body[0].value.value is Ellipsis


def _classes_implementing_get_result(source_root: Path) -> set[str]:
    """Return {"module.dotted.path.ClassName", ...} for every class defined
    anywhere under `source_root` that declares a *real* (non-Protocol-stub)
    `get_result` method -- i.e. every class that actually implements
    `UpstreamValidationResultClient`, found by parsing the real shipped
    source files, not by trusting an import list or a comment. The Protocol
    interface itself (`get_result`'s body is just `...`) is deliberately
    excluded -- it declares the contract, it does not implement it.
    """
    implementers: set[str] = set()
    for py_file in source_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        module_dotted = ".".join(
            ("app",) + py_file.relative_to(source_root).with_suffix("").parts
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if (
                        isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and child.name == "get_result"
                        and not _is_protocol_stub_body(child)
                    ):
                        implementers.add(f"{module_dotted}.{node.name}")
    return implementers


def test_mock_client_is_the_only_di_wired_implementation() -> None:
    implementers = _classes_implementing_get_result(APP_SRC_DIR)

    assert implementers == {"app.upstream_client.MockValidationResultClient"}, (
        "Exactly one class implementing UpstreamValidationResultClient's "
        "get_result method may exist in src/app/ this sprint (README.md "
        f"trigger-#11 override disclosure); found: {implementers}"
    )

    wired_instance = get_upstream_client()

    assert type(wired_instance) is MockValidationResultClient
    assert isinstance(wired_instance, UpstreamValidationResultClient)


def test_upstream_validation_result_client_dep_default_is_mock_client() -> None:
    default = UpstreamValidationResultClientDep.__metadata__[0].dependency
    assert default is get_upstream_client
    assert type(default()) is MockValidationResultClient


@pytest.mark.parametrize(
    ("tenant_id", "validation_run_id"),
    [
        ("tenant-1", "run-abc123"),
        ("tenant-2-with-a-very-different-shape", "run-xyz-999"),
    ],
)
def test_mock_client_result_source_is_always_mock_fixture_never_live(
    tenant_id: str, validation_run_id: str
) -> None:
    client = MockValidationResultClient()

    result = client.get_result(tenant_id, validation_run_id)

    assert isinstance(result, UpstreamValidationResult)
    assert result.source == "mock_fixture"
    assert result.source != "live"


def test_mock_client_repr_makes_fabrication_unambiguous() -> None:
    client = MockValidationResultClient()

    representation = repr(client)

    assert "mock_fixture" in representation
    assert "no real validation-service call" in representation


def test_upstream_client_module_has_no_httpx_import_and_no_url_env_var_read() -> None:
    source = (APP_SRC_DIR / "upstream_client.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    # "os" not in imported_roots is the real structural guarantee here -- an
    # env var read is impossible without importing os (or an equivalent),
    # and none is imported. A raw "_URL" substring search across the whole
    # file (including this module's own docstring, which explains this rule
    # in prose using the literal text "*_URL") produces a false positive on
    # documentation, not on code -- so the substring check below is scoped
    # to non-docstring source only (triple-quoted string literals stripped).
    assert "httpx" not in imported_roots
    assert "os" not in imported_roots
    code_without_docstrings = re.sub(r'"""[\s\S]*?"""', "", source)
    assert "_URL" not in code_without_docstrings
