"""RS-001 baseline test: the app module imports and constructs cleanly.

Deliberately minimal -- this ticket's own AC only requires `uv run pytest`
to pass with a working test config, not real route coverage yet (RS-004/
RS-005/RS-006/RS-007 add that).
"""

from app.main import app


def test_app_is_a_fastapi_instance():
    assert app.title == "reporting-service"
