"""AI-004-02: `run_new.html`'s conversational widget + finished
`_configure_run_suggestions.html` -- template-rendering tests only, no new
backend logic. Mirrors `tests/test_configure_run.py`'s Jinja render approach.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.assistant.configure_run import ConfigureRunResult, RunFieldSuggestion
from app.main import templates

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src" / "app" / "templates"


def _render(template_name: str, **context) -> str:
    template = templates.env.get_template(template_name)
    return template.render(**context)


# -- run_new.html: widget lives outside <form id="run-form"> ----------------


def test_configure_run_widget_lives_outside_run_form():
    source = (TEMPLATES_DIR / "run_new.html").read_text(encoding="utf-8")

    form_match = re.search(
        r'<form method="post" action="/runs/new" id="run-form".*?</form>',
        source,
        re.DOTALL,
    )
    assert form_match is not None
    form_body = form_match.group(0)

    assert "configure-run-widget" not in form_body
    assert "configure-run-suggestions" not in form_body
    assert "/assistant/configure-run" not in form_body


def test_configure_run_widget_present_before_run_form():
    source = (TEMPLATES_DIR / "run_new.html").read_text(encoding="utf-8")

    widget_index = source.index('id="configure-run-widget"')
    form_index = source.index('id="run-form"')

    assert widget_index < form_index
    assert 'hx-post="/assistant/configure-run"' in source
    assert 'hx-target="#configure-run-suggestions"' in source


def test_configure_run_widget_badges_hidden_by_default_in_run_form():
    source = (TEMPLATES_DIR / "run_new.html").read_text(encoding="utf-8")

    for field in ("horizon", "purge_gap_hours", "train_window", "test_window", "step", "label"):
        assert f'id="{field}-suggestion-badge"' in source
        badge_match = re.search(
            rf'<span id="{field}-suggestion-badge"[^>]*>', source
        )
        assert badge_match is not None
        assert "hidden" in badge_match.group(0)


# -- _configure_run_suggestions.html -----------------------------------------


def test_configure_run_suggestions_fragment_never_sets_real_field_value_server_side():
    source = (TEMPLATES_DIR / "_configure_run_suggestions.html").read_text(encoding="utf-8")

    assert 'value="{{ suggestion' not in source
    assert re.search(r"<input[^>]*value=", source) is None
    assert re.search(r"<textarea[^>]*>\{\{\s*suggestion", source) is None


def test_configure_run_suggestions_fragment_renders_suggestion_details():
    result = ConfigureRunResult(
        suggestions=[
            RunFieldSuggestion(
                field="horizon",
                value="24",
                explanation="Suggested value based on your answer, please confirm.",
            )
        ],
        degraded=False,
    )

    html = _render("_configure_run_suggestions.html", result=result)

    assert "horizon" in html
    assert "24" in html
    assert "suggested value based on your answer, please confirm" in html.lower()
    assert "apply suggestion" in html.lower()
    assert "applyRunSuggestion('horizon', '24')" in html


def test_configure_run_suggestions_fragment_degraded_renders_fixed_unavailable_message():
    result = ConfigureRunResult(suggestions=[], degraded=True)

    html = _render("_configure_run_suggestions.html", result=result)

    normalized = " ".join(html.lower().split())
    assert "suggestions are currently unavailable" in normalized
    assert "fill out the form below yourself" in normalized
    assert "<button" not in html


def test_configure_run_suggestions_fragment_no_suggestions_renders_fixed_unavailable_message():
    result = ConfigureRunResult(suggestions=[], degraded=False)

    html = _render("_configure_run_suggestions.html", result=result)

    assert "suggestions are currently unavailable" in html.lower()
    assert "<button" not in html


def test_run_new_page_unaffected_by_degraded_suggestions_fragment(tmp_path):
    """The plain `run-form` markup renders independently of the fragment --
    swapping in the degraded fragment never touches `run_new.html`'s own
    `<form id="run-form">` block (no shared partial/include between them)."""
    run_new_source = (TEMPLATES_DIR / "run_new.html").read_text(encoding="utf-8")
    suggestions_source = (TEMPLATES_DIR / "_configure_run_suggestions.html").read_text(
        encoding="utf-8"
    )

    assert "{% include" not in run_new_source
    assert 'id="run-form"' in run_new_source
    assert "run-form" not in suggestions_source
