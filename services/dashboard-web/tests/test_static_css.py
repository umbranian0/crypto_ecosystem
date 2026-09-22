"""Regression guards for layout rules that only break under real data.

A Jinja render test cannot catch a layout defect, and this service's e2e suite
runs against a stub gateway-api with no ingested datasets -- so the bug these
rules fix was invisible to every existing test. It only appeared in a browser,
against a tenant that actually had datasets. Asserting the rules are present is
a proxy for that, deliberately: it cannot prove the layout is correct, only that
nobody removed the constraint without reading this note.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLE_CSS = Path(__file__).resolve().parents[1] / "src" / "app" / "static" / "style.css"


def _rule_body(selector: str) -> str:
    """The body of the top-level `selector { ... }` rule, comments stripped so a
    rule preceded by an explanatory comment still matches.
    """
    css = re.sub(r"/\*.*?\*/", "", STYLE_CSS.read_text(encoding="utf-8"), flags=re.S)
    match = re.search(rf"(?:^|\}})\s*{re.escape(selector)}\s*\{{([^{{}}]*)\}}", css, re.S)
    assert match, f"no `{selector}` rule found in style.css"
    return match.group(1)


def test_fieldset_cannot_be_stretched_by_a_wide_child() -> None:
    """A fieldset defaults to `min-width: min-content`, so a wide child stretches
    it instead of being constrained by it. The stored-dataset <select> carries
    option labels of ~100 characters (source + full date range + row count),
    which pushed its fieldset 168px past the 560px form and visibly broke it out
    of the panel.
    """
    body = _rule_body("fieldset")

    assert "min-width: 0" in body
    assert "max-width: 100%" in body


def test_select_cannot_drive_page_width() -> None:
    """Complements the fieldset rule: cap the control itself, so no single long
    <option> can drive layout. The option text is deliberately not shortened --
    source, date range and row count are all information a tenant picks on.
    """
    body = _rule_body("select")

    assert "max-width: 100%" in body
